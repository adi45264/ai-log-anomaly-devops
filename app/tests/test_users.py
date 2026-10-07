def test_list_users(client):
    r = client.get("/api/users")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["users"][0]["name"] == "alice"
