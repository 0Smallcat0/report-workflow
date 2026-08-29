"""REGISTER_GATE - a report is not a work log, whoever it is for.

`ADMISSIONS_TONE_GATE` returns immediately unless the profile is
`admissions_report`, and its four patterns are English admissions phrasing. So a
quantitative backtest report shipped with the chat message that commissioned it
quoted verbatim at the top of a section — name, date, quotation marks — plus
first-person confessions about the author's own iterations, emoji in a results
table, and blog connectives. Every gate in the pipeline passed it.

None of those are admissions problems. They are register problems, and register
is not a function of who the reader is: a report states what was found, not who
asked or how the author got there.

Each pattern here is one that actually reached a delivered document.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState


#: (label, pattern, what to write instead). The label is what the author sees.
REGISTER_PATTERNS: list[tuple[str, str, str]] = [
    (
        "chat attribution",
        r"(原話|原话)\s*[:：]|(導師|导师|老師|老师|客戶|客户)\s*\d{4}-\d{2}-\d{2}\s*[:：]"
        r"|\b(?:the client|the reviewer|my (?:advisor|supervisor))\s+said\b",
        "state the question the section answers, not who asked it or when",
    ),
    (
        "first-person process narration",
        r"(?<![自忘無无唯])我(?![們们])|\b(?:I|we)\s+(?:originally|first|then|forgot|missed|realised|realized)\b",
        "report what holds, not how the author arrived at it",
    ),
    (
        "development-process confession",
        r"第一版|差點|差点|我當時|我当时|忘記了|忘记了"
        r"|\b(?:at first|originally)\s+(?:I|we)\b|\bmy (?:first|earlier) (?:attempt|version)\b",
        "an earlier draft being wrong is not a finding; state the finding",
    ),
    (
        "emoji",
        r"[✅❌⭕\U0001F7E1\U0001F534\U0001F7E2\U0001F535\U0001F4CC\U0001F6E1\U0001F4E6]",
        "use a word: effective / ineffective / limited",
    ),
    (
        "blog connective",
        r"(要一句話|要一句话|[一二三四五六七八九十]句話[:：]|[一二三四五六七八九十]句话[:：]"
        r"|先講清楚|先讲清楚|說白了|说白了|老實說|老实说)"
        r"|\b(?:in a nutshell|long story short|let'?s be honest)\b",
        "drop the connective and state the point",
    ),
]

#: Lines that carry someone else's words or machine output on purpose. A quoted
#: requirement is the question the report answers, and a code block is a
#: transcript; neither is the report's own register.
#:
#: A table row is **not** exempt. The emoji that shipped were in a results
#: table, and a table is the report speaking in its own voice.
_EXEMPT_LINE = re.compile(r"^\s*(>|```|~~~)")


def _prose_lines(markdown: str) -> list[tuple[int, str]]:
    """Numbered lines that are the report speaking in its own voice."""
    out: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(markdown.splitlines(), start=1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or _EXEMPT_LINE.match(line):
            continue
        out.append((number, line))
    return out


def find_register_issues(markdown: str) -> list[str]:
    """Every register violation in the document's own prose, as author-facing text."""
    issues: list[str] = []
    for number, line in _prose_lines(markdown):
        for label, pattern, remedy in REGISTER_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            start = max(0, match.start() - 12)
            end = min(len(line), match.end() + 12)
            issues.append(
                f"line {number}: {label} — 「{line[start:end].strip()}」; {remedy}"
            )
    return issues


def run_register_gate(state: ReportState) -> ReportState:
    """Block work-log register in the drafted document, for every profile."""
    draft_path = (
        state.drafts.get("publication_style_draft")
        or state.drafts.get("merged_draft_cited_md")
        or state.drafts.get("merged_draft_md")
    )
    if not draft_path or not Path(draft_path).exists():
        state.runtime["register_report_path"] = ""
        return state

    issues = find_register_issues(Path(draft_path).read_text(encoding="utf-8"))
    report = {
        "job_id": state.job_id,
        "status": "passed" if not issues else "failed",
        "issues": issues,
    }
    state.runtime["register_report_path"] = write_json_artifact(
        state, "register_report.json", report
    )
    if issues:
        raise QAHardBlockError("REGISTER_GATE: " + "; ".join(issues[:8]))
    return state
