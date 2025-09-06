from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_list_cryptos_and_sorting():
    r = client.get('/api/cryptos')
    assert r.status_code == 200
    data = r.json()
    assert data['total'] == 20
    assert len(data['items']) == 20
    assert data['items'][0]['latest']['scores']['global'] is not None

    r = client.get('/api/cryptos?sort=score_global&order=desc')
    items = r.json()['items']
    scores = [it['latest']['scores']['global'] for it in items]
    assert scores == sorted(scores, reverse=True)
