from __future__ import annotations


def test_scores_endpoint(client, authorized_headers):
    response = client.get("/api/scores", headers=authorized_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["coin"] == "btc"
