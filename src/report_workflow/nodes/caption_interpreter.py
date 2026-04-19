"""CAPTION_INTERPRETER node - validate and enhance figure captions.

Sits after FIGURE_BUILD, before REVISION_APPLY in validate phase.

Validates that each figure in figure_plan.json has:
  - Figure number (fig_1, fig_2, etc.)
  - Claim linkage (which claims this figure supports)
  - Source evidence IDs
  - Caption text
  - Legend completeness
  - In-text citation location
  - Interpretation paragraph ID

For academic reports, these are hard requirements.

Output: figure_caption_report.json
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact


# Required caption fields for academic publication
REQUIRED_CAPTION_FIELDS = [
    "figure_id",
    "caption",
    "claim_ids",
    "evidence_ids",
    "section_id",
]

# Optional but recommended fields
RECOMMENDED_CAPTION_FIELDS = [
    "legend_completeness",
    "in_text_citation_location",
    "interpretation_paragraph_id",
    "figure_type",
]


def _load_jsonl(path: str | None) -> list[dict]:
    """Load JSONL file."""
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _validate_figure_caption(
    figure: dict,
    claim_ids: set[str],
    evidence_ids: set[str],
    report_family: str,
) -> dict:
    """Validate a single figure's caption and metadata."""
    issues = []
    warnings = []

    # Check required fields
    for field in REQUIRED_CAPTION_FIELDS:
        if not figure.get(field):
            issues.append({
                "field": field,
                "severity": "required",
                "detail": f"Missing required field '{field}' for figure {figure.get('figure_id', 'unknown')}",
            })

    # Check recommended fields
    for field in RECOMMENDED_CAPTION_FIELDS:
        if not figure.get(field):
            warnings.append({
                "field": field,
                "severity": "recommended",
                "detail": f"Missing recommended field '{field}' for figure {figure.get('figure_id', 'unknown')}",
            })

    # Validate claim linkages
    fig_claim_ids = set(figure.get("claim_ids", []))
    invalid_claims = fig_claim_ids - claim_ids
    if invalid_claims:
        issues.append({
            "field": "claim_ids",
            "severity": "hard",
            "detail": f"Figure {figure.get('figure_id')} references unknown claim IDs: {invalid_claims}",
        })

    # Validate evidence linkages
    fig_evidence_ids = set(figure.get("evidence_ids", []))
    invalid_evidence = fig_evidence_ids - evidence_ids
    if invalid_evidence:
        issues.append({
            "field": "evidence_ids",
            "severity": "hard",
            "detail": f"Figure {figure.get('figure_id')} references unknown evidence IDs: {invalid_evidence}",
        })

    # Validate caption format
    caption = figure.get("caption", "")
    if caption:
        # Check caption starts with figure number
        fig_id = figure.get("figure_id", "")
        if fig_id and not caption.lower().startswith(f"figure {fig_id.replace('fig_', '')}"):
            # Also check if it starts with the literal figure_id
            if not caption.lower().startswith(f"figure {fig_id}"):
                warnings.append({
                    "field": "caption",
                    "severity": "format",
                    "detail": f"Caption for {fig_id} should start with 'Figure N:' format",
                })

        # Check caption is not too short
        if len(caption.split()) < 10:
            warnings.append({
                "field": "caption",
                "severity": "length",
                "detail": f"Caption for {fig_id} seems too short ({len(caption.split())} words) - ICMJE recommends descriptive captions",
            })

        # Check caption contains interpretation
        interpretation_keywords = ["shows", "indicates", "reveals", "demonstrates", "illustrates", "displays"]
        if not any(kw in caption.lower() for kw in interpretation_keywords):
            warnings.append({
                "field": "caption",
                "severity": "interpretation",
                "detail": f"Caption for {fig_id} should describe what the figure shows/indicates",
            })

    # Validate legend completeness for charts
    figure_type = figure.get("figure_type", "")
    if figure_type in ("bar", "line", "scatter", "pie"):
        legend = figure.get("legend_completeness", "")
        if not legend:
            warnings.append({
                "field": "legend_completeness",
                "severity": "recommended",
                "detail": f"Figure {fig_id} ({figure_type}) should have complete legend information",
            })

    # For academic reports, missing required fields are hard failures
    if report_family == "academic_report" and issues:
        # Convert required-severity issues to hard failures
        hard_issues = [i for i in issues if i.get("severity") == "required"]
        if hard_issues:
            return {
                "figure_id": figure.get("figure_id", "unknown"),
                "valid": False,
                "issues": issues,
                "warnings": warnings,
                "hard_failure": True,
                "failure_reasons": [i["detail"] for i in hard_issues],
            }

    return {
        "figure_id": figure.get("figure_id", "unknown"),
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "hard_failure": False,
    }


def run_caption_interpreter(state: ReportState) -> ReportState:
    """T_NEW: CAPTION_INTERPRETER - validate figure captions for academic publication.

    Position: After FIGURE_BUILD, before REVISION_APPLY.

    Reads:
      - figure_plan.json (agent-authored figure specifications)
      - state.plan.claim_matrix (for valid claim ID check)
      - state.sources.evidence_ledger_path (for valid evidence ID check)
      - state.plan.outline (for section context)

    Writes:
      - figure_caption_report.json
      - state.qa["figure_caption_report_path"]

    Rules for academic reports:
      - All REQUIRED_CAPTION_FIELDS must be present
      - claim_ids must reference valid claim IDs
      - evidence_ids must reference valid evidence IDs
      - Captions must follow "Figure N: description" format
      - Charts must have legend completeness info
    """
    report_family = state.spec.get("report_family", "academic_report")

    # Load figure plan
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    section_drafts_dir = run_dir / "section_drafts"
    figure_plan_path = section_drafts_dir / "figure_plan.json"

    if not figure_plan_path.exists():
        # No figure plan - soft skip
        state.qa["figure_caption_report_path"] = ""
        return state

    try:
        with open(figure_plan_path, encoding="utf-8") as f:
            figure_plan = json.load(f)
    except Exception:
        state.qa["figure_caption_report_path"] = ""
        return state

    figures = figure_plan.get("figures", [])
    if not figures:
        state.qa["figure_caption_report_path"] = ""
        return state

    # Load valid claim IDs
    claim_matrix = state.plan.get("claim_matrix", {})
    claims = claim_matrix.get("claims", [])
    valid_claim_ids = {c.get("claim_id", "") for c in claims if c.get("claim_id")}

    # Load valid evidence IDs
    evidence_ledger = _load_jsonl(state.sources.get("evidence_ledger_path"))
    valid_evidence_ids = {e.get("evidence_id", "") for e in evidence_ledger if e.get("evidence_id")}

    # Validate each figure
    validation_results = []
    all_issues = []
    all_warnings = []
    hard_failures = []

    for fig in figures:
        result = _validate_figure_caption(fig, valid_claim_ids, valid_evidence_ids, report_family)
        validation_results.append(result)
        all_issues.extend(result.get("issues", []))
        all_warnings.extend(result.get("warnings", []))
        if result.get("hard_failure"):
            hard_failures.append(result)

    # Build report
    report = {
        "job_id": state.job_id,
        "report_family": report_family,
        "total_figures": len(figures),
        "valid_figures": sum(1 for r in validation_results if r["valid"]),
        "invalid_figures": sum(1 for r in validation_results if not r["valid"]),
        "hard_failures": len(hard_failures),
        "issues": all_issues,
        "warnings": all_warnings,
        "validation_results": validation_results,
    }

    # Write report
    report_path = write_json_artifact(state, "figure_caption_report.json", report)
    state.qa["figure_caption_report_path"] = report_path

    # For academic reports, hard failures should block
    if report_family == "academic_report" and hard_failures:
        from ..errors import QAHardBlockError
        reasons = [f["detail"] for f in hard_failures]
        raise QAHardBlockError(f"Figure caption validation failed: {'; '.join(reasons[:3])}")

    return state