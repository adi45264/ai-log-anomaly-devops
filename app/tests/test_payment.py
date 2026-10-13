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


def test_payment_outage_declines_with_402(client):
    client.post("/api/failure/payment")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 402
    assert "declined" in r.json()["detail"]


def test_latency_outage_still_approves_but_slow(client):
    client.post("/api/failure/latency")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["latency_ms"] >= 3000


def test_shop_works_when_platform_unreachable(client, monkeypatch):
    """Forwarding to the platform is best-effort: shop never breaks."""
    monkeypatch.setenv("LOG_PLATFORM_URL", "http://127.0.0.1:9")
    client.post("/api/failure/database")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 500
    client.post("/api/failure/stop")
    r = client.post("/api/payment", json={"order_id": 1, "amount": 42.0})
    assert r.status_code == 200
