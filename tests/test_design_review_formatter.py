"""Tests for the design review planner formatter."""

from __future__ import annotations

import pytest

from backend.app import planner


def _sample_steps() -> list[planner.ReviewStep]:
    return [
        planner.ReviewStep(
            title="Outline discovery workshop agenda",
            subject="discovery workshop",
            score=0.96,
            result=(
                "Develop a workshop outline covering vision alignment, persona refresh, and"
                " opportunity sizing exercises with clear facilitation notes."
            ),
            strengths=["Structured flow aligning stakeholders effectively."],
            improvements=["Specify timing for each activity to support logistics."],
        ),
        planner.ReviewStep(
            title="Map customer journey touchpoints",
            subject="customer journey",
            score=0.92,
            result=(
                "Produce a journey map spanning awareness to retention, annotating pain points"
                " and supporting data sources per stage."
            ),
            strengths=["Highlights data-backed decision points."],
            improvements=["Add ownership for future optimisation tasks."],
        ),
        planner.ReviewStep(
            title="Draft launch measurement plan",
            subject="analytics plan",
            score=0.94,
            result=(
                "Compile success metrics, baseline assumptions, and instrumentation notes"
                " across acquisition, engagement, and retention signals."
            ),
            strengths=["Comprehensive metric coverage."],
            improvements=["Clarify reporting cadence expectations."],
        ),
    ]


def _context(
    prompt_language: str = "fr",
    requested_output_language: str | None = None,
) -> planner.DesignReviewContext:
    return planner.DesignReviewContext(
        prompt_language=prompt_language,
        requested_output_language=requested_output_language,
        goal="Préparer un plan de lancement produit avec des étapes actionnables.",
        initial_request="Prépare un plan de lancement produit complet avec suivi qualité.",
    )


def test_step_titles_are_displayed_in_full_and_length_checked() -> None:
    report = planner.generate_design_review_report(_context(), _sample_steps())
    for index, step in enumerate(_sample_steps(), start=1):
        assert f"Étape {index} – {step.title}" in report

    oversize_step = planner.ReviewStep(
        title="X" * 81,
        subject="oversized title",
        score=0.5,
        result="Placeholder",
        strengths=[],
        improvements=[],
    )

    with pytest.raises(ValueError):
        planner.generate_design_review_report(_context(), [oversize_step])


def test_summary_mentions_goal_subjects_and_step_overview() -> None:
    report = planner.generate_design_review_report(_context(), _sample_steps())
    assert "Objectif" in report
    assert "Demande initiale" in report
    for step in _sample_steps():
        assert step.subject in report
        assert step.title in report


def test_language_selection_follows_prompt_and_requested_language() -> None:
    fr_report = planner.generate_design_review_report(_context(), _sample_steps())
    assert "## Section 1 – Résumé rapide" in fr_report
    assert "## Section 2 – Points forts et axes d'amélioration" in fr_report

    en_context = _context(prompt_language="en")
    en_context = planner.DesignReviewContext(
        prompt_language="en",
        requested_output_language=None,
        goal="Prepare a launch plan with actionable steps.",
        initial_request="Create a detailed launch plan with quality checks.",
    )
    en_report = planner.generate_design_review_report(en_context, _sample_steps())
    assert "## Section 1 – Quick summary" in en_report
    assert "## Section 2 – Strengths and improvements" in en_report

    forced_context = planner.DesignReviewContext(
        prompt_language="fr",
        requested_output_language="en",
        goal="Préparer un plan international.",
        initial_request="Prépare un plan international et réponds en anglais.",
    )
    forced_report = planner.generate_design_review_report(forced_context, _sample_steps())
    assert "## Section 1 – Quick summary" in forced_report
    assert "## Section 2 – Strengths and improvements" in forced_report


def test_table_does_not_duplicate_step_results() -> None:
    report = planner.generate_design_review_report(_context(), _sample_steps())
    table_section, _, _ = report.partition("### Détails des livrables")
    for step in _sample_steps():
        assert step.result not in table_section


def test_follow_up_section_prioritises_all_improvements() -> None:
    report = planner.generate_design_review_report(_context(), _sample_steps())
    assert "## Section 3 – Suivi prioritaire" in report
    for improvement in [imp for step in _sample_steps() for imp in step.improvements]:
        assert improvement in report


def test_unsupported_language_raises_clear_error() -> None:
    context = planner.DesignReviewContext(
        prompt_language="de",
        requested_output_language=None,
        goal="Erstelle einen Plan",
        initial_request="Erstelle einen detaillierten Plan",
    )
    with pytest.raises(ValueError):
        planner.generate_design_review_report(context, _sample_steps())
