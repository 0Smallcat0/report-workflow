"""WAIVER_GOVERNANCE node - decide which QA failures to waive vs patch.

Phase 3: Reads QA reports from Phase 2, applies waiver policy, produces
an edit_manifest of patchable issues and a list of waived issues.
"""
import json
from pathlib import Path
from typing import Optional

from ..state import ReportState

# Severity thresholds: issue is "critical" if >= threshold
_SEVERITY_ORDER = ["low", "medium", "high", "critical"]

# Default severity mapping for consistency sub-checks
_CONSISTENCY_SEVERITY = {
    "numeric_contradiction": "critical",
    "value_range_violation": "high",
    "percentile_misalignment": "medium",
    "self_contradiction": "critical",
    "terminology_drift": "medium",
    "inconsistent_citation": "medium",
    "broken_crossref": "high",
    "missing_crossref_target": "high",
    "unit_mismatch": "medium",
    "compound_unit_confusion": "low",
    "claim_evidence_mismatch": "high",
    "overclaiming": "high",
    "underclaiming": "medium",
}

_STYLE_SEVERITY = {
    "passive_voice": "medium",
    "hedging": "low",
    "first_person": "low",
    "informal_tone": "low",
    "jargon": "medium",
    "acronym_without_expansion": "low",
    "sentence_length": "low",
    "paragraph_length": "low",
}

_GUIDELINE_SEVERITY = {
    "missing_required_section": "high",
    "missing_critical_element": "critical",
    "inconsistent_reporting": "medium",
    "unreported_item": "medium",
}


def _severity_rank(sev: str) -> int:
    try:
        return _SEVERITY_ORDER.index(sev)
    except ValueError:
        return 0  # treat unknown as low


def _default_policy() -> dict:
    """Default waiver policy when user hasn't configured one."""
    return {
        "numeric_contradiction": "never",        # critical → escalate
        "self_contradiction": "never",           # critical → escalate
        "broken_crossref": "patch",              # high → patch
        "missing_crossref_target": "patch",      # high → patch
        "claim_evidence_mismatch": "patch",      # high → patch
        "overclaiming": "patch",                 # high → patch
        "value_range_violation": "patch",        # high → patch
        "unit_mismatch": "patch",               # medium → patch
        "inconsistent_citation": "patch",       # medium → patch
        "terminology_drift": "patch",           # medium → patch
        "inconsistent_reporting": "waive",     # medium → waive
        "unreported_item": "patch",             # medium → patch
        "missing_required_section": "patch",   # high → patch
        "missing_critical_element": "never",   # critical → escalate
        "default": "waive",                    # everything else → waive
    }


def _load_json(path: Optional[str]) -> dict:
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_jsonl(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        with open(path) as f:
            return [json.loads(line) for line in f]
    except Exception:
        return []


def _extract_issues(consistency_report: dict) -> list:
    """Extract flat list of issues from consistency report sub-checks."""
    issues = []
    sub_checks = consistency_report.get("sub_checks", {})
    for check_name, check_data in sub_checks.items():
        if not isinstance(check_data, dict):
            continue
        issues_found = check_data.get("issues", [])
        for issue in issues_found:
            sev_key = issue.get("type", "")
            severity = _CONSISTENCY_SEVERITY.get(sev_key, "medium")
            issues.append({
                "layer": "consistency",
                "check": check_name,
                "type": sev_key,
                "severity": severity,
                "location": issue.get("location", ""),
                "description": issue.get("message", issue.get("description", "")),
            })
    return issues


def _extract_style_issues(style_report: dict) -> list:
    """Extract flat list of issues from style report."""
    issues = []
    for layer, layer_data in style_report.items():
        if not isinstance(layer_data, dict):
            continue
        for issue in layer_data.get("issues", []):
            sev_key = issue.get("type", "")
            severity = _STYLE_SEVERITY.get(sev_key, "low")
            issues.append({
                "layer": "style",
                "check": layer,
                "type": sev_key,
                "severity": severity,
                "location": issue.get("location", ""),
                "description": issue.get("message", ""),
            })
    return issues


def _extract_guideline_issues(guideline_report: dict) -> list:
    """Extract flat list of issues from guideline report."""
    issues = []
    checks = guideline_report.get("checks", guideline_report.get("summary", {}))
    if isinstance(checks, dict):
        for check_name, check_data in checks.items():
            if not isinstance(check_data, dict):
                continue
            for item in check_data.get("violations", check_data.get("issues", [])):
                sev_key = item.get("type", "")
                severity = _GUIDELINE_SEVERITY.get(sev_key, "medium")
                issues.append({
                    "layer": "guideline",
                    "check": check_name,
                    "type": sev_key,
                    "severity": severity,
                    "location": item.get("location", ""),
                    "description": item.get("description", item.get("message", "")),
                })
    return issues


def _decide(
    issue: dict,
    policy: dict,
    severity_threshold: str = "high",
) -> str:
    """Decide: patch | waive | escalate | skip."""
    issue_type = issue.get("type", "")
    severity = issue.get("severity", "medium")

    # Never waive critical issues unless explicitly configured
    if _severity_rank(severity) >= _severity_rank("critical"):
        return policy.get(issue_type, "escalate")

    # Check configured action for this issue type
    action = policy.get(issue_type, policy.get("default", "waive"))

    # Check severity threshold
    if _severity_rank(severity) >= _severity_rank(severity_threshold):
        return action

    return "skip"  # below threshold


def run_waiver_governance(state: ReportState) -> ReportState:
    """T23: WAIVER_GOVERNANCE - decide which QA failures to waive vs patch.

    Reads QA reports from Phase 2 (consistency, style, guideline).
    Applies user-configured waiver policy (or default).
    Emits:
        state.governance["waiver_log"]   - list of waiver decisions
        state.governance["edit_manifest"] - structured patch instructions for revision_apply
        state.governance["gate_override"] - bool, True if any "escalate" decision
    """
    policy = state.spec.get("waiver_policy") or _default_policy()
    severity_threshold = state.spec.get("waiver_severity_threshold", "high")

    consistency_report = _load_json(state.qa.get("consistency_report_path"))
    style_report = _load_json(state.qa.get("style_report_path"))
    guideline_report = _load_json(state.qa.get("guideline_report_path"))

    # Collect all issues
    all_issues: list[dict] = []
    all_issues.extend(_extract_issues(consistency_report))
    all_issues.extend(_extract_style_issues(style_report))
    all_issues.extend(_extract_guideline_issues(guideline_report))

    # Sort: critical first, then high, then medium, then low
    all_issues.sort(key=lambda x: -_severity_rank(x["severity"]))

    # Deduplicate by location + type
    seen = set()
    unique_issues = []
    for issue in all_issues:
        key = (issue.get("location", ""), issue.get("type", ""))
        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    waiver_log: list[dict] = []
    edit_manifest_items: list[dict] = []
    escalated: list[dict] = []

    for issue in unique_issues:
        decision = _decide(issue, policy, severity_threshold)

        log_entry = {
            "issue": issue,
            "decision": decision,
            "layer": issue.get("layer", ""),
        }
        waiver_log.append(log_entry)

        if decision == "patch":
            edit_manifest_items.append({
                "layer": issue.get("layer", ""),
                "type": issue.get("type", ""),
                "location": issue.get("location", ""),
                "description": issue.get("description", ""),
                "severity": issue.get("severity", ""),
            })
        elif decision == "escalate":
            escalated.append(issue)

    # Gate override: escalate means human must approve before final_publish
    gate_override = len(escalated) > 0

    state.governance["waiver_log"] = waiver_log
    state.governance["edit_manifest"] = edit_manifest_items
    state.governance["gate_override"] = gate_override
    state.governance["escalated_issues"] = escalated
    state.governance["patchable_count"] = len(edit_manifest_items)
    state.governance["waived_count"] = sum(
        1 for e in waiver_log if e["decision"] == "waive"
    )

    # Persist
    run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(run_dir / "waiver_log.json", "w") as f:
        _json.dump(waiver_log, f, indent=2, default=str)
    with open(run_dir / "edit_manifest.json", "w") as f:
        _json.dump(edit_manifest_items, f, indent=2, default=str)

    state.governance["waiver_log_path"] = str(run_dir / "waiver_log.json")
    state.governance["edit_manifest_path"] = str(run_dir / "edit_manifest.json")

    return state
