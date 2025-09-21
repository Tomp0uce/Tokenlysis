from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _reload_main():
    import backend.app.core.settings as settings_module
    import backend.app.main as main_module

    importlib.reload(settings_module)
    return importlib.reload(main_module)


def _static_mount(app):
    for route in app.routes:
        if getattr(route, "name", None) == "static":
            return route
    raise AssertionError("static mount not found")


def test_static_root_uses_repo_frontend(monkeypatch):
    monkeypatch.delenv("STATIC_ROOT", raising=False)
    main_module = _reload_main()
    mount = _static_mount(main_module.app)
    expected = Path(main_module.__file__).resolve().parents[2] / "frontend"
    assert Path(mount.app.directory) == expected
    _reload_main()


def test_static_root_override(monkeypatch, tmp_path):
    custom_index = tmp_path / "index.html"
    custom_index.write_text("<html><body>override</body></html>", encoding="utf-8")

    monkeypatch.setenv("STATIC_ROOT", str(tmp_path))
    try:
        main_module = _reload_main()
        mount = _static_mount(main_module.app)
        assert Path(mount.app.directory) == tmp_path
    finally:
        monkeypatch.delenv("STATIC_ROOT", raising=False)
        _reload_main()


def test_uvicorn_serves_frontend_from_subdirectory(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    extra_path = str(repo_root)
    env["PYTHONPATH"] = (
        extra_path if not pythonpath else os.pathsep.join([extra_path, pythonpath])
    )

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        "warning",
        "--lifespan",
        "off",
    ]

    proc = subprocess.Popen(
        cmd,
        cwd=run_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    url = f"http://{host}:{port}/index.html"
    deadline = time.time() + 20
    last_error: Exception | None = None
    body: bytes | None = None
    status: int | None = None
    stdout_data = ""
    stderr_data = ""
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    body = resp.read()
                    status = resp.getcode()
                break
            except urllib.error.URLError as exc:  # pragma: no cover - retry loop
                last_error = exc
                time.sleep(0.2)
    finally:
        proc.terminate()
        try:
            stdout_data, stderr_data = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
            stdout_data, stderr_data = proc.communicate(timeout=5)

    if body is None or status != 200:
        raise AssertionError(
            "Uvicorn did not serve index.html"
            f" (return code={proc.returncode}, last_error={last_error}, stdout={stdout_data}, stderr={stderr_data})"
        )

    assert b"<!DOCTYPE html" in body or b"<html" in body
