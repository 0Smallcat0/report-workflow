"""PUBLICATION_NATURALNESS_PASS - remove workflow-defense prose from main text."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR
from .style_pass import _is_structural_markdown_block, _split_markdown_blocks


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

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    output_path = run_dir / "publication_naturalness_draft.md"
    output_path.write_text(cleaned, encoding="utf-8")
    state.drafts["publication_style_draft"] = str(output_path)

    report = {
        "job_id": state.job_id,
        "removed_count": len(removed),
        "removed_samples": removed[:20],
        "status": "passed",
        "output_path": str(output_path),
    }
    state.runtime["publication_naturalness_report_path"] = write_json_artifact(
        state, "publication_naturalness_report.json", report
    )
    return state
