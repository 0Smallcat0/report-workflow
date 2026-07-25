"""ABSTRACT_CHECK - merged abstract validation and compression node.

MERGES: abstract_compress + abstract_sanity_check (Week 1 consolidation).

Design philosophy (from academic-report-simplify-retrospective):
  If the abstract is malformed, the agent should fix it, not the pipeline.
  This node validates and, if needed, performs minimal cleanup only.
  Complex structural reconstruction has been removed.

Position: After SECTION_DRAFT, replaces ABSTRACT_COMPRESS + ABSTRACT_SANITY_CHECK.

Responsibilities:
  1. Strip [CITE:...], [Source:...], and reference citation patterns
  2. Verify 5-section structure (## Background, ## Objective, ## Methods,
     ## Principal Findings, ## Significance) for academic_paper
  3. Word count gate: 180-220 words for academic_paper
  4. Sanity checks: trailing ellipses, unfinished sentences,
     incomplete comparatives, internal markers, placeholder text
  5. Hard fail: agent must rewrite; do NOT auto-repair

Reads:
  - state.drafts.section_drafts["abstract"]

Writes:
  - abstract_final.md
  - state.drafts["abstract_final"]
"""
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..language import count_words, detect_document_language
from ..runtime_support import PLACEHOLDER_TEXT
from ..policies import get_policy


# ------------------------------------------------------------------
# Patterns
# ------------------------------------------------------------------

_INCOMPLETE_COMPARATIVE = re.compile(
    r'\b(more|less|better|worse|higher|lower|greater|smaller|fewer)'
    r'\s+[a-z]+'
    r'\s+(?:than)\s*'
    r'(?:enforceable|applicable|sufficient|necessary|appropriate|adequate|effective|valid)(?:\s|$)',
    re.IGNORECASE
)
_INTERNAL_MARKER = re.compile(r'\[(?:CITE:|Source:|graphify:)[^\]]+\]', re.IGNORECASE)
_PLACEHOLDER_PAT = re.compile(re.escape(PLACEHOLDER_TEXT), re.IGNORECASE)

# Required section headings for academic abstract
_REQUIRED_ABSTRACT_HEADINGS = {
    "background", "objective", "methods", "principal findings", "significance"
}

_ABSTRACT_HEADING_ALIASES = {
    "methodology": "methods",
    "method": "methods",
    "principal finding": "principal findings",
    "findings": "principal findings",
}


# ------------------------------------------------------------------
# Stripping helpers
# ------------------------------------------------------------------

def _strip_markers(text: str) -> str:
    """Remove all internal workflow markers from abstract text."""
    text = re.sub(r'\[CITE:[^\]]+\]', '', text)
    text = re.sub(r'\[Source:[^\]]+\]', '', text)
    text = re.sub(r'\[graphify:[^\]]+\]', '', text)
    # Remove reference citations: (Author et al., 2020)
    text = re.sub(r'\([A-Z][a-z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-z]+))?(?:,?\s*\d{4}[a-z]?)\)', '', text)
    # Remove numbered citations: [1], [2-4]
    text = re.sub(r'\[[\d,\-]+(?:\s*,\s*[\d,\-]+)*\]', '', text)
    return text


def _count_words(text: str) -> int:
    return count_words(text)


# ------------------------------------------------------------------
# Structure detection
# ------------------------------------------------------------------

def _check_structure(text: str) -> list[str]:
    """Check abstract has required section headings.

    Returns list of error messages (empty = pass).
    """
    errors = []
    heading_counts: dict[str, int] = {}

    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'^##\s+([^:]+?)(?:\s*:?\s*)?$', line, re.IGNORECASE)
        if m:
            heading = m.group(1).strip().lower()
            heading = _ABSTRACT_HEADING_ALIASES.get(heading, heading)
            heading_counts[heading] = heading_counts.get(heading, 0) + 1

    found = set(heading_counts.keys())
    required = _REQUIRED_ABSTRACT_HEADINGS.copy()

    for heading in found:
        for req in list(required):
            if heading == req or req.startswith(heading) or heading.startswith(req):
                required.discard(req)

    if required:
        errors.append(
            f"Abstract missing required sections: {', '.join(sorted(required))}. "
            f"Found: {', '.join(sorted(found)) or 'none'}. "
            f"Use exactly: ## Background:, ## Objective:, ## Methods:, ## Principal Findings:, ## Significance:"
        )

    return errors


# ------------------------------------------------------------------
# Sanity checks (from abstract_sanity_check)
# ------------------------------------------------------------------

def _sanity_checks(text: str) -> list[str]:
    """Run all sanity checks. Returns list of error messages."""
    errors = []

    # Trailing ellipses
    for i, line in enumerate(text.split('\n'), 1):
        if re.search(r'\.{3,}$', line.rstrip()):
            errors.append(f"Line {i}: trailing ellipsis: {line.rstrip()[:60]!r}")

    # Incomplete comparatives
    for m in _INCOMPLETE_COMPARATIVE.finditer(text):
        errors.append(f"Incomplete comparative: {m.group(0)!r}")

    # Internal markers
    for m in _INTERNAL_MARKER.finditer(text):
        errors.append(f"Internal marker residue: {m.group(0)!r}")

    # Placeholder text
    if _PLACEHOLDER_PAT.search(text):
        errors.append(f"Placeholder text found: {PLACEHOLDER_TEXT!r}")

    return errors


#: count_words counts each CJK character as one unit, but the policy bounds are
#: English word counts, and an English word carries roughly two Chinese
#: characters of content — the conventional pairing is a 250-word English
#: abstract beside a 500-字 Chinese one. Comparing the two directly held every
#: Chinese abstract to about half its intended length.
CJK_ABSTRACT_SCALE = 2


def _word_count_check(text: str, family: str) -> list[str]:
    """Check word count is in range per policy."""
    errors = []
    words = _count_words(text)
    policy = get_policy(family)
    scale = CJK_ABSTRACT_SCALE if detect_document_language(text) == "zh" else 1
    minimum = policy.abstract.word_count_min * scale
    maximum = policy.abstract.word_count_max * scale
    unit = "characters" if scale > 1 else "words"
    if words < minimum:
        errors.append(
            f"Abstract too short: {words} {unit} (minimum {minimum} for {family})"
        )
    elif words > maximum:
        errors.append(
            f"Abstract too long: {words} {unit} (maximum {maximum} for {family})"
        )
    return errors


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_abstract_check(state: ReportState) -> ReportState:
    """ABSTRACT_CHECK - validate (and minimally clean) abstract for academic publication.

    Reads state.drafts.section_drafts["abstract"] (draft from agent).
    Writes state.drafts["abstract_final"] (cleaned publication-ready abstract).

    Hard blocks:
      - Missing required section headings for academic_paper
      - Word count out of range (180-220 for academic)
      - Trailing ellipses, incomplete sentences, internal markers
      - Placeholder text

    Does NOT attempt complex structural reconstruction.
    If validation fails, raises QAHardBlockError; agent must fix the draft.
    """
    section_drafts = state.drafts.get("section_drafts", {})
    abstract_path = section_drafts.get("abstract", "")
    family = state.spec.get("report_profile", "academic_paper")

    if not abstract_path or not Path(abstract_path).exists():
        # No abstract; let QA_GATE catch it
        return state

    try:
        raw_text = Path(abstract_path).read_text(encoding="utf-8")
    except Exception:
        return state

    if not raw_text.strip():
        return state

    all_errors: list[str] = []

    # Step 1: Strip internal markers
    cleaned = _strip_markers(raw_text)

    # Step 2: Structure check per policy
    policy = get_policy(family)
    if policy.abstract.structure_required:
        all_errors.extend(_check_structure(cleaned))

    # Step 3: Sanity checks (always run)
    all_errors.extend(_sanity_checks(cleaned))

    # Step 4: Word count check
    all_errors.extend(_word_count_check(cleaned, family))

    if all_errors:
        raise QAHardBlockError(
            f"ABSTRACT_CHECK failed: {len(all_errors)} issue(s):\n"
            + "\n".join(f"  - {e}" for e in all_errors)
        )

    # Write final abstract
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    final_path = run_dir / "abstract_final.md"
    final_path.write_text(cleaned, encoding="utf-8")

    state.drafts["abstract_final"] = str(final_path)
    return state
