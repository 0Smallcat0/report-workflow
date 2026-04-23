"""HEADING_CONTRACT_CHECK - normalize and verify publication heading structure."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def _norm(text: str) -> str:
    text = _NUMBERED_RE.sub("", text).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _section_id_for_heading(text: str, sections: dict) -> str:
    normalized = _norm(text)
    aliases = {
        "research_scope": "research_scope",
        "research_scope_and_design_framing": "research_scope",
        "scope": "research_scope",
        "design_framing": "research_scope",
        "findings": "results",
        "methodology": "methods",
        "conclusions": "conclusion",
        "bibliography": "references",
    }
    if normalized in sections:
        return normalized
    return aliases.get(normalized, normalized)


def _canonical_heading(section_id: str, title: str, ordinal: int | None) -> str:
    if section_id == "abstract":
        return "# Abstract"
    if section_id == "references":
        return "## References"
    if ordinal is None:
        return f"# {title}"
    return f"# {ordinal}. {title}"


def normalize_heading_contract(markdown: str, blueprint: dict) -> tuple[str, list[str]]:
    """Return markdown with canonical top-level section headings."""
    sections = blueprint.get("sections", {}) or {}
    section_order = blueprint.get("section_order", []) or []
    ordinal_by_sid: dict[str, int] = {}
    ordinal = 1
    for sid in section_order:
        if sid in {"abstract", "references"}:
            continue
        ordinal_by_sid[sid] = ordinal
        ordinal += 1

    seen: set[str] = set()
    issues: list[str] = []

    def replace(match: re.Match) -> str:
        hashes, heading = match.group(1), match.group(2).strip()
        sid = _section_id_for_heading(heading, sections)
        is_wrapper_level = len(hashes) == 1 or (sid == "references" and len(hashes) <= 2)
        if is_wrapper_level and sid in sections:
            seen.add(sid)
            title = sections[sid].get("title", sid.replace("_", " ").title())
            return _canonical_heading(sid, title, ordinal_by_sid.get(sid))
        return match.group(0)

    normalized = _HEADING_RE.sub(replace, markdown)

    required = [
        sid for sid in section_order
        if sections.get(sid, {}).get("required", False)
    ]
    for sid in required:
        if sid not in seen:
            issues.append(f"Missing required top-level section heading: {sid}")

    # Catch subsection leakage: 3.1 Methods detail without # 3. Methods.
    for sid, ord_value in ordinal_by_sid.items():
        title = sections.get(sid, {}).get("title", sid.replace("_", " ").title())
        wrapper = _canonical_heading(sid, title, ord_value)
        if re.search(rf"^#{2,6}\s+{ord_value}\.\d+\s+", normalized, re.MULTILINE) and wrapper not in normalized:
            issues.append(f"Subsections for section {ord_value} exist but wrapper heading is missing: {title}")

    return normalized, issues


def run_heading_contract_check(state: ReportState) -> ReportState:
    """Normalize heading labels and hard-block incomplete section wrappers."""
    draft_path = state.drafts.get("publication_style_draft") or state.drafts.get("merged_draft_cited_md")
    if not draft_path or not Path(draft_path).exists():
        state.runtime["heading_contract_report_path"] = ""
        return state

    markdown = Path(draft_path).read_text(encoding="utf-8")
    normalized, issues = normalize_heading_contract(markdown, state.plan.get("blueprint") or {})

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    normalized_path = run_dir / "heading_contract_draft.md"
    normalized_path.write_text(normalized, encoding="utf-8")
    state.drafts["publication_style_draft"] = str(normalized_path)

    report = {
        "job_id": state.job_id,
        "issues": issues,
        "status": "passed" if not issues else "failed",
        "output_path": str(normalized_path),
    }
    state.runtime["heading_contract_report_path"] = write_json_artifact(state, "heading_contract_report.json", report)

    if issues:
        raise QAHardBlockError("HEADING_CONTRACT_CHECK: " + "; ".join(issues))
    return state
