"""Tests for incident summarization (FR-4)."""


def _flood_errors(client, n=6):
    for _ in range(n):
        client.post("/logs", json={"service": "demo-app", "message": "boom", "status_code": 500})


def test_no_incidents_on_clean_state(client):
    body = client.get("/incidents").json()
    assert body["count"] == 0
    assert body["incidents"] == []


def test_incident_created_from_anomalies(client):
    _flood_errors(client)
    body = client.get("/incidents").json()
    assert body["count"] == 1
    inc = body["incidents"][0]
    assert inc["id"] == 1
    assert inc["anomaly_count"] >= 1
    assert "error_spike" in inc["anomaly_types"]
    assert inc["severity"] in ("low", "medium", "high")
    assert inc["summary"]
    assert inc["created_at"]


def test_get_incident_by_id(client):
    _flood_errors(client)
    client.get("/incidents")
    r = client.get("/incidents/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_get_unknown_incident_returns_404(client):
    r = client.get("/incidents/999")
    assert r.status_code == 404
