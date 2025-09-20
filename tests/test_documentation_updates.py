from __future__ import annotations

import importlib
import inspect
from pathlib import Path


def _section(content: str, heading: str) -> str:
    marker = f"### {heading}"
    if marker not in content:
        return ""
    _, _, tail = content.partition(marker)
    # split until the next level-3 heading to isolate the section body
    next_heading_index = tail.find("\n### ")
    body = tail if next_heading_index == -1 else tail[:next_heading_index]
    return body


def test_readme_lists_market_endpoints() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "get /api/price/{coin_id}" in lowered
    assert "get /api/diag" in lowered
    assert "seed fallback" in lowered or "fallback seed" in lowered


def test_readme_uses_checkboxes_for_phase_status() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for chunk in content.split("### ")[1:]:
        header, _, body = chunk.partition("\n")
        sections[header.strip()] = body

    poc = sections.get("Proof of Concept (delivered)")
    assert poc is not None and "- [x]" in poc

    mvp = sections.get("Minimum Viable Product (planned)")
    assert mvp is not None and "- [ ]" in mvp

    evt = sections.get("Engineering Validation Test (future)")
    assert evt is not None and "- [ ]" in evt


def test_readme_describes_asset_reference_dashboard() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "score total dynamique" in lowered
    assert "score fondamental" in lowered
    assert "total value locked (tvl)" in lowered
    assert "abonnés twitter" in lowered
    for label in ("communauté", "liquidité", "opportunité", "sécurité", "technologie", "tokenomics"):
        assert label in lowered


def test_functional_specs_outlines_asset_data_coverage() -> None:
    content = Path("Functional_specs.md").read_text(encoding="utf-8")
    lowered = content.lower()
    required_phrases = (
        "score total dynamique",
        "score fondamental",
        "total value locked",
        "abonnés twitter",
        "google trends",
    )
    for phrase in required_phrases:
        assert phrase in lowered


def test_evt_roadmap_groups_features_by_category() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    section = _section(readme, "Engineering Validation Test (future)")
    lowered = section.lower()
    assert "market intelligence" in lowered
    assert "community" in lowered
    assert "liquidity" in lowered
    assert "sécurité" in lowered
    assert "tokenomics" in lowered
    for feature in ("score total dynamique", "score fondamental", "total value locked", "abonnés twitter"):
        assert f"- [ ]" in section
        assert feature in lowered

    specs = Path("Functional_specs.md").read_text(encoding="utf-8")
    evt_section = _section(specs, "Engineering Validation Test (future)")
    evt_lower = evt_section.lower()
    assert "market intelligence" in evt_lower
    assert "community" in evt_lower
    assert "liquidity" in evt_lower
    assert "sécurité" in evt_lower
    assert "tokenomics" in evt_lower
    for feature in ("score total dynamique", "score fondamental", "total value locked", "abonnés twitter"):
        assert "- [ ]" in evt_section
        assert feature in evt_lower


def test_functional_specs_describes_current_stack() -> None:
    content = Path("Functional_specs.md").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "vanilla javascript" in lowered or "static html" in lowered
    assert "sqlite" in lowered
    assert "background" in lowered and "etl" in lowered


def test_readme_contains_proprietary_notice_and_no_mit() -> None:
    content = Path("README.md").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "⚠️ **proprietary notice**" in lowered
    assert "not open source" in lowered
    assert "mit license" not in lowered


def test_license_is_proprietary() -> None:
    content = Path("LICENSE").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "proprietary license" in lowered
    assert "copyright © 2025 tokenlysis" in lowered
    assert "mit license" not in lowered


def test_key_docstrings_explain_behaviour() -> None:
    main_module = importlib.import_module("backend.app.main")
    doc = inspect.getdoc(main_module.markets_top)
    assert doc is not None and "clamp" in doc.lower()
    assert "unsupported vs" in doc.lower()

    indicators = importlib.import_module("backend.app.services.indicators")
    rsi_doc = inspect.getdoc(indicators.rsi)
    assert rsi_doc is not None and "relative strength index" in rsi_doc.lower()


def test_refresh_interval_docstring_mentions_fallback() -> None:
    main_module = importlib.import_module("backend.app.main")
    doc = inspect.getdoc(main_module.refresh_interval_seconds)
    assert doc is not None
    lowered = doc.lower()
    assert "fallback" in lowered
    assert "12" in doc


def test_frontend_main_includes_section_comments() -> None:
    js = Path("frontend/main.js").read_text(encoding="utf-8")
    assert "// ===== formatting helpers =====" in js.lower()
    assert "// ===== sorting helpers =====" in js.lower()
