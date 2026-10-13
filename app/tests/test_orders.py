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


def test_cancel_unpaid_order(client):
    client.post("/api/orders", json={"item": "widget", "amount": 5.0})
    r = client.delete("/api/orders/1")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert client.get("/api/orders").json()["count"] == 0


def test_cancel_unknown_order_returns_404(client):
    r = client.delete("/api/orders/999")
    assert r.status_code == 404


def test_cancel_paid_order_returns_409(client):
    client.post("/api/orders", json={"item": "widget", "amount": 5.0})
    client.post("/api/payment", json={"order_id": 1, "amount": 5.0})
    r = client.delete("/api/orders/1")
    assert r.status_code == 409


def test_payment_marks_order_paid(client):
    client.post("/api/orders", json={"item": "widget", "amount": 5.0})
    r = client.post("/api/payment", json={"order_id": 1, "amount": 5.0})
    assert r.status_code == 200
    orders = client.get("/api/orders").json()["orders"]
    assert orders[0]["status"] == "paid"
