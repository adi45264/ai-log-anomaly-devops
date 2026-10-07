def test_payment_approved(client):
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["amount"] == 42.0
    assert body["latency_ms"] >= 0


def test_payment_database_failure_returns_500(client):
    client.post("/api/failure/database")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 500
    assert "database timeout" in r.json()["detail"]


def test_failure_stop_resets_state(client):
    client.post("/api/failure/database")
    client.post("/api/failure/stop")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 10.0})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
