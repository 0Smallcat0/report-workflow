"""ADMISSIONS_MONOGRAPH_POLISH - deterministic polish for admissions-facing reports."""
from __future__ import annotations

import re
from pathlib import Path

from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR
from .style_pass import _is_structural_markdown_block, _split_markdown_blocks


# Phrase-level strippers (must run before token-level rewrites so that e.g.
# "In this paper," is removed whole rather than partially rewritten).
_PHRASE_STRIPPERS = [
    (r"\bIn this paper,\s*", ""),
    (r"\bIn this study,\s*", ""),
    (r"\bin this paper,\s*", ""),
    (r"\bin this study,\s*", ""),
    (r"\bThe paper is organized as follows\.[^.]*\.", ""),
    (r"\bThe remainder of this paper is organized as follows\.[^.]*\.", ""),
    (r"\bThe remainder of this report is organized as follows\.[^.]*\.", ""),
    (r"\bFor graduate research purposes,\s*", ""),
    (r"\bFor academic purposes,\s*", ""),
]

# (pattern, capitalised_replacement, lowercase_replacement) for case-preserving rewrites.
# The sentence-initial capital in the replacement tracks the match's first letter.
_REPLACEMENTS: list[tuple[str, str, str]] = [
    (r"\bThis work presents\b", "This project develops", "this project develops"),
    (r"\bThis work proposes\b", "This project proposes", "this project proposes"),
    (r"\bThis work\b(?!\s+(?:of|in|on))", "This project", "this project"),
    (r"\bThis study presents\b", "This project develops", "this project develops"),
    (r"\bThis study\b", "This project", "this project"),
    (r"\bThis paper\b", "This report", "this report"),
    (r"\bThis manuscript\b", "This report", "this report"),
    (r"\bThis research\b", "This project", "this project"),
    (r"\bthe present study\b", "The present project", "this project"),
    (r"\bthe present paper\b", "The present report", "this report"),
]

# Case-preserving "we ..." rewrites. Handled as a separate pass so that a
# sentence-initial "We propose" becomes "This project proposes" (capitalised)
# while a mid-sentence "we propose" becomes "this project proposes".
_WE_REWRITES = [
    (r"\bwe propose\b", "project proposes"),
    (r"\bwe present\b", "project presents"),
    (r"\bwe aim to\b", "project aims to"),
    (r"\bwe demonstrate\b", "project demonstrates"),
    (r"\bwe introduce\b", "project introduces"),
    (r"\bwe show(?: that)?\b", "project shows"),
]

_REPLACEMENTS_TAIL = [
    (r"\bserves as a research platform\b", "functions as a research platform"),
    (r"\bnot a trading strategy or an assertion of alpha superiority\b", "not an alpha claim"),
    (r"\bbeyond the scope of this paper\b", "beyond the scope of this project"),
    (r"\bbeyond the scope of this study\b", "beyond the scope of this project"),
]


def polish_admissions_monograph(markdown: str) -> tuple[str, list[str]]:
    """Apply conservative admissions-facing polish without adding new claims."""
    changed: list[str] = []
    blocks = []
    for block in _split_markdown_blocks(markdown):
        if _is_structural_markdown_block(block):
            blocks.append(block)
            continue
        updated = block
        # Phrase strippers first (case-sensitive so the IN/In variants drop
        # correctly without double-processing leftover fragments).
        for pattern, replacement in _PHRASE_STRIPPERS:
            new_updated = re.sub(pattern, replacement, updated)
            if new_updated != updated:
                changed.append(pattern)
                updated = new_updated
        for pattern, cap_repl, low_repl in _REPLACEMENTS:
            def _repl(m: re.Match, _cap: str = cap_repl, _low: str = low_repl) -> str:
                return _cap if m.group(0)[:1].isupper() else _low
            new_updated = re.sub(pattern, _repl, updated, flags=re.IGNORECASE)
            if new_updated != updated:
                changed.append(pattern)
                updated = new_updated
        # Case-preserving "we ..." rewrites.
        for pattern, tail in _WE_REWRITES:
            def _repl(m: re.Match, _tail: str = tail) -> str:
                head = "This" if m.group(0)[0].isupper() else "this"
                return f"{head} {_tail}"
            new_updated = re.sub(pattern, _repl, updated, flags=re.IGNORECASE)
            if new_updated != updated:
                changed.append(pattern)
                updated = new_updated
        for pattern, replacement in _REPLACEMENTS_TAIL:
            new_updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
            if new_updated != updated:
                changed.append(pattern)
                updated = new_updated
        # Tighten stock report-transition prose.
        updated = re.sub(r"\s{2,}", " ", updated).strip()
        if updated:
            blocks.append(updated)
    return "\n\n".join(blocks).strip() + "\n", sorted(set(changed))


def run_admissions_monograph_polish(state: ReportState) -> ReportState:
    """Polish admissions-facing academic reports into a project monograph tone."""
    if state.spec.get("report_family_detail") != "admissions_report":
        state.runtime["admissions_monograph_report_path"] = ""
        return state

    draft_path = state.drafts.get("publication_style_draft") or state.drafts.get("merged_draft_cited_md")
    if not draft_path or not Path(draft_path).exists():
        state.runtime["admissions_monograph_report_path"] = ""
        return state

    markdown = Path(draft_path).read_text(encoding="utf-8")
    polished, changed_patterns = polish_admissions_monograph(markdown)

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    output_path = run_dir / "admissions_monograph_draft.md"
    output_path.write_text(polished, encoding="utf-8")
    state.drafts["publication_style_draft"] = str(output_path)

    report = {
        "job_id": state.job_id,
        "changed_patterns": changed_patterns,
        "status": "passed",
        "output_path": str(output_path),
    }
    state.runtime["admissions_monograph_report_path"] = write_json_artifact(
        state, "admissions_monograph_report.json", report
    )
    return state
