"""PUBLICATION_NATURALNESS_PASS - remove workflow-defense prose from main text."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR
from .style_pass import _is_structural_markdown_block, _split_markdown_blocks


#: Workflow identifiers that must never appear in a delivered report. These
#: lived in SCHOLARLY_QUALITY, which ran 672 lines to produce an advisory report
#: nothing gated on plus this one hard check, and applied it to two profiles out
#: of seven. A workflow identifier in the body is a defect in any report, so the
#: check moved here — where the same class of leak was already hard-blocked —
#: and the special case went with the file.
FORBIDDEN_WORKFLOW_IDENTIFIERS = (
    "query_evidence",
    "claim_matrix",
    "evidence_ledger",
    "sentence_map",
    "section_drafts",
)

FORBIDDEN_PUBLICATION_PHRASES = (
    "retained outside the main report",
    "outside the main report",
    "supplementary verification evidence",
    "engineering evidence",
    "internal traceability",
    "traceability appendix",
    "Appendix E",
    "Appendices A and B",
)


# Machine-writing tells: internal identifiers that read as machine output when
# they appear in publication prose. Advisory only — code-artifact reports may
# legitimately name identifiers in prose, so this warns (for the authoring
# agent to repair) instead of hard-blocking. Fenced code blocks are structural
# and are never scanned.
_SNAKE_CASE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_INTERNAL_ID_RE = re.compile(r"\bfigrec_\w+\b|\b\w+_source\b|\bev_[a-z0-9_]+\b")


def detect_machine_tell_identifiers(markdown: str) -> list[str]:
    """Return snake_case / internal-id tokens found in publication prose."""
    found: list[str] = []
    for block in _split_markdown_blocks(markdown):
        if _is_structural_markdown_block(block):
            continue
        for match in _SNAKE_CASE_RE.finditer(block):
            token = match.group(0)
            if token not in found:
                found.append(token)
        for match in _INTERNAL_ID_RE.finditer(block):
            token = match.group(0)
            if token not in found:
                found.append(token)
    return found


def remove_workflow_defense_sentences(markdown: str) -> tuple[str, list[str]]:
    """Drop sentences that explain workflow evasions instead of research content."""
    removed: list[str] = []
    cleaned_blocks: list[str] = []
    for block in _split_markdown_blocks(markdown):
        if _is_structural_markdown_block(block):
            cleaned_blocks.append(block)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", block)
        kept: list[str] = []
        for sentence in sentences:
            if any(phrase.lower() in sentence.lower() for phrase in FORBIDDEN_PUBLICATION_PHRASES):
                removed.append(" ".join(sentence.split())[:240])
            else:
                kept.append(sentence)
        paragraph = " ".join(part.strip() for part in kept if part.strip())
        if paragraph:
            cleaned_blocks.append(paragraph)
    return "\n\n".join(cleaned_blocks).strip() + "\n", removed


def run_publication_naturalness_pass(state: ReportState) -> ReportState:
    """Remove unnatural appendix/evidence-routing residue from publication prose."""
    draft_path = state.drafts.get("publication_style_draft") or state.drafts.get("merged_draft_cited_md")
    if not draft_path or not Path(draft_path).exists():
        state.runtime["publication_naturalness_report_path"] = ""
        return state

    markdown = Path(draft_path).read_text(encoding="utf-8")
    cleaned, removed = remove_workflow_defense_sentences(markdown)

    remaining = [
        phrase for phrase in FORBIDDEN_PUBLICATION_PHRASES
        if phrase.lower() in cleaned.lower()
    ]
    if remaining:
        raise QAHardBlockError(
            "PUBLICATION_NATURALNESS_PASS: forbidden workflow-defense phrase(s) remain: "
            + ", ".join(remaining)
        )

    identifiers = [
        term for term in FORBIDDEN_WORKFLOW_IDENTIFIERS
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", cleaned, re.I)
    ]
    if identifiers:
        raise QAHardBlockError(
            "PUBLICATION_NATURALNESS_PASS: workflow identifier(s) in the publication "
            "body: " + ", ".join(identifiers)
            + ". Those name this pipeline's own files; a reader of the report has no "
            "use for them."
        )

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    output_path = run_dir / "publication_naturalness_draft.md"
    output_path.write_text(cleaned, encoding="utf-8")
    state.drafts["publication_style_draft"] = str(output_path)

    machine_tells = detect_machine_tell_identifiers(cleaned)
    report = {
        "job_id": state.job_id,
        "removed_count": len(removed),
        "removed_samples": removed[:20],
        # Advisory: snake_case / internal ids in publication prose read as
        # machine output. Surfaced for authoring-agent repair, never blocking
        # (code-artifact reports may name identifiers legitimately).
        "machine_tell_warnings": machine_tells[:20],
        "machine_tell_count": len(machine_tells),
        "status": "passed",
        "output_path": str(output_path),
    }
    state.runtime["publication_naturalness_report_path"] = write_json_artifact(
        state, "publication_naturalness_report.json", report
    )
    return state
