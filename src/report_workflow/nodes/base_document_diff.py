"""BASE_DOCUMENT_DIFF — diff preview and validation tools for revision workflows.

Provides utility functions for:
  1. Pre-validating revision_plan.json before applying changes
  2. Detecting overlapping/conflicting changes
  3. Computing section-level diff summaries
  4. Generating human-readable diff previews

These are tool functions called by agent_wrapper, NOT pipeline nodes.
"""
import difflib
import json

from ..state import WORKFLOW_RUNS_DIR


def compute_revision_diff(
    base_sections: dict[str, str],
    revision_plan: dict,
) -> dict:
    """Pre-validate a revision_plan against base_document_sections.

    For each proposed change, checks whether the original_text can be found
    in the target section. Returns a structured report with valid/invalid
    changes and a human-readable preview.

    Args:
        base_sections: section_id -> markdown content from BASE_DOCUMENT_PARSE.
        revision_plan: The agent-authored revision_plan (with "changes" list).

    Returns:
        {
            "total_changes": int,
            "valid_changes": int,
            "conflicts": [(idx_a, idx_b), ...],
            "unresolvable": [{"change_index": int, "reason": str}, ...],
            "preview": [
                {
                    "change_index": int,
                    "section_id": str,
                    "change_type": str,
                    "context_before": str,
                    "original_text": str,
                    "new_text": str,
                    "context_after": str,
                    "status": "valid" | "unresolvable" | "conflict",
                }
            ],
        }
    """
    changes = revision_plan.get("changes", [])
    total = len(changes)
    valid = 0
    unresolvable: list[dict] = []
    preview: list[dict] = []

    # Check each change
    for i, change in enumerate(changes):
        section_id = change.get("section_id", "preamble")
        change_type = change.get("change_type", "")
        original_text = change.get("original_text", "")
        new_text = change.get("new_text", "")

        section_content = base_sections.get(section_id, "")
        status = "valid"
        reason = ""

        if change_type == "replace" and original_text == new_text:
            status = "unresolvable"
            reason = "No-op replace change: original_text and new_text are identical"
        elif change_type == "insert" and not new_text.strip():
            status = "unresolvable"
            reason = "No-op insert change: new_text is empty"
        elif section_id not in base_sections:
            # Membership, not emptiness. A heading with nothing under it is a
            # section the author may legitimately insert into; reporting it as
            # missing sent them hunting for an id that was already right.
            status = "unresolvable"
            reason = (
                f"Section '{section_id}' not found in base document; "
                f"sections are: {', '.join(sorted(base_sections))}"
            )
        elif change_type in ("replace", "delete") and original_text:
            if original_text not in section_content:
                status = "unresolvable"
                reason = (
                    f"original_text not found in section '{section_id}': "
                    f"'{original_text[:60]}...'"
                )
        elif change_type == "insert" and original_text:
            if original_text not in section_content:
                status = "unresolvable"
                reason = (
                    f"Insert anchor not found in section '{section_id}': "
                    f"'{original_text[:60]}...'"
                )
        elif change_type not in ("replace", "insert", "delete"):
            status = "unresolvable"
            reason = f"Unknown change_type: '{change_type}'"

        if status == "valid":
            valid += 1
        else:
            unresolvable.append({"change_index": i, "reason": reason})

        # Build context preview
        context_before = ""
        context_after = ""
        if original_text and original_text in section_content:
            idx = section_content.index(original_text)
            context_before = section_content[max(0, idx - 80):idx]
            end_idx = idx + len(original_text)
            context_after = section_content[end_idx:end_idx + 80]

        preview.append({
            "change_index": i,
            "section_id": section_id,
            "change_type": change_type,
            "context_before": context_before,
            "original_text": original_text[:200] if original_text else "",
            "new_text": new_text[:200] if new_text else "",
            "context_after": context_after,
            "status": status,
        })

    # Detect overlapping changes
    conflicts = detect_overlapping_changes(changes, base_sections)

    # Mark conflicting changes in preview
    conflict_indices = set()
    for a, b in conflicts:
        conflict_indices.add(a)
        conflict_indices.add(b)
    for p in preview:
        if p["change_index"] in conflict_indices and p["status"] == "valid":
            p["status"] = "conflict"

    return {
        "total_changes": total,
        "valid_changes": valid,
        "conflicts": conflicts,
        "unresolvable": unresolvable,
        "preview": preview,
    }


def detect_overlapping_changes(
    changes: list[dict],
    base_sections: dict[str, str] | None = None,
) -> list[tuple[int, int]]:
    """Detect pairs of changes that modify overlapping text in the same section.

    Two changes overlap if they target the same section and their
    original_text ranges overlap in the base document.

    Args:
        changes: List of change dicts from revision_plan.
        base_sections: section_id -> content. Needed for position-based overlap.

    Returns:
        List of (index_a, index_b) tuples for conflicting change pairs.
    """
    if not base_sections:
        return []

    conflicts: list[tuple[int, int]] = []

    # Group changes by section
    by_section: dict[str, list[tuple[int, dict]]] = {}
    for i, change in enumerate(changes):
        sid = change.get("section_id", "preamble")
        by_section.setdefault(sid, []).append((i, change))

    for sid, section_changes in by_section.items():
        content = base_sections.get(sid, "")
        if not content:
            continue

        # Find positions of each change's original_text
        positioned: list[tuple[int, int, int]] = []  # (change_idx, start, end)
        for i, change in section_changes:
            original = change.get("original_text", "")
            if original and original in content:
                start = content.index(original)
                end = start + len(original)
                positioned.append((i, start, end))

        # Check pairwise overlap
        for a_idx in range(len(positioned)):
            for b_idx in range(a_idx + 1, len(positioned)):
                ci_a, s_a, e_a = positioned[a_idx]
                ci_b, s_b, e_b = positioned[b_idx]
                # Overlap if ranges intersect
                if s_a < e_b and s_b < e_a:
                    conflicts.append((ci_a, ci_b))

    return conflicts


def compute_section_diff_summary(old_text: str, new_text: str) -> dict:
    """Compute a line-level diff summary between old and new section text.

    Uses Python's difflib to compute a similarity ratio and count
    added/removed/changed lines.

    Returns:
        {
            "added_lines": int,
            "removed_lines": int,
            "similarity_ratio": float (0.0-1.0),
            "total_old_lines": int,
            "total_new_lines": int,
        }
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    ratio = matcher.ratio()

    # Count added and removed
    added = 0
    removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1

    return {
        "added_lines": added,
        "removed_lines": removed,
        "similarity_ratio": round(ratio, 4),
        "total_old_lines": len(old_lines),
        "total_new_lines": len(new_lines),
    }


def write_diff_report(job_id: str, diff_result: dict) -> str:
    """Write a diff report JSON to the run directory.

    Returns the path to the written file.
    """
    run_dir = WORKFLOW_RUNS_DIR / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "revision_diff_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(diff_result, f, indent=2, default=str)
    return str(report_path)
