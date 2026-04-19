"""PUBLICATION_STYLE_PASS node - polish prose to academic publication standard.

Sits between QA_GATE and DOCX_RENDER in the render phase.

Applies publication-style polish:
  - Compress verbose sentences
  - Strengthen topic sentences (first sentence of each paragraph)
  - Reduce redundancy across paragraphs
  - Uniform academic tone (passive voice where appropriate)
  - Fix weasel words and marketing language
  - Ensure IMRaD section openers are proper academic prose

Output:
  - publication_style_draft.md (replaces merged draft for rendering)
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact


# ------------------------------------------------------------------
# Academic style rules
# ------------------------------------------------------------------

# Weasel words to remove or replace
WEASEL_WORDS = {
    "very": "",
    "really": "",
    "basically": "",
    "actually": "",
    "literally": "",
    "simply": "",
    "just": "",
    "quite": "",
    "somewhat": "",
    "fairly": "",
    "pretty": "",
    "rather": "",
}

# Marketing/sales language patterns
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

# Weak verbs that need strengthening
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


def _fix_weasel_words(text: str) -> str:
    """Remove or replace weasel words."""
    for word, replacement in WEASEL_WORDS.items():
        pattern = r'\b' + word + r'\b'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _fix_marketing_language(text: str) -> str:
    """Replace marketing language with academic alternatives."""
    for pattern, replacement in MARKETING_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _strengthen_weak_verbs(text: str) -> str:
    """Replace weak/hedging verb phrases with stronger alternatives."""
    for pattern, replacement in WEAK_VERBS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _compress_sentence(sentence: str) -> str:
    """Compress a single sentence by removing filler."""
    sentence = re.sub(r'\([^)]*\bvery\b[^)]*\)', '', sentence)
    sentence = re.sub(r'\bthat being said\b', 'however', sentence)
    sentence = re.sub(r'\bhaving said that\b', 'however', sentence)
    sentence = re.sub(r'\b(\w+),\s+\1\b', r'\1', sentence)
    return sentence


def _improve_topic_sentence(sentence: str) -> str:
    """Strengthen a topic sentence (first sentence of paragraph)."""
    sentence = re.sub(r'^In this (paper|study|article),\s*', '', sentence, flags=re.IGNORECASE)
    sentence = re.sub(r"It is (important|interesting|notable) to note that\s+", '', sentence, flags=re.IGNORECASE)
    return sentence


def _process_paragraph(para: str) -> str:
    """Process a single paragraph."""
    if not para.strip():
        return para
    sentences = re.split(r'(?<=[.!?])\s+', para)
    if not sentences:
        return para
    sentences[0] = _improve_topic_sentence(sentences[0])
    sentences = [_compress_sentence(s) for s in sentences]
    return ' '.join(sentences)


def _check_section_opener(section_name: str, text: str) -> list[str]:
    """Check if a section has a proper academic opener."""
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


def run_publication_style_pass(state: ReportState) -> ReportState:
    """T_NEW: PUBLICATION_STYLE_PASS - polish prose to academic publication standard.

    Position: After QA_GATE, before DOCX_RENDER (render phase).
    """
    draft_path = state.drafts.get("merged_draft_cited_md") or state.drafts.get("merged_draft_md")
    if not draft_path or not Path(draft_path).exists():
        return state

    with open(draft_path, encoding="utf-8") as f:
        original_text = f.read()

    sections = re.split(r'(?=^#{1,3}\s+)', original_text, flags=re.MULTILINE)
    styled_sections = []
    all_style_issues = []

    for section in sections:
        if not section.strip():
            continue
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', section.strip())
        if heading_match:
            heading_level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            content = section[len(heading_match.group(0)):].strip()
            processed_content = _process_paragraph(content)
            if content.strip():
                all_style_issues.extend(_check_section_opener(heading_text, content))
            processed_content = _fix_weasel_words(processed_content)
            processed_content = _fix_marketing_language(processed_content)
            processed_content = _strengthen_weak_verbs(processed_content)
            styled_sections.append(f"{'#' * heading_level} {heading_text}\n\n{processed_content}")
        else:
            processed = _process_paragraph(section)
            processed = _fix_weasel_words(processed)
            processed = _fix_marketing_language(processed)
            processed = _strengthen_weak_verbs(processed)
            styled_sections.append(processed)

    styled_text = "\n\n".join(styled_sections)
    run_dir = WORKFLOW_RUNS_DIR / state.job_id

    styled_path = run_dir / "publication_style_draft.md"
    with open(styled_path, "w", encoding="utf-8") as f:
        f.write(styled_text)

    issues_report = {
        "job_id": state.job_id,
        "original_length": len(original_text),
        "styled_length": len(styled_text),
        "issues_found": len(all_style_issues),
        "issues": all_style_issues,
    }
    issues_path = run_dir / "style_issues_report.json"
    with open(issues_path, "w", encoding="utf-8") as f:
        json.dump(issues_report, f, indent=2)

    state.drafts["publication_style_draft"] = str(styled_path)
    state.drafts["style_issues_report_path"] = str(issues_path)
    return state