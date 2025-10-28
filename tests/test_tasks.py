from __future__ import annotations


def test_schedule_recalculation(client, authorized_headers):
    response = client.post("/api/tasks/recalculate", headers=authorized_headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "scheduled"


def test_schedule_recalculation_requires_admin(client, limited_headers):
    response = client.post("/api/tasks/recalculate", headers=limited_headers)
    assert response.status_code == 403
