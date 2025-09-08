from __future__ import annotations

from .test_version_endpoint import _make_client


def test_info_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_VERSION", "1.0.0")
    monkeypatch.setenv("GIT_COMMIT", "deadbeef")
    monkeypatch.setenv("BUILD_TIME", "2024-01-01T00:00:00Z")
    client, main_module = _make_client(monkeypatch, tmp_path)
    resp = client.get("/info")
    assert resp.status_code == 200
    assert resp.json() == {
        "version": "1.0.0",
        "commit": "deadbeef",
        "build_time": "2024-01-01T00:00:00Z",
    }
    main_module.app.dependency_overrides.clear()
