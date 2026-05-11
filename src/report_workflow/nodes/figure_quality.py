"""FIGURE_QUALITY node - consolidated figure quality and contract checking.

Consolidates:
  - figure_build.py: generates figures from figure_plan.json (kept separate, matplotlib generation)
  - caption_interpreter.py: interprets figure captions (absorbed into this node)
  - figure_contract_check.py: validates figure usage contract (absorbed into this node)

Position: After MERGE_DRAFT, before QA_GATE.

Figure planning should happen BEFORE drafting (via figure_plan.json in section_drafts/),
not as an afterthought. This node validates the figure quality after drafting.

Academic report-specific rules:
  - Internal audit tables (Claim-Evidence Matrix, Community-to-Contribution) should
    NOT appear in the main publication text; they belong in supplementary materials.
    This node CHECKS that these tables are NOT in the main text.
  - Figure captions and in-text references are validated.
"""
import json
import logging
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, run_dir_for
from ..runtime_support import write_json_artifact
from ..policies import get_policy


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Pattern: [FIGURE:id] or [FIGURE:id caption text], matching DOCX_RENDER.
_FIGURE_PLACEHOLDER_RE = re.compile(r"\[FIGURE:\s*([^\]\s]+)(?:\s+([^\]]+))?\]", re.IGNORECASE)

# Pattern: prose reference to a figure, e.g. "see figure 1", "figure 2 shows".
_FIGURE_PROSE_RE = re.compile(
    r"\b(?:see\s+figure\s+|figure\s+)([a-z]|\d+|[a-z0-9_.-]*[\d_.-][a-z0-9_.-]*)\b(?!\s*:)",
    re.IGNORECASE,
)

# Pattern: caption start, e.g. "Figure 1:" or "[Figure 1]" at start of line/sentence.
_FIGURE_CAPTION_RE = re.compile(
    r"(?:^|(?<=\n))(\[?Figure\s+([a-z]|\d+|[a-z0-9_.-]*[\d_.-][a-z0-9_.-]*)\]?:?\s+)",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_figure_placeholders(text: str) -> set[str]:
    return {m.group(1).lower() for m in _FIGURE_PLACEHOLDER_RE.finditer(text)}


def _extract_prose_refs(text: str) -> set[str]:
    return {m.group(1).lower() for m in _FIGURE_PROSE_RE.finditer(text)}


def _extract_captions(text: str) -> set[str]:
    return {m.group(2).lower() for m in _FIGURE_CAPTION_RE.finditer(text)}


def _extract_known_prose_refs(text: str, known_ids: set[str]) -> set[str]:
    refs = _extract_prose_refs(text)
    for figure_id in known_ids:
        if not figure_id:
            continue
        pattern = re.compile(
            rf"\b(?:see\s+figure\s+|figure\s+){re.escape(figure_id)}\b(?!\s*:)",
            re.IGNORECASE,
        )
        if pattern.search(text):
            refs.add(figure_id.lower())
    return refs


def _extract_known_captions(text: str, known_ids: set[str]) -> set[str]:
    captions = _extract_captions(text)
    for figure_id in known_ids:
        if not figure_id:
            continue
        pattern = re.compile(
            rf"(?:^|(?<=\n))\[?Figure\s+{re.escape(figure_id)}\]?:?\s+",
            re.IGNORECASE | re.MULTILINE,
        )
        if pattern.search(text):
            captions.add(figure_id.lower())
    return captions


def _read_json_object(path: str | Path | None) -> dict:
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


def _planned_figures(state: ReportState) -> list[dict]:
    plan_path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
    payload = _read_json_object(plan_path)
    figures = payload.get("figures", [])
    return [figure for figure in figures if isinstance(figure, dict)]


def _recommendation_keys(recommendations: list[dict]) -> tuple[set[str], set[str]]:
    recommendation_ids = {
        str(rec.get("recommendation_id"))
        for rec in recommendations
        if isinstance(rec, dict) and rec.get("recommendation_id")
    }
    evidence_ids: set[str] = set()
    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        for evidence_id in rec.get("evidence_ids", []) or []:
            if evidence_id:
                evidence_ids.add(str(evidence_id))
    return recommendation_ids, evidence_ids


def _figure_evidence_ids(figure: dict) -> set[str]:
    values: set[str] = set()
    for key in ("source_evidence_id", "evidence_id"):
        raw = figure.get(key)
        if raw:
            values.add(str(raw))
    for key in ("source_evidence_ids", "evidence_ids"):
        raw_list = figure.get(key) or []
        if isinstance(raw_list, list):
            values.update(str(item) for item in raw_list if item)
    return values


def _is_recommendation_backed_figure(figure: dict, recommendation_ids: set[str], evidence_ids: set[str]) -> bool:
    recommendation_id = str(figure.get("recommendation_id") or "")
    if recommendation_id and recommendation_id in recommendation_ids:
        return True
    return bool(_figure_evidence_ids(figure) & evidence_ids)


def _body_mentions_figure_id(merged_text: str, figure_id: str) -> bool:
    if not figure_id:
        return False
    normalized = figure_id.lower()
    if normalized in _extract_figure_placeholders(merged_text):
        return True
    pattern = re.compile(
        rf"\b(?:see\s+figure\s+|figure\s+){re.escape(figure_id)}\b(?!\s*:)",
        re.IGNORECASE,
    )
    return bool(pattern.search(merged_text))


def _figure_recommendations_payload(state: ReportState) -> dict:
    output_path = state.output.get("figure_recommendations_path", "")
    payload = _read_json_object(output_path)
    if payload:
        return payload
    return _read_json_object(run_dir_for(state) / "figure_recommendations.json")


def _check_planned_figure_usage(
    state: ReportState,
    merged_text: str,
    outline_figure_ids: list[str],
) -> list[dict]:
    recommendations_payload = _figure_recommendations_payload(state)
    recommendations = [
        rec for rec in recommendations_payload.get("recommendations", [])
        if isinstance(rec, dict)
    ]
    if not recommendations:
        return []

    figures = _planned_figures(state)
    if not figures:
        return []

    recommendation_ids, evidence_ids = _recommendation_keys(recommendations)
    outline_ids = {str(fid).lower() for fid in outline_figure_ids}
    recommendation_backed_figures = [
        figure
        for figure in figures
        if _is_recommendation_backed_figure(figure, recommendation_ids, evidence_ids)
    ]

    unused: list[dict] = []
    for index, figure in enumerate(recommendation_backed_figures):
        figure_id = str(figure.get("figure_id") or f"index_{index}").strip()
        if not figure_id:
            continue
        normalized = figure_id.lower()
        if normalized in outline_ids or _body_mentions_figure_id(merged_text, figure_id):
            continue
        unused.append({
            "type": "planned_figure_not_used",
            "severity": "warning",
            "figure_id": figure_id,
            "recommendation_id": figure.get("recommendation_id", ""),
            "section_id": figure.get("section_id", ""),
            "detail": (
                f"Figure '{figure_id}' is present in figure_plan.json but is not listed in "
                "outline figure_ids and is not referenced in the draft body."
            ),
            "repair_hint": (
                f"Add '{figure_id}' to the target section figure_ids and place "
                f"[FIGURE:{figure_id}] where the cited evidence is discussed, or remove the planned figure."
            ),
        })

    if unused and len(unused) == len(recommendation_backed_figures):
        unused.append({
            "type": "recommended_figure_plan_unused",
            "severity": "warning",
            "figure_ids": [issue["figure_id"] for issue in unused if issue.get("type") == "planned_figure_not_used"],
            "detail": "All recommendation-backed figures in figure_plan.json are unused by outline and draft body.",
            "repair_hint": "Use the recommended figures in the outline/draft or remove the unused figure plans.",
        })
    return unused


# ------------------------------------------------------------------
# Academic mode: check that internal audit tables are NOT in main text
# These belong in supplementary, not in the publication body
# ------------------------------------------------------------------

_AUDIT_TABLE_PATTERNS = [
    (r"\|?\s*Claim\s+ID\s*\|", "claim_id_table"),
    (r"\|?\s*Evidence\s+ID\s*\|", "evidence_id_table"),
    (r"\|?\s*Claim\s+-\s+Evidence", "claim_evidence_matrix"),
    (r"Community.*Contribution\s+Mapping", "community_contribution_table"),
    (r"\|?\s*Status\s*\|", "status_column"),
    (r"Evidence\s+IDs.*Claim", "evidence_claim_table"),
]


def _check_no_audit_tables_in_main_text(merged_text: str, report_profile: str) -> list[dict]:
    """Check that internal audit tables are NOT in main text.

    Returns hard issues if audit tables are FOUND in main text.
    """
    issues = []

    policy = get_policy(report_profile)
    if not policy.figure.audit_table_hard_block:
        return issues

    for pattern, table_type in _AUDIT_TABLE_PATTERNS:
        if re.search(pattern, merged_text, re.IGNORECASE):
            issues.append({
                "type": "audit_table_in_main_text",
                "severity": "hard",
                "table_type": table_type,
                "detail": (
                    f"Internal audit table ({table_type}) found in main publication text. "
                    "These tables belong in supplementary materials. "
                    "Remove from main text or move to supplementary."
                ),
            })

    return issues


def _check_figure_contract(
    merged_text: str,
    outline_figure_ids: list[str],
    hard_contract: bool = False,
) -> list[dict]:
    """Check figure contract and return list of issues."""
    issues = []

    placeholders = _extract_figure_placeholders(merged_text)
    outline_ids = {str(fid).lower() for fid in outline_figure_ids}
    prose_refs = _extract_known_prose_refs(merged_text, placeholders | outline_ids)
    captions = _extract_known_captions(merged_text, placeholders | outline_ids)
    all_fig_ids = placeholders | outline_ids
    issue_severity = "hard" if hard_contract else "soft"

    for fig_id in sorted(prose_refs - all_fig_ids):
        issues.append({
            "figure_id": fig_id,
            "issues": [{
                "type": "undeclared_prose_reference",
                "severity": issue_severity,
                "detail": (
                    f"Figure '{fig_id}' is mentioned in prose but is not declared "
                    "in outline figure_ids or as a [FIGURE:<id>] placeholder"
                ),
            }],
        })

    for fig_id in sorted(all_fig_ids):
        issues_dict: dict = {"figure_id": fig_id, "issues": []}

        # Check 1: placeholder exists for figures in outline
        if outline_ids and fig_id not in placeholders and fig_id in outline_ids:
            issues_dict["issues"].append({
                "type": "missing_placeholder",
                "severity": issue_severity,
                "detail": f"Figure '{fig_id}' is in outline but has no [FIGURE:{fig_id}] placeholder",
            })

        # Check 2: prose reference exists
        if fig_id not in prose_refs:
            issues_dict["issues"].append({
                "type": "missing_prose_reference",
                "severity": issue_severity,
                "detail": f"Figure '{fig_id}' is referenced but not mentioned in prose (e.g. 'see Figure {fig_id}')",
            })

        # Check 3: caption exists
        if fig_id not in captions:
            issues_dict["issues"].append({
                "type": "missing_caption",
                "severity": issue_severity,
                "detail": f"Figure '{fig_id}' has no caption ('Figure {fig_id}: ...' or similar)",
            })

        if issues_dict["issues"]:
            issues.append(issues_dict)

    return issues


def run_figure_quality(state: ReportState) -> ReportState:
    """FIGURE_QUALITY - consolidated figure quality and contract checking.

    Combines:
      - Caption interpretation (from caption_interpreter)
      - Figure contract validation (from figure_contract_check)
      - Audit table detection (prevents internal tables in main text)

    Reads:
      - state.drafts["merged_draft_md"] (publication draft)
      - state.plan["outline"] (figure_ids from outline)

    Writes:
      - figure_quality_report.json

    Academic mode hard blocks if:
      - Internal audit tables (Claim-Evidence Matrix, etc.) are found in main text
      - These tables should only be in supplementary materials
    """
    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        state.qa["figure_quality_report_path"] = ""
        return state

    merged_text = Path(merged_path).read_text(encoding="utf-8")
    report_profile = state.spec.get("report_profile", "")
    policy = get_policy(report_profile)

    # Collect figure_ids from outline
    outline = state.plan.get("outline", {})
    outline_figure_ids: list[str] = []
    for section in outline.get("sections", {}).values():
        fid_list = section.get("figure_ids", [])
        if isinstance(fid_list, list):
            outline_figure_ids.extend(fid_list)

    all_issues = []

    # 1. Check that internal audit tables are NOT in main text (academic mode)
    audit_issues = _check_no_audit_tables_in_main_text(merged_text, report_profile)
    if audit_issues:
        all_issues.extend(audit_issues)

    # 2. Figure contract checks (placeholder, prose reference, caption)
    contract_issues = _check_figure_contract(
        merged_text,
        outline_figure_ids,
        hard_contract=policy.figure.figure_contract_required,
    )
    if contract_issues:
        all_issues.extend(contract_issues)

    # 3. Warning-only usage lint: planned recommendation-backed figures should
    # either enter the outline or be referenced by the draft body.
    usage_issues = _check_planned_figure_usage(state, merged_text, outline_figure_ids)
    if usage_issues:
        all_issues.extend(usage_issues)

    # 4. Figure manifest reality check: outline declared figures but no manifest
    # means figure_plan.json was missing/malformed or matplotlib skipped them.
    # For academic_paper (where figures are load-bearing), this is a hard fail
    # per the user's directive: never ship a silently-missing-figure doc.
    if outline_figure_ids and policy.figure.audit_table_hard_block:
        manifest_path = state.output.get("figure_manifest_path", "")
        manifest_generated = 0
        manifest_errors: list[str] = []
        if manifest_path and Path(manifest_path).exists():
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest_generated = int(manifest.get("generated_count", 0) or 0)
                manifest_errors = list(manifest.get("errors", []) or [])
            except Exception as exc:
                manifest_errors = [f"manifest parse error: {exc}"]
        if manifest_generated < len(outline_figure_ids):
            all_issues.append({
                "type": "figure_manifest_shortfall",
                "severity": "hard",
                "detail": (
                    f"Outline declares {len(outline_figure_ids)} figure(s) "
                    f"but figure manifest generated only {manifest_generated}. "
                    f"Errors: {manifest_errors[:3] if manifest_errors else 'no manifest / empty'}. "
                    "Either remove figures from outline or fix figure_plan.json."
                ),
            })

    # Collect hard issues
    hard_issues = []
    for i in all_issues:
        if "issues" in i:
            # Nested format
            if any(j.get("severity") == "hard" for j in i.get("issues", [])):
                hard_issues.append(i)
        elif i.get("severity") == "hard":
            # Flat format
            hard_issues.append(i)

    report = {
        "job_id": state.job_id,
        "figures_in_outline": outline_figure_ids,
        "placeholder_count": len(_extract_figure_placeholders(merged_text)),
        "caption_count": len(_extract_captions(merged_text)),
        "prose_reference_count": len(_extract_prose_refs(merged_text)),
        "issues": all_issues,
        "total_issues": sum(
            len(i.get("issues", [])) if "issues" in i else 1
            for i in all_issues
        ),
        "hard_issues": hard_issues,
        "status": "passed" if not hard_issues else "failed",
    }
    report_path = write_json_artifact(state, "figure_quality_report.json", report)
    state.qa["figure_quality_report_path"] = str(report_path)

    # Hard block if audit tables in main text (per policy)
    if policy.figure.audit_table_hard_block and hard_issues:
        hard_details = [f"[{h.get('type')}] {h.get('detail', '')}" for h in hard_issues[:3]]
        raise QAHardBlockError(
            f"FIGURE_QUALITY: {len(hard_issues)} hard issue(s): {'; '.join(hard_details)}"
        )

    return state
