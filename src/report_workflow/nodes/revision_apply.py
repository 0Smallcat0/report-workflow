"""REVISION_APPLY node - apply a revision_plan to the base_document.

Sits between SECTION_DRAFT and MERGE_DRAFT.
Only runs when state.spec["task_intent"] == 'revise_existing'.

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
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..artifact_contract import validate_base_document_integrity
from .citation_bind import REFERENCE_LIST_HEADING


def _reference_ids(sections: dict[str, str], kind: str) -> set[str]:
    pattern = re.compile(rf"\b{kind}\s+(\d+|[A-Za-z])\b", re.IGNORECASE)
    text = "\n".join(sections.values())
    return {match.group(1).lower() for match in pattern.finditer(text)}


def _preservation_reason_allowed(changes: list[dict], reason: str) -> bool:
    return any(str(change.get("change_reason", "")).lower() == reason for change in changes)


def _preservation_change_complete(changes: list[dict], reason: str) -> bool:
    for change in changes:
        if str(change.get("change_reason", "")).lower() != reason:
            continue
        decision = str(change.get("figure_preservation_decision", "")).strip().lower()
        replacement = str(change.get("replacement_text", "")).strip()
        if reason == "remove_figure_reference":
            if decision in {"replace_with_textual_description", "replace_with_table_reference", "remove_because_no_source_asset"}:
                return True
            if replacement:
                return True
        if reason == "remove_table_reference":
            if decision in {"replace_with_textual_description", "remove_because_no_source_asset"}:
                return True
            if replacement:
                return True
    return False


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
            # No fallback. Retargeting an unknown section at the preamble put
            # the author's new sentence on the title page, where the title lift
            # then dropped it — and the diff report still counted it applied.
            unapplied.append(
                f"[{change_type}] unknown section_id '{section_id}'; "
                f"base document sections are: {', '.join(sorted(updated))}"
            )
            continue

        content = updated[section_id]

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


_EDITORIAL_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_EDITORIAL_QUOTE_RE = re.compile(r"「[^」]{1,200}」|\"[^\"]{1,200}\"")


def _editorial_guard_violations(new_text: str, old_text: str) -> list[str]:
    """Deterministic 'no new facts' check for editorial (claim-free) changes.

    An editorial change may reword, repunctuate, or retitle, but it may not
    introduce numbers or quoted spans that the text it replaces did not
    already contain — those are factual content and must go through a normal
    claim-linked change instead.
    """
    violations: list[str] = []
    old_numbers = set(_EDITORIAL_NUMBER_RE.findall(old_text or ""))
    new_numbers = [n for n in _EDITORIAL_NUMBER_RE.findall(new_text or "") if n not in old_numbers]
    if new_numbers:
        violations.append("introduces numbers absent from the original text: " + ", ".join(sorted(set(new_numbers))[:5]))
    old_quotes = set(_EDITORIAL_QUOTE_RE.findall(old_text or ""))
    new_quotes = [q for q in _EDITORIAL_QUOTE_RE.findall(new_text or "") if q not in old_quotes]
    if new_quotes:
        violations.append("introduces quoted spans absent from the original text: " + "; ".join(sorted(set(new_quotes))[:3]))
    return violations


def _strip_leading_heading_from_content(content: str, sid: str) -> str:
    """If section content's first line is identical (case-insensitive) to the
    formatted heading, strip that first line. This prevents duplicate headings
    like '## Research Questions And Contributions' + 'Research Questions And Contributions'.
    """
    formatted_heading = sid.replace("_", " ").title()
    first_line = content.split("\n", 1)[0].strip()
    if first_line.lower() == formatted_heading.lower():
        # Strip the first line and leading whitespace
        remaining = content[len(first_line):]
        return remaining.lstrip("\n")
    return content


def run_revision_apply(state: ReportState) -> ReportState:
    """T12b: REVISION_APPLY - apply revision_plan to base_document.

    Only runs for revise_existing workflows.
    Reads base_document_sections (from BASE_DOCUMENT_PARSE) and
    revision_plan.json (from agent), applies changes, and writes merged_draft_md.

    Canonical assembly order:
      1. Abstract (always first)
      2. Blueprint sections in section_order
      3. Other non-blueprint sections (middle)
      4. References (always last)
    """
    task_intent = state.spec.get("task_intent", "new_draft")
    if task_intent != "revise_existing":
        return state  # passthrough — MERGE_DRAFT will handle new_draft

    # Load canonical base_document_sections from disk rather than trusting
    # checkpoint-embedded mutable state. The immutable integrity sidecar catches
    # direct edits to this file.
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    sections_path = Path(state.sources.get("base_document_sections_path", "")) if state.sources.get("base_document_sections_path") else run_dir / "base_document_sections.json"
    base_sections: dict[str, str] = {}
    if sections_path.exists():
        try:
            with open(sections_path, encoding="utf-8") as f:
                loaded_sections = json.load(f)
            if isinstance(loaded_sections, dict):
                base_sections = loaded_sections
                state.sources["base_document_sections"] = loaded_sections
                state.sources["base_document_sections_path"] = str(sections_path)
        except (json.JSONDecodeError, OSError) as exc:
            raise QAHardBlockError(f"Could not read base_document_sections.json: {exc}") from exc
    if not base_sections:
        raise QAHardBlockError(
            "revision_plan requires base_document sections; "
            "BASE_DOCUMENT_PARSE may have failed"
        )

    validate_base_document_integrity(state, base_sections)

    # Load revision_plan
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

    # Original heading text sidecar (written by BASE_DOCUMENT_PARSE) — needed
    # both for retitle validation here and heading restoration at merge time.
    base_titles: dict = state.sources.get("base_document_titles") or {}
    if not base_titles:
        titles_path = run_dir / "base_document_titles.json"
        if titles_path.exists():
            try:
                with open(titles_path, encoding="utf-8") as f:
                    base_titles = json.load(f)
            except json.JSONDecodeError:
                base_titles = {}

    CONTENT_CHANGE_TYPES = {"replace", "insert", "delete"}
    STRUCTURAL_CHANGE_TYPES = {"retitle", "remove_section"}

    for index, change in enumerate(changes):
        change_type = change.get("change_type", "")
        if change_type == "replace" and change.get("original_text", "") == change.get("new_text", ""):
            raise QAHardBlockError(f"revision_plan change {index} is a no-op replace")
        if change_type == "insert" and not str(change.get("new_text", "")).strip():
            raise QAHardBlockError(f"revision_plan change {index} is a no-op insert")
        if change_type == "retitle":
            if not str(change.get("new_text", "")).strip():
                raise QAHardBlockError(f"revision_plan change {index}: retitle requires a non-empty new_text")
            if change.get("section_id") not in base_sections:
                raise QAHardBlockError(f"revision_plan change {index}: retitle targets unknown section: {change.get('section_id')}")
        if change_type == "remove_section" and change.get("section_id") not in base_sections:
            raise QAHardBlockError(f"revision_plan change {index}: remove_section targets unknown section: {change.get('section_id')}")

        # Editorial changes carry no claim linkage but must not introduce new
        # facts; everything else in the content classes must cite its claims.
        if change.get("editorial") is True:
            if change_type in {"replace", "insert"}:
                reference_text = change.get("original_text", "")
            elif change_type == "retitle":
                reference_text = base_titles.get(change.get("section_id"), "")
            else:
                reference_text = None
            if reference_text is not None:
                violations = _editorial_guard_violations(str(change.get("new_text", "")), str(reference_text))
                if violations:
                    raise QAHardBlockError(
                        f"revision_plan change {index} is marked editorial but "
                        + "; ".join(violations)
                        + ". Factual content requires a claim-linked change."
                    )
        elif change_type in CONTENT_CHANGE_TYPES:
            if not change.get("claim_ids") or not change.get("evidence_ids"):
                raise QAHardBlockError(
                    f"revision_plan change {index} ({change_type}) has no claim_ids/evidence_ids; "
                    "link it to claims and evidence, or mark it editorial: true if it changes wording only"
                )

    structural_changes = [c for c in changes if c.get("change_type") in STRUCTURAL_CHANGE_TYPES]
    content_changes = [c for c in changes if c.get("change_type") not in STRUCTURAL_CHANGE_TYPES]

    # --- Conflict detection ---
    from .base_document_diff import (
        detect_overlapping_changes,
        compute_section_diff_summary,
        write_diff_report,
    )

    conflicts = detect_overlapping_changes(content_changes, base_sections)
    if conflicts:
        conflict_desc = "; ".join(
            f"change {a} vs change {b}" for a, b in conflicts
        )
        raise QAHardBlockError(
            f"Conflicting changes detected in revision_plan.json: {conflict_desc}. "
            f"Two changes modify overlapping text in the same section. "
            f"Split them into non-overlapping changes."
        )

    # Apply changes
    base_figures = _reference_ids(base_sections, "Figure")
    base_tables = _reference_ids(base_sections, "Table")
    updated_sections, unapplied = _apply_changes(base_sections, content_changes)

    # Structural changes: whole-section removal and retitling. Both are
    # recorded in the diff report below — an explicit audit trail instead of
    # forcing fake claim linkage onto structural edits.
    removed_section_ids: list[str] = []
    retitled_sections: dict[str, str] = {}
    for change in structural_changes:
        sid = change.get("section_id")
        if change.get("change_type") == "remove_section":
            if sid in updated_sections:
                updated_sections[sid] = ""
                removed_section_ids.append(sid)
        elif change.get("change_type") == "retitle":
            new_title = str(change.get("new_text", "")).strip()
            retitled_sections[sid] = new_title
            base_titles[sid] = new_title
    updated_figures = _reference_ids(updated_sections, "Figure")
    updated_tables = _reference_ids(updated_sections, "Table")
    removed_figures = sorted(base_figures - updated_figures)
    removed_tables = sorted(base_tables - updated_tables)
    if removed_figures and not _preservation_reason_allowed(changes, "remove_figure_reference"):
        raise QAHardBlockError(
            "revision_plan removed figure references without explicit change_reason='remove_figure_reference': "
            + ", ".join(removed_figures)
        )
    if removed_figures and not _preservation_change_complete(changes, "remove_figure_reference"):
        raise QAHardBlockError(
            "figure reference removal requires replacement_text or figure_preservation_decision "
            "(replace_with_textual_description | replace_with_table_reference | remove_because_no_source_asset)"
        )
    if removed_tables and not _preservation_reason_allowed(changes, "remove_table_reference"):
        raise QAHardBlockError(
            "revision_plan removed table references without explicit change_reason='remove_table_reference': "
            + ", ".join(removed_tables)
        )
    if removed_tables and not _preservation_change_complete(changes, "remove_table_reference"):
        raise QAHardBlockError(
            "table reference removal requires replacement_text or figure_preservation_decision "
            "(replace_with_textual_description | remove_because_no_source_asset)"
        )

    prompt = str(state.spec.get("user_prompt", "")).lower()
    if any(phrase in prompt for phrase in ("preserve figure", "preserve table", "preserve figure/table", "all figure/table references preserved")):
        if removed_figures or removed_tables:
            raise QAHardBlockError(
                "User requested preservation of figure/table references; revision_plan cannot remove them in this run."
            )

    if unapplied:
        allow_partial = state.flags.get("allow_partial_revision", False)
        if allow_partial:
            # Backward-compatible: warn but don't block
            state.runtime["revision_unapplied"] = unapplied
        else:
            # Default: hard block on any unapplied change
            unapplied_desc = "; ".join(unapplied)
            raise QAHardBlockError(
                f"Revision plan has {len(unapplied)} unapplied change(s): "
                f"{unapplied_desc}. "
                f"Ensure original_text matches the base document exactly. "
                f"Set state.flags['allow_partial_revision'] = True to allow partial application."
            )

    # --- Per-section diff summary ---
    diff_summaries: dict[str, dict] = {}
    for sid in updated_sections:
        old = base_sections.get(sid, "")
        new = updated_sections[sid]
        if old != new:
            summary = compute_section_diff_summary(old, new)
            diff_summaries[sid] = summary
            # Short sections trip the full-rewrite heuristic on any whole-
            # sentence replacement; only warn when there was enough text for
            # the ratio to mean anything. Explicit remove_section changes are
            # intentional and never a rewrite warning.
            if summary["similarity_ratio"] < 0.3 and len(old) > 200 and sid not in removed_section_ids:
                import logging
                logging.getLogger(__name__).warning(
                    f"[REVISION_APPLY] Section '{sid}' was changed by "
                    f"{(1 - summary['similarity_ratio']) * 100:.0f}% — "
                    f"this may indicate an unintended full rewrite. "
                    f"Consider using new_draft mode instead."
                )

    # Write diff report
    diff_report = {
        "total_changes": len(changes),
        "applied": len(changes) - len(unapplied),
        "unapplied": len(unapplied),
        "section_diffs": diff_summaries,
        "removed_sections": removed_section_ids,
        "retitled_sections": retitled_sections,
        "editorial_changes": sum(1 for c in changes if c.get("editorial") is True),
    }
    report_path = write_diff_report(state.job_id, diff_report)
    state.runtime["revision_diff_report_path"] = report_path

    # Canonical order: title, Abstract first, base-document sections, References last
    ABSTRACT_SECTION = "abstract"
    REFERENCES_SECTION = "references"

    # Sections neither abstract nor references nor preamble (preamble is metadata-only;
    # its front matter fields are extracted by front_matter_build separately)
    other_sections = {
        sid: content for sid, content in updated_sections.items()
        if sid not in (ABSTRACT_SECTION, REFERENCES_SECTION, "preamble")
    }

    merged_lines: list[str] = []

    # 0. Front matter. The base document's H1 lives in the preamble
    # (retitle-aware via base_titles); without this, a revised document
    # loses its title whenever the profile has no required front matter.
    #
    # A rendered .docx has no H1 there at all: its preamble is the title page
    # itself — course, author, affiliation, date, as plain paragraphs. Matching
    # only an H1 dropped the lot, so revising a report quietly removed the
    # author's own name from it. When there is no heading to lift, the block
    # carries through as it stood.
    preamble_content = str(base_sections.get("preamble") or "").strip()
    doc_title = str(base_titles.get("preamble") or "").strip()
    if not doc_title:
        title_match = re.match(r"\s*#\s+(.+)", preamble_content)
        if title_match:
            doc_title = title_match.group(1).strip()
    if doc_title:
        merged_lines.append(f"# {doc_title}\n")
    elif preamble_content:
        # One title-page line per paragraph. Consecutive markdown lines are a
        # single paragraph, which ran course, author, affiliation, and date
        # together into one unbroken string.
        merged_lines.append(
            "\n\n".join(
                line.strip() for line in preamble_content.split("\n") if line.strip()
            )
            + "\n"
        )

    # 1. Abstract — always first
    abstract_content = updated_sections.get(ABSTRACT_SECTION, "").strip()
    if abstract_content:
        abstract_content = _strip_leading_heading_from_content(abstract_content, ABSTRACT_SECTION)
        merged_lines.append(f"# Abstract\n\n{abstract_content}\n")

    # Original heading text from the base document (loaded above, with any
    # retitle changes already applied); slug-derived titles are the fallback
    # only (they mangle Chinese and aliased headings).
    def _heading_for(sid: str) -> str:
        return base_titles.get(sid) or sid.replace("_", " ").title()

    # 2. Body sections in the base document's own order. The blueprint's
    # order only ever matched a base document by coincidence: a partially
    # overlapping English draft had its Conclusion hoisted to the top
    # because "conclusion" happened to be a blueprint id. For a revision,
    # the base document's own order is the canonical one.
    for sid, content in other_sections.items():
        if sid in (ABSTRACT_SECTION, REFERENCES_SECTION):
            continue
        if content.strip():
            content = _strip_leading_heading_from_content(content, sid)
            merged_lines.append(f"# {_heading_for(sid)}\n\n{content}\n")

    # 4. References — always last, at the same level as every other section.
    refs_content = updated_sections.get(REFERENCES_SECTION, "").strip()
    if refs_content:
        # Strip stray "References" plain-text label that may appear as the first
        # line (the heading already provides the label)
        refs_lines = refs_content.splitlines()
        if refs_lines and refs_lines[0].strip() == "References":
            refs_lines = refs_lines[1:]
        refs_content = "\n".join(refs_lines).strip()
        if refs_content:
            merged_lines.append(f"{REFERENCE_LIST_HEADING}\n\n{refs_content}\n")

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
