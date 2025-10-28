from __future__ import annotations

def test_create_and_list_users(client, authorized_headers):
    payload = {"email": "user@example.com", "full_name": "Example User"}
    response = client.post("/api/users", json=payload, headers=authorized_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]

    list_response = client.get("/api/users", headers=authorized_headers)
    assert list_response.status_code == 200
    users = list_response.json()
    assert any(user["email"] == payload["email"] for user in users)


def test_rbac_blocks_non_admin(client, limited_headers):
    response = client.post(
        "/api/users",
        json={"email": "blocked@example.com", "full_name": "Blocked"},
        headers=limited_headers,
    )
    assert response.status_code == 403
