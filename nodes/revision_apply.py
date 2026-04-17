"""REVISION_APPLY node - apply waiver-approved patches to merged draft.

Phase 3: Reads edit_manifest from waiver_governance, applies patchable issues
to merged_draft.md, writes revised draft for DOCX_RENDER.

Strategy:
  - Work on merged_draft.md (markdown source), NOT on rendered DOCX.
  - QA_GATE passes → FIGURE_TABLE_PLAN → WAIVER_GOVERNANCE → REVISION_APPLY → DOCX_RENDER.
  - In fresh_doc mode: patch merged_draft.md in-place.
  - In tracked_review mode: if base_doc exists, diff-based patch applied to merged_draft.md.
  - edit_manifest items with layer "consistency"/"style"/"guideline" and
    type + location (line number or paragraph marker) are applied.
  - Issues that cannot be auto-patched (e.g., ambiguous location, complex rewrite)
    are flagged in governance["unpatchable"] for human review.
"""
import json
import logging
import re
import hashlib
from pathlib import Path
from typing import Optional

from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)

# Manifest item types that can be auto-patched
_AUTO_PATCHABLE_TYPES = {
    # Numeric / terminology / crossref / citation
    "numeric_contradiction",
    "value_range_violation",
    "terminology_drift",
    "inconsistent_citation",
    "broken_crossref",
    "missing_crossref_target",
    "unit_mismatch",
    # Style
    "passive_voice",
    "first_person",
    "informal_tone",
    "jargon",
    "acronym_without_expansion",
    # Guideline
    "missing_required_section",
    "inconsistent_reporting",
    "unreported_item",
}

# Manifest item types that should NEVER be auto-patched
_NEVER_PATCH_TYPES = {
    "self_contradiction",
    "claim_evidence_mismatch",
    "overclaiming",
    "missing_critical_element",
}


def _load_manifest(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"[REVISION_APPLY] manifest not found: {path}")
        return []
    except json.JSONDecodeError as exc:
        logger.exception(f"[REVISION_APPLY] manifest JSON decode error: {exc}")
        return []
    except OSError as exc:
        logger.exception(f"[REVISION_APPLY] manifest read error: {exc}")
        return []


def _load_merged(path: Optional[str]) -> str:
    if not path:
        return ""
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"[REVISION_APPLY] merged draft not found: {path}")
        return ""
    except OSError as exc:
        logger.exception(f"[REVISION_APPLY] merged draft read error: {exc}")
        return ""


def _location_to_line_range(location: str, lines: list[str]) -> tuple[int, int]:
    """Parse location string to (start_line, end_line) 1-indexed.

    Accepts formats:
      "line 42"         -> (42, 42)
      "line 42-45"      -> (42, 45)
      "line 42:5"       -> (42, 46) [col 5]
      "para 3"          -> map paragraph to line range
      "section:intro"   -> find section header
    Falls back to (1, 1) if unparseable.
    """
    loc = location.strip()
    m = re.match(r"line\s+(\d+)(?[-:](\d+))?", loc, re.IGNORECASE)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        return max(1, start), max(start, end)

    m = re.match(r"para\s+(\d+)", loc, re.IGNORECASE)
    if m:
        para_idx = int(m.group(1)) - 1
        para_count = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith(">"):
                if para_count == para_idx:
                    start = i + 1
                    end = i + 1
                    while end < len(lines) and lines[end].strip() and not lines[end].startswith("#"):
                        end += 1
                    return start, end
                para_count += 1
        return 1, 1

    return 1, 1


def _patch_terminology_drift(lines: list[str], start: int, end: int, description: str) -> list[str]:
    """Patch terminology drift by replacing the drifted term with canonical form.

    description format: "Term 'X' should be 'Y'"
    """
    m = re.search(r"Term\s+'([^']+)'\s+should\s+be\s+'([^']+)'", description)
    if not m:
        return lines
    wrong, correct = m.group(1), m.group(2)
    # Replace wrong term (case-insensitive whole word) in line range
    pattern = re.compile(rf"\\b{re.escape(wrong)}\\b", re.IGNORECASE)
    patched = []
    for i, line in enumerate(lines):
        ln = i + 1
        if start <= ln <= end:
            line = pattern.sub(correct, line)
        patched.append(line)
    return patched


def _patch_passive_voice(lines: list[str], start: int, end: int) -> list[str]:
    """Attempt to rewrite passive voice to active.

    Very conservative: only handles common academic patterns.
    Returns unchanged lines if no clear fix.
    """
    passive_patterns = [
        (re.compile(r"\bwas\s+(\w+ed)\b"), r"\1"),
        (re.compile(r"\bwere\s+(\w+ed)\b"), r"\1"),
    ]
    patched = []
    changed = False
    for i, line in enumerate(lines):
        ln = i + 1
        if start <= ln <= end:
            for pat, repl in passive_patterns:
                new_line = pat.sub(repl, line)
                if new_line != line:
                    line = new_line
                    changed = True
        patched.append(line)
    return patched  # always return the (possibly unchanged) copy


def _patch_unit_mismatch(lines: list[str], start: int, end: int, description: str) -> list[str]:
    """Patch unit mismatch. description format: "Expected 'X' found 'Y'." """
    m = re.search(r"Expected\s+'([^']+)'\s+found\s+'([^']+)'", description)
    if not m:
        return lines
    expected, found = m.group(1), m.group(2)
    pattern = re.compile(rf"\\b{re.escape(found)}\\b", re.IGNORECASE)
    patched = []
    for i, line in enumerate(lines):
        ln = i + 1
        if start <= ln <= end:
            line = pattern.sub(expected, line)
        patched.append(line)
    return patched


def _patch_broken_crossref(lines: list[str], start: int, end: int, description: str) -> list[str]:
    """Try to fix broken cross-references.

    Scans description for "ref to Figure/Table ID not found".
    Looks for the actual figure/table declaration with matching ID.
    Inserts the inline reference at the location of the broken ref (start line).
    """
    m = re.search(r"ref\s+to\s+(\w+)\s+'?([^']+)'?\s+not\s+found", description, re.IGNORECASE)
    if not m:
        return lines
    kind, ref_id = m.group(1).lower(), m.group(2).strip("'").strip()

    # Find the figure/table declaration with matching ID in the document
    if kind in ("figure", "fig"):
        fig_decl_pattern = re.compile(r"^\!\[\[.*?" + re.escape(ref_id) + r".*?\]\]", re.MULTILINE)
        insert_after = -1
        for i, line in enumerate(lines):
            if fig_decl_pattern.search(line):
                insert_after = i
        if insert_after >= 0:
            # Insert inline figure ref after the declaration
            lines = lines[:insert_after + 1] + [f"[Figure {ref_id}]"] + lines[insert_after + 1:]
    elif kind in ("table", "tab"):
        tab_decl_pattern = re.compile(r"^Table\s+\d+.*?" + re.escape(ref_id), re.MULTILINE)
        insert_after = -1
        for i, line in enumerate(lines):
            if tab_decl_pattern.search(line):
                insert_after = i
        if insert_after >= 0:
            lines = lines[:insert_after + 1] + [f"[Table {ref_id}]"] + lines[insert_after + 1:]

    return lines


def _patch_section(lines: list[str], section_type: str) -> list[str]:
    """Insert missing required section."""
    section_markers = {
        "methods": ("## Methods\n", "## Methodology\n"),
        "results": ("## Results\n", "## Findings\n"),
        "discussion": ("## Discussion\n",),
        "conclusion": ("## Conclusion\n",),
        "limitations": ("## Limitations\n",),
        "references": ("## References\n",),
    }
    markers = section_markers.get(section_type.lower(), (f"## {section_type.title()}\n",))
    # Find last section header and insert after it
    last_header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("## "):
            last_header_idx = i
    if last_header_idx >= 0:
        insert_content = ["\n"] + list(markers) + ["\n"]
        lines = lines[:last_header_idx + 1] + insert_content + lines[last_header_idx + 1:]
    else:
        lines = list(markers) + ["\n"] + lines
    return lines


def _checksum(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


def apply_revision(state: ReportState) -> ReportState:
    """Apply patchable issues from edit_manifest to merged_draft.md."""
    manifest_path = state.governance.get("edit_manifest_path")
    merged_path = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path", "")
    if not manifest_path or not merged_path:
        return state

    manifest = _load_manifest(manifest_path)
    if not manifest:
        return state

    text = _load_merged(merged_path)
    lines = text.split("\n")
    pre_checksum = _checksum(text)

    unpatchable: list[dict] = []

    for item in manifest:
        issue_type = item.get("type", "")
        location = item.get("location", "")
        description = item.get("description", "")

        # Never auto-patch hard cases
        if issue_type in _NEVER_PATCH_TYPES:
            unpatchable.append(item)
            continue

        # Skip non-auto-patchable types
        if issue_type not in _AUTO_PATCHABLE_TYPES:
            continue

        start, end = _location_to_line_range(location, lines)

        if issue_type == "terminology_drift":
            lines = _patch_terminology_drift(lines, start, end, description)
        elif issue_type == "passive_voice":
            lines = _patch_passive_voice(lines, start, end)
        elif issue_type == "unit_mismatch":
            lines = _patch_unit_mismatch(lines, start, end, description)
        elif issue_type == "broken_crossref":
            lines = _patch_broken_crossref(lines, start, end, description)
        elif issue_type == "missing_required_section":
            section_name = item.get("check", "")
            lines = _patch_section(lines, section_name)
        elif issue_type in (
            "numeric_contradiction", "value_range_violation",
            "inconsistent_citation", "missing_crossref_target",
            "inconsistent_reporting", "unreported_item",
            "first_person", "informal_tone", "jargon",
            "acronym_without_expansion",
        ):
            # These require semantic understanding — flag as unpatchable
            unpatchable.append(item)

    post_checksum = _checksum("\n".join(lines))
    revised_text = "\n".join(lines)

    if post_checksum != pre_checksum:
        # Write revised merged draft
        try:
            with open(merged_path, "w") as f:
                f.write(revised_text)
        except OSError as exc:
            logger.exception(f"[REVISION_APPLY] failed to write revised merged draft: {exc}")
            state.governance["revision_status"] = f"write_error: {exc}"
            raise
        state.drafts["merged_draft_md"] = merged_path
        state.drafts["revision_applied"] = True

    state.governance["unpatchable"] = unpatchable
    state.governance["revision_patch_count"] = (
        len(manifest) - len(unpatchable) - sum(1 for i in manifest if i.get("type") in _NEVER_PATCH_TYPES)
    )

    return state


def run_revision_apply(state: ReportState) -> ReportState:
    """T24: REVISION_APPLY - apply auto-patchable issues to merged draft.

    Modes:
      fresh_doc:        apply patches to merged_draft.md
      tracked_review:   diff-based patch (future: integrate with git)
    """
    delivery_mode = state.spec.get("delivery_mode", "fresh_doc")
    edit_manifest_path = state.governance.get("edit_manifest_path", "")
    patchable_count = state.governance.get("patchable_count", 0)

    if patchable_count == 0:
        state.governance["revision_status"] = "no_patches"
        return state

    if delivery_mode == "tracked_review":
        state.revision["revision_mode"] = "tracked_review"
        # TODO: integrate with git diff for tracked review
        # For now, fall back to fresh_doc behavior
        pass

    try:
        state = apply_revision(state)
        state.governance["revision_status"] = "applied"
    except Exception as exc:
        logger.exception("[REVISION_APPLY] apply_revision failed")
        state.governance["revision_status"] = f"error: {type(exc).__name__}: {exc}"
        state.governance["revision_error"] = str(exc)

    return state
