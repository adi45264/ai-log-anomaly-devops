"""Tests for Phase 4: Anomaly Detection.

All tests are deterministic:
* Observations are injected with explicit timestamps and latency values.
* No real wall-clock sleeping.
* The module-level detector singleton is reset by the ``client`` fixture in
  conftest.py before every test that uses it, and by calling
  ``detector.clear()`` explicitly in unit tests that bypass the HTTP client.

Test groups
-----------
1. Unit tests for AnomalyDetector (no HTTP stack needed)
   - Normal traffic ⟹ no false positives
   - Error spike detection
   - High-latency detection
   - Z-score detection with valid baseline
   - Insufficient baseline (z-score must not fire)
   - Zero-variance baseline (z-score must not fire)
   - detect() response shape

2. Integration tests via TestClient
   - GET /api/anomalies response shape
   - Existing endpoints are still functional
"""
from __future__ import annotations

import pytest

from app.anomaly_detector import AnomalyDetector, Observation, detector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = 1_700_000_000.0  # arbitrary fixed epoch (deterministic)


def _obs(
    *,
    status_code: int = 200,
    latency_ms: float = 100.0,
    ts: float = _BASE_TS,
    path: str = "/api/health",
    method: str = "GET",
) -> Observation:
    return Observation(
        timestamp=ts,
        method=method,
        path=path,
        status_code=status_code,
        latency_ms=latency_ms,
    )


def _fill_normal(det: AnomalyDetector, n: int = 40, latency_ms: float = 100.0) -> None:
    """Inject *n* healthy 200-OK observations with uniform latency."""
    for i in range(n):
        det.record(_obs(latency_ms=latency_ms, ts=_BASE_TS + i))


# ---------------------------------------------------------------------------
# 1. Unit tests — AnomalyDetector
# ---------------------------------------------------------------------------


class TestNoFalsePositives:
    """Normal traffic should produce zero anomalies."""

    def test_empty_buffer_returns_no_anomalies(self):
        det = AnomalyDetector()
        result = det.detect(at=_BASE_TS)
        assert result["anomalies"] == []

    def test_healthy_traffic_no_anomalies(self):
        det = AnomalyDetector(
            error_spike_threshold=5,
            latency_threshold_ms=2000.0,
            zscore_threshold=3.0,
            min_baseline_size=30,
        )
        _fill_normal(det, n=50, latency_ms=120.0)
        result = det.detect(at=_BASE_TS)
        assert result["anomalies"] == []

    def test_single_500_below_threshold_no_spike(self):
        """One 5xx response alone must NOT trigger an error-spike anomaly."""
        det = AnomalyDetector(error_spike_threshold=5)
        _fill_normal(det, n=10)
        det.record(_obs(status_code=500, ts=_BASE_TS + 11))
        result = det.detect(at=_BASE_TS)
        spike_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spike_anomalies == [], "A single 500 must not fire an error-spike alert"

    def test_four_errors_below_threshold_no_spike(self):
        """Four errors is still below the default threshold of 5."""
        det = AnomalyDetector(error_spike_threshold=5)
        _fill_normal(det, n=6)
        for i in range(4):
            det.record(_obs(status_code=503, ts=_BASE_TS + 10 + i))
        result = det.detect(at=_BASE_TS)
        spike_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spike_anomalies == []


class TestErrorSpike:
    """HTTP 5xx spikes above threshold should fire."""

    def test_spike_fires_when_threshold_met(self):
        det = AnomalyDetector(error_spike_threshold=5, error_spike_window=20)
        _fill_normal(det, n=5)
        for i in range(5):  # exactly at threshold
            det.record(_obs(status_code=500, ts=_BASE_TS + 10 + i))
        result = det.detect(at=_BASE_TS)
        spikes = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert len(spikes) == 1
        assert spikes[0]["metrics"]["error_count"] == 5

    def test_spike_severity_medium_when_rate_below_50_pct(self):
        det = AnomalyDetector(error_spike_threshold=5, error_spike_window=20)
        _fill_normal(det, n=15)   # 15 successes
        for i in range(5):        # 5 errors → 25 % error rate
            det.record(_obs(status_code=500, ts=_BASE_TS + 20 + i))
        result = det.detect(at=_BASE_TS)
        spikes = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spikes, "Error spike should fire"
        assert spikes[0]["severity"] == "medium"

    def test_spike_severity_high_when_rate_at_or_above_50_pct(self):
        det = AnomalyDetector(error_spike_threshold=5, error_spike_window=10)
        _fill_normal(det, n=5)    # 5 successes
        for i in range(5):        # 5 errors → 50 % error rate
            det.record(_obs(status_code=500, ts=_BASE_TS + 10 + i))
        result = det.detect(at=_BASE_TS)
        spikes = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spikes
        assert spikes[0]["severity"] == "high"

    def test_spike_metrics_contain_required_keys(self):
        det = AnomalyDetector(error_spike_threshold=3, error_spike_window=10)
        for i in range(3):
            det.record(_obs(status_code=502, ts=_BASE_TS + i))
        result = det.detect(at=_BASE_TS)
        spikes = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spikes
        m = spikes[0]["metrics"]
        for key in ("error_count", "window_size", "error_rate", "threshold", "window_start", "window_end"):
            assert key in m, f"Missing metric key: {key}"

    def test_different_5xx_codes_all_count(self):
        det = AnomalyDetector(error_spike_threshold=3)
        for code in (500, 502, 503):
            det.record(_obs(status_code=code, ts=_BASE_TS))
        result = det.detect(at=_BASE_TS)
        spikes = [a for a in result["anomalies"] if a["anomaly_type"] == "error_spike"]
        assert spikes
        assert spikes[0]["metrics"]["error_count"] == 3


class TestHighLatency:
    """Single requests above the latency threshold should fire."""

    def test_high_latency_fires(self):
        det = AnomalyDetector(latency_threshold_ms=2000.0)
        det.record(_obs(latency_ms=2500.0, ts=_BASE_TS))
        result = det.detect(at=_BASE_TS)
        lat_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "high_latency"]
        assert len(lat_anomalies) == 1

    def test_latency_exactly_at_threshold_does_not_fire(self):
        """Latency must EXCEED (not merely equal) the threshold."""
        det = AnomalyDetector(latency_threshold_ms=2000.0)
        det.record(_obs(latency_ms=2000.0, ts=_BASE_TS))
        result = det.detect(at=_BASE_TS)
        lat_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "high_latency"]
        assert lat_anomalies == []

    def test_high_latency_severity_medium(self):
        det = AnomalyDetector(latency_threshold_ms=2000.0)
        det.record(_obs(latency_ms=3000.0, ts=_BASE_TS))  # 1.5× threshold
        result = det.detect(at=_BASE_TS)
        lat = [a for a in result["anomalies"] if a["anomaly_type"] == "high_latency"]
        assert lat
        assert lat[0]["severity"] == "medium"

    def test_high_latency_severity_high(self):
        det = AnomalyDetector(latency_threshold_ms=2000.0)
        det.record(_obs(latency_ms=4001.0, ts=_BASE_TS))  # > 2× threshold
        result = det.detect(at=_BASE_TS)
        lat = [a for a in result["anomalies"] if a["anomaly_type"] == "high_latency"]
        assert lat
        assert lat[0]["severity"] == "high"

    def test_high_latency_metrics_contain_required_keys(self):
        det = AnomalyDetector(latency_threshold_ms=500.0)
        det.record(_obs(latency_ms=600.0, path="/api/payment", method="POST", ts=_BASE_TS))
        result = det.detect(at=_BASE_TS)
        lat = [a for a in result["anomalies"] if a["anomaly_type"] == "high_latency"]
        assert lat
        m = lat[0]["metrics"]
        for key in ("slow_request_count", "worst_latency_ms", "threshold_ms", "worst_method", "worst_path", "worst_at"):
            assert key in m, f"Missing metric key: {key}"
        assert m["worst_method"] == "POST"
        assert m["worst_path"] == "/api/payment"


class TestZScore:
    """Z-score outlier detection against a held-out baseline partition.

    Buffer layout used throughout this class (unless noted):
        [  baseline partition  ] [ evaluation window ]
        buffer[:-window]          buffer[-window:]

    The baseline is computed exclusively from the older partition so that
    outliers in the evaluation window cannot inflate their own baseline.
    """

    # ------------------------------------------------------------------
    # Helper — build a buffer with a clear baseline + evaluation split
    # ------------------------------------------------------------------

    @staticmethod
    def _setup(
        det: AnomalyDetector,
        baseline_n: int,
        baseline_latency: float,
        eval_obs: list[float],
    ) -> None:
        """Fill *det* with *baseline_n* normal observations, then the eval list.

        Each observation gets a monotonically increasing timestamp so ordering
        is unambiguous and tests remain fully deterministic.
        """
        for i in range(baseline_n):
            det.record(_obs(latency_ms=baseline_latency, ts=_BASE_TS + i))
        offset = baseline_n
        for j, lat in enumerate(eval_obs):
            det.record(_obs(latency_ms=lat, ts=_BASE_TS + offset + j))

    # ------------------------------------------------------------------
    # Core behaviour
    # ------------------------------------------------------------------

    def test_zscore_detects_outlier(self):
        """A massive outlier in the evaluation window must be detected.

        Sizes: error_spike_window=10, min_baseline_size=20.
        We record 30 baseline obs → baseline partition = buf[:-10] = 20 obs ≥ 20 ✓.
        The outlier lands in buf[-10:] (the eval window).
        """
        det = AnomalyDetector(
            min_baseline_size=20,    # need baseline partition ≥ 20
            zscore_threshold=3.0,
            error_spike_window=10,   # baseline = buffer[:-10], eval = buffer[-10:]
        )
        # 30 obs: the last 10 form the eval window; first 20 form the baseline.
        for i in range(29):
            det.record(_obs(latency_ms=100.0 + (i % 5), ts=_BASE_TS + i))
        # 30th obs is in the eval window — an extreme outlier.
        det.record(_obs(latency_ms=10_000.0, ts=_BASE_TS + 30))
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        assert z_anomalies, "Expected a z-score anomaly for a 10 000 ms observation in a ~100 ms baseline"

    def test_outlier_excluded_from_its_own_baseline(self):
        """The outlier's latency must NOT be included in the baseline statistics.

        Buffer layout (error_spike_window=5, min_baseline_size=10):
          obs[0..14]  → baseline = buf[:-5] = 15 obs (first 15)   ≥ min_baseline_size ✓
          obs[15..19] → eval window = buf[-5:] = last 5 obs

        Baseline: alternating 99/101 ms → mean=100, std=1.
        Eval window: 4 normal obs + 1 outlier at 5 200 ms.
        z_outlier = (5200 - 100) / 1 = 5100 >> zscore_threshold=50.

        If the outlier were included in the baseline the std would rise to ~1500,
        making z ≈ 3.4, which is below threshold=50 → detection would fail.
        """
        det = AnomalyDetector(
            min_baseline_size=10,
            zscore_threshold=50.0,   # only reachable when outlier is excluded from baseline
            error_spike_window=5,    # eval = last 5, baseline = everything before
        )
        # 15 baseline obs: alternating 99/101 → mean=100, std=1
        for i in range(15):
            det.record(_obs(latency_ms=99.0 if i % 2 == 0 else 101.0, ts=_BASE_TS + i))
        # 4 normal eval obs + 1 outlier (last 5 = eval window)
        for j in range(4):
            det.record(_obs(latency_ms=100.0, ts=_BASE_TS + 15 + j))
        det.record(_obs(latency_ms=5_200.0, ts=_BASE_TS + 19))
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        # z = (5200 - 100) / 1 = 5100 >> threshold of 50
        assert z_anomalies, (
            "Outlier must be detected against the pure historical baseline "
            "(z≈5100 >> 50). If it were in the baseline the std would rise "
            "and z would drop well below the threshold."
        )
        # Confirm the anomaly metrics reflect only the baseline partition (15 obs).
        m = z_anomalies[0]["metrics"]
        assert m["baseline_mean_ms"] == pytest.approx(100.0, abs=0.01)
        assert m["baseline_std_ms"] == pytest.approx(1.0, abs=0.01)
        assert m["baseline_size"] == 15

    def test_zscore_does_not_fire_when_baseline_insufficient(self):
        """Buffer too small to form a valid baseline partition — must not fire."""
        det = AnomalyDetector(
            min_baseline_size=30,
            zscore_threshold=3.0,
            error_spike_window=10,
        )
        # Only 11 obs total → baseline = buffer[:-10] = 1 obs < min_baseline_size
        for i in range(10):
            det.record(_obs(latency_ms=100.0, ts=_BASE_TS + i))
        det.record(_obs(latency_ms=50_000.0, ts=_BASE_TS + 11))
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        assert z_anomalies == [], "Z-score must not fire without sufficient baseline partition"

    def test_zscore_does_not_fire_on_zero_variance_baseline(self):
        """Baseline has zero std — z-score is undefined; must not fire."""
        det = AnomalyDetector(
            min_baseline_size=5,
            zscore_threshold=3.0,
            error_spike_window=5,
        )
        # 10 baseline obs, all exactly 200 ms → std=0
        for i in range(10):
            det.record(_obs(latency_ms=200.0, ts=_BASE_TS + i))
        # 1 eval obs at a very different latency
        det.record(_obs(latency_ms=9999.0, ts=_BASE_TS + 11))
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        assert z_anomalies == [], "Z-score must not fire when baseline std=0"

    def test_zscore_has_sufficient_baseline_flag_false_when_partition_too_small(self):
        """has_sufficient_baseline reflects the baseline *partition*, not the full buffer."""
        det = AnomalyDetector(min_baseline_size=5, error_spike_window=10)
        # Add 14 obs total → baseline = buffer[:-10] = 4 obs < min_baseline_size=5
        for i in range(14):
            det.record(_obs(ts=_BASE_TS + i))
        result = det.detect(at=_BASE_TS)
        assert result["has_sufficient_baseline"] is False

    def test_zscore_has_sufficient_baseline_flag_true_when_partition_adequate(self):
        """has_sufficient_baseline becomes True once the baseline partition is large enough."""
        det = AnomalyDetector(min_baseline_size=5, error_spike_window=10)
        # 15 obs → baseline = buffer[:-10] = 5 obs == min_baseline_size → True
        for i in range(15):
            det.record(_obs(ts=_BASE_TS + i))
        result = det.detect(at=_BASE_TS)
        assert result["has_sufficient_baseline"] is True

    def test_zscore_normal_eval_window_no_false_positive(self):
        """Eval observations that match the baseline distribution must not fire.

        _setup records baseline_n obs then appends eval_obs.
        With error_spike_window=10 and total = baseline_n + len(eval_obs) = 23:
          baseline = buf[:-10] = first 13 obs.
          eval     = buf[-10:] = last 10 obs (3 from eval_obs + 7 from baseline tail).
        min_baseline_size=10 ≤ 13 → detection is active.
        eval obs (98–102 ms) are within 3σ of a ~100 ms baseline → no anomaly.
        """
        det = AnomalyDetector(
            min_baseline_size=10,    # 13 baseline obs ≥ 10 ✓ (detection active)
            zscore_threshold=3.0,
            error_spike_window=10,
        )
        self._setup(det, baseline_n=20, baseline_latency=100.0, eval_obs=[102.0, 98.0, 101.0])
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        assert z_anomalies == [], "Normal eval obs must not trigger z-score alert"

    def test_zscore_metrics_contain_required_keys(self):
        """Anomaly metrics dict must contain all documented keys.

        Sizes: error_spike_window=5, min_baseline_size=10.
        Need total - 5 ≥ 10  →  total ≥ 15.
        We record 14 normal obs + 1 extreme outlier = 15 total.
        baseline = buf[:-5] = first 10 obs; eval = buf[-5:] = last 5 obs.
        """
        det = AnomalyDetector(
            min_baseline_size=10,
            zscore_threshold=2.0,
            error_spike_window=5,    # baseline = buffer[:-5], eval = buffer[-5:]
        )
        # 14 baseline obs with small, non-zero spread (50, 51, … 63 ms)
        for i in range(14):
            det.record(_obs(latency_ms=50.0 + i, ts=_BASE_TS + i))
        # 1 outlier — falls in the eval window (last 5 obs = indices 10..14)
        det.record(_obs(latency_ms=5000.0, ts=_BASE_TS + 14))
        result = det.detect(at=_BASE_TS)
        z_anomalies = [a for a in result["anomalies"] if a["anomaly_type"] == "latency_zscore"]
        assert z_anomalies
        m = z_anomalies[0]["metrics"]
        for key in (
            "outlier_count",
            "worst_zscore",
            "worst_latency_ms",
            "baseline_mean_ms",
            "baseline_std_ms",
            "baseline_size",
            "zscore_threshold",
        ):
            assert key in m, f"Missing metric key: {key}"
        # baseline_size must reflect only the baseline partition (first 10 obs),
        # not the full buffer (15 obs).
        assert m["baseline_size"] == 10


class TestDetectResponseShape:
    """The dict returned by detect() must always have the documented keys."""

    def _required_top_level_keys(self):
        return {"anomalies", "observation_count", "window_size", "has_sufficient_baseline", "thresholds"}

    def _required_threshold_keys(self):
        return {
            "error_spike_threshold",
            "error_spike_window",
            "latency_threshold_ms",
            "zscore_threshold",
            "min_baseline_size",
        }

    def _required_anomaly_keys(self):
        return {"anomaly_type", "severity", "description", "detected_at", "metrics"}

    def test_empty_buffer_shape(self):
        det = AnomalyDetector()
        result = det.detect(at=_BASE_TS)
        assert self._required_top_level_keys() <= result.keys()
        assert self._required_threshold_keys() <= result["thresholds"].keys()
        assert isinstance(result["anomalies"], list)

    def test_anomaly_dict_shape(self):
        det = AnomalyDetector(error_spike_threshold=1)
        det.record(_obs(status_code=500, ts=_BASE_TS))
        result = det.detect(at=_BASE_TS)
        assert result["anomalies"]
        for a in result["anomalies"]:
            assert self._required_anomaly_keys() <= a.keys()

    def test_observation_count_reflects_buffer(self):
        det = AnomalyDetector()
        assert det.detect()["observation_count"] == 0
        det.record(_obs())
        det.record(_obs())
        assert det.detect()["observation_count"] == 2

    def test_buffer_is_bounded(self):
        det = AnomalyDetector(buffer_size=5)
        for i in range(10):
            det.record(_obs(ts=_BASE_TS + i))
        assert det.observation_count == 5


# ---------------------------------------------------------------------------
# 2. Integration tests — TestClient / API
# ---------------------------------------------------------------------------


class TestAnomaliesEndpoint:
    """GET /api/anomalies via the real FastAPI app."""

    def test_anomalies_returns_200(self, client):
        r = client.get("/api/anomalies")
        assert r.status_code == 200

    def test_anomalies_response_shape(self, client):
        r = client.get("/api/anomalies")
        body = r.json()
        for key in ("anomalies", "observation_count", "window_size", "has_sufficient_baseline", "thresholds"):
            assert key in body, f"Missing key: {key}"

    def test_anomalies_is_list(self, client):
        r = client.get("/api/anomalies")
        assert isinstance(r.json()["anomalies"], list)

    def test_anomalies_empty_on_clean_traffic(self, client):
        """Normal 200 responses should not produce anomalies."""
        for _ in range(10):
            client.get("/api/health")
        r = client.get("/api/anomalies")
        body = r.json()
        assert body["anomalies"] == [], f"Unexpected anomalies: {body['anomalies']}"

    def test_observation_count_increments(self, client):
        before = client.get("/api/anomalies").json()["observation_count"]
        client.get("/api/health")
        after = client.get("/api/anomalies").json()["observation_count"]
        # at least the /api/health call was recorded (the /api/anomalies calls are also recorded)
        assert after > before

    def test_error_spike_via_endpoint(self, client):
        """Injecting 5xx observations directly should cause an error_spike anomaly."""
        # Bypass HTTP and inject directly so the test is fast and deterministic.
        for i in range(10):
            detector.record(_obs(status_code=500, ts=_BASE_TS + i))
        r = client.get("/api/anomalies")
        body = r.json()
        spike_types = [a["anomaly_type"] for a in body["anomalies"]]
        assert "error_spike" in spike_types

    def test_high_latency_via_endpoint(self, client):
        """Injecting a slow observation should cause a high_latency anomaly."""
        detector.record(_obs(latency_ms=9999.0, ts=_BASE_TS))
        r = client.get("/api/anomalies")
        body = r.json()
        lat_types = [a["anomaly_type"] for a in body["anomalies"]]
        assert "high_latency" in lat_types


class TestExistingEndpointsUnchanged:
    """All pre-Phase-4 endpoints must continue to function as before."""

    def test_health_still_200(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_create_order_still_201(self, client):
        r = client.post("/api/orders", json={"item": "widget", "amount": 5.0})
        assert r.status_code == 201

    def test_list_orders_still_200(self, client):
        r = client.get("/api/orders")
        assert r.status_code == 200

    def test_list_users_still_200(self, client):
        r = client.get("/api/users")
        assert r.status_code == 200

    def test_failure_simulation_start_stop(self, client):
        r = client.post("/api/failure/database")
        assert r.status_code == 200
        assert r.json()["kind"] == "database"
        r = client.post("/api/failure/stop")
        assert r.status_code == 200

    def test_unknown_failure_kind_still_404(self, client):
        r = client.post("/api/failure/earthquake")
        assert r.status_code == 404

    def test_payment_still_approved_without_failure(self, client):
        r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_payment_still_500_with_database_failure(self, client):
        client.post("/api/failure/database")
        r = client.post("/api/payment", json={"order_id": 1, "amount": 10.0})
        assert r.status_code == 500
        assert "database timeout" in r.json()["detail"]

    def test_request_id_header_still_present(self, client):
        r = client.get("/api/health")
        assert "x-request-id" in r.headers
