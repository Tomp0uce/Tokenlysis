from pathlib import Path


def test_frontend_fetches_markets_top():
    html = Path("frontend/index.html").read_text()
    assert "/markets/top?limit=20&vs=usd" in html
    assert "/markets?" not in html.replace("/markets/top?limit=20&vs=usd", "")


def test_frontend_no_ranking_call():
    html = Path("frontend/index.html").read_text()
    assert "/ranking" not in html


def test_frontend_version_scripts_present():
    html = Path("frontend/index.html").read_text()
    assert '<script src="./app-version.js"></script>' in html
    assert "import { getAppVersion } from './version.js';" in html
