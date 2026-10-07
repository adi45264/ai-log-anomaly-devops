def test_create_order_returns_201(client):
    r = client.post("/api/orders", json={"item": "widget", "quantity": 2, "amount": 19.99})
    assert r.status_code == 201
    body = r.json()
    assert body["order_id"] == 1
    assert body["item"] == "widget"
    assert body["status"] == "created"


def test_create_then_list_orders(client):
    client.post("/api/orders", json={"item": "a", "amount": 5})
    client.post("/api/orders", json={"item": "b", "amount": 7})
    r = client.get("/api/orders")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_order_missing_body_defaults(client):
    r = client.post("/api/orders", json={})
    assert r.status_code == 201
    assert r.json()["item"] == "unknown"
