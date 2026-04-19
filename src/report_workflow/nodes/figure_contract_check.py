"""FIGURE_CONTRACT_CHECK node - verify figure contract integrity.

Sits between GUIDELINE_CHECK (or CONSISTENCY_CHECK) and QA_GATE.
Validates three aspects of figure usage in the report:

  1. [FIGURE:<id>] syntax presence: every placeholder in the draft has a
     matching entry in outline.figure_ids.
  2. Prose references: "see Figure N" / "Figure N shows" style citations
     appear for every figure.
  3. Caption presence: every figure has a caption (section or paragraph
     starting with "Figure N:" or "[FIGURE N]" style).

Output: figure_contract_report.json
Soft issues (missing prose reference) do NOT hard-fail.
Hard issues (placeholder with no caption) do NOT hard-fail (caption is agent's job).
Only unresolved severe mismatches (placeholder count ≠ caption count) warrant attention.
"""
import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Pattern: [FIGURE:id] or [FIGURE:id caption text]
_FIGURE_PLACEHOLDER_RE = re.compile(r"\[FIGURE:([^\]]+)\]", re.IGNORECASE)

# Pattern: prose reference to a figure — "see figure 1", "figure 2 shows", etc.
# Excludes "Figure N:" at start of caption (caption check is separate).
_FIGURE_PROSE_RE = re.compile(
    r"\b(?:see\s+figure\s+|figure\s+)(\d+|[a-z])\b(?!\s*:)",
    re.IGNORECASE,
)

# Pattern: caption start — "Figure 1:" or "[Figure 1]" at start of line/sentence
_FIGURE_CAPTION_RE = re.compile(
    r"(?:^|(?<=\n))(\[?Figure\s+(\d+|[a-z])\]?:?\s+)",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_figure_placeholders(text: str) -> set[str]:
    return {m.group(1).lower() for m in _FIGURE_PLACEHOLDER_RE.finditer(text)}


def _extract_prose_refs(text: str) -> set[str]:
    return {m.group(1).lower() for m in _FIGURE_PROSE_RE.finditer(text)}


def _extract_captions(text: str) -> set[str]:
    return {m.group(2).lower() for m in _FIGURE_CAPTION_RE.finditer(text)}


# ------------------------------------------------------------------
# Fix #10: academic_report figure/table hard requirements
# ------------------------------------------------------------------
# For academic_report, these tables are REQUIRED hard gates:
#   1. Graph metrics table  (nodes, edges, INFERRED%, avg confidence)
#   2. Community-to-contribution table
#   3. Claim-evidence matrix
# ------------------------------------------------------------------


def _check_academic_report_tables(
    merged_text: str,
    report_family: str,
) -> list[dict]:
    """Check academic_report-specific table requirements.

    Returns hard issues if required tables are missing.
    """
    import re

    issues = []

    if report_family != "academic_report":
        return issues

    # 1. Graph metrics table — look for table with node/edge counts and INFERRED%
    #    Expected patterns: "nodes", "edges", "INFERRED", "%"
    graph_table_pattern = re.compile(
        r"(?:^|\n)(?:Table|tbl|tbl\s+\d+)[^\n]*\n[^\n]*"
        r"(?:nodes?|edges?|vertices?)[^\n]*"
        r"(?:inferred|INFERRED)[^\n]*",
        re.IGNORECASE | re.MULTILINE,
    )
    # Simpler fallback: look for "nodes" + "edges" + "INFERRED" all within ~500 chars
    # of each other (rough table detection)
    near_match = re.compile(
        r"(?:nodes?|edges?)[^\n]{10,500}(?:inferred|INFERRED)",
        re.IGNORECASE,
    )

    has_graph_table = bool(
        graph_table_pattern.search(merged_text) or near_match.search(merged_text)
    )
    if not has_graph_table:
        issues.append({
            "type": "missing_graph_metrics_table",
            "severity": "hard",
            "detail": (
                "academic_report requires a graph metrics table "
                "(nodes, edges, INFERRED% / avg confidence)"
            ),
        })

    # 2. Community-to-contribution table — look for "community" near "contribution"
    community_contrib_pattern = re.compile(
        r"(?:community|module|component)[^\n]{5,200}(?:contribution|contrib)",
        re.IGNORECASE,
    )
    has_community_table = bool(community_contrib_pattern.search(merged_text))
    if not has_community_table:
        issues.append({
            "type": "missing_community_contribution_table",
            "severity": "hard",
            "detail": (
                "academic_report requires a community-to-contribution table "
                "(maps communities/modules to their architectural contributions)"
            ),
        })

    # 3. Claim-evidence matrix — look for "claim" near "evidence" in table context
    claim_evidence_pattern = re.compile(
        r"(?:claim|assertion)[^\n]{5,300}(?:evidence|evidence_id)",
        re.IGNORECASE,
    )
    has_claim_matrix_table = bool(claim_evidence_pattern.search(merged_text))
    if not has_claim_matrix_table:
        issues.append({
            "type": "missing_claim_evidence_matrix",
            "severity": "hard",
            "detail": (
                "academic_report requires a claim-evidence matrix table "
                "(claim IDs mapped to evidence IDs)"
            ),
        })

    return issues

def _check_figure_contract(
    merged_text: str,
    outline_figure_ids: list[str],
) -> list[dict]:
    """Check figure contract and return list of issues."""
    issues = []

    placeholders = _extract_figure_placeholders(merged_text)
    prose_refs = _extract_prose_refs(merged_text)
    captions = _extract_captions(merged_text)

    outline_ids = {str(fid).lower() for fid in outline_figure_ids}
    all_fig_ids = placeholders | outline_ids

    for fig_id in sorted(all_fig_ids):
        issues_dict: dict = {"figure_id": fig_id, "issues": []}

        # Check 1: placeholder exists for figures in outline
        if outline_ids and fig_id not in placeholders and fig_id in outline_ids:
            issues_dict["issues"].append({
                "type": "missing_placeholder",
                "severity": "soft",
                "detail": f"Figure '{fig_id}' is in outline but has no [FIGURE:{fig_id}] placeholder",
            })

        # Check 2: prose reference exists
        if fig_id not in prose_refs:
            issues_dict["issues"].append({
                "type": "missing_prose_reference",
                "severity": "soft",
                "detail": f"Figure '{fig_id}' is referenced but not mentioned in prose (e.g. 'see Figure {fig_id}')",
            })

        # Check 3: caption exists
        if fig_id not in captions:
            issues_dict["issues"].append({
                "type": "missing_caption",
                "severity": "soft",
                "detail": f"Figure '{fig_id}' has no caption ('Figure {fig_id}: ...' or similar)",
            })

        if issues_dict["issues"]:
            issues.append(issues_dict)

    return issues


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_figure_contract_check(state: ReportState) -> ReportState:
    """T15: FIGURE_CONTRACT_CHECK - validate figure usage contract.

    Reads merged_draft_md and outline.json.
    Writes figure_contract_report.json.
    Does NOT raise QAHardBlockError (soft issues only).
    """
    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        state.qa["figure_contract_report_path"] = ""
        return state

    merged_text = Path(merged_path).read_text(encoding="utf-8")

    # Collect figure_ids from outline
    outline = state.plan.get("outline", {})
    outline_figure_ids: list[str] = []
    for section in outline.get("sections", {}).values():
        fid_list = section.get("figure_ids", [])
        if isinstance(fid_list, list):
            outline_figure_ids.extend(fid_list)

    issues = _check_figure_contract(merged_text, outline_figure_ids)

    # Fix #10: Add academic_report table requirements
    report_family = state.spec.get("report_family", "")
    academic_table_issues = _check_academic_report_tables(merged_text, report_family)
    if academic_table_issues:
        issues.extend(academic_table_issues)

    # Determine hard issues (would warrant QA fail)
    # Collect both:
    #  (a) nested hard issues: items in issues[] that have an "issues" list with severity=hard
    #  (b) flat hard issues: items in issues[] that directly have severity=hard at root
    #     (returned by _check_academic_report_tables as flat dicts)
    hard_issues = []
    for i in issues:
        if "issues" in i:
            # Nested format (from _check_figure_contract)
            if any(j.get("severity") == "hard" for j in i.get("issues", [])):
                hard_issues.append(i)
        elif i.get("severity") == "hard":
            # Flat format (from _check_academic_report_tables)
            hard_issues.append(i)

    report = {
        "job_id": state.job_id,
        "figures_in_outline": outline_figure_ids,
        "placeholder_count": len(_extract_figure_placeholders(merged_text)),
        "caption_count": len(_extract_captions(merged_text)),
        "prose_reference_count": len(_extract_prose_refs(merged_text)),
        "issues": issues,
        "total_issues": sum(len(i.get("issues", [])) for i in issues),
        "hard_issues": hard_issues,
    }

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "figure_contract_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    state.qa["figure_contract_report_path"] = str(report_path)

    # Fix #10: academic_report hard table requirements → hard gate
    if report_family == "academic_report" and hard_issues:
        hard_details = [f"[{h.get('type')}] {h.get('detail')}" for h in hard_issues]
        raise QAHardBlockError(
            "figure/table contract violations (academic_report): " + "; ".join(hard_details)
        )

    return state
