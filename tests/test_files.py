from __future__ import annotations


def test_signed_upload_url(client, authorized_headers):
    response = client.post(
        "/api/files/sign",
        json={"object_name": "reports/daily.csv", "expires_in": 60},
        headers=authorized_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"].startswith("https://minio.local")
    assert "fields" in data
