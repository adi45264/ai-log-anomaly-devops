def test_health_returns_200(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["service"] == "ai-log-app"


def test_health_has_request_id_header(client):
    r = client.get("/api/health")
    assert "x-request-id" in r.headers


def test_unknown_route_returns_404(client):
    r = client.get("/api/invalid")
    assert r.status_code == 404


def test_index_serves_demo_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "SwiftCart" in r.text
