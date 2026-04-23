"""FRONT_MATTER_BUILD node - assemble title page, author block, keywords for academic reports.

ACADEMIC MODE OVERRIDE (2026-04-19):
  For report_family == "academic_report", placeholder values in author_block,
  affiliation_block, or correspondence field raise QAHardBlockError.
  Placeholder patterns: [Author Name], [email@...], [Department of...], etc.
  Previously this node only emitted warnings. Now it hard-blocks for academic mode.

Sits between SECTION_PLAN_FREEZE and SECTION_DRAFT in the validate phase.
For academic_report family, front matter is REQUIRED.
For other families, front matter is optional.

Outputs:
  - front_matter.json (artifact)
  - state.plan["front_matter"] populated
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..policies import get_policy
from ..runtime_support import write_json_artifact


# ------------------------------------------------------------------
# ICMJE / academic publication front matter requirements
# ------------------------------------------------------------------
# - title (required)
# - short_title / running title (optional)
# - author block (required for academic)
# - affiliation block (required for academic)
# - keywords (required for academic - 4-6 terms)
# - correspondence (required for academic)
# - acknowledgements (optional)
# - funding / conflict note (optional)
# ------------------------------------------------------------------


def _parse_author_from_user_prompt(user_prompt: str) -> str:
    """Extract author name from user prompt if recognizable."""
    # Common patterns: "by Author", "Author Name:", "author:"
    patterns = [
        # "Author: Full Name" or "Author - Full Name"
        r"(?:author[:\-\s]+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        # "by Author Full Name"
        r"(?:by\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:\s*,|\s*\n|$)",
        # "Full Name (Author)" or "Full Name, Author"
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[,;(]?\s*(?:author|student|researcher)",
        # Standalone 2-3 word name at start of prompt
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[,.\n]",
    ]
    for pattern in patterns:
        m = re.search(pattern, user_prompt, re.IGNORECASE | re.MULTILINE)
        if m:
            name = m.group(1).strip()
            # Filter out obvious non-names
            if len(name) > 5 and not any(kw in name.lower() for kw in ["report", "thesis", "study", "paper", "analysis"]):
                return name
    return ""


def _parse_title_from_user_prompt(user_prompt: str) -> str:
    """Extract title from user prompt if recognizable."""
    lines = user_prompt.split('\n')
    for line in lines[:5]:  # Check first 5 lines
        line = line.strip()
        # Skip very short lines
        if len(line) < 10:
            continue
        # Skip lines that look like commands/paths
        if re.match(r'^[a-zA-Z]:|^\s*--|^pip |^python |^report-workflow', line):
            continue
        # Skip lines that look like file references
        if re.search(r'\.(txt|docx|pdf|csv|xlsx|json)\b', line, re.IGNORECASE):
            continue
        # Lines that look like titles (may have subtitle separator)
        if len(line) > 15 and len(line) < 200:
            # Title-like: starts capitalized or has em-dash/subtitle separator
            if line[0].isupper() or '—' in line or ':' in line[:50]:
                # Clean up any prefix markers
                cleaned = re.sub(r'^(?:title[:\-\s]+|"#?\s*)', '', line, flags=re.IGNORECASE).strip()
                if cleaned and len(cleaned) > 10:
                    return cleaned
    return ""


def _parse_affiliation_from_user_prompt(user_prompt: str) -> str:
    """Extract affiliation/institution from user prompt if recognizable."""
    patterns = [
        # "Affiliation: ..." or "Institution: ..."
        r"(?:affiliation|institution|department|university|company|organization)[:\s]+([^\n]{10,100})",
        # "at Institution Name"
        r"\bat\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, user_prompt, re.IGNORECASE)
        if m:
            affil = m.group(1).strip().rstrip(',.;')
            if len(affil) > 5:
                return affil
    return ""


# Stopwords to filter from keyword extraction
# Covers: capitalized sentence-starts, Python identifiers, generic academic words
_KEYWORD_STOPWORDS = {
    # Capitalized sentence-starts / pronouns / adverbs (very common false positives)
    "The", "This", "That", "These", "Those", "A", "An",
    "No", "Not", "But", "And", "Or", "So", "If", "Then", "Else",
    "When", "Where", "Which", "While", "Who", "What", "Why", "How",
    "However", "Nevertheless", "Moreover", "Furthermore", "Additionally",
    "Therefore", "Thus", "Hence", "Consequently",
    "First", "Second", "Third", "Finally", "Lastly",
    "Meanwhile", "Nonetheless",
    "It", "Its", "He", "She", "They", "We", "You", "I",
    "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Much", "Many", "More", "Most", "Less", "Least", "Very",
    "Only", "Even", "Just", "Still", "Already", "Yet",
    # Python / programming identifiers
    "Python", "Module", "Class", "Function", "Method", "Def", "Import",
    "Return", "Yield", "Raise", "Lambda", "Decorator",
    "Rule", "Operand", "Operator", "Expression", "Statement", "Variable",
    "Parameter", "Argument", "Attribute", "Property", "Element", "Node",
    "List", "Dict", "Tuple", "Set", "Array", "Object", "Instance",
    "String", "Integer", "Float", "Boolean", "Number",
    "None", "True", "False", "Self", "Cls",
    "Assert", "Break", "Continue", "Del", "Exec", "Global", "Nonlocal",
    "Pass", "Print", "In", "Is", "As", "Async", "Await",
    # Generic academic/prose words
    "Analysis", "Study", "Research", "Report", "Paper", "System", "Method",
    "Results", "Finding", "Findings", "Discussion", "Conclusion", "Abstract",
    "Introduction", "Background", "Objective", "Methods", "Data", "Source",
    "Chapter", "Section", "Figure", "Table", "Equation", "Example",
    "Note", "Notes", "See", "Also", "Thus", "Therefore", "However",
    "Context", "Strategy", "Approach", "Framework", "Architecture",
    "Design", "Implementation", "Performance", "Efficiency", "Validation",
    "Problem", "Solution", "Result", "Outcome", "Process", "Pipeline",
    "Model", "Algorithm", "Technique", "Mechanism", "Structure",
    "Component", "Interface", "Protocol", "Contract", "Specification",
    "Type", "Schema", "Format", "Syntax", "Semantics",
    "Case", "Example", "Sample", "Instance",
    "Use", "Used", "Using", "Based", "With", "From", "Into", "During",
    "Such", "Each", "Every", "Any", "All", "Both", "Same",
    "After", "Before", "Under", "Over", "Through", "Across", "Between",
    "Can", "May", "Must", "Shall", "Will", "Would", "Could", "Should",
    "Need", "Needs", "Want", "Wants", "Seem", "Seems", "Appear", "Appears",
}

# Regex patterns for INVALID keywords — hard-block these during extraction
_INVALID_KEYWORD_PATTERNS = [
    # Bare section/figure numbering: "Figure 1", "Table 2", "Section 3", "Chapter 4"
    re.compile(r"^\s*(Figure|Table|Section|Chapter|Algorithm|Equation|Listing)\s+\d+", re.IGNORECASE),
    # Pure numeric or too short
    re.compile(r"^\s*\d+\s*$"),
    # Contains internal underscores (code identifiers leaking through)
    re.compile(r"_"),
    # All-caps abbreviations that are actually acronyms not keywords (URL, API, SQL, etc.)
    re.compile(r"^[A-Z]{2,}$"),  # Too short all-caps
]


def _is_valid_keyword(phrase: str) -> bool:
    """Return True if phrase is a valid academic keyword.

    Rejects:
      - Section/figure/table numbering ("Figure 1")
      - Pure numbers
      - Code identifiers with underscores
      - Single all-caps acronyms
    """
    phrase_stripped = phrase.strip()
    for pattern in _INVALID_KEYWORD_PATTERNS:
        if pattern.search(phrase_stripped):
            return False
    # Must have at least 2 alphabetic characters
    if sum(c.isalpha() for c in phrase_stripped) < 2:
        return False
    return True


def _extract_keywords_from_evidence(evidence_ledger_path: str | None) -> list[str]:
    """Extract potential keywords from evidence ledger.

    Post-processing: only keeps phrases that are either in the research pool,
    successfully mapped by the implementation→research map, or appear as
    claim topic_tags. This prevents generic noun phrases like "Summary",
    "God Nodes", "Reduce", "Input" from polluting front matter keywords.
    """
    keywords = []
    if not evidence_ledger_path or not Path(evidence_ledger_path).exists():
        return keywords

    # Build the accept-list once
    research_lower = {k.lower() for k in _RESEARCH_KEYWORD_POOL}
    impl_map_lower = set(k.lower() for k in _IMPLEMENTATION_TO_RESEARCH_KEYWORD_MAP)
    impl_values_lower = set()
    for v in _IMPLEMENTATION_TO_RESEARCH_KEYWORD_MAP.values():
        for term in v.split(", "):
            impl_values_lower.add(term.lower())

    try:
        with open(evidence_ledger_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    # Extract from claim_text or content snippets
                    text = entry.get("claim_text", "") + " " + entry.get("content", "")
                    # Look for capitalized noun phrases (potential technical terms)
                    phrases = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text)
                    # Filter to likely keywords (1-3 words, technical terms, not stopwords)
                    stopword_set_lower = {kw.lower() for kw in _KEYWORD_STOPWORDS}
                    for phrase in phrases:
                        phrase_lower = phrase.lower()
                        if phrase in _KEYWORD_STOPWORDS:
                            continue
                        if phrase_lower in stopword_set_lower:
                            continue
                        # Reject multi-word phrases where ANY word is a stopword
                        # (prevents "The Context", "No Strategy", "Rule Operand" etc.)
                        words_in_phrase = phrase_lower.split()
                        if len(words_in_phrase) > 1:
                            if any(w in _KEYWORD_STOPWORDS or w.capitalize() in _KEYWORD_STOPWORDS or w in stopword_set_lower for w in words_in_phrase):
                                continue
                        # Hard-block invalid keyword patterns (Figure 1, _underscore, etc.)
                        if not _is_valid_keyword(phrase):
                            continue
                        # Only accept if phrase is in research pool, maps to research term,
                        # or is an implementation key — prevents generic noun phrases
                        if phrase_lower not in research_lower and \
                           phrase_lower not in impl_map_lower and \
                           phrase_lower not in impl_values_lower:
                            continue
                        if len(phrase.split()) in (1, 2, 3) and phrase not in keywords:
                            if len(keywords) < 12:  # Extract more for later enrichment
                                keywords.append(phrase)
    except Exception:
        pass

    return keywords


# Mapping from implementation-level terms to research-level academic keywords
_IMPLEMENTATION_TO_RESEARCH_KEYWORD_MAP = {
    "Backtrader": "algorithmic trading",
    "Pydantic": "schema validation",
    "ASTBuilder": "compiler architecture",
    "AST": "abstract syntax tree",
    "Sharpe": "risk-adjusted returns",
    "Bayesian": "Bayesian inference",
    "HMM": "hidden Markov model",
    "HRP": "hierarchical risk parity",
    "DRL": "deep reinforcement learning",
    "Ollama": "local large language models",
    "Gemini": "LLM integration",
    "StrategyIR": "domain-specific language",
    "Backtest": "strategy backtesting",
    "Kelly": "optimal position sizing",
    "Corpus": "code corpus analysis",
    "graphify": "graph-based analysis",
    "Community Detection": "graph community detection",
}

# Research-level keywords that should be included when relevant evidence exists
_RESEARCH_KEYWORD_POOL = [
    "algorithmic trading",
    "domain-specific language",
    "compiler architecture",
    "strategy verification",
    "large language models",
    "quantitative finance",
    "risk-adjusted returns",
    "hidden Markov model",
    "hierarchical risk parity",
    "Bayesian inference",
    "schema validation",
    "graph-based analysis",
    "compiler design",
    "strategy generation",
    "formal verification",
]

_GENERIC_METADATA_VALUES = {
    "author",
    "independent researcher",
    "author@example.com",
    "untitled report",
    "research author",
    "research university",
    "department of computer science, research university",
    "research@university.edu",
}

_PROMPT_LEAK_PATTERNS = [
    re.compile(r"\brevise\s+the\s+base\s+document\b", re.IGNORECASE),
    re.compile(r"\bwrite\s+an?\s+academic\s+report\b", re.IGNORECASE),
    re.compile(r"\bgenerate\s+an?\s+academic\s+report\b", re.IGNORECASE),
]

_THESIS_ALIGNED_KEYWORDS = [
    "deterministic compilation",
    "StrategyIR",
    "domain-specific intermediate representation",
    "abstract syntax tree compilation",
    "strategy verification",
    "constrained large language models",
]


def _structured_front_matter_from_spec(spec: dict) -> dict:
    """Return caller-provided structured front matter fields only."""
    raw = spec.get("front_matter") or {}
    if not isinstance(raw, dict):
        return {}
    allowed = {
        "title",
        "short_title",
        "author_block",
        "affiliation_block",
        "correspondence",
        "keywords",
        "acknowledgements",
        "funding",
        "conflict_note",
    }
    return {key: value for key, value in raw.items() if key in allowed and value}


def _parse_preamble_metadata_line(line: str) -> tuple[str, str] | None:
    """Parse plain or Markdown-bold front matter lines into (field, value)."""
    match = re.match(
        r"^\s*\**\s*(Author|Affiliation|Correspondence|Keywords)\s*:\s*\**\s*(.*?)\s*\**\s*$",
        line.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    field = match.group(1).lower()
    value = match.group(2).strip().strip("*").strip()
    return field, value


def _select_thesis_aligned_keywords(user_prompt: str = "") -> list[str]:
    """Select stable admissions-facing keywords from the thesis spine."""
    return list(_THESIS_ALIGNED_KEYWORDS)


def _enrich_keywords_to_research_level(
    raw_keywords: list[str],
    claim_matrix: dict | None = None,
    user_prompt: str = "",
) -> list[str]:
    """Map implementation-level terms to research-level keywords.

    1. Replace known implementation terms with their research equivalents.
    2. If claim_matrix is available, look for topic_tags and use those as keywords.
    3. Fall back to research keyword pool when evidence is thin.
    """
    enriched: list[str] = []
    seen_lower: set[str] = set()

    # Step 1: Map implementation terms to research terms
    for kw in raw_keywords:
        kw_lower = kw.lower()
        if kw_lower in seen_lower:
            continue
        # Direct mapping
        if kw_lower in _IMPLEMENTATION_TO_RESEARCH_KEYWORD_MAP:
            mapped = _IMPLEMENTATION_TO_RESEARCH_KEYWORD_MAP[kw_lower]
            for term in mapped.split(", "):
                t_lower = term.lower()
                if t_lower not in seen_lower:
                    enriched.append(term)
                    seen_lower.add(t_lower)
        else:
            # Keep as-is if not a stopword and not already seen
            if kw_lower not in seen_lower:
                enriched.append(kw)
                seen_lower.add(kw_lower)

    # Step 2: Pull keywords from claim matrix topic_tags if available
    if claim_matrix:
        for claim in claim_matrix.get("claims", []):
            for tag in claim.get("topic_tags", []):
                tag_lower = tag.lower()
                if tag_lower not in seen_lower:
                    enriched.append(tag)
                    seen_lower.add(tag_lower)

    # Step 3: If we still have fewer than 4, supplement from research pool
    if len(enriched) < 4:
        for kw in _RESEARCH_KEYWORD_POOL:
            kw_lower = kw.lower()
            if kw_lower not in seen_lower:
                # Only add if the term appears in user_prompt or evidence
                prompt_lower = user_prompt.lower()
                if kw_lower in prompt_lower or any(kw_lower in k.lower() for k in raw_keywords):
                    enriched.append(kw)
                    seen_lower.add(kw_lower)
                    if len(enriched) >= 6:
                        break

    return enriched[:6]  # Return max 6 keywords


def _build_front_matter(state: ReportState) -> dict:
    """Build the front matter from blueprint, spec, and evidence."""
    blueprint = state.plan.get("blueprint", {})
    spec = state.spec
    report_family = spec.get("report_family", "academic_report")
    user_prompt = spec.get("user_prompt", "")

    # Get blueprint front_matter template (may be empty/dict)
    blueprint_fm = blueprint.get("front_matter", {}) or {}

    # Build front matter with ICMJE-compliant structure
    front_matter = {
        "title": blueprint_fm.get("title", ""),
        "short_title": blueprint_fm.get("short_title", ""),
        "author_block": blueprint_fm.get("author_block", ""),
        "affiliation_block": blueprint_fm.get("affiliation_block", ""),
        "correspondence": blueprint_fm.get("correspondence", ""),
        "keywords": list(blueprint_fm.get("keywords", [])),
        "acknowledgements": blueprint_fm.get("acknowledgements", ""),
        "funding": blueprint_fm.get("funding", ""),
        "conflict_note": blueprint_fm.get("conflict_note", ""),
    }
    structured_front_matter = _structured_front_matter_from_spec(spec)
    front_matter.update(structured_front_matter)

    # For academic_report: ensure required fields
    policy = get_policy(report_family, spec.get("report_family_detail") or None)
    if policy.front_matter.auto_populate_missing_fields:
        # In revise_existing mode: try to extract front matter from the preamble
        # in base_document_sections before falling back to user_prompt parsing.
        task_intent = state.spec.get("task_intent", "new_draft")
        if task_intent == "revise_existing":
            # base_document_sections may not be embedded in the checkpoint
            # (SourcesState Pydantic model drops unknown fields on deserialization).
            # Fall back to loading from the file path if present.
            base_sections: dict = state.sources.get("base_document_sections", {})
            if not base_sections:
                bd_path = state.sources.get("base_document_sections_path")
                if bd_path and Path(bd_path).exists():
                    with open(bd_path, encoding="utf-8") as _f:
                        base_sections = json.load(_f)
            preamble_text = base_sections.get("preamble", "")
            if preamble_text:
                # Parse structured fields from preamble block.
                # Title: first non-empty line before the first "---" separator.
                # Supports both "# Title" markdown headings and plain text titles.
                # Author / Affiliation / Correspondence / Keywords:
                #   Supports both plain "Author: ..." and Markdown bold "**Author:** ..." formats.
                first_dash = preamble_text.find("\n---")
                if first_dash > 10:
                    title_candidate = preamble_text[:first_dash].strip()
                    # Strip leading '#' markdown heading marker
                    title_candidate = title_candidate.lstrip("#").strip()
                    if title_candidate and len(title_candidate) > 10 and not structured_front_matter.get("title"):
                        # Cap at Nature's recommended 120 characters
                        if len(title_candidate) > 120:
                            title_candidate = title_candidate[:120].rstrip() + "..."
                        front_matter["title"] = title_candidate

                # Parse metadata fields; accept both plain and Markdown-bold formats.
                # Examples: "Author: A", "**Author:** A", "Keywords: ** x, y".
                for line in preamble_text.split("\n"):
                    parsed = _parse_preamble_metadata_line(line)
                    if not parsed:
                        continue
                    field, value = parsed
                    if field == "author" and not structured_front_matter.get("author_block") and not front_matter.get("author_block"):
                        front_matter["author_block"] = value
                    elif field == "affiliation" and not structured_front_matter.get("affiliation_block") and not front_matter.get("affiliation_block"):
                        front_matter["affiliation_block"] = value
                    elif field == "correspondence" and not structured_front_matter.get("correspondence") and not front_matter.get("correspondence"):
                        front_matter["correspondence"] = value
                    elif field == "keywords" and not structured_front_matter.get("keywords") and not front_matter.get("keywords"):
                        kw_str = value
                        if kw_str:
                            front_matter["keywords"] = [k.strip().strip("*").strip() for k in kw_str.split(",") if k.strip()]

        # In new_draft academic mode, front matter must come from structured
        # fields. Do not infer title/author/contact from the task prompt.
        if task_intent != "new_draft":
            if not front_matter["title"]:
                title = _parse_title_from_user_prompt(user_prompt)
                if title:
                    front_matter["title"] = title

            if not front_matter["author_block"]:
                author = _parse_author_from_user_prompt(user_prompt)
                if author:
                    front_matter["author_block"] = author

            if not front_matter["affiliation_block"]:
                affiliation = _parse_affiliation_from_user_prompt(user_prompt)
                if affiliation:
                    front_matter["affiliation_block"] = affiliation

        # Extract keywords from evidence if not provided
        if not front_matter["keywords"]:
            if task_intent == "new_draft" and report_family == "academic_report":
                front_matter["keywords"] = _select_thesis_aligned_keywords(user_prompt)
            else:
                raw_keywords = _extract_keywords_from_evidence(state.sources.get("evidence_ledger_path"))
                claim_matrix = state.plan.get("claim_matrix")
                enriched_keywords = _enrich_keywords_to_research_level(
                    raw_keywords,
                    claim_matrix=claim_matrix,
                    user_prompt=user_prompt,
                )
                if enriched_keywords:
                    front_matter["keywords"] = enriched_keywords

    # Cap title at Nature's recommended 120 characters (applied to all sources)
    title = front_matter.get("title", "")
    if len(title) > 120:
        front_matter["title"] = title[:120].rstrip() + "..."

    return front_matter


def _validate_front_matter(front_matter: dict, report_family: str) -> list[str]:
    """Validate front matter completeness. Returns list of warnings (not hard errors)."""
    warnings = []

    policy = get_policy(report_family)
    if not policy.front_matter.required:
        return warnings

    # ICMJE requires: title, author, affiliation, keywords, correspondence
    if not front_matter.get("title"):
        warnings.append("title is empty - academic reports require a title")
    if not front_matter.get("author_block"):
        warnings.append("author_block is empty - academic reports require author attribution")
    if not front_matter.get("affiliation_block"):
        warnings.append("affiliation_block is empty - academic reports require affiliation")
    if not front_matter.get("keywords"):
        warnings.append("keywords missing - academic reports typically require 4-6 keywords")
    elif len(front_matter.get("keywords", [])) < 3:
        warnings.append(f"only {len(front_matter.get('keywords', []))} keywords - ICMJE recommends 4-6")
    if not front_matter.get("correspondence"):
        warnings.append("correspondence missing - academic reports require corresponding author contact")

    for field in ("title", "author_block", "affiliation_block", "correspondence"):
        value = str(front_matter.get(field, "")).strip()
        if value.lower() in _GENERIC_METADATA_VALUES:
            warnings.append(f"{field} contains generic template metadata: {value}")
        if "**" in value:
            warnings.append(f"{field} contains leftover Markdown bold marker")
        if any(pattern.search(value) for pattern in _PROMPT_LEAK_PATTERNS):
            warnings.append(f"{field} appears to contain task prompt text")

    noisy_keywords = {"corpus", "backtrader", "pydantic", "kelly", "bayesian", "ollama"}
    keyword_values = [str(keyword).strip() for keyword in front_matter.get("keywords", [])]
    leaked_keywords = [keyword for keyword in keyword_values if keyword.lower() in noisy_keywords]
    if leaked_keywords:
        warnings.append("keywords contain implementation-noise metadata: " + ", ".join(leaked_keywords))
    markdown_keywords = [keyword for keyword in keyword_values if "**" in keyword]
    if markdown_keywords:
        warnings.append("keywords contain leftover Markdown bold marker")

    # Title length check (Nature style: concise, verb-first)
    title = front_matter.get("title", "")
    if len(title) > 150:
        warnings.append(f"title is {len(title)} chars - Nature recommends ≤120 characters")

    return warnings


def _format_front_matter_markdown(front_matter: dict) -> str:
    """Format front matter as markdown for prepending to document."""
    sections = []

    # Use a plain heading. "# {.Title} Title" leaks the marker in Pandoc.
    if front_matter.get("title"):
        sections.append(f"# {front_matter['title']}")

    # Short title (running title)
    if front_matter.get("short_title"):
        sections.append(f"**Running title:** {front_matter['short_title']}\n")

    # Author block
    if front_matter.get("author_block"):
        sections.append(front_matter["author_block"])

    # Affiliation block
    if front_matter.get("affiliation_block"):
        sections.append(front_matter["affiliation_block"])

    # Correspondence
    if front_matter.get("correspondence"):
        sections.append(f"\n**Correspondence:** {front_matter['correspondence']}")

    # Keywords
    if front_matter.get("keywords"):
        keywords_str = ", ".join(front_matter["keywords"])
        sections.append(f"\n**Keywords:** {keywords_str}")

    # Acknowledgements
    if front_matter.get("acknowledgements"):
        sections.append(f"\n## Acknowledgements\n\n{front_matter['acknowledgements']}")

    # Funding
    if front_matter.get("funding"):
        sections.append(f"\n## Funding\n\n{front_matter['funding']}")

    # Conflict of interest
    if front_matter.get("conflict_note"):
        sections.append(f"\n## Conflict of Interest\n\n{front_matter['conflict_note']}")

    return "\n\n".join(sections)


def run_front_matter_build(state: ReportState) -> ReportState:
    """T_NEW: FRONT_MATTER_BUILD - assemble front matter for academic publication.

    Position: After SECTION_PLAN_FREEZE, before SECTION_DRAFT.

    Reads:
      - state.plan["blueprint"] (for front_matter template)
      - state.spec (for user_prompt, report_family)
      - state.sources["evidence_ledger_path"] (for keyword extraction)

    Writes:
      - front_matter.json artifact
      - state.plan["front_matter"] = populated front_matter dict
      - state.plan["front_matter_md"] = markdown-formatted front matter

    ACADEMIC MODE: Hard block on placeholder values. See placeholder regex below.
    """
    report_family = state.spec.get("report_family", "academic_report")

    # Build front matter
    front_matter = _build_front_matter(state)

    # Validate and collect warnings
    warnings = _validate_front_matter(front_matter, report_family)
    if warnings:
        state.runtime["warnings"] = state.runtime.get("warnings", []) + [
            f"FRONT_MATTER_BUILD: {w}" for w in warnings
        ]

    # ------------------------------------------------------------------
    # Strict academic front matter. Placeholder bracket patterns are stripped,
    # but missing/generic metadata must be supplied as structured fields rather
    # than fabricated from prompt text or generic defaults.
    # ------------------------------------------------------------------
    policy = get_policy(report_family, state.spec.get("report_family_detail") or None)
    import re as _re
    _BRACKET_PLACEHOLDER_RE = _re.compile(r"\[[^\]]+\]")

    # Strip any [bracketed placeholder] patterns from existing values
    for field_key in ("author_block", "affiliation_block", "correspondence"):
        val = front_matter.get(field_key, "")
        if val and _BRACKET_PLACEHOLDER_RE.search(val):
            front_matter[field_key] = _BRACKET_PLACEHOLDER_RE.sub("", val).strip()

    if policy.front_matter.required:
        strict_warnings = _validate_front_matter(front_matter, report_family)
        if strict_warnings:
            raise QAHardBlockError(
                "FRONT_MATTER_BUILD failed strict metadata policy: "
                + "; ".join(strict_warnings)
            )

    # Format as markdown for document injection
    front_matter_md = _format_front_matter_markdown(front_matter)

    # Write artifact
    fm_path = write_json_artifact(state, "front_matter.json", front_matter)

    # Update state
    state.plan["front_matter"] = front_matter
    state.plan["front_matter_path"] = fm_path
    state.plan["front_matter_md"] = front_matter_md

    return state
