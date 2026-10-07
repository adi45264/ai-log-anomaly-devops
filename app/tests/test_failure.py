def test_failure_start_and_stop(client):
    r = client.post("/api/failure/database")
    assert r.status_code == 200
    assert r.json()["kind"] == "database"
    r = client.post("/api/failure/stop")
    assert r.status_code == 200
    assert r.json()["previous_kind"] == "database"


def test_unknown_failure_kind_returns_404(client):
    r = client.post("/api/failure/earthquake")
    assert r.status_code == 404


def test_payment_failure_generates_structured_error_log(client, caplog):
    import logging
    from app.logger import JsonFormatter

    client.post("/api/failure/database")
    with caplog.at_level(logging.ERROR, logger="app"):
        client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    records = [r for r in caplog.records if r.name == "app" and getattr(r, "event", None) == "database_timeout"]
    assert records, "expected a database_timeout log record"
    formatted = JsonFormatter().format(records[-1])
    import json
    payload = json.loads(formatted)
    assert payload["level"] == "ERROR"
    assert payload["event"] == "database_timeout"
    assert payload["status_code"] == 500
    assert "timestamp" in payload and "service" in payload
