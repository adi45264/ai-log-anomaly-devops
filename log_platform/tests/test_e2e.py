"""End-to-end test spanning both sibling apps (NFR-6).

Flow: demo app (producer) generates failures -> each failure is shipped as a
log record to the log-platform (consumer) via POST /logs -> anomaly detected
-> incident summarized.
"""
from fastapi.testclient import TestClient

from app.main import app as demo_app
from app.main import failure_state as demo_failure_state
from app.main import orders as demo_orders
from log_platform.detector import detector as platform_detector
from log_platform.main import app as platform_app
from log_platform.main import incidents as platform_incidents


def _clients():
    demo_failure_state.update(active=False, kind=None, started_at=None)
    demo_orders.clear()
    platform_detector.clear()
    platform_incidents.clear()
    return TestClient(demo_app), TestClient(platform_app)


def test_e2e_failure_to_incident(monkeypatch):
    # Speed up the demo app's simulated 7-9s database latency.
    import time as _time

    orig = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: orig(min(s, 0.05)))

    demo, platform = _clients()
    with demo, platform:
        # 0. Both services healthy.
        assert demo.get("/api/health").status_code == 200
        assert platform.get("/health").status_code == 200

        # 1. Start failure simulation on the demo app.
        assert demo.post("/api/failure/database").status_code == 200

        # 2. Generate failing traffic; ship each failure to the platform.
        for _ in range(6):
            r = demo.post("/api/payment", json={"order_id": 1, "amount": 10.0})
            assert r.status_code == 500
            pr = platform.post(
                "/logs",
                json={
                    "service": "demo-app",
                    "level": "ERROR",
                    "message": "database timeout while processing payment",
                    "method": "POST",
                    "path": "/api/payment",
                    "status_code": 500,
                    "latency_ms": 8000.0,
                },
            )
            assert pr.status_code == 201

        # 3. Anomaly detected on the platform.
        anomalies = platform.get("/anomalies").json()["anomalies"]
        assert any(a["anomaly_type"] == "error_spike" for a in anomalies)

        # 4. Incident summarized on the platform.
        body = platform.get("/incidents").json()
        assert body["count"] >= 1
        latest = body["incidents"][-1]
        assert "error_spike" in latest["anomaly_types"]
        assert latest["summary"]
        assert platform.get(f"/incidents/{latest['id']}").status_code == 200

        # 5. Stop failure; demo app healthy again.
        assert demo.post("/api/failure/stop").status_code == 200
        r = demo.post("/api/payment", json={"order_id": 1, "amount": 10.0})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
