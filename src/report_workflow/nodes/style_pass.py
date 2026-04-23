"""STYLE_PASS node - merged language sanity + publication style for render phase.

MERGES:
  - language_sanity_pass (broken sentences, incomplete comparatives, orphaned fragments)
  - publication_style_pass (weasel words, marketing language, weak verbs, topic sentences)

Position: After QA_GATE, before DOCX_RENDER (render phase).

Responsibilities:
  1. Language sanity: incomplete comparatives, trailing ellipses, broken hyphenation,
     orphaned headings, duplicate phrases, orphan than clauses, incomplete clauses
  2. Publication style: weasel word removal, marketing language replacement,
     weak verb strengthening, topic sentence improvement

Output:
  - style_pass_report.json
  - Hard failures block render
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact


# ------------------------------------------------------------------
# Language sanity patterns (from language_sanity_pass)
# ------------------------------------------------------------------

INCOMPLETE_COMPARATIVE = re.compile(
    r"\bmore\s+(\w+(?:\s+\w+){0,4})\s+than\s*"
    r"(?="
    r"[a-z]+\s+(?:by|from|with|to|for|of|on|at|than)\s*"
    r"|\s*$"
    r"|[A-Z][a-z]+\s*$"
    r"|\s*\.\.\."
    r"|\s*[,;]\s*$"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

MID_SENTENCE_ELLIPSIS = re.compile(r"\w\b\s*\.{2,}(?=\s+[A-Z])", re.MULTILINE)
BROKEN_HYPHENATION = re.compile(r"\b\w+-\n\w+\b", re.MULTILINE)
ORPHANED_HEADING = re.compile(r"(^#{1,3}\s+[^\n]+)\n\n(?=#{1,3}\s|\Z)", re.MULTILINE)
DUPLICATE_PHRASE = re.compile(r"\b(\b\w+(?:\s+\w+){2,})\b\s+(?:\1\s+){1,}", re.IGNORECASE)
ORPHAN_THAN_CLAUSE = re.compile(r"(?<=[,;])\s+(than\s+(?:by|for|to|of|with|from|on|at)\s+\w+)", re.IGNORECASE)
INCOMPLETE_CLAUSE = re.compile(
    r"[.!?]\s*((?:that|which|because|when|where|while|although)\s+[A-Z][a-z]*(?:\s+(?:is|are|was|were|has|have|had|will|would|can|could|may|might|should)\s+)?)$",
    re.MULTILINE,
)
COMPARATIVE_NO_COMPLETION = re.compile(
    r"\b(more|less|better|worse|higher|lower|greater|smaller|fewer)\s+\w+(?:\s+\w+){0,3}\s+than\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ------------------------------------------------------------------
# Publication style patterns (from publication_style_pass)
# ------------------------------------------------------------------

WEASEL_WORDS = {
    "very": "", "really": "", "basically": "", "actually": "", "literally": "",
    "simply": "", "just": "", "quite": "", "somewhat": "", "fairly": "", "pretty": "",
}

MARKETING_PATTERNS = [
    (r"\bstate-of-the-art\b", "advanced"),
    (r"\bcutting-edge\b", "advanced"),
    (r"\bnext-generation\b", "advanced"),
    (r"\bpioneering\b", "innovative"),
    (r"\brevolutionize[sd]?\b", "significantly improved"),
    (r"\bgame-chang(?:er|ing)\b", "significant"),
    (r"\bbreakthrough\b", "significant advance"),
    (r"\bworld-class\b", "high quality"),
    (r"\bleading-edge\b", "advanced"),
]

WEAK_VERBS = {
    r"\bmakes use of\b": "uses",
    r"\butilizes\b": "uses",
    r"\bperforms an analysis of\b": "analyzes",
    r"\bcarries out\b": "conducts",
    r"\bis able to\b": "can",
    r"\bin order to\b": "to",
    r"\bdue to the fact that\b": "because",
    r"\bin the event that\b": "if",
    r"\bfor the purpose of\b": "to",
}


# ------------------------------------------------------------------
# Language sanity checks
# ------------------------------------------------------------------

def _check_language_sanity(text: str) -> tuple[list[dict], list[dict]]:
    """Run all language sanity checks. Returns (hard_issues, soft_issues)."""
    issues = []

    for m in INCOMPLETE_COMPARATIVE.finditer(text):
        ctx = text[max(0, m.start() - 60):m.end() + 60]
        issues.append({"type": "incomplete_comparative", "matched": m.group(0).strip(), "context": ctx})

    for m in MID_SENTENCE_ELLIPSIS.finditer(text):
        ctx = text[max(0, m.start() - 60):m.end() + 60]
        issues.append({"type": "trailing_ellipsis", "matched": m.group(0).strip(), "context": ctx})

    for m in BROKEN_HYPHENATION.finditer(text):
        issues.append({"type": "broken_hyphenation", "matched": m.group(0).replace("\n", ""), "context": m.group(0)})

    for m in ORPHANED_HEADING.finditer(text):
        issues.append({"type": "orphaned_heading", "matched": m.group(1).strip(), "context": m.group(0)})

    for m in DUPLICATE_PHRASE.finditer(text):
        ctx = text[max(0, m.start() - 40):m.end() + 40]
        issues.append({"type": "duplicate_phrase", "matched": m.group(0).strip(), "context": ctx})

    for m in ORPHAN_THAN_CLAUSE.finditer(text):
        ctx = text[max(0, m.start() - 40):m.end() + 40]
        issues.append({"type": "orphan_than_clause", "matched": m.group(1).strip(), "context": ctx})

    for m in INCOMPLETE_CLAUSE.finditer(text):
        issues.append({"type": "incomplete_clause", "matched": m.group(0).strip(), "context": m.group(0)})

    for m in COMPARATIVE_NO_COMPLETION.finditer(text):
        ctx = text[max(0, m.start() - 40):m.end() + 40]
        issues.append({"type": "comparative_incomplete", "matched": m.group(0).strip(), "context": ctx})

    hard_types = {
        "incomplete_comparative", "comparative_incomplete",
        "orphaned_heading", "broken_hyphenation",
        "duplicate_phrase",         # repeated consecutive phrases — hard fail
        "orphan_than_clause",        # "more X than" fragments — hard fail
    }
    hard_issues = [i for i in issues if i["type"] in hard_types]
    soft_issues = [i for i in issues if i["type"] not in hard_types]
    return hard_issues, soft_issues


# ------------------------------------------------------------------
# Publication style helpers
# ------------------------------------------------------------------

def _fix_weasel_words(text: str) -> str:
    for word, replacement in WEASEL_WORDS.items():
        pattern = r'\b' + word + r'\b'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def _fix_marketing_language(text: str) -> str:
    for pattern, replacement in MARKETING_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _strengthen_weak_verbs(text: str) -> str:
    for pattern, replacement in WEAK_VERBS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _compress_sentence(sentence: str) -> str:
    sentence = re.sub(r'\([^)]*\bvery\b[^)]*\)', '', sentence)
    sentence = re.sub(r'\bthat being said\b', 'however', sentence)
    sentence = re.sub(r'\bhaving said that\b', 'however', sentence)
    sentence = re.sub(r'\b(\w+),\s+\1\b', r'\1', sentence)
    return sentence


def _improve_topic_sentence(sentence: str) -> str:
    sentence = re.sub(r'^In this (paper|study|article),\s*', '', sentence, flags=re.IGNORECASE)
    sentence = re.sub(r"It is (important|interesting|notable) to note that\s+", '', sentence, flags=re.IGNORECASE)
    return sentence


def _apply_admissions_polish(text: str) -> str:
    """Light rewrite pass for admissions-facing project reports."""
    replacements = [
        (r"\bThis study presents\b", "This project develops"),
        (r"\bThis study\b", "This project"),
        (r"\bThis paper\b", "This report"),
        (r"\bThe remainder of this paper is organized as follows\.[^.]*\.", ""),
        (r"\bFor graduate research purposes,\s*", ""),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _process_paragraph(para: str) -> str:
    if not para.strip():
        return para
    sentences = re.split(r'(?<=[.!?])\s+', para)
    if not sentences:
        return para
    sentences[0] = _improve_topic_sentence(sentences[0])
    sentences = [_compress_sentence(s) for s in sentences]
    return ' '.join(sentences)


def _is_markdown_table(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    if not all("|" in line for line in lines[:2]):
        return False
    return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", lines[1]))


def _is_structural_markdown_block(block: str) -> bool:
    stripped = block.strip()
    if not stripped:
        return True
    lines = stripped.splitlines()
    first = lines[0].strip()
    if first.startswith(("```", "~~~")):
        return True
    if re.match(r"^#{1,6}\s+", first):
        return True
    if first.startswith("!["):
        return True
    if _is_markdown_table(stripped):
        return True
    if all(re.match(r"^\s*[-*+]\s+", line) for line in lines if line.strip()):
        return True
    if all(re.match(r"^\s*\d+\.\s+", line) for line in lines if line.strip()):
        return True
    return False


def _split_markdown_blocks(text: str) -> list[str]:
    """Split markdown into blocks without breaking fenced code or pipe tables."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append("\n".join(current).strip("\n"))
            current = []

    for line in text.splitlines():
        stripped = line.strip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not in_fence:
                flush()
                in_fence = True
                fence_marker = marker
                current.append(line)
            else:
                current.append(line)
                if marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                    flush()
            continue

        if in_fence:
            current.append(line)
            continue

        if not stripped:
            flush()
            continue

        # Headings, images, and list/table starts become their own block shape.
        current.append(line)

    flush()
    return blocks


def _check_section_opener(section_name: str, text: str) -> list[str]:
    issues = []
    if not text.strip():
        return issues
    first_sentence = text.split('.')[0] if '.' in text else text
    weak_openers = [
        "we show that", "we demonstrate that", "we found that", "our results show",
        "this paper presents", "this study shows", "the goal of this paper",
    ]
    for opener in weak_openers:
        if opener.lower() in first_sentence.lower():
            issues.append(f"{section_name}: starts with '{opener}' - consider academic phrasing")
    if re.search(r'\bwe\b', first_sentence) and 'introduction' in section_name.lower():
        issues.append(f"{section_name}: uses 'we' in introduction - prefer passive or impersonal")
    return issues


def _apply_style_polish(text: str) -> tuple[str, list[str]]:
    """Apply publication style polish. Returns (polished_text, style_issues)."""
    blocks = _split_markdown_blocks(text)
    styled_blocks = []
    all_style_issues = []

    previous_heading = ""
    for block in blocks:
        if not block.strip():
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", block.strip())
        if heading_match:
            previous_heading = heading_match.group(2).strip()
            styled_blocks.append(block)
            continue
        if _is_structural_markdown_block(block):
            styled_blocks.append(block)
            continue

        all_style_issues.extend(_check_section_opener(previous_heading, block))
        processed = _process_paragraph(block)
        processed = _fix_weasel_words(processed)
        processed = _fix_marketing_language(processed)
        processed = _strengthen_weak_verbs(processed)
        styled_blocks.append(processed)

    return "\n\n".join(styled_blocks), all_style_issues


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_style_pass(state: ReportState) -> ReportState:
    """STYLE_PASS - merged language sanity + publication style check.

    Position: After QA_GATE, before DOCX_RENDER (render phase).

    Reads: merged_draft_cited_md or merged_draft_md
    Writes: style_pass_report.json
    Hard fails on: incomplete comparatives, orphaned headings, broken hyphenation
    """
    draft_path = state.drafts.get("merged_draft_cited_md") or state.drafts.get("merged_draft_md")
    if not draft_path or not Path(draft_path).exists():
        state.runtime["style_pass_report_path"] = ""
        return state

    with open(draft_path, encoding="utf-8") as f:
        original_text = f.read()

    # Step 1: Language sanity checks
    hard_lang_issues, soft_lang_issues = _check_language_sanity(original_text)

    if hard_lang_issues:
        reasons = [f"{i['type']}: '{i['matched'][:50]}'" for i in hard_lang_issues[:5]]
        raise QAHardBlockError(f"Style pass language failures: {', '.join(reasons)}")

    # Step 2: Apply publication style polish
    polished_text, style_issues = _apply_style_polish(original_text)
    if state.spec.get("report_family_detail") == "admissions_report":
        polished_text = _apply_admissions_polish(polished_text)

    # Write polished draft
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    styled_path = run_dir / "publication_style_draft.md"
    with open(styled_path, "w", encoding="utf-8") as f:
        f.write(polished_text)

    state.drafts["publication_style_draft"] = str(styled_path)

    # Write report
    report = {
        "job_id": state.job_id,
        "original_length": len(original_text),
        "polished_length": len(polished_text),
        "hard_language_issues": len(hard_lang_issues),
        "soft_language_issues": len(soft_lang_issues),
        "style_issues": style_issues,
        "language_issues": hard_lang_issues + soft_lang_issues,
    }
    report_path = write_json_artifact(state, "style_pass_report.json", report)
    state.runtime["style_pass_report_path"] = str(report_path)

    return state
