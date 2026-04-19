"""LANGUAGE_SANITY_PASS node - catch broken sentences, incomplete comparatives, orphaned fragments.

Sits between QA_GATE and DOCX_RENDER in the render phase.

Checks for:
  1. Incomplete comparatives ("more X than" — missing completion)
  2. Trailing ellipses in mid-sentence
  3. Incomplete sentences (no terminal punctuation or truncated structure)
  4. Orphaned heading markers without content
  5. Duplicate consecutive phrases
  6. Mid-sentence line breaks (paragraph continuation broken by blank line)

Output:
  - language_sanity_report.json
  - Hard failures block render unless --force
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact


# ------------------------------------------------------------------
# Detection patterns
# ------------------------------------------------------------------

# Incomplete comparative: "more X than" followed by no clause
# Matches "more X than Y" where Y is empty, a fragment, or a preposition
INCOMPLETE_COMPARATIVE = re.compile(
    r"\bmore\s+(\w+(?:\s+\w+){0,4})\s+than\s+"
    r"(?="
    r"[a-z]+\s+(?:by|from|with|to|for|of|on|at|than)\s*"  # "more X than by..." (preposition fragment)
    r"|\s*$"                                                  # "more X than" (end of sentence)
    r"|[A-Z][a-z]+\s*$"                                      # "more X than Something" (no verb)
    r"|\s*\.\.\."                                             # "more X than..."
    r"|\s*[,;]\s*$"                                          # "more X than," (punctuation only)
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# Trailing ellipsis mid-sentence (not at end of block)
MID_SENTENCE_ELLIPSIS = re.compile(
    r"\w\b\s*\.{2,}(?=\s+[A-Z])",
    re.MULTILINE,
)

# Sentence that ends mid-word or ends with hyphenation
BROKEN_HYPHENATION = re.compile(
    r"\b\w+-\n\w+\b",
    re.MULTILINE,
)

# Orphaned heading (heading with no content following until next heading)
ORPHANED_HEADING = re.compile(
    r"(^#{1,3}\s+[^\n]+)\n\n(?=#{1,3}\s|\Z)",
    re.MULTILINE,
)

# Duplicate consecutive phrases "word word word, word word word"
DUPLICATE_PHRASE = re.compile(
    r"\b(\b\w+(?:\s+\w+){2,})\b\s+(?:\1\s+){1,}",
    re.IGNORECASE,
)

# Sentence starting with "than" (orphan fragment after comma splice)
ORPHAN_THAN_CLAUSE = re.compile(
    r"(?<=[,;])\s+(than\s+(?:by|for|to|of|with|from|on|at)\s+\w+)",
    re.IGNORECASE,
)

# Incomplete sentence: ends with "that", "which", "because" without verb
INCOMPLETE_CLAUSE = re.compile(
    r"[.!?]\s*((?:that|which|because|when|where|while|although)\s+[A-Z][a-z]*(?:\s+(?:is|are|was|were|has|have|had|will|would|can|could|may|might|should)\s+)?)$",
    re.MULTILINE,
)

# Fragment: "X than" (comparative without a proper "than Y" clause)
COMPARATIVE_NO_COMPLETION = re.compile(
    r"\b(more|less|better|worse|higher|lower|greater|smaller|fewer)\s+\w+(?:\s+\w+){0,3}\s+than\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _check_incomplete_comparatives(text: str) -> list[dict]:
    """Find 'more X than' phrases that lack a proper completion."""
    issues = []
    for m in INCOMPLETE_COMPARATIVE.finditer(text):
        context = text[max(0, m.start() - 60):m.end() + 60]
        issues.append({
            "type": "incomplete_comparative",
            "matched": m.group(0).strip(),
            "context": context,
            "suggestion": "Ensure comparative is fully stated: 'more X than Y' with Y as a complete clause.",
        })
    return issues


def _check_trailing_ellipses(text: str) -> list[dict]:
    """Find mid-sentence ellipses that truncate thought."""
    issues = []
    for m in MID_SENTENCE_ELLIPSIS.finditer(text):
        context = text[max(0, m.start() - 60):m.end() + 60]
        issues.append({
            "type": "trailing_ellipsis",
            "matched": m.group(0).strip(),
            "context": context,
            "suggestion": "Remove mid-sentence ellipsis or complete the truncated thought.",
        })
    return issues


def _check_broken_hyphenation(text: str) -> list[dict]:
    """Find words broken across lines by hyphenation."""
    issues = []
    for m in BROKEN_HYPHENATION.finditer(text):
        issues.append({
            "type": "broken_hyphenation",
            "matched": m.group(0).replace("\n", ""),
            "context": m.group(0),
            "suggestion": "Fix hyphenation break across lines.",
        })
    return issues


def _check_orphaned_headings(text: str) -> list[dict]:
    """Find headings without content between them."""
    issues = []
    for m in ORPHANED_HEADING.finditer(text):
        issues.append({
            "type": "orphaned_heading",
            "matched": m.group(1).strip(),
            "context": m.group(0),
            "suggestion": "Either add content under this heading or remove the heading.",
        })
    return issues


def _check_duplicate_phrases(text: str) -> list[dict]:
    """Find consecutive duplicate phrase repetitions."""
    issues = []
    for m in DUPLICATE_PHRASE.finditer(text):
        issues.append({
            "type": "duplicate_phrase",
            "matched": m.group(0).strip(),
            "context": text[max(0, m.start() - 40):m.end() + 40],
            "suggestion": "Remove duplicate consecutive phrase.",
        })
    return issues


def _check_orphan_than_clause(text: str) -> list[dict]:
    """Find 'than' clauses that are orphaned after comma splice."""
    issues = []
    for m in ORPHAN_THAN_CLAUSE.finditer(text):
        issues.append({
            "type": "orphan_than_clause",
            "matched": m.group(1).strip(),
            "context": text[max(0, m.start() - 40):m.end() + 40],
            "suggestion": "Reword to avoid comma splice with 'than' clause.",
        })
    return issues


def _check_incomplete_clauses(text: str) -> list[dict]:
    """Find sentences ending with incomplete subordinate clause."""
    issues = []
    for m in INCOMPLETE_CLAUSE.finditer(text):
        issues.append({
            "type": "incomplete_clause",
            "matched": m.group(0).strip(),
            "context": m.group(0),
            "suggestion": "Complete the subordinate clause or end with a full clause.",
        })
    return issues


def _check_comparative_no_completion(text: str) -> list[dict]:
    """Find comparative phrases that end with 'than' and nothing after."""
    issues = []
    for m in COMPARATIVE_NO_COMPLETION.finditer(text):
        issues.append({
            "type": "comparative_incomplete",
            "matched": m.group(0).strip(),
            "context": text[max(0, m.start() - 40):m.end() + 40],
            "suggestion": "Complete the comparative: 'more X than Y' not just 'more X than'.",
        })
    return issues


def run_language_sanity_pass(state: ReportState) -> ReportState:
    """T_NEW: LANGUAGE_SANITY_PASS - catch broken sentences before render.

    Position: After QA_GATE, before DOCX_RENDER (render phase).

    Returns state with language_sanity_report_path set.
    Hard fails on broken comparatives and orphaned headings.
    """
    draft_path = state.drafts.get("merged_draft_cited_md") or state.drafts.get("merged_draft_md")
    if not draft_path or not Path(draft_path).exists():
        # Can't check if no draft
        state.runtime["language_sanity_report_path"] = ""
        return state

    with open(draft_path, encoding="utf-8") as f:
        text = f.read()

    all_issues = []
    all_issues.extend(_check_incomplete_comparatives(text))
    all_issues.extend(_check_trailing_ellipses(text))
    all_issues.extend(_check_broken_hyphenation(text))
    all_issues.extend(_check_orphaned_headings(text))
    all_issues.extend(_check_duplicate_phrases(text))
    all_issues.extend(_check_orphan_than_clause(text))
    all_issues.extend(_check_incomplete_clauses(text))
    all_issues.extend(_check_comparative_no_completion(text))

    hard_issues = [i for i in all_issues if i["type"] in (
        "incomplete_comparative",
        "comparative_incomplete",
        "orphaned_heading",
        "broken_hyphenation",
    )]
    soft_issues = [i for i in all_issues if i["type"] not in (
        "incomplete_comparative",
        "comparative_incomplete",
        "orphaned_heading",
        "broken_hyphenation",
    )]

    report = {
        "job_id": state.job_id,
        "total_issues": len(all_issues),
        "hard_issues": len(hard_issues),
        "soft_issues": len(soft_issues),
        "issues": all_issues,
    }

    report_path = write_json_artifact(state, "language_sanity_report.json", report)
    state.runtime["language_sanity_report_path"] = str(report_path)

    if hard_issues:
        reasons = [f"{i['type']}: '{i['matched'][:50]}'" for i in hard_issues[:5]]
        raise QAHardBlockError(f"Language sanity failures: {', '.join(reasons)}")

    return state
