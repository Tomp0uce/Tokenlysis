from __future__ import annotations


def test_sse_stream(client, authorized_headers):
    with client.stream("GET", "/api/stream/scores", headers=authorized_headers) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes())
    assert b"event: score" in body


def test_websocket_scores(client) -> None:
    with client.websocket_connect("/ws/scores") as websocket:
        websocket.send_json({"type": "subscribe", "coin": "btc"})
        data = websocket.receive_json()
        assert data["coin"] == "btc"
        assert "score" in data
