from __future__ import annotations


def test_metrics_endpoint(client, authorized_headers):
    response = client.get("/metrics", headers=authorized_headers)
    assert response.status_code == 200
    assert b"http_requests_total" in response.content


def test_metrics_requires_admin(client, limited_headers):
    response = client.get("/metrics", headers=limited_headers)
    assert response.status_code == 403
