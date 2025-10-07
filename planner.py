"""Utilities to produce structured design review reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ReviewStep:
    """Represents the outcome of a single reviewed step."""

    title: str
    subject: str
    score: float
    result: str
    strengths: Sequence[str]
    improvements: Sequence[str]


@dataclass(frozen=True)
class DesignReviewContext:
    """Carries metadata about the review."""

    prompt_language: str
    goal: str
    initial_request: str
    requested_output_language: str | None = None


@dataclass(frozen=True)
class _LanguagePack:
    document_title: str
    section1_title: str
    section2_title: str
    section3_title: str
    goal_line: str
    request_line: str
    subjects_line: str
    deliverable_line: str
    overview_header: str
    overview_item: str
    table_header: str
    table_divider: str
    step_label: str
    detail_heading: str
    follow_up_intro: str
    follow_up_item: str
    follow_up_none: str
    follow_up_conclusion: str
    strengths_fallback: str
    improvements_fallback: str


LANGUAGE_PACKS: dict[str, _LanguagePack] = {
    "fr": _LanguagePack(
        document_title="# Design Review",
        section1_title="## Section 1 – Résumé rapide",
        section2_title="## Section 2 – Points forts et axes d'amélioration",
        section3_title="## Section 3 – Suivi prioritaire",
        goal_line="- Objectif : {goal}",
        request_line="- Demande initiale : {request}",
        subjects_line="- Sujets couverts : {subjects}.",
        deliverable_line="- Livrable obtenu : {count} étape(s) validée(s).",
        overview_header="- Aperçu des étapes :",
        overview_item="  {index}. Étape {index} – {title} ({subject})",
        table_header="| Étape | Score | Points forts | Axes d'amélioration |",
        table_divider="| :--- | :---: | :--- | :--- |",
        step_label="Étape",
        detail_heading="### Détails des livrables",
        follow_up_intro=(
            "Les axes d'amélioration listés ci-dessous sont classés par ordre de priorité "
            "pour consolider les prochaines itérations."
        ),
        follow_up_item="{rank}. Priorité {rank} – Étape {step_index} : {improvement}",
        follow_up_none="Aucune action prioritaire supplémentaire n'a été identifiée.",
        follow_up_conclusion=(
            "Conclusion : pour atteindre l'objectif « {goal} », traiter {count} axe(s) "
            "d'amélioration renforcera la cohérence globale."
        ),
        strengths_fallback="Maintenir la qualité observée sur cette étape.",
        improvements_fallback="Aucun ajustement immédiat identifié.",
    ),
    "en": _LanguagePack(
        document_title="# Design Review",
        section1_title="## Section 1 – Quick summary",
        section2_title="## Section 2 – Strengths and improvements",
        section3_title="## Section 3 – Prioritised follow-up",
        goal_line="- Goal: {goal}",
        request_line="- Original request: {request}",
        subjects_line="- Covered subjects: {subjects}.",
        deliverable_line="- Delivered outcome: {count} validated step(s).",
        overview_header="- Step overview:",
        overview_item="  {index}. Step {index} – {title} ({subject})",
        table_header="| Step | Score | Strengths | Improvements |",
        table_divider="| :--- | :---: | :--- | :--- |",
        step_label="Step",
        detail_heading="### Deliverable details",
        follow_up_intro=(
            "The improvement themes below are ordered by priority to steer next iterations."
        ),
        follow_up_item="{rank}. Priority {rank} – Step {step_index}: {improvement}",
        follow_up_none="No additional priority actions were identified.",
        follow_up_conclusion=(
            "Conclusion: addressing {count} improvement item(s) will better fulfil the goal "
            "“{goal}”."
        ),
        strengths_fallback="Sustain the quality observed in this step.",
        improvements_fallback="No immediate adjustment identified.",
    ),
}


def _normalise_language(code: str | None) -> str | None:
    if code is None:
        return None
    trimmed = code.strip().lower()
    if not trimmed:
        return None
    return trimmed.split("-")[0]


def _ensure_notes(notes: Sequence[str], fallback: str) -> str:
    filtered = [note.strip() for note in notes if note.strip()]
    if not filtered:
        return fallback
    return " · ".join(filtered)


def _validate_step(step: ReviewStep, pack: _LanguagePack) -> None:
    if len(step.title.strip()) == 0:
        raise ValueError("Each review step must include a non-empty title.")
    if len(step.title.strip()) > 80:
        raise ValueError(
            "Step titles must be 80 characters or fewer to avoid truncated displays."
        )
    if len(step.subject.strip()) == 0:
        raise ValueError("Each review step must reference a subject to summarise outcomes.")
    # Use pack to avoid unused warning if future localisation adds constraints
    _ = pack.step_label


def generate_design_review_report(
    context: DesignReviewContext, steps: Iterable[ReviewStep]
) -> str:
    """Render a markdown design review report compliant with localisation rules."""

    response_language = _normalise_language(context.requested_output_language)
    if response_language is None:
        response_language = _normalise_language(context.prompt_language)

    if response_language is None:
        raise ValueError(
            "Unable to determine the response language. Provide prompt or requested language."
        )

    pack = LANGUAGE_PACKS.get(response_language)
    if pack is None:
        raise ValueError(
            "The requested language is not supported yet for design review formatting."
        )

    step_list = list(steps)
    if not step_list:
        raise ValueError("At least one review step is required to build the report.")

    for step in step_list:
        _validate_step(step, pack)

    subjects = ", ".join(step.subject for step in step_list)
    summary_lines = [
        pack.section1_title,
        pack.goal_line.format(goal=context.goal),
        pack.request_line.format(request=context.initial_request),
        pack.subjects_line.format(subjects=subjects),
        pack.deliverable_line.format(count=len(step_list)),
        pack.overview_header,
    ]
    for index, step in enumerate(step_list, start=1):
        summary_lines.append(
            pack.overview_item.format(index=index, title=step.title, subject=step.subject)
        )

    table_lines = [
        pack.section2_title,
        pack.table_header,
        pack.table_divider,
    ]
    for index, step in enumerate(step_list, start=1):
        strengths = _ensure_notes(step.strengths, pack.strengths_fallback)
        improvements = _ensure_notes(step.improvements, pack.improvements_fallback)
        table_lines.append(
            f"| {pack.step_label} {index} – {step.title} | {step.score:.2f} | {strengths} | {improvements} |"
        )

    details_lines = [pack.detail_heading]
    for index, step in enumerate(step_list, start=1):
        details_lines.extend(
            [
                "",
                f"#### {pack.step_label} {index} – {step.title}",
                step.result,
            ]
        )

    follow_up_lines = [pack.section3_title, pack.follow_up_intro]
    rank = 1
    for index, step in enumerate(step_list, start=1):
        for improvement in step.improvements:
            if not improvement.strip():
                continue
            follow_up_lines.append(
                pack.follow_up_item.format(
                    rank=rank, step_index=index, improvement=improvement.strip()
                )
            )
            rank += 1

    total_improvements = rank - 1
    if total_improvements == 0:
        follow_up_lines.append(pack.follow_up_none)

    follow_up_lines.append(
        pack.follow_up_conclusion.format(goal=context.goal, count=total_improvements)
    )

    sections = [
        pack.document_title,
        "",
        *summary_lines,
        "",
        *table_lines,
        "",
        *details_lines,
        "",
        *follow_up_lines,
    ]
    return "\n".join(sections).strip() + "\n"
