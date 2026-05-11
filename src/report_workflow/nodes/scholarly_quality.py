"""SCHOLARLY_QUALITY - review-grade scholarly article quality audit.

This node keeps the workflow deterministic: it does not rewrite prose and it
does not call an LLM. It records whether agent-authored artifacts contain the
spine, methods, figure, table, and reference cues expected by serious academic
and Chinese engineering documents.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..runtime_support import run_dir_for, write_json_artifact
from ..state import ReportState


PAPER_SPINE_FIELDS = (
    "problem",
    "gap",
    "objective",
    "contribution",
    "method_basis",
    "main_limitation",
)

LAB_SPINE_FIELDS = (
    "experiment_purpose",
    "variables",
    "apparatus_procedure_basis",
    "measurement_basis",
    "uncertainty_limitations",
)

HARD_WORKFLOW_ARTIFACT_TERMS = (
    "query_evidence",
    "claim_matrix",
    "evidence_ledger",
    "sentence_map",
    "section_drafts",
)

REVIEW_WORKFLOW_JARGON_PATTERNS = (
    r"\bNotebookLM\b",
    r"\breport workflow\b",
    r"\bworkflow artifact\b",
    r"\bagent-authored\b",
    r"\bagent task\b",
    r"\btool call\b",
    "I inferred",
    "this report uses your provided",
)

UNSUPPORTED_CERTAINTY_TERMS = (
    "proves",
    "proven",
    "perfect",
    "100%",
    "without any error",
    "completely accurate",
)

CHAPTER_OUTLINE_PATTERNS = (
    r"this (?:paper|report|article) is organized as follows",
    r"the remainder of this (?:paper|report|article)",
    r"section\s+\d+\s+(?:describes|presents|discusses|introduces)",
    r"chapter\s+\d+\s+(?:describes|presents|discusses|introduces)",
)

METHOD_FINDING_PATTERNS = (
    r"\bresults? (?:show|shows|indicate|indicates|demonstrate|demonstrates)\b",
    r"\bfindings? (?:show|shows|indicate|indicates|demonstrate|demonstrates)\b",
    r"\bwe (?:found|conclude|concluded|demonstrate|demonstrated)\b",
    r"\bthis (?:proves|confirms|shows)\b",
)

FIGURE_TYPES_WITH_AXES = {
    "bar",
    "line",
    "scatter",
    "histogram",
    "boxplot",
    "error_bar",
    "stacked_bar",
}

MAX_MAIN_TEXT_CATEGORIES = 12


def _issue(
    issues: list[dict[str, Any]],
    issue_type: str,
    severity: str,
    detail: str,
    repair_hint: str,
    **extra: Any,
) -> None:
    payload = {
        "type": issue_type,
        "severity": severity,
        "detail": detail,
        "repair_hint": repair_hint,
    }
    payload.update(extra)
    issues.append(payload)


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists():
        return ""
    try:
        return candidate.read_text(encoding="utf-8")
    except Exception:
        return ""


def _read_json(path: str | Path | None) -> dict:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _split_merged_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "preamble"
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().lower().replace(" ", "_")
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {section: "\n".join(lines).strip() for section, lines in sections.items()}


def _section_texts(state: ReportState) -> dict[str, str]:
    sections: dict[str, str] = {}
    for section_id, path in (state.drafts.get("section_drafts") or {}).items():
        text = _read_text(path)
        if text:
            sections[str(section_id)] = text

    merged_path = (
        state.drafts.get("publication_draft_md")
        or state.drafts.get("merged_draft_cited_md")
        or state.drafts.get("merged_draft_md")
    )
    merged = _read_text(merged_path)
    if merged:
        for section_id, text in _split_merged_sections(merged).items():
            sections.setdefault(section_id, text)
    return sections


def _body_text(state: ReportState, sections: dict[str, str]) -> str:
    merged_path = (
        state.drafts.get("publication_draft_md")
        or state.drafts.get("merged_draft_cited_md")
        or state.drafts.get("merged_draft_md")
    )
    merged = _read_text(merged_path)
    if merged:
        return merged
    return "\n\n".join(sections.values())


def _text_has_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _text_matches_any(text: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _blank_fields(payload: dict, required_fields: tuple[str, ...]) -> list[str]:
    missing = []
    for field in required_fields:
        value = payload.get(field)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(field)
    return missing


def _template_like_fields(payload: dict, required_fields: tuple[str, ...]) -> list[str]:
    template_patterns = (
        r"\bFor academic_paper:",
        r"\bFor engineering_lab_report:",
        r"\bthe concrete problem or phenomenon\b",
        r"\bWhat prior work, current practice, or the source material leaves unresolved\b",
        r"\bThe specific aim of this paper\b",
        r"\bThe main contribution the report can support with evidence\b",
        r"\bThe reproducible method or analysis basis\b",
        r"\bThe main limitation that should temper the claim\b",
        r"\bwhat the experiment is meant to determine\b",
        r"\bIndependent/dependent/control variables and units\b",
        r"\bWhich apparatus and procedure support the measurements\b",
        r"\bWhere measured/calculated values come from\b",
        r"\bKnown uncertainty, assumptions, or measurement limits\b",
    )
    template_fields = []
    for field in required_fields:
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        if _text_matches_any(value, template_patterns):
            template_fields.append(field)
    return template_fields


def _check_spine(state: ReportState, profile: str, issues: list[dict[str, Any]]) -> None:
    outline = state.plan.get("outline") or {}
    if profile == "academic_paper":
        spine = outline.get("paper_spine")
        if not isinstance(spine, dict):
            _issue(
                issues,
                "paper_spine_missing",
                "review",
                "outline.json has no paper_spine block for academic_paper.",
                "Add paper_spine with problem, gap, objective, contribution, method_basis, and main_limitation.",
            )
            return
        missing = _blank_fields(spine, PAPER_SPINE_FIELDS)
        if missing:
            _issue(
                issues,
                "paper_spine_incomplete",
                "review",
                "paper_spine is missing: " + ", ".join(missing),
                "Fill each spine field before drafting so the paper has a stable argument structure.",
                missing_fields=missing,
            )
        template_fields = _template_like_fields(spine, PAPER_SPINE_FIELDS)
        if template_fields:
            _issue(
                issues,
                "paper_spine_template_text",
                "review",
                "paper_spine appears to retain starter/template wording: " + ", ".join(template_fields),
                "Replace starter text with report-specific problem, gap, objective, contribution, method basis, and limitation.",
                template_fields=template_fields,
            )
    elif profile == "engineering_lab_report":
        spine = outline.get("lab_spine")
        if not isinstance(spine, dict):
            _issue(
                issues,
                "lab_spine_missing",
                "review",
                "outline.json has no lab_spine block for engineering_lab_report.",
                "Add lab_spine with experiment purpose, variables, apparatus/procedure basis, measurement basis, and uncertainty/limitations.",
            )
            return
        missing = _blank_fields(spine, LAB_SPINE_FIELDS)
        if missing:
            _issue(
                issues,
                "lab_spine_incomplete",
                "review",
                "lab_spine is missing: " + ", ".join(missing),
                "Fill each lab spine field so results and calculations remain tied to the experiment.",
                missing_fields=missing,
            )
        template_fields = _template_like_fields(spine, LAB_SPINE_FIELDS)
        if template_fields:
            _issue(
                issues,
                "lab_spine_template_text",
                "review",
                "lab_spine appears to retain starter/template wording: " + ", ".join(template_fields),
                "Replace starter text with experiment-specific purpose, variables, apparatus/procedure basis, measurement basis, and uncertainty limits.",
                template_fields=template_fields,
            )


def _check_introduction(profile: str, sections: dict[str, str], issues: list[dict[str, Any]]) -> None:
    if profile != "academic_paper":
        return
    intro = sections.get("introduction", "")
    if not intro.strip():
        _issue(
            issues,
            "introduction_missing",
            "review",
            "No introduction section text was available for scholarly audit.",
            "Draft an Introduction that establishes problem, gap, objective, and contribution.",
        )
        return
    gap_terms = ("gap", "limited", "limitation", "lack", "unclear", "challenge", "need", "however")
    objective_terms = ("objective", "aim", "purpose", "this study", "this paper", "this report")
    contribution_terms = ("contribution", "contributes", "provides", "develops", "offers", "demonstrates")
    missing_roles = []
    if not _text_has_any(intro, gap_terms):
        missing_roles.append("gap")
    if not _text_has_any(intro, objective_terms):
        missing_roles.append("objective")
    if not _text_has_any(intro, contribution_terms):
        missing_roles.append("contribution")
    if missing_roles:
        _issue(
            issues,
            "introduction_spine_weak",
            "review",
            "Introduction does not clearly signal: " + ", ".join(missing_roles),
            "Revise the Introduction so it moves from problem context to gap, objective, and contribution.",
            missing_roles=missing_roles,
        )


def _check_methods(profile: str, sections: dict[str, str], issues: list[dict[str, Any]]) -> None:
    if profile not in {"academic_paper", "engineering_lab_report"}:
        return
    methods = sections.get("methods") or sections.get("procedure") or sections.get("apparatus", "")
    if not methods.strip() and profile == "academic_paper":
        _issue(
            issues,
            "methods_missing",
            "review",
            "No methods section text was available for scholarly audit.",
            "Draft a reproducible Methods section before validation.",
        )
        return
    if not methods.strip():
        return
    reproducibility_groups = {
        "source_or_sample": ("data", "dataset", "source", "sample", "corpus", "specimen"),
        "procedure": ("procedure", "measured", "computed", "analyzed", "parsed", "constructed", "recorded"),
        "parameters": ("parameter", "threshold", "criteria", "version", "software", "instrument", "setting"),
        "exclusions_or_transforms": ("exclude", "inclusion", "transform", "normalize", "calibrate", "filter"),
    }
    missing = [
        name
        for name, terms in reproducibility_groups.items()
        if not _text_has_any(methods, terms)
    ]
    if len(missing) >= 2:
        _issue(
            issues,
            "methods_reproducibility_weak",
            "review",
            "Methods section lacks reproducibility cues: " + ", ".join(missing),
            "Add data/source basis, procedure, parameters/software/instrument settings, and exclusions or transformations when applicable.",
            missing_cues=missing,
        )
    if _text_matches_any(methods, METHOD_FINDING_PATTERNS):
        _issue(
            issues,
            "methods_contains_findings",
            "review",
            "Methods section appears to contain findings or conclusions.",
            "Move findings to Results and interpretation to Discussion; keep Methods procedural and past-tense.",
        )


def _check_abstract_and_title(state: ReportState, profile: str, sections: dict[str, str], issues: list[dict[str, Any]]) -> None:
    if profile not in {"academic_paper", "engineering_lab_report"}:
        return
    abstract = sections.get("abstract", "")
    if abstract and _text_matches_any(abstract, CHAPTER_OUTLINE_PATTERNS):
        _issue(
            issues,
            "abstract_reads_like_outline",
            "review",
            "Abstract contains paper/chapter organization prose instead of a self-contained summary.",
            "Rewrite the abstract to summarize background, objective, methods, main findings, and significance.",
        )
    front_matter = state.plan.get("front_matter") or {}
    title = str(front_matter.get("title") or "").strip()
    if profile == "academic_paper" and title:
        word_count = len(re.findall(r"\b\w+\b", title))
        if word_count < 5 or word_count > 22:
            _issue(
                issues,
                "title_precision_review",
                "review",
                f"Academic title has {word_count} words.",
                "Use a precise, information-bearing title that names the object, method, and contribution without becoming a sentence.",
                word_count=word_count,
            )


def _check_language_rules(profile: str, body: str, issues: list[dict[str, Any]]) -> None:
    if profile not in {"academic_paper", "engineering_lab_report"}:
        return
    for term in HARD_WORKFLOW_ARTIFACT_TERMS:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", body, re.IGNORECASE):
            _issue(
                issues,
                "workflow_jargon_in_body",
                "hard",
                f"Publication body contains workflow/agent jargon: {term}",
                "Remove workflow implementation terms from the publishable report body.",
                matched=term,
            )
    for pattern in REVIEW_WORKFLOW_JARGON_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            _issue(
                issues,
                "workflow_jargon_review",
                "review",
                "Publication body contains workflow/process language that may not belong in the final article.",
                "Keep implementation process notes out of publishable prose unless they are part of the subject matter.",
                pattern=pattern,
            )
    for term in UNSUPPORTED_CERTAINTY_TERMS:
        if re.search(re.escape(term), body, re.IGNORECASE):
            _issue(
                issues,
                "unsupported_certainty_language",
                "review",
                f"Body contains high-certainty wording that may overclaim: {term}",
                "Replace absolute certainty with evidence-calibrated wording unless the cited data truly justify it.",
                matched=term,
            )


def _label_has_unit_or_scale(label: str) -> bool:
    text = str(label or "").strip().lower()
    if not text:
        return False
    if re.search(r"\([^)]{1,20}\)", text):
        return True
    return any(term in text for term in ("%", "percent", "count", "score", "ratio", "index"))


def _labels_from_figure_data(data: dict) -> list[str]:
    labels = data.get("labels", [])
    if isinstance(labels, list):
        return [str(label) for label in labels]
    return []


def _figure_mentions(body: str, figure_id: str) -> tuple[bool, bool, bool]:
    placeholder = bool(re.search(rf"\[FIGURE:\s*{re.escape(figure_id)}(?:\s|\])", body, re.IGNORECASE))
    prose = bool(re.search(rf"\bfigure\s+{re.escape(figure_id)}\b", body, re.IGNORECASE))
    caption = bool(re.search(rf"(?:^|\n)\s*(?:\*+)?Figure\s+{re.escape(figure_id)}\s*[:.]", body, re.IGNORECASE))
    return placeholder, prose, caption


def _check_figures(state: ReportState, body: str, issues: list[dict[str, Any]]) -> None:
    figure_plan = _read_json(run_dir_for(state) / "section_drafts" / "figure_plan.json")
    figures = figure_plan.get("figures", [])
    if not isinstance(figures, list):
        return
    for index, figure in enumerate(figures):
        if not isinstance(figure, dict):
            continue
        figure_id = str(figure.get("figure_id") or f"index_{index}").strip()
        figure_type = str(figure.get("figure_type") or "").strip().lower()
        data = figure.get("data", {}) if isinstance(figure.get("data", {}), dict) else {}
        title = str(figure.get("title") or "").strip()

        if not title or title.lower() in {figure_id.lower(), "figure", "chart", "plot"}:
            _issue(
                issues,
                "figure_title_not_self_contained",
                "review",
                f"Figure {figure_id} lacks a specific publication-safe title.",
                "Use a self-contained title that names the relationship, variable, or comparison shown.",
                figure_id=figure_id,
            )

        if figure_type in FIGURE_TYPES_WITH_AXES:
            ylabel = str(figure.get("ylabel") or "").strip()
            if not _label_has_unit_or_scale(ylabel):
                _issue(
                    issues,
                    "figure_axis_unit_missing",
                    "review",
                    f"Figure {figure_id} has no clear y-axis unit or value scale.",
                    "Set ylabel with units or scale, for example 'Voltage (V)', 'Share (%)', or 'Count'.",
                    figure_id=figure_id,
                    axis="y",
                )

        labels = _labels_from_figure_data(data)
        if len(labels) > MAX_MAIN_TEXT_CATEGORIES:
            _issue(
                issues,
                "figure_category_density_high",
                "review",
                f"Figure {figure_id} has {len(labels)} categories.",
                "Group minor categories, split the figure, or move exact dense values to a table or appendix.",
                figure_id=figure_id,
                category_count=len(labels),
                threshold=MAX_MAIN_TEXT_CATEGORIES,
            )

        if figure_type == "error_bar":
            explanation = " ".join([
                str(figure.get("error_definition") or ""),
                str(figure.get("uncertainty_basis") or ""),
                str(figure.get("chart_selection_reason") or ""),
            ]).lower()
            if not any(term in explanation for term in ("sd", "standard deviation", "se", "standard error", "ci", "confidence interval", "uncertainty")):
                _issue(
                    issues,
                    "error_bar_uncertainty_undefined",
                    "review",
                    f"Figure {figure_id} is an error bar chart without an uncertainty definition.",
                    "State whether error bars show SD, SE, CI, measurement uncertainty, or another defined quantity.",
                    figure_id=figure_id,
                )

        placeholder, prose, caption = _figure_mentions(body, figure_id)
        if (placeholder or prose) and not caption:
            _issue(
                issues,
                "figure_caption_missing",
                "review",
                f"Figure {figure_id} is used or referenced without a nearby self-contained caption.",
                "Add a caption beginning with 'Figure <id>:' that explains what is plotted and the data basis.",
                figure_id=figure_id,
            )


def _check_references(state: ReportState, profile: str, issues: list[dict[str, Any]]) -> None:
    if profile != "academic_paper":
        return
    ref_path = state.citations.get("publication_reference_list_path", "")
    ref_text = _read_text(ref_path)
    if not ref_text:
        return
    pseudo_patterns = (
        r"\[(?:PDF|Word|Text|Data) document\]",
        r"\[Dataset\]",
        r"\bn\.d\.\b",
        r"\bunknown\b",
        r"\b[\w.-]+\.(?:pdf|docx|txt|csv|xlsx|json)\b",
    )
    for pattern in pseudo_patterns:
        if re.search(pattern, ref_text, re.IGNORECASE):
            _issue(
                issues,
                "filename_derived_reference",
                "review",
                "Publication reference list appears to contain filename-derived or metadata-poor references.",
                "Supply real bibliographic metadata for academic_paper references when possible.",
                pattern=pattern,
            )
            return


def _build_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Scholarly Quality Report",
        "",
        f"- Status: {report['status']}",
        f"- Report profile: {report['report_profile'] or 'unknown'}",
        f"- Issues: {report['issue_count']} ({report['hard_issue_count']} hard, {report['review_issue_count']} review)",
        "",
        "## Checks",
        "",
        "- Paper/lab spine: " + report["checks"]["spine"],
        "- Introduction: " + report["checks"]["introduction"],
        "- Methods: " + report["checks"]["methods"],
        "- Abstract/title: " + report["checks"]["abstract_title"],
        "- Figures/tables: " + report["checks"]["figures"],
        "- References: " + report["checks"]["references"],
        "",
    ]
    if report["issues"]:
        lines.extend(["## Issues", ""])
        for issue in report["issues"]:
            lines.append(f"- [{issue['severity']}] {issue['type']}: {issue['detail']}")
    else:
        lines.extend(["## Issues", "", "- None"])
    lines.append("")
    return "\n".join(lines)


def run_scholarly_quality(state: ReportState) -> ReportState:
    """Audit scholarly writing, methods, figures, and references.

    This node is intentionally review-grade in v1: it writes structured QA
    evidence but does not raise hard blocks. Existing factuality, citation,
    figure, and render gates remain the source of blocking publication safety.
    """
    profile = state.spec.get("report_profile", "")
    if profile not in {"academic_paper", "engineering_lab_report"}:
        report = {
            "job_id": state.job_id,
            "status": "skipped",
            "report_profile": profile,
            "issue_count": 0,
            "hard_issue_count": 0,
            "review_issue_count": 0,
            "checks": {},
            "issues": [],
        }
        json_path = write_json_artifact(state, "scholarly_quality_report.json", report)
        md_path = run_dir_for(state) / "scholarly_quality_report.md"
        md_path.write_text("# Scholarly Quality Report\n\n- Status: skipped\n", encoding="utf-8")
        state.qa["scholarly_quality_report_path"] = json_path
        state.qa["scholarly_quality_report_md_path"] = str(md_path)
        state.output["scholarly_quality_report_path"] = json_path
        state.output["scholarly_quality_report_md_path"] = str(md_path)
        return state

    sections = _section_texts(state)
    body = _body_text(state, sections)
    issues: list[dict[str, Any]] = []

    _check_spine(state, profile, issues)
    _check_introduction(profile, sections, issues)
    _check_methods(profile, sections, issues)
    _check_abstract_and_title(state, profile, sections, issues)
    _check_language_rules(profile, body, issues)
    _check_figures(state, body, issues)
    _check_references(state, profile, issues)

    hard_count = len([issue for issue in issues if issue.get("severity") == "hard"])
    review_count = len([issue for issue in issues if issue.get("severity") != "hard"])
    status = "passed" if not issues else ("failed" if hard_count else "review")

    issue_types = {issue["type"] for issue in issues}
    checks = {
        "spine": "review" if {
            "paper_spine_missing",
            "paper_spine_incomplete",
            "paper_spine_template_text",
            "lab_spine_missing",
            "lab_spine_incomplete",
            "lab_spine_template_text",
        } & issue_types else "pass",
        "introduction": "review" if {"introduction_missing", "introduction_spine_weak"} & issue_types else "pass",
        "methods": "review" if {"methods_missing", "methods_reproducibility_weak", "methods_contains_findings"} & issue_types else "pass",
        "abstract_title": "review" if {"abstract_reads_like_outline", "title_precision_review"} & issue_types else "pass",
        "figures": "review" if any(issue.get("type", "").startswith("figure_") or issue.get("type", "").startswith("error_bar") for issue in issues) else "pass",
        "references": "review" if {"filename_derived_reference"} & issue_types else "pass",
    }

    report = {
        "job_id": state.job_id,
        "status": status,
        "report_profile": profile,
        "issue_count": len(issues),
        "hard_issue_count": hard_count,
        "review_issue_count": review_count,
        "checks": checks,
        "issues": issues,
        "contract": {
            "blocking_behavior": "review_grade_v1",
            "public_selector": "report_profile",
        },
    }
    json_path = write_json_artifact(state, "scholarly_quality_report.json", report)
    md_path = run_dir_for(state) / "scholarly_quality_report.md"
    md_path.write_text(_build_markdown_report(report), encoding="utf-8")
    state.qa["scholarly_quality_report_path"] = json_path
    state.qa["scholarly_quality_report_md_path"] = str(md_path)
    state.output["scholarly_quality_report_path"] = json_path
    state.output["scholarly_quality_report_md_path"] = str(md_path)
    return state
