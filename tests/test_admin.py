from __future__ import annotations


def test_sqladmin_dashboard_available(client, authorized_headers):
    response = client.get("/admin", headers=authorized_headers, follow_redirects=True)
    assert response.status_code == 200
    assert "Tokenlysis Admin" in response.text
