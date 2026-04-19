"""REVISION_APPLY node - apply a revision_plan to the base_document.

Sits between SECTION_DRAFT and MERGE_DRAFT.
Only runs when state.spec["task_intent"] == "revise_existing".

Reads:
  - run_dir / "revision_plan.json"     ← agent-authored change manifest
  - state.sources["base_document_sections"]  ← from BASE_DOCUMENT_PARSE

Writes:
  - run_dir / "merged_draft.md"       ← applied result (same key MERGE_DRAFT writes to)
  - state.drafts["merged_draft_md"]

The change_types are:
  - replace: replace original_text with new_text in the given section
  - insert : insert new_text after original_text (or at section start/end)
  - delete : remove original_text

Each change carries claim_ids + evidence_ids so it feeds into sentence_map
and the normal FACTUALITY/CONSISTENCY gates.
"""
import json
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR


def _apply_changes(
    sections: dict[str, str],
    changes: list[dict],
) -> tuple[dict[str, str], list[dict]]:
    """Apply revision_plan changes to section content.

    Returns (updated_sections, unapplied_reasons).
    unapplied_reasons is a list of strings describing changes that could
    not be applied verbatim.
    """
    updated = dict(sections)
    unapplied: list[str] = []

    for change in changes:
        section_id = change.get("section_id", "preamble")
        change_type = change.get("change_type", "")
        original_text = change.get("original_text", "")
        new_text = change.get("new_text", "")

        if section_id not in updated:
            # Fallback to preamble if section not found
            section_id = "preamble"

        content = updated.get(section_id, "")

        if change_type == "replace":
            if original_text in content:
                content = content.replace(original_text, new_text, 1)
            else:
                unapplied.append(
                    f"[replace] '{original_text[:40]}' not found in section '{section_id}'"
                )
            updated[section_id] = content

        elif change_type == "delete":
            if original_text in content:
                content = content.replace(original_text, "", 1)
            else:
                unapplied.append(
                    f"[delete] '{original_text[:40]}' not found in section '{section_id}'"
                )
            updated[section_id] = content

        elif change_type == "insert":
            if original_text and original_text in content:
                idx = content.index(original_text) + len(original_text)
                content = content[:idx] + new_text + content[idx:]
            elif not original_text:
                # Insert at end of section
                content = content + "\n" + new_text
            else:
                unapplied.append(
                    f"[insert] anchor '{original_text[:40]}' not found in section '{section_id}'"
                )
            updated[section_id] = content

        else:
            unapplied.append(f"Unknown change_type: {change_type}")

    return updated, unapplied


def run_revision_apply(state: ReportState) -> ReportState:
    """T12b: REVISION_APPLY - apply revision_plan to base_document.

    Only runs for revise_existing workflows.
    Reads base_document_sections (from BASE_DOCUMENT_PARSE) and
    revision_plan.json (from agent), applies changes, and writes merged_draft_md.
    """
    task_intent = state.spec.get("task_intent", "new_draft")
    if task_intent != "revise_existing":
        return state  # passthrough — MERGE_DRAFT will handle new_draft

    # Load base_document_sections
    base_sections: dict[str, str] = state.sources.get("base_document_sections", {})
    if not base_sections:
        raise QAHardBlockError(
            "revision_plan requires base_document sections; "
            "BASE_DOCUMENT_PARSE may have failed"
        )

    # Load revision_plan
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    revision_plan_path = run_dir / "revision_plan.json"
    if not revision_plan_path.exists():
        raise QAHardBlockError(
            "revision_plan.json not found; agent must produce it for revise_existing workflows"
        )

    try:
        with open(revision_plan_path, encoding="utf-8") as f:
            revision_plan = json.load(f)
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed revision_plan.json: {exc}")

    changes = revision_plan.get("changes", [])
    if not changes:
        raise QAHardBlockError("revision_plan.json has no changes; aborting revision")

    # Apply changes
    updated_sections, unapplied = _apply_changes(base_sections, changes)

    if unapplied:
        # Emit warnings (not hard-fail) into runtime
        state.runtime["revision_unapplied"] = unapplied

    # Build merged_draft_md in blueprint section order
    blueprint = state.plan.get("blueprint") or {}
    section_order = blueprint.get("section_order", [])

    merged_lines: list[str] = []
    # First emit any preamble (sections not in blueprint order)
    for sid, content in updated_sections.items():
        if sid not in section_order and content.strip():
            merged_lines.append(f"# {sid.replace('_', ' ').title()}\n\n{content}\n")

    # Then emit in blueprint order
    for sid in section_order:
        content = updated_sections.get(sid, "")
        if content.strip():
            merged_lines.append(f"# {sid.replace('_', ' ').title()}\n\n{content}\n")

    merged_draft_md = "\n\n".join(merged_lines)

    # Write merged_draft_md
    merged_path = run_dir / "merged_draft.md"
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write(merged_draft_md)

    state.drafts["merged_draft_md"] = str(merged_path)

    # NOTE: section_drafts are NOT updated here.
    # _artifact_hard_fail_reasons (qa_gate) checks section_drafts for [CITE:...]
    # placeholders, but revision_apply produces a merged document where per-section
    # citation tracking is handled by MERGE_DRAFT → CITATION_BIND on the merged output.
    # Leaving section_drafts unchanged keeps the downstream citation checks happy.

    return state
