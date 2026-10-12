"""Anomaly detector for HTTP request observations.

Observations are collected from the logging middleware and stored in a bounded
in-memory deque (no external dependencies). Three complementary rules run on
every call to :func:`detect`:

* **error_spike** ΓÇô a window of recent requests contains more than
  ``error_spike_threshold`` HTTP 5xx responses.
* **high_latency** ΓÇô any single observation exceeds
  ``latency_threshold_ms`` milliseconds.
* **latency_zscore** ΓÇô a request's latency is more than
  ``zscore_threshold`` standard deviations above the mean of a
  *held-out baseline* (observations older than the evaluation window).
  Only fires when the baseline partition has at least
  ``min_baseline_size`` observations and a non-zero standard deviation.
  Outliers in the evaluation window cannot inflate their own baseline.

All thresholds are configurable at construction time.  Detection is fully
deterministic: no external APIs, no randomness, no wall-clock sleeps.

Usage::

    from app.anomaly_detector import AnomalyDetector, Observation

    detector = AnomalyDetector()
    detector.record(Observation(
        timestamp=1234567890.0,
        method="GET",
        path="/api/health",
        status_code=200,
        latency_ms=45.0,
    ))
    result = detector.detect()
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Observation:
    """A single HTTP request observation recorded by the middleware.

    Attributes:
        timestamp:   Unix epoch seconds (float) at which the request arrived.
        method:      HTTP method (GET, POST, ΓÇª).
        path:        URL path (no query string, no host).
        status_code: HTTP response status code.
        latency_ms:  End-to-end latency in milliseconds (float).
    """

    timestamp: float
    method: str
    path: str
    status_code: int
    latency_ms: float


@dataclass
class Anomaly:
    """A single detected anomaly.

    Attributes:
        anomaly_type: Machine-readable label (``error_spike``,
                      ``high_latency``, ``latency_zscore``).
        severity:     ``"low"``, ``"medium"``, or ``"high"``.
        description:  Human-readable explanation.
        detected_at:  ISO-8601 UTC timestamp of detection.
        metrics:      Supporting numeric evidence (threshold, actual value, ΓÇª).
    """

    anomaly_type: str
    severity: str
    description: str
    detected_at: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "description": self.description,
            "detected_at": self.detected_at,
            "metrics": self.metrics,
        }


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

_DEFAULT_BUFFER_SIZE = 1000          # maximum observations kept
_DEFAULT_WINDOW_SIZE = 50            # recent observations examined for error-spike
_DEFAULT_ERROR_SPIKE_THRESHOLD = 5   # minimum 5xx count to trigger spike alert
_DEFAULT_LATENCY_THRESHOLD_MS = 2000.0  # ms above which a request is "slow"
_DEFAULT_ZSCORE_THRESHOLD = 3.0      # z-score above which latency is an outlier
_DEFAULT_MIN_BASELINE_SIZE = 30      # minimum buffer size before z-score kicks in


class AnomalyDetector:
    """In-memory anomaly detector for HTTP request streams.

    Parameters
    ----------
    buffer_size:
        Maximum number of observations retained (oldest are evicted first).
    error_spike_window:
        Number of most-recent observations to check for 5xx errors.
    error_spike_threshold:
        Minimum number of 5xx responses in the window to fire an alert.
    latency_threshold_ms:
        Per-request latency (ms) above which a *high_latency* anomaly fires.
    zscore_threshold:
        Z-score above which a request's latency is flagged as a
        *latency_zscore* outlier.
    min_baseline_size:
        Minimum buffer length required before z-score analysis is attempted.
    """

    def __init__(
        self,
        *,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        error_spike_window: int = _DEFAULT_WINDOW_SIZE,
        error_spike_threshold: int = _DEFAULT_ERROR_SPIKE_THRESHOLD,
        latency_threshold_ms: float = _DEFAULT_LATENCY_THRESHOLD_MS,
        zscore_threshold: float = _DEFAULT_ZSCORE_THRESHOLD,
        min_baseline_size: int = _DEFAULT_MIN_BASELINE_SIZE,
    ) -> None:
        self._buffer: deque[Observation] = deque(maxlen=buffer_size)
        self.buffer_size = buffer_size
        self.error_spike_window = error_spike_window
        self.error_spike_threshold = error_spike_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.zscore_threshold = zscore_threshold
        self.min_baseline_size = min_baseline_size

    # ------------------------------------------------------------------
    # Observation ingestion
    # ------------------------------------------------------------------

    def record(self, obs: Observation) -> None:
        """Append *obs* to the internal buffer (thread-safe via the GIL)."""
        self._buffer.append(obs)

    def clear(self) -> None:
        """Discard all buffered observations (used in tests)."""
        self._buffer.clear()

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def observation_count(self) -> int:
        """Number of observations currently in the buffer."""
        return len(self._buffer)

    @property
    def window_size(self) -> int:
        """Configured error-spike window size."""
        return self.error_spike_window

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, *, at: float | None = None) -> dict[str, Any]:
        """Run all detectors and return a structured result dict.

        Parameters
        ----------
        at:
            Unix epoch timestamp to use as *now* for the ``detected_at``
            field.  Defaults to the current UTC time.  Injecting this value
            keeps tests deterministic.

        Returns
        -------
        dict with keys:

        * ``anomalies`` ΓÇô list of anomaly dicts (may be empty).
        * ``observation_count`` ΓÇô total buffered observations.
        * ``window_size`` ΓÇô configured error-spike window.
        * ``has_sufficient_baseline`` ΓÇô whether z-score detection is active.
        * ``thresholds`` ΓÇô dict of all configured thresholds.
        """
        now_iso = _utc_iso(at)
        anomalies: list[Anomaly] = []

        anomalies.extend(self._check_error_spike(now_iso))
        anomalies.extend(self._check_high_latency(now_iso))
        anomalies.extend(self._check_zscore(now_iso))

        return {
            "anomalies": [a.to_dict() for a in anomalies],
            "observation_count": len(self._buffer),
            "window_size": self.error_spike_window,
            "has_sufficient_baseline": self._has_baseline(),
            "thresholds": {
                "error_spike_threshold": self.error_spike_threshold,
                "error_spike_window": self.error_spike_window,
                "latency_threshold_ms": self.latency_threshold_ms,
                "zscore_threshold": self.zscore_threshold,
                "min_baseline_size": self.min_baseline_size,
            },
        }

    # ------------------------------------------------------------------
    # Internal check helpers
    # ------------------------------------------------------------------

    def _recent(self) -> list[Observation]:
        """Return the *error_spike_window* most recent observations."""
        buf = list(self._buffer)
        return buf[-self.error_spike_window :]

    def _has_baseline(self) -> bool:
        """Return True when the baseline partition has enough observations for z-score analysis.

        The baseline partition is ``buffer[:-error_spike_window]`` ΓÇö everything
        older than the evaluation window.  This mirrors the split used by
        :meth:`_check_zscore` so the flag is always accurate.
        """
        baseline_size = max(0, len(self._buffer) - self.error_spike_window)
        return baseline_size >= self.min_baseline_size

    def _check_error_spike(self, now_iso: str) -> list[Anomaly]:
        """Detect a spike in HTTP 5xx responses in the recent window."""
        window = self._recent()
        if not window:
            return []
        errors = [o for o in window if o.status_code >= 500]
        count = len(errors)
        if count < self.error_spike_threshold:
            return []

        rate = count / len(window)
        severity = "high" if rate >= 0.5 else "medium"
        earliest = min(o.timestamp for o in errors)
        latest = max(o.timestamp for o in errors)
        return [
            Anomaly(
                anomaly_type="error_spike",
                severity=severity,
                description=(
                    f"{count} HTTP 5xx responses detected in the last "
                    f"{len(window)} observations "
                    f"({rate * 100:.1f}% error rate)."
                ),
                detected_at=now_iso,
                metrics={
                    "error_count": count,
                    "window_size": len(window),
                    "error_rate": round(rate, 4),
                    "threshold": self.error_spike_threshold,
                    "window_start": _utc_iso(earliest),
                    "window_end": _utc_iso(latest),
                },
            )
        ]

    def _check_high_latency(self, now_iso: str) -> list[Anomaly]:
        """Detect any single request that exceeds *latency_threshold_ms*."""
        window = self._recent()
        slow = [o for o in window if o.latency_ms > self.latency_threshold_ms]
        if not slow:
            return []

        worst = max(slow, key=lambda o: o.latency_ms)
        return [
            Anomaly(
                anomaly_type="high_latency",
                severity="high" if worst.latency_ms > self.latency_threshold_ms * 2 else "medium",
                description=(
                    f"{len(slow)} request(s) in the last {len(window)} observations "
                    f"exceeded the latency threshold of {self.latency_threshold_ms:.0f} ms. "
                    f"Worst: {worst.latency_ms:.1f} ms "
                    f"({worst.method} {worst.path})."
                ),
                detected_at=now_iso,
                metrics={
                    "slow_request_count": len(slow),
                    "worst_latency_ms": worst.latency_ms,
                    "threshold_ms": self.latency_threshold_ms,
                    "worst_method": worst.method,
                    "worst_path": worst.path,
                    "worst_at": _utc_iso(worst.timestamp),
                },
            )
        ]

    def _check_zscore(self, now_iso: str) -> list[Anomaly]:
        """Detect latency outliers using a Z-score computed from a held-out baseline.

        The buffer is split into two non-overlapping partitions:

        * **baseline** ΓÇô all observations *older* than the evaluation window
          (``buffer[:-error_spike_window]``).  Statistics (mean, std) are
          computed exclusively from this set so that outliers in the evaluation
          window cannot inflate the baseline and mask themselves.
        * **evaluation window** ΓÇô the ``error_spike_window`` most-recent
          observations (same slice used by ``_recent()``).  Each observation
          in this set is scored against the baseline statistics.

        Detection is skipped when:
        * The baseline partition has fewer than ``min_baseline_size`` entries.
        * The baseline standard deviation is zero (all baseline latencies are
          identical ΓÇö z-score would be undefined).
        """
        buf = list(self._buffer)
        # Evaluation window: newest observations (may overlap entire buffer when
        # error_spike_window >= len(buf), which is handled by the baseline check).
        eval_window = buf[-self.error_spike_window :]
        # Baseline: everything older than the evaluation window.
        baseline = buf[: max(0, len(buf) - self.error_spike_window)]

        if len(baseline) < self.min_baseline_size:
            # Not enough historical data to form a reliable reference.
            return []

        baseline_latencies = [o.latency_ms for o in baseline]
        n = len(baseline_latencies)
        mean = sum(baseline_latencies) / n
        variance = sum((x - mean) ** 2 for x in baseline_latencies) / n
        std = math.sqrt(variance)

        if std == 0.0:
            # Baseline has zero variance ΓÇö z-score undefined; skip silently.
            return []

        outliers = []
        for obs in eval_window:
            z = (obs.latency_ms - mean) / std
            if z > self.zscore_threshold:
                outliers.append((obs, z))

        if not outliers:
            return []

        worst_obs, worst_z = max(outliers, key=lambda t: t[1])
        return [
            Anomaly(
                anomaly_type="latency_zscore",
                severity="high" if worst_z > self.zscore_threshold * 1.5 else "medium",
                description=(
                    f"{len(outliers)} latency outlier(s) detected in the last "
                    f"{len(eval_window)} observations (z > {self.zscore_threshold}). "
                    f"Worst z-score: {worst_z:.2f} "
                    f"(latency={worst_obs.latency_ms:.1f} ms, "
                    f"baseline mean={mean:.1f} ms, baseline std={std:.1f} ms)."
                ),
                detected_at=now_iso,
                metrics={
                    "outlier_count": len(outliers),
                    "worst_zscore": round(worst_z, 4),
                    "worst_latency_ms": worst_obs.latency_ms,
                    "baseline_mean_ms": round(mean, 4),
                    "baseline_std_ms": round(std, 4),
                    "baseline_size": n,
                    "zscore_threshold": self.zscore_threshold,
                },
            )
        ]


# ---------------------------------------------------------------------------
# Module-level singleton (used by main.py / middleware)
# ---------------------------------------------------------------------------

detector = AnomalyDetector()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso(ts: float | None = None) -> str:
    """Return an ISO-8601 UTC string for *ts* (or now if *ts* is None)."""
    if ts is None:
        dt = datetime.now(tz=UTC)
    else:
        dt = datetime.fromtimestamp(ts, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

