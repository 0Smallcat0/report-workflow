"""HEADING_CONTRACT_CHECK - normalize and verify publication heading structure."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..language import (
    ZH_ORDINAL_PREFIX_RE,
    derived_section_title,
    detect_document_language,
    localized_section_title,
)
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def _norm(text: str) -> str:
    """Normalize a heading for section-id matching, preserving CJK.

    Stripping to ``[a-z0-9]`` collapsed every Chinese heading to an empty
    slug, so Chinese documents failed the required-section check even when
    every canonical heading was present.
    """
    text = _NUMBERED_RE.sub("", text.strip())
    text = ZH_ORDINAL_PREFIX_RE.sub("", text).strip().lower()
    return re.sub(r"[^a-z0-9一-鿿㐀-䶿]+", "_", text).strip("_")


def _blueprint_title_map(sections: dict) -> dict[str, str]:
    """Map normalized blueprint titles (en, zh, derived) to section ids."""
    title_map: dict[str, str] = {}
    for sid, section in (sections or {}).items():
        section = section or {}
        for candidate in (section.get("title"), section.get("title_zh"), derived_section_title(sid)):
            normalized = _norm(str(candidate)) if candidate else ""
            if normalized:
                title_map.setdefault(normalized, sid)
    return title_map


def _section_id_for_heading(text: str, sections: dict, title_map: dict[str, str]) -> str:
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
    if normalized in title_map:
        return title_map[normalized]
    return aliases.get(normalized, normalized)


def _canonical_heading(section_id: str, title: str, ordinal: int | None) -> str:
    # Abstract/References stay unnumbered but follow the document language:
    # the caller passes the localized blueprint title ("Abstract"/"摘要"),
    # so English documents render byte-identically.
    if section_id == "abstract":
        return f"# {title}"
    if section_id == "references":
        return f"## {title}"
    if ordinal is None:
        return f"# {title}"
    return f"# {ordinal}. {title}"


def normalize_heading_contract(markdown: str, blueprint: dict) -> tuple[str, list[str]]:
    """Return markdown with canonical top-level section headings."""
    sections = blueprint.get("sections", {}) or {}
    section_order = blueprint.get("section_order", []) or []
    language = detect_document_language(markdown)
    title_map = _blueprint_title_map(sections)
    ordinal_by_sid: dict[str, int] = {}
    ordinal = 1
    for sid in section_order:
        # Abstract/References stay unnumbered by convention; the cover is a
        # title page, not a numbered body section — the renderer promotes it
        # to a centered cover block, so numbering starts at the first real
        # section.
        if sid in {"abstract", "references", "cover"}:
            continue
        ordinal_by_sid[sid] = ordinal
        ordinal += 1

    seen: set[str] = set()
    issues: list[str] = []

    def replace(match: re.Match) -> str:
        hashes, heading = match.group(1), match.group(2).strip()
        sid = _section_id_for_heading(heading, sections, title_map)
        is_wrapper_level = len(hashes) == 1 or (sid == "references" and len(hashes) <= 2)
        if is_wrapper_level and sid in sections:
            seen.add(sid)
            title = localized_section_title(sections[sid], sid, language)
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
        title = localized_section_title(sections.get(sid), sid, language)
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

    # A revised document keeps the base document's own heading structure; the
    # new-draft blueprint contract does not apply. Record findings as advisory
    # instead of hard-blocking.
    revise_mode = state.spec.get("task_intent") == "revise_existing"

    report = {
        "job_id": state.job_id,
        "issues": issues,
        "status": "passed" if not issues else ("advisory" if revise_mode else "failed"),
        "output_path": str(normalized_path),
    }
    state.runtime["heading_contract_report_path"] = write_json_artifact(state, "heading_contract_report.json", report)

    if issues and not revise_mode:
        raise QAHardBlockError("HEADING_CONTRACT_CHECK: " + "; ".join(issues))
    return state
