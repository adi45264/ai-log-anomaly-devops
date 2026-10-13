"""Tests for POST /logs log ingestion (FR-1 acceptance: 201 on valid record)."""


def test_ingest_valid_record_returns_201(client):
    r = client.post("/logs", json={"service": "demo-app", "level": "ERROR", "message": "db timeout"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "accepted"
    assert body["observation_count"] == 1


def test_ingest_event_without_message_returns_201(client):
    r = client.post("/logs", json={"service": "demo-app", "event": "database_timeout"})
    assert r.status_code == 201


def test_ingest_missing_message_and_event_returns_422(client):
    r = client.post("/logs", json={"service": "demo-app"})
    assert r.status_code == 422


def test_ingested_error_logs_drive_anomaly_detection(client):
    for _ in range(6):
        r = client.post(
            "/logs",
            json={"service": "demo-app", "message": "boom", "status_code": 500},
        )
        assert r.status_code == 201
    body = client.get("/anomalies").json()
    types = [a["anomaly_type"] for a in body["anomalies"]]
    assert "error_spike" in types


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "log-platform"


def test_index_serves_platform_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Log Platform" in r.text
