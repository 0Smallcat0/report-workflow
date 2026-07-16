"""Run controlled end-to-end benchmarks for built-in report profiles.

This runner is intentionally repo-local and deterministic. It prepares a report
run, writes controlled agent-authored artifacts against the run's own evidence
ledger, then attempts validate and render. The compact evidence written under
``benchmarks/evidence`` is meant for workflow optimization decisions, not for
publication.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from report_workflow.run_workflow import prepare_workflow, render_workflow, validate_workflow
from report_workflow.runtime_support import run_dir_for


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks" / "fixtures" / "controlled_source.md"
CHART_FIXTURES = [
    ROOT / "benchmarks" / "fixtures" / "chart_source.csv",
    ROOT / "benchmarks" / "fixtures" / "chart_line_source.csv",
    ROOT / "benchmarks" / "fixtures" / "chart_scatter_source.csv",
    ROOT / "benchmarks" / "fixtures" / "chart_boxplot_source.csv",
    ROOT / "benchmarks" / "fixtures" / "chart_table_fallback_source.csv",
]
SOURCE_FIXTURES = [FIXTURE, *CHART_FIXTURES]
RUN_ROOT = ROOT / "output" / "benchmark_runs"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / "full_benchmark_2026-05-13"
EXPECTED_FIGURE_TYPES = {"bar", "line", "scatter", "boxplot", "table"}

PROFILES = [
    "engineering_lab_report",
    "academic_paper",
    "business_report",
    "proposal",
    "admissions_report",
    "admissions_project_report",
    "custom",
]

GAP_CATEGORIES = {
    "skill_guidance_gap",
    "profile_policy_gap",
    "deterministic_pipeline_gap",
    "render_template_gap",
    "agent_authoring_gap",
    "external_reference_gap",
}

PROMPTS = {
    "engineering_lab_report": "Write an engineering lab report about the structured workflow pilot.",
    "academic_paper": "Write an academic paper about the structured workflow pilot.",
    "business_report": "Write a business report about the structured workflow pilot.",
    "proposal": "Write a proposal for adopting the structured workflow pilot.",
    "admissions_report": "Write an admissions-facing scholarly report about the structured workflow project.",
    "admissions_project_report": "Write an admissions-facing project report about the structured workflow project.",
    "custom": "Write a custom hybrid report about the structured workflow pilot.",
}

QA_SNAPSHOT_FILES = [
    "qa_summary.json",
    "factuality_report.json",
    "scholarly_quality_report.json",
    "scholarly_quality_report.md",
    "engineering_audit_report.json",
    "figure_visual_quality_report.json",
    "figure_plan_audit_report.json",
    "section_role_report.json",
    "admissions_tone_report.json",
    "project_identity_report.json",
    "reference_verify_report.json",
    "reference_relevance_report.json",
    "post_render_validate_report.json",
]

PUBLISHED_QA_FILES = [
    "final_qa_summary.json",
    "final_qa_summary.md",
    "template_style_map.json",
    "template_style_map.md",
    "figure_visual_quality_report.json",
    "scholarly_quality_report.json",
]


def _rel(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(ROOT))
    except Exception:
        return str(candidate)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict) and "_contract" not in payload:
            rows.append(payload)
    return rows


def _evidence_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("content", "quote", "source_file", "source_role", "evidence_type")
    )


def _pick_evidence(rows: list[dict[str, Any]], terms: list[str], fallback_index: int) -> str:
    scored: list[tuple[int, str]] = []
    for row in rows:
        text = _evidence_text(row).lower()
        score = sum(1 for term in terms if term.lower() in text)
        if score:
            scored.append((score, str(row.get("evidence_id") or "")))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]
    if not rows:
        raise RuntimeError("evidence ledger is empty")
    return str(rows[min(fallback_index, len(rows) - 1)].get("evidence_id") or "")


def _front_matter(profile: str) -> dict[str, Any]:
    title = {
        "engineering_lab_report": "Structured Workflow Pilot Laboratory Report",
        "academic_paper": "Structured Workflow Pilot for Evidence-Bounded Report Generation",
        "business_report": "Structured Workflow Pilot Business Review",
        "proposal": "Structured Workflow Pilot Adoption Proposal",
        "admissions_report": "Evidence-Bounded Workflow Project for Graduate Study Readiness",
        "admissions_project_report": "Evidence-Bounded Workflow Project Report",
        "custom": "Structured Workflow Pilot Hybrid Report",
    }[profile]
    return {
        "title": title,
        "short_title": "Structured Workflow Pilot",
        "author_block": "Benchmark Agent, Report Workflow Lab",
        "affiliation_block": "Report Workflow Benchmark Suite",
        "correspondence": "benchmark@example.com",
        "keywords": [
            "structured workflow",
            "evidence handling",
            "quality assurance",
            "pilot evaluation",
        ],
        "conflict_note": "The benchmark uses synthetic controlled source data.",
    }


def _project_identity() -> dict[str, Any]:
    return {
        "required_terms": [
            "structured workflow",
            "evidence handling",
            "QA thinking",
        ],
        "required_context_terms": [
            "auditable artifacts",
            "graduate study",
            "technical communication",
        ],
        "canonical_title_terms": ["workflow", "evidence"],
        "forbidden_terms": [],
        "domain_context": (
            "Structured workflow project for graduate admissions readiness in "
            "human-centered computing, technical communication, or applied information systems."
        ),
        "author_metadata": {},
    }


def _claims(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = {
        "context": _pick_evidence(rows, ["converted intake notes", "final DOCX report package"], 3),
        "method": _pick_evidence(rows, ["same 42 participants", "compare median processing"], 7),
        "measurement": _pick_evidence(rows, ["baseline_manual", "structured_workflow", "median_processing_minutes"], 5),
        "limit": _pick_evidence(rows, ["not be generalized beyond", "tested intake"], 10),
        "satisfaction": _pick_evidence(rows, ["supportive, not primary", "reviewer satisfaction"], 11),
        "proposal": _pick_evidence(rows, ["six weeks", "USD 4,800", "onboarding sessions"], 13),
    }
    return [
        {
            "claim_id": "c_context",
            "claim_text": (
                "The pilot converted intake notes into a structured evidence ledger, "
                "a claim matrix, and a final DOCX report package."
            ),
            "claim_type": "factual",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [ids["context"]],
            "topic_tags": ["workflow design", "evidence handling"],
        },
        {
            "claim_id": "c_method",
            "claim_text": (
                "The procedure processed the same participant notes through both baseline manual "
                "and structured workflow methods before comparison."
            ),
            "claim_type": "factual",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [ids["method"]],
            "topic_tags": ["method", "controlled comparison"],
        },
        {
            "claim_id": "c_measurement",
            "claim_text": (
                "Across the same 42 participant notes, the structured workflow cut median "
                "processing time from 28 to 20 minutes per note and the error rate from "
                "7.5% to 4.1%, while reviewer satisfaction rose from 71% to 84%."
            ),
            "claim_type": "factual",
            "claim_role": "primary",
            "status": "supported",
            "evidence_ids": [ids["measurement"]],
            "topic_tags": ["pilot outcome", "measurement"],
        },
        {
            "claim_id": "c_limit",
            "claim_text": "The study is a pilot that should not be generalized beyond the tested intake workflow.",
            "claim_type": "factual",
            "claim_role": "background",
            "status": "supported",
            "evidence_ids": [ids["limit"]],
            "topic_tags": ["limitation"],
        },
        {
            "claim_id": "c_satisfaction",
            "claim_text": "Reviewer satisfaction was collected as supportive rather than primary evidence.",
            "claim_type": "factual",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [ids["satisfaction"]],
            "topic_tags": ["reviewer evidence"],
        },
        {
            "claim_id": "c_proposal",
            "claim_text": (
                "The proposal inputs identify six weeks of implementation effort, USD 4,800 in "
                "direct setup cost, reviewer training risk, and onboarding mitigation."
            ),
            "claim_type": "factual",
            "claim_role": "background",
            "status": "supported",
            "evidence_ids": [ids["proposal"]],
            "topic_tags": ["proposal", "implementation"],
        },
    ]


def _claim_by_id(claims: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(claim["claim_id"]): claim for claim in claims}


def _sent(text: str, claim_ids: list[str], claims: list[dict[str, Any]], strength: str = "hedged") -> dict[str, Any]:
    evidence_ids: list[str] = []
    by_id = _claim_by_id(claims)
    for claim_id in claim_ids:
        evidence_ids.extend(by_id[claim_id]["evidence_ids"])
    return {
        "text": text,
        "claim_ids": claim_ids,
        "evidence_ids": evidence_ids,
        "citation_ids": evidence_ids,
        "wording_strength": strength,
    }


def _abstract_academic(claims: list[dict[str, Any]]) -> dict[str, Any]:
    text = """## Background
Document intake work often loses traceability when source notes, claims, and final prose are reviewed as separate products. The controlled pilot examined a small academic-lab intake workflow where notes were normalized into evidence-bounded report artifacts.
## Objective
The objective was to assess whether a structured workflow could preserve auditability while improving practical review signals for processing, errors, reviewer confidence, and future adoption planning.
## Methods
The same 42 participant notes were processed once with the baseline manual method and once with the structured workflow, then compared on median processing time per note, the share of notes needing reviewer repair, and reviewer satisfaction. The procedure also recorded constraints that limit generalization.
## Principal Findings
The structured workflow reduced median processing time from 28 to 20 minutes per note and the error rate from 7.5% to 4.1%, while reviewer satisfaction rose from 71% to 84%. Satisfaction remains supportive rather than primary evidence, and the proposal inputs frame adoption through six weeks of effort, USD 4,800 in setup cost, training risk, and onboarding mitigation.
## Significance
The benchmark supports using evidence boundaries, explicit methods, adoption assumptions, and limitation statements as quality controls for report generation research. Its value is methodological: it creates a controlled profile comparison without converting one sample report into a universal template."""
    return _sent(
        text,
        ["c_context", "c_method", "c_measurement", "c_limit", "c_satisfaction", "c_proposal"],
        claims,
    )


def _abstract_plain(profile: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    if profile in {"admissions_report", "admissions_project_report"}:
        text = (
            "This report presents a structured workflow project as evidence of graduate-study readiness, "
            "technical judgment, and reflective quality assurance practice. The project converted ambiguous "
            "intake notes into auditable artifacts, processed the same notes through baseline and structured "
            "conditions, and compared processing, repair, and reviewer response signals without treating the "
            "pilot as broadly generalizable. The strongest admissions-facing contribution is not a claim of "
            "universal performance; it is the demonstrated habit of drawing boundaries around evidence, "
            "selecting claims that can be supported, and naming limits before interpretation. The project also "
            "shows practical implementation awareness because proposal inputs identify effort, setup cost, "
            "reviewer training risk, and onboarding mitigation. For programs in human-centered computing, "
            "technical communication, or applied information systems, the work illustrates how reliability, "
            "source discipline, and communication design can be joined in a small but auditable project. It also "
            "shows the applicant can separate supportive satisfaction evidence from primary measured evidence."
        )
        return _sent(text, ["c_context", "c_method", "c_limit", "c_proposal"], claims)
    text = (
        "The controlled source describes a synthetic pilot for converting intake notes into auditable report "
        "artifacts. It records the workflow context, comparison procedure, measurement table, proposal inputs, "
        "and project-learning constraints. The report uses these source elements to describe what changed, "
        "what can be recommended, and what should remain bounded as pilot evidence."
    )
    return _sent(text, ["c_context", "c_method", "c_measurement", "c_limit"], claims)


def _section_sentence(profile: str, section_id: str, claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    if section_id in {"references", "appendix"}:
        return None
    if section_id == "abstract":
        if profile == "academic_paper":
            return _abstract_academic(claims)
        return _abstract_plain(profile, claims)
    if section_id == "introduction" and profile == "academic_paper":
        return _sent(
            "The gap addressed by this benchmark is the limited visibility between source intake notes, claim selection, and final report prose in small evidence-handling workflows. The objective is to evaluate a controlled structured workflow pilot using the same source data, procedure, quality criteria, and report-profile comparison across every run. The contribution is a reproducible source-to-report case that demonstrates how evidence boundaries, deterministic chart guidance, and QA artifacts can be assessed without treating one reference report as a universal template.",
            ["c_context", "c_method", "c_measurement", "c_limit"],
            claims,
        )
    if section_id in {"introduction", "cover", "executive_summary"}:
        return _sent(
            "The structured workflow pilot is best read as a bounded evidence-handling and QA thinking project: it converted intake notes into auditable report artifacts, compared a controlled procedure, recorded measurement signals, bounded its claims, treated satisfaction as supportive evidence, and named adoption assumptions.",
            ["c_context", "c_method", "c_measurement", "c_limit", "c_satisfaction", "c_proposal"],
            claims,
        )
    if section_id in {"research_scope", "objectives", "requirements", "problem_statement"}:
        return _sent(
            "The controlled scope keeps the project tied to the tested intake workflow, the same participant-note procedure, and explicit limits on generalization.",
            ["c_method", "c_limit"],
            claims,
        )
    if section_id in {"methods", "procedure", "proposed_approach"}:
        return _sent(
            "The methods used the controlled source dataset as the sample basis, processed the same 42 participant notes once with the baseline manual procedure and once with the structured workflow, compared the conditions on median processing time per note, detected error rate, and reviewer satisfaction, and used no exclusions beyond the documented pilot scope; deterministic chart transforms were kept in figure metadata rather than recomputed in prose.",
            ["c_method", "c_measurement", "c_limit"],
            claims,
        )
    if section_id in {"results", "data", "findings"}:
        return _sent(
            "Across the same 42 notes, median processing time fell from 28 minutes per note under the manual baseline to 20 minutes under the structured workflow, the share of notes needing reviewer repair fell from 7.5% to 4.1%, and reviewer satisfaction rose from 71% to 84%.",
            ["c_measurement"],
            claims,
        )
    if section_id in {"discussion", "results_discussion"}:
        return _sent(
            "The pattern — faster processing, fewer repairs, and higher reviewer satisfaction — is useful for decision-making because it combines practical review signals with a clear warning that the pilot should not be generalized beyond the tested workflow.",
            ["c_measurement", "c_limit"],
            claims,
        )
    if section_id == "limitations":
        return _sent(
            "The study remains a pilot, and reviewer satisfaction should be interpreted as supportive evidence rather than the primary basis for adoption.",
            ["c_limit", "c_satisfaction"],
            claims,
        )
    if section_id in {"recommendations", "evaluation"}:
        return _sent(
            "A cautious next step is to evaluate adoption with reviewer training, onboarding sessions, and the same evidence-boundary discipline used in the pilot.",
            ["c_proposal", "c_satisfaction"],
            claims,
        )
    if section_id in {"timeline", "budget_resources", "risks", "scope_deliverables"}:
        return _sent(
            "The proposal inputs define implementation effort, setup cost, reviewer training risk, onboarding mitigation, and a limited adoption scope.",
            ["c_proposal"],
            claims,
        )
    if section_id == "theory":
        return _sent(
            "The reporting theory behind the pilot is that reliability can be strengthened when claims, evidence boundaries, and review responsibilities are made explicit before prose polish.",
            ["c_context", "c_limit"],
            claims,
        )
    if section_id == "apparatus":
        return _sent(
            "The apparatus for this synthetic lab case is the documented intake workflow and its normalized report package rather than a physical instrument.",
            ["c_context"],
            claims,
        )
    if section_id == "calculations":
        return _sent(
            "The calculation basis is the measured comparison itself: median processing time of 28 minutes per note under the manual baseline versus 20 minutes under the structured workflow, an error rate of 7.5% versus 4.1%, and reviewer satisfaction of 71% versus 84%.",
            ["c_measurement"],
            claims,
        )
    if section_id == "conclusion":
        if profile == "admissions_report":
            return _sent(
                "The project demonstrates evidence handling, workflow design, QA thinking, and the discipline to keep learning claims within the tested source boundaries.",
                ["c_context", "c_limit", "c_satisfaction"],
                claims,
            )
        return _sent(
            "Overall, the pilot supports cautious workflow adoption and further study because its favorable review signals remain bounded by a small synthetic source fixture.",
            ["c_measurement", "c_limit"],
            claims,
        )
    return _sent(
        "This section uses the controlled source to keep the profile-specific report tied to documented context, method, measurements, and limitations.",
        ["c_context", "c_limit"],
        claims,
    )


def _figure_target_section(blueprint: dict[str, Any]) -> str | None:
    sections = set((blueprint.get("sections") or {}).keys())
    for section_id in ("results", "data", "findings", "evaluation", "executive_summary"):
        if section_id in sections:
            return section_id
    return None


def _read_figures(run_dir: Path) -> list[dict[str, Any]]:
    figure_plan = _read_json(run_dir / "section_drafts" / "figure_plan.json")
    figures = figure_plan.get("figures", [])
    if not isinstance(figures, list):
        return []
    return [figure for figure in figures if isinstance(figure, dict)]


def _publication_ylabel(label: str, title: str = "") -> str:
    text = str(label or "").strip()
    lowered = " ".join([text, str(title or "")]).lower()
    if re.search(r"\([^)]{1,20}\)", text) or any(token in text.lower() for token in ("%", "percent", "count", "score", "ratio", "index")):
        return text
    if "minute" in lowered or "processing" in lowered:
        return "Processing time (minutes)"
    if "error" in lowered:
        return "Error rate (%)"
    if "satisfaction" in lowered:
        return "Reviewer satisfaction (%)"
    if "strength" in lowered:
        return "Strength (score)"
    if "temperature" in lowered:
        return "Temperature (C)"
    if "cost" in lowered:
        return "Cost (USD)"
    if text:
        return f"{text} (value)"
    return "Value (count)"


def _normalize_figure_for_publication(figure: dict[str, Any], section_id: str) -> bool:
    changed = False
    if figure.get("section_id") != section_id:
        figure["section_id"] = section_id
        changed = True

    figure_type = str(figure.get("figure_type") or "").strip().lower()
    if figure_type in {"bar", "line", "scatter", "boxplot", "histogram", "error_bar", "stacked_bar"}:
        ylabel = _publication_ylabel(str(figure.get("ylabel") or ""), str(figure.get("title") or ""))
        if ylabel and figure.get("ylabel") != ylabel:
            figure["ylabel"] = ylabel
            changed = True

    title = str(figure.get("title") or "").strip()
    figure_id = str(figure.get("figure_id") or "").strip()
    generic_title = (
        not title
        or title.lower() in {figure_id.lower(), "figure", "chart", "plot"}
        # Auto-plan titles like "Bar view of chart_source" leak internal
        # dataset filenames into the rendered chart; replace them with the
        # human caption for that chart type.
        or re.search(r"(?i)\bview of\b|_source\b", title) is not None
    )
    if generic_title:
        _, human_caption = _FIGURE_COPY.get(
            figure_type, ("", "Source-data view supporting the pilot comparison")
        )
        figure["title"] = human_caption
        changed = True
    return changed


def _retarget_figure_plan(run_dir: Path, section_id: str | None) -> None:
    if not section_id:
        return
    path = run_dir / "section_drafts" / "figure_plan.json"
    figure_plan = _read_json(path)
    figures = figure_plan.get("figures", [])
    if not isinstance(figures, list):
        return
    changed = False
    display_number = 0
    for figure in figures:
        if isinstance(figure, dict):
            # Renumber ids to the publication-facing "1".."5" so prose
            # references ("Figure 1"), [FIGURE:<id>] placeholders, and outline
            # figure_ids all agree, and no figrec_* internal id can leak into
            # the rendered document. recommendation_id keeps the audit trail
            # back to figure_recommendations.json.
            display_number += 1
            new_id = str(display_number)
            if figure.get("figure_id") != new_id:
                figure["figure_id"] = new_id
                changed = True
            changed = _normalize_figure_for_publication(figure, section_id) or changed
    if changed:
        _write_json(path, figure_plan)


def _outline(
    profile: str,
    blueprint: dict[str, Any],
    claims: list[dict[str, Any]],
    figure_ids: list[str],
    figure_section: str | None,
) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    claim_ids = [str(claim["claim_id"]) for claim in claims]
    for section_id in blueprint.get("section_order", []):
        sections[section_id] = {
            "section_id": section_id,
            "title": blueprint.get("sections", {}).get(section_id, {}).get("title") or section_id.replace("_", " ").title(),
            "claim_ids": [] if section_id in {"references", "appendix"} else claim_ids,
            "figure_ids": figure_ids if section_id == figure_section else [],
        }
    outline: dict[str, Any] = {
        "thesis_statement": (
            "The structured workflow pilot demonstrates that evidence handling, QA thinking, controlled "
            "procedure, and explicit quality boundaries can support a serious but bounded report-generation project."
        ),
        "sections": sections,
    }
    if profile == "academic_paper":
        outline["paper_spine"] = {
            "problem": "Document intake reports can lose traceability between sources, claims, and final prose.",
            "gap": "Small report workflows often lack a benchmark that connects controlled source data to review-grade output quality.",
            "objective": "Evaluate a synthetic structured workflow pilot using evidence-bounded report-generation criteria.",
            "contribution": "Provide a controlled source-to-report case for comparing profile behavior and QA artifacts.",
            "method_basis": "Use the same fixture, evidence ledger, controlled claims, outline, and section drafts for every profile.",
            "main_limitation": "The source is synthetic and supports workflow-quality conclusions only within the tested pilot.",
        }
    if profile == "engineering_lab_report":
        outline["lab_spine"] = {
            "experiment_purpose": "Determine whether structured evidence handling can strengthen a pilot intake reporting workflow.",
            "variables": "Condition is baseline_manual versus structured_workflow; outcomes are processing, repair, and satisfaction fields.",
            "apparatus_procedure_basis": "The apparatus is the documented intake workflow fixture and the same-note comparison procedure.",
            "measurement_basis": "Measurements come from the fixture's comparison table and documented procedure.",
            "uncertainty_limitations": "The fixture is synthetic, small, and not generalizable beyond the tested intake workflow.",
        }
    return outline


# One distinct lead-in and one human caption per chart, written from what each
# fixture dataset actually contains. Repeating a single template sentence with
# a swapped noun is exactly the machine-writing tell the Prose Quality
# contract forbids, and internal ids (figrec_*, *_source filenames) must never
# reach body text or captions.
_FIGURE_COPY: dict[str, tuple[str, str]] = {
    "bar": (
        "Figure {n} compares the two conditions directly: the structured workflow "
        "brings median processing time down from 28 to 20 minutes per note.",
        "Median processing time per note, manual baseline versus structured workflow (minutes)",
    ),
    "line": (
        "Figure {n} traces the month-by-month trend across the pilot period, with "
        "median processing time falling as the structured workflow settled in.",
        "Median processing time per note by month over the pilot period (minutes)",
    ),
    "scatter": (
        "Figure {n} sets intake complexity against review effort, showing that "
        "more complex notes demanded proportionally more reviewer attention.",
        "Review effort score versus intake complexity score for the sampled notes",
    ),
    "boxplot": (
        "Figure {n} shows the spread of per-note processing times within each "
        "condition, not just the medians.",
        "Distribution of per-note processing minutes under each condition",
    ),
    "table": (
        "Figure {n} lists the adoption parameters behind the proposal: two "
        "onboarding sessions, a one-week shadow period, and USD 4,800 in setup cost.",
        "Adoption planning parameters from the proposal inputs",
    ),
}


def _figure_sentence(
    figure: dict[str, Any],
    claims: list[dict[str, Any]],
    display_number: int,
) -> dict[str, Any] | None:
    figure_id = str(figure.get("figure_id") or "").strip()
    if not figure_id:
        return None
    figure_type = str(figure.get("figure_type") or "").strip().lower()
    lead_in, caption = _FIGURE_COPY.get(
        figure_type,
        (
            "Figure {n} presents the supporting source-data view for this comparison.",
            "Source-data view supporting the pilot comparison",
        ),
    )
    return _sent(
        (
            f"{lead_in.format(n=display_number)} [FIGURE:{figure_id}]\n\n"
            f"Figure {display_number}: {caption}."
        ),
        ["c_measurement"],
        claims,
    )


def _structured_drafts(
    profile: str,
    blueprint: dict[str, Any],
    claims: list[dict[str, Any]],
    figures: list[dict[str, Any]],
    figure_section: str | None,
) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for section_id in blueprint.get("section_order", []):
        sentence = _section_sentence(profile, section_id, claims)
        sentences = [] if sentence is None else [sentence]
        if section_id == figure_section:
            for display_number, figure in enumerate(figures, start=1):
                figure_sentence = _figure_sentence(figure, claims, display_number)
                if figure_sentence:
                    sentences.append(figure_sentence)
        sections[section_id] = {
            "title": blueprint.get("sections", {}).get(section_id, {}).get("title") or section_id.replace("_", " ").title(),
            "sentences": sentences,
        }
    return {
        "generated_by": "scripts.run_report_benchmarks",
        "benchmark_fixture": _rel(FIXTURE),
        "sections": sections,
    }


def _write_agent_artifacts(state: Any, profile: str) -> dict[str, Any]:
    run_dir = run_dir_for(state)
    evidence_rows = _read_jsonl(Path(state.sources["evidence_ledger_path"]))
    claims = _claims(evidence_rows)
    figure_section = _figure_target_section(state.plan.get("blueprint") or {})
    _retarget_figure_plan(run_dir, figure_section)
    figures = _read_figures(run_dir)
    figure_ids = [
        str(figure.get("figure_id") or "").strip()
        for figure in figures
        if str(figure.get("figure_id") or "").strip()
    ]
    claim_matrix = {
        "claims": claims,
        "benchmark_note": "Controlled benchmark artifact generated from the current run evidence ledger.",
    }
    outline = _outline(profile, state.plan.get("blueprint") or {}, claims, figure_ids, figure_section)
    structured = _structured_drafts(profile, state.plan.get("blueprint") or {}, claims, figures, figure_section)

    _write_json(run_dir / "claim_matrix.json", claim_matrix)
    _write_json(run_dir / "outline.json", outline)
    _write_json(run_dir / "structured_drafts.json", structured)
    return {
        "claim_count": len(claims),
        "evidence_count": len(evidence_rows),
        "section_count": len(structured["sections"]),
        "figure_ids": figure_ids,
        "figure_section": figure_section,
    }


def _copy_snapshots(profile: str, run_dir: Path, evidence_root: Path) -> list[dict[str, str]]:
    profile_dir = evidence_root / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for name in QA_SNAPSHOT_FILES:
        src = run_dir / name
        if src.exists():
            dest = profile_dir / name
            shutil.copy2(src, dest)
            copied.append({"role": name, "path": _rel(dest)})
    published_qa = run_dir / "published" / "qa"
    for name in PUBLISHED_QA_FILES:
        src = published_qa / name
        if src.exists():
            dest = profile_dir / f"published_{name}"
            shutil.copy2(src, dest)
            copied.append({"role": f"published/{name}", "path": _rel(dest)})
    for name in ("claim_matrix.json", "outline.json", "structured_drafts.json"):
        src = run_dir / name
        if src.exists():
            dest = profile_dir / name
            shutil.copy2(src, dest)
            copied.append({"role": name, "path": _rel(dest)})
    return copied


def _classify_error(message: str) -> str:
    text = message.lower()
    if "admissions_tone_gate" in text or "section role violations" in text or "thesis_spine_missing" in text:
        return "profile_policy_gap"
    if "nameerror" in text or "undefined" in text:
        return "deterministic_pipeline_gap"
    if "render" in text or "docx" in text or "template" in text:
        return "render_template_gap"
    if "abstract_check" in text or "claim_matrix" in text or "structured_drafts" in text or "sentence_map" in text:
        return "agent_authoring_gap"
    if "reference" in text:
        return "external_reference_gap"
    return "skill_guidance_gap"


def _qa_digest(run_dir: Path) -> dict[str, Any]:
    digest: dict[str, Any] = {}
    qa_summary = _read_json(run_dir / "qa_summary.json")
    if qa_summary:
        digest["qa_decision"] = qa_summary.get("qa_decision")
        digest["hard_fail_reasons"] = qa_summary.get("hard_fail_reasons", [])
    scholarly = _read_json(run_dir / "scholarly_quality_report.json")
    if scholarly:
        digest["scholarly_quality"] = {
            "status": scholarly.get("status"),
            "issue_count": scholarly.get("issue_count"),
            "hard_issue_count": scholarly.get("hard_issue_count"),
            "issues": [issue.get("type") for issue in scholarly.get("issues", [])[:10] if isinstance(issue, dict)],
        }
    figure = _read_json(run_dir / "figure_visual_quality_report.json")
    if figure:
        digest["figure_visual_quality"] = {
            "status": figure.get("status"),
            "issue_count": figure.get("issue_count"),
        }
    final_qa = _read_json(run_dir / "published" / "qa" / "final_qa_summary.json")
    if final_qa:
        digest["final_qa_summary_status"] = final_qa.get("status") or final_qa.get("qa_decision")
    recommendations = _read_json(run_dir / "figure_recommendations.json")
    if recommendations:
        recs = recommendations.get("recommendations", [])
        digest["figure_recommendations"] = {
            "status": recommendations.get("status"),
            "recommendation_count": recommendations.get("recommendation_count", 0),
            "recommended_types": [
                rec.get("recommended_figure_type")
                for rec in recs
                if isinstance(rec, dict) and rec.get("recommended_figure_type")
            ],
        }
    plan_audit = _read_json(run_dir / "figure_plan_audit_report.json")
    if plan_audit:
        figure_plan = _read_json(run_dir / "section_drafts" / "figure_plan.json")
        planned_types = [
            str(figure.get("figure_type") or "").strip().lower()
            for figure in figure_plan.get("figures", [])
            if isinstance(figure, dict) and str(figure.get("figure_type") or "").strip()
        ]
        digest["figure_plan_audit"] = {
            "status": plan_audit.get("status"),
            "figure_count": plan_audit.get("figure_count", 0),
            "planned_types": planned_types,
            "hard_issue_count": len(plan_audit.get("hard_issues", []) or []),
        }
    return digest


def run_profile(profile: str, evidence_root: Path = EVIDENCE_ROOT) -> dict[str, Any]:
    record: dict[str, Any] = {
        "report_profile": profile,
        "prompt": PROMPTS[profile],
        "fixture": _rel(FIXTURE),
        "chart_fixtures": [_rel(path) for path in CHART_FIXTURES],
        "status": "started",
        "gap_classification": None,
    }
    try:
        state = prepare_workflow(
            user_prompt=PROMPTS[profile],
            uploaded_files=[str(path) for path in SOURCE_FIXTURES],
            output_dir=str(RUN_ROOT),
            report_profile=profile,
            front_matter=_front_matter(profile),
            project_identity=_project_identity() if profile in {"admissions_report", "admissions_project_report"} else None,
            enable_research=False,
            enable_notebook_sync=False,
        )
        run_dir = run_dir_for(state)
        record.update({
            "job_id": state.job_id,
            "run_dir": _rel(run_dir),
            "prepare_status": state.status,
        })
        record["agent_artifacts"] = _write_agent_artifacts(state, profile)

        validated = validate_workflow(state.job_id, workspace_root=str(RUN_ROOT))
        record["validate_status"] = validated.status

        try:
            rendered = render_workflow(state.job_id, workspace_root=str(RUN_ROOT))
            record["render_status"] = rendered.status
            record["final_docx_path"] = _rel(rendered.output.get("published_report_path") or rendered.output.get("final_docx_path"))
            record["status"] = "pass"
        except Exception as exc:
            record["render_status"] = "failed"
            record["status"] = "render_failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["gap_classification"] = _classify_error(record["error"])
            record["traceback_tail"] = traceback.format_exc().splitlines()[-8:]
    except Exception as exc:
        run_dir = Path(record.get("run_dir", ""))
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["gap_classification"] = _classify_error(record["error"] + "\n" + traceback.format_exc())
        record["traceback_tail"] = traceback.format_exc().splitlines()[-8:]
        if not run_dir.exists() and record.get("job_id"):
            matches = sorted(RUN_ROOT.glob(f"*--{record['job_id']}"))
            if matches:
                run_dir = matches[0]
                record["run_dir"] = _rel(run_dir)
    finally:
        if record.get("run_dir"):
            run_dir = ROOT / str(record["run_dir"])
            if run_dir.exists():
                record["qa_digest"] = _qa_digest(run_dir)
                record["snapshots"] = _copy_snapshots(profile, run_dir, evidence_root)
    return record


def write_summary(
    results: list[dict[str, Any]],
    evidence_root: Path = EVIDENCE_ROOT,
    title: str = "Full Benchmark Run 2026-05-13",
) -> dict[str, Any]:
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fixture": _rel(FIXTURE),
        "fixtures": [_rel(path) for path in SOURCE_FIXTURES],
        "public_interface_selector": "report_profile",
        "gap_categories": sorted(GAP_CATEGORIES),
        "profiles": results,
        "counts": {
            "total": len(results),
            "pass": sum(1 for result in results if result.get("status") == "pass"),
            "failed": sum(1 for result in results if result.get("status") != "pass"),
        },
    }
    _write_json(evidence_root / "summary.json", summary)

    lines = [
        f"# {title}",
        "",
        f"- Fixture: `{summary['fixture']}`",
        "- Public selector: `report_profile`",
        "- Fixtures: " + ", ".join(f"`{_rel(path)}`" for path in SOURCE_FIXTURES),
        f"- Passed: {summary['counts']['pass']} / {summary['counts']['total']}",
        "",
        "| Profile | Status | Gap Classification | QA Digest |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        digest = result.get("qa_digest", {})
        digest_bits = []
        if digest.get("qa_decision"):
            digest_bits.append(f"qa={digest['qa_decision']}")
        scholarly = digest.get("scholarly_quality")
        if scholarly:
            digest_bits.append(
                f"scholarly={scholarly.get('status')} ({scholarly.get('issue_count')} issues)"
            )
        figure_recs = digest.get("figure_recommendations")
        if figure_recs:
            recommended_types = sorted(set(figure_recs.get("recommended_types") or []))
            digest_bits.append(
                f"figures={figure_recs.get('recommendation_count')} rec "
                f"({', '.join(recommended_types)})"
            )
        if result.get("error"):
            digest_bits.append(re.sub(r"\s+", " ", str(result["error"]))[:120])
        lines.append(
            "| {profile} | {status} | {gap} | {digest} |".format(
                profile=result["report_profile"],
                status=result["status"],
                gap=result.get("gap_classification") or "",
                digest="; ".join(digest_bits) or "-",
            )
        )
    lines.append("")
    (evidence_root / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def check_existing_summary() -> list[str]:
    issues: list[str] = []
    summary_path = EVIDENCE_ROOT / "summary.json"
    if not summary_path.exists():
        return [f"missing benchmark summary: {_rel(summary_path)}"]

    summary = _read_json(summary_path)
    profiles = summary.get("profiles", [])
    profile_ids = {
        str(profile.get("report_profile"))
        for profile in profiles
        if isinstance(profile, dict)
    }
    if profile_ids != set(PROFILES):
        issues.append(f"profile set mismatch: expected {sorted(PROFILES)}, got {sorted(profile_ids)}")

    counts = summary.get("counts", {})
    if counts.get("total") != len(PROFILES) or counts.get("pass") != len(PROFILES) or counts.get("failed") != 0:
        issues.append(f"benchmark counts are not all-pass: {counts}")

    if summary.get("public_interface_selector") != "report_profile":
        issues.append("public_interface_selector must remain report_profile")

    # Archived summary.json may store paths with either separator (evidence is
    # commonly generated on Windows); normalize to POSIX before comparing so
    # `--check` is portable across operating systems.
    fixtures = {str(item).replace("\\", "/") for item in summary.get("fixtures", [])}
    expected_fixtures = {_rel(path).replace("\\", "/") for path in SOURCE_FIXTURES}
    if not expected_fixtures.issubset(fixtures):
        issues.append(f"missing benchmark fixtures: {sorted(expected_fixtures - fixtures)}")

    for profile in profiles:
        if not isinstance(profile, dict):
            issues.append("profile record is not an object")
            continue
        report_profile = str(profile.get("report_profile") or "<missing>")
        if profile.get("status") != "pass":
            issues.append(f"{report_profile}: status is not pass")
        if profile.get("validate_status") != "validated":
            issues.append(f"{report_profile}: validate_status is not validated")
        if profile.get("render_status") != "completed":
            issues.append(f"{report_profile}: render_status is not completed")

        digest = profile.get("qa_digest") if isinstance(profile.get("qa_digest"), dict) else {}
        if digest.get("qa_decision") != "pass":
            issues.append(f"{report_profile}: qa_decision is not pass")
        visual_quality = digest.get("figure_visual_quality") if isinstance(digest.get("figure_visual_quality"), dict) else {}
        if visual_quality.get("status") != "passed":
            issues.append(f"{report_profile}: figure_visual_quality did not pass")
        figure_recs = digest.get("figure_recommendations") if isinstance(digest.get("figure_recommendations"), dict) else {}
        if int(figure_recs.get("recommendation_count", 0) or 0) < len(EXPECTED_FIGURE_TYPES):
            issues.append(f"{report_profile}: insufficient figure recommendations recorded")
        recommended_types = {str(item) for item in figure_recs.get("recommended_types", [])}
        missing_recommended = EXPECTED_FIGURE_TYPES - recommended_types
        if missing_recommended:
            issues.append(f"{report_profile}: missing recommended figure types {sorted(missing_recommended)}")
        figure_plan = digest.get("figure_plan_audit") if isinstance(digest.get("figure_plan_audit"), dict) else {}
        if figure_plan.get("status") not in {"passed", "passed_with_warnings"}:
            issues.append(f"{report_profile}: figure_plan_audit did not pass")
        if int(figure_plan.get("figure_count", 0) or 0) < len(EXPECTED_FIGURE_TYPES):
            issues.append(f"{report_profile}: insufficient audited figures recorded")
        planned_types = {str(item) for item in figure_plan.get("planned_types", [])}
        missing_planned = EXPECTED_FIGURE_TYPES - planned_types
        if missing_planned:
            issues.append(f"{report_profile}: missing planned figure types {sorted(missing_planned)}")

        snapshot_roles = {
            str(item.get("role"))
            for item in profile.get("snapshots", [])
            if isinstance(item, dict)
        }
        for role in ("published/final_qa_summary.json", "figure_plan_audit_report.json", "figure_visual_quality_report.json"):
            if role not in snapshot_roles:
                issues.append(f"{report_profile}: missing snapshot role {role}")
        for item in profile.get("snapshots", []):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            snapshot_path = ROOT / str(item["path"]).replace("\\", "/")
            if not snapshot_path.exists():
                issues.append(f"{report_profile}: missing snapshot file {item['path']}")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, action="append", help="Run only selected profile(s).")
    parser.add_argument("--check", action="store_true", help="Validate existing benchmark evidence without rerunning.")
    args = parser.parse_args()

    if args.check:
        issues = check_existing_summary()
        if issues:
            print("benchmark evidence check failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print("benchmark evidence check passed")
        return 0

    profiles = args.profile or PROFILES
    evidence_root = EVIDENCE_ROOT
    title = "Full Benchmark Run 2026-05-13"
    if args.profile:
        partial_name = "__".join(profiles)
        evidence_root = EVIDENCE_ROOT / "partial" / partial_name
        title = f"Partial Benchmark Run 2026-05-13 ({', '.join(profiles)})"
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    evidence_root.mkdir(parents=True, exist_ok=True)
    results = [run_profile(profile, evidence_root=evidence_root) for profile in profiles]
    summary = write_summary(results, evidence_root=evidence_root, title=title)
    print(json.dumps(summary["counts"], indent=2))
    return 0 if summary["counts"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
