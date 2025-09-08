from pathlib import Path


def test_frontend_fetches_markets_top():
    js = Path("frontend/main.js").read_text()
    assert "/markets/top?limit=20&vs=usd" in js
    assert "/markets?" not in js.replace("/markets/top?limit=20&vs=usd", "")


def test_frontend_no_ranking_call():
    html = Path("frontend/index.html").read_text()
    assert "/ranking" not in html


def test_frontend_version_scripts_present():
    html = Path("frontend/index.html").read_text()
    assert '<script src="./app-version.js"></script>' in html
    assert '<script type="module" src="./main.js"></script>' in html


def test_no_debug_panel_or_endpoint():
    html = Path("frontend/index.html").read_text()
    assert 'id="debug-panel"' not in html
    js = Path("frontend/main.js").read_text()
    assert "/debug/last-request" not in js
