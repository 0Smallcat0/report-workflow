"""CITATION_BIND node - dual-layer citation system for academic publication.

Implements three separate layers:

1. INTERNAL TRACE LAYER (audit/appendix only):
   - Maps claim_id -> evidence_ids -> source_ids
   - Preserves internal file references for traceability
   - NEVER appears in publication output
   - Output: internal_trace_map.json

2. SOURCE APPENDIX LAYER (human-readable appendix):
   - Collects all [Source: ...] inline markers stripped from body prose
   - Produces a human-readable "Source Appendix" section
   - Maps each source file to its evidence items
   - Output: internal_source_appendix.md (wired into final DOCX as last appendix)

3. PUBLICATION LAYER (publication-ready):
   - Formal APA 7th edition citations
   - In-text: (Author, Year) format for research documents
   - Reference list entries only for external sources (research_document, primary_source)
   - Graph analysis figures -> "[Source: Figure N]" format in-text
   - Internal filenames NEVER appear in final publication body

Key rules:
   - code_artifact / graph_analysis / derived_summary -> in-text only, NO reference entry
   - research_document / primary_source -> APA 7th author-year format (in-text + reference entry)
   - [Source: filename] markers -> STRIPPED from body prose, moved to Source Appendix
   - Internal filenames NEVER appear in final publication body

Position: After MERGE_DRAFT, before FACTUALITY_CHECK in validate phase.
"""
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact
from ..policies import get_policy
from .cited_sources import (
    format_bibtex_entry as format_cited_bibtex_entry,
    format_reference_entry as format_cited_reference_entry,
)


# ------------------------------------------------------------------
# Citation style configurations
# ------------------------------------------------------------------

# Source role -> citation behavior
# - "in_text_only": citation appears in-text only, no reference entry
# - "reference_entry": both in-text and reference list entry
SOURCE_ROLE_CITATION_TYPE = {
    "code_artifact": "in_text_only",
    "graph_analysis": "in_text_only",
    "derived_summary": "in_text_only",
    "internal_project_source": "sidecar_only",
    "research_document": "reference_entry",
    "primary_source": "reference_entry",
}

GBT_7714_2025_EFFECTIVE_DATE = date(2026, 7, 1)


def default_gbt7714_standard(as_of: date | None = None) -> str:
    """Return the default GB/T 7714 standard for a given date.

    GB/T 7714-2025 has been issued but is not the default before its
    2026-07-01 effective date. This function keeps that date boundary explicit
    and testable.
    """
    current = as_of or date.today()
    if current >= GBT_7714_2025_EFFECTIVE_DATE:
        return "GB/T 7714-2025"
    return "GB/T 7714-2015"


def citation_style_for_profile(report_profile: str | None) -> str:
    """Return the internal publication citation style for a report profile."""
    if report_profile == "engineering_lab_report":
        return "gb_t_7714_2015"
    return "apa"


def _split_cite_ids(raw: str) -> list[str]:
    """Return individual citation IDs from one [CITE:...] payload."""
    return [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]


# ------------------------------------------------------------------
# Internal trace layer
# ------------------------------------------------------------------

def _build_internal_trace_map(
    evidence_ledger: list[dict],
    claim_matrix: dict,
    sentence_map: list[dict],
) -> dict:
    """Build the internal trace map: claim -> evidence -> source mapping.

    This map is for audit/traceability purposes only.
    It preserves internal references like [Source: graphify:GRAPH_REPORT.md]
    and is NOT part of the publication output.
    """
    trace_map = {
        "version": "1.0",
        "description": "Internal trace map for audit and traceability. NOT for publication.",
        "claims": [],
        "unmapped_evidence": [],
        "source_roles": {},
    }

    # Build evidence_id -> evidence lookup
    evidence_by_id = {e["evidence_id"]: e for e in evidence_ledger}

    # Process each claim
    for claim in claim_matrix.get("claims", []):
        claim_id = claim.get("claim_id", "")
        evidence_ids = claim.get("evidence_ids", [])

        claim_trace = {
            "claim_id": claim_id,
            "claim_text": claim.get("claim_text", ""),
            "evidence_ids": evidence_ids,
            "sources": [],
            "internal_refs": [],
        }

        for eid in evidence_ids:
            if eid in evidence_by_id:
                ev = evidence_by_id[eid]
                source_id = ev.get("source_id", "")
                source_role = ev.get("source_role", "unknown")
                source_file = ev.get("source_file_name", "")

                claim_trace["sources"].append({
                    "source_id": source_id,
                    "source_role": source_role,
                    "source_file": source_file,
                    "evidence_id": eid,
                })

                # Track internal references for audit
                if source_role in ("code_artifact", "graph_analysis", "derived_summary"):
                    claim_trace["internal_refs"].append(source_file)

                # Track source role distribution
                if source_role not in trace_map["source_roles"]:
                    trace_map["source_roles"][source_role] = 0
                trace_map["source_roles"][source_role] += 1

        trace_map["claims"].append(claim_trace)

    # Find unmapped evidence (evidence not linked to any claim)
    mapped_evidence_ids = set()
    for claim_trace in trace_map["claims"]:
        mapped_evidence_ids.update(claim_trace["evidence_ids"])

    for ev in evidence_ledger:
        eid = ev.get("evidence_id", "")
        if eid and eid not in mapped_evidence_ids:
            trace_map["unmapped_evidence"].append({
                "evidence_id": eid,
                "source_id": ev.get("source_id", ""),
                "source_role": ev.get("source_role", ""),
            })

    return trace_map


# ------------------------------------------------------------------
# Publication citation formatting
# ------------------------------------------------------------------

def _format_apa_author_year(file_name: str, file_type: str = "unknown") -> str:
    """Format a pseudo-APA citation from a file name.

    For research documents without actual author metadata,
    we generate a citetag based on the file name and mark it as
    file-derived to distinguish from real literature references.
    """
    # A file name does not say who wrote the thing, or how many people did.
    # Splitting it on underscores and joining the pieces with "&" or "et al."
    # asserted both: "Shah2003_PlateExchangers.pdf" was cited as "Shah2003 &
    # PlateExchangers", crediting a title fragment as a co-author, and
    # "熱傳學_王小明_2019.pdf" became "熱傳學 et al." — the book's title
    # standing in for the author, who was in the file name and was dropped.
    # A reference list naming people who do not exist is the one thing this
    # pipeline may not produce.
    #
    # So: the first token is used as a locating tag and nothing is claimed
    # about authorship, in the same spirit as the "(n.d.)" rule below — the
    # file name is shown in full in the entry's title position, where it
    # asserts nothing.
    base = Path(file_name).stem.replace("_", " ").replace("-", " ")
    parts = base.split()
    tag = parts[0] if parts else "Unknown"
    return f"{tag} (n.d.)"


#: file_type -> (bracketed label for its reference entry, is it a local file
#: artifact rather than a publication).
#:
#: One table, because three separate facts derive from it: the label an entry
#: carries, the file types whose in-text citations must be suppressed, and the
#: labels reference_verify curates out of the publication list. They used to be
#: three hand-copied lists, and the copies drifted — the curation filter knew
#: four labels while the publication-candidate test knew one, so a .csv source
#: was carried into the bibliography and then hard-failed REFERENCE_QA as "not
#: a publication", making any run with a dataset source unpublishable.
_REFERENCE_LABELS: dict[str, tuple[str, bool]] = {
    "pdf": ("PDF document", False),
    "docx": ("Word document", True),
    "txt": ("Text file", True),
    "md": ("Text file", True),
    "csv": ("Dataset", True),
    "json": ("Data file", True),
    "unknown": ("Project file", True),
}

#: File types whose reference entry publication curation removes. Their in-text
#: citations are suppressed too: a citation must point at something the
#: reference list actually carries.
LOCAL_ARTIFACT_FILE_TYPES = frozenset(
    file_type for file_type, (_, is_local) in _REFERENCE_LABELS.items() if is_local
)

def _is_local_artifact(evidence: dict) -> bool:
    """True when this source's reference entry will be curated away.

    The rule above — a citation must point at something the reference list
    actually carries — was enforced only where the author-year formatter runs.
    The GB/T numeric branch never called it, so a Chinese-language lab report
    citing its own .csv put [1] into the prose thirteen times, curation then
    removed the entry it pointed at, and the deliverable went out with a
    bibliography that had nothing in it. Same rule, both notations.
    """
    metadata = evidence.get("metadata") or {}
    file_type = str(
        evidence.get("file_type") or metadata.get("file_type") or ""
    ).lower().lstrip(".")
    return file_type in LOCAL_ARTIFACT_FILE_TYPES


#: The bracketed labels those entries carry. reference_verify curates on these.
LOCAL_ARTIFACT_LABELS = tuple(
    sorted({label for label, is_local in _REFERENCE_LABELS.values() if is_local})
)

#: Heading for a reference list the pipeline generates itself (as opposed to one
#: the author drafted). It is a top-level section like every other one, so it
#: must not be demoted — at H2 a Word table of contents nests it under whatever
#: section happens to precede it. `docx_render._localize_reference_heading`
#: swaps the title for the blueprint's `title_zh` and keeps whatever level it
#: finds here, so this string decides the level in the rendered document.
REFERENCE_LIST_HEADING = "# References"

#: Heading for the generated evidence-trace list, and its Chinese title.
#:
#: Separate from References on purpose. A project source file is not a
#: publication, and the formatter one function up refuses to dress one as
#: another — but the reader still has to be able to check a number. This list
#: says where each cited figure sits: file, line span, and the text it was
#: taken from. It is generated from the ledger, so no author writes it.
SOURCE_LIST_HEADING = "# Sources"
SOURCE_LIST_HEADING_ZH = "# 資料來源"

#: How much of the cited row to quote in that list. Long enough to recognize
#: the figure, short enough that a hundred entries stay readable.
SOURCE_TRACE_QUOTE_CHARS = 140


def _format_apa_reference_entry(file_name: str, file_type: str, source_id: str) -> str:
    """Format a full APA reference entry for a research document."""
    author = _format_apa_author_year(file_name, file_type).split(" (")[0]

    # Map file types to appropriate reference format.
    # Two honesty rules, learned from a fabricated bibliography entry
    # ("literature. (2026). *literature*.") reaching a rendered paper:
    # 1. Never invent a year — a project source file has no publication date,
    #    so it is cited as (n.d.), not as the current year.
    # 2. Every format carries a bracketed file label ([Text file], [Dataset],
    #    …) because the publication-reference curation filter keys off those
    #    labels to keep internal file citations out of the published
    #    bibliography. "md" was missing from this map and fell through to an
    #    unlabeled format that slipped past the filter.
    label, _ = _REFERENCE_LABELS.get(
        file_type.lower(), _REFERENCE_LABELS["unknown"]
    )
    fmt = f"{author}. (n.d.). *{Path(file_name).stem}* [{label}]."

    # If we have a real source_id that looks like a DOI or URL, use it
    if source_id.startswith("doi:") or source_id.startswith("http"):
        # This would be a real DOI/URL citation
        pass

    return fmt


# One citation shape: numeric [3], author-year (Tsai, 2026), undated
# ((手冊 (n.d.))), or an internal [Source: file] marker. The undated shape
# nests parentheses and carries no four-digit year, so the author-year
# alternative cannot match it — repeats of an undated source rendered doubled.
_CITATION_TOKEN = (
    r"(?:\[\d+\]|\([^()]*\(n\.d\.\)\)|\([^()]*\b\d{4}[a-z]?\)|\[Source:[^\]]*\])"
)
_ADJACENT_DUPLICATE_CITATION_RE = re.compile(rf"({_CITATION_TOKEN})(?:\s*\1)+")


def _collapse_adjacent_duplicate_citations(text: str) -> str:
    """Collapse repeated adjacent identical citations to a single marker.

    A sentence that cites two evidence rows from the same source carries two
    separate ``[CITE:...]`` markers, which resolve independently and used to
    render as "[1] [1]". Deduplication inside one marker cannot catch that,
    because the duplicates come from different markers; the reader just sees
    a doubled citation.
    """
    previous = None
    while previous != text:
        previous = text
        text = _ADJACENT_DUPLICATE_CITATION_RE.sub(r"\1", text)
    return text


def _format_in_text_citation(evidence: dict) -> str:
    """Format an in-text citation based on source_role.

    Returns the appropriate citation format for in-text use:
    - code_artifact: [Source: filename.py]
    - graph_analysis: [Source: Figure N] or [Source: graphify:filename]
    - derived_summary: [Source: Summary -> filename]
    - internal_project_source: omitted from publication text; tracked in sidecars
    - research_document: (Author, Year)
    - primary_source: (Author, Year)
    """
    source_role = evidence.get("source_role", "primary_source")
    file_name = evidence.get("source_file_name", evidence.get("source_id", "unknown"))
    file_type = evidence.get("file_type", "unknown")

    if source_role == "code_artifact":
        return f"[Source: {file_name}]"
    elif source_role == "graph_analysis":
        # Check if this is a figure reference
        figure_ref = evidence.get("figure_reference", "")
        if figure_ref:
            return f"[Source: {figure_ref}]"
        return f"[Source: graphify:{file_name}]"
    elif source_role == "derived_summary":
        return f"[Source: Summary - {file_name}]"
    elif source_role == "internal_project_source":
        return ""
    elif file_type.lower() in LOCAL_ARTIFACT_FILE_TYPES:
        # A citation must point at something. The reference entry for these
        # file types carries a local-artifact label, and publication
        # reference curation removes exactly those entries — so an author-year
        # citation here would send the reader to a bibliography that never
        # lists it. A quote sheet cited three times rendered three dangling
        # markers over an empty reference list.
        return ""
    elif source_role in ("research_document", "primary_source"):
        # APA author-year format
        author_year = _format_apa_author_year(file_name, file_type)
        return f"({author_year})"
    else:
        # Default to author-year
        author_year = _format_apa_author_year(file_name, file_type)
        return f"({author_year})"


def _load_cited_sources(state: ReportState) -> list[dict]:
    """The cited-source registry EVIDENCE_NORMALIZE wrote, or an empty list."""
    path = state.sources.get("cited_sources_path", "")
    if not path or not Path(path).exists():
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = payload.get("cited_sources") if isinstance(payload, dict) else payload
    return [row for row in (rows or []) if isinstance(row, dict)]


def _format_source_trace_entry(evidence: dict, number: int) -> str:
    """One line of the generated Sources list: where this figure came from.

    Everything here is read off the ledger row, so nothing is asserted that
    the pipeline did not parse out of the source itself — no invented author,
    no invented year.
    """
    file_name = str(
        evidence.get("source_file_name") or evidence.get("source_id") or "unknown source"
    )
    span = str(evidence.get("source_span") or "").strip()
    quote = " ".join(str(evidence.get("quote") or evidence.get("content") or "").split())
    quote = quote[:SOURCE_TRACE_QUOTE_CHARS].rstrip()
    if quote.endswith("..."):
        quote = quote[:-3].rstrip()

    # File name, line span and quote are what a reader can act on. The ledger's
    # evidence id is an internal handle — the same rule that keeps `[CITE:E…]`
    # out of the body keeps it out of the delivered source list; it stays in
    # `internal_source_appendix.md`, which is where the audit trail lives.
    # The span usually opens with the file name already — "products.csv (544
    # rows)" — so joining the two printed it twice on every line of the source
    # list. Same defect as the table provenance line repaired in 0e0a40f, one
    # renderer over; the regression test there covered the table line only.
    locator = " ".join(
        part for part in (("" if span.startswith(file_name) else file_name), span)
        if part
    ) or file_name
    parts = [f"[S{number}] {locator}"]
    if quote:
        parts.append(f"“{quote}”")

    # A cited row often carries the outside source it was taken from — a URL,
    # or a house named in a parenthetical. The source document had 37 such
    # links and the deliverable had none, because the entry stopped at the
    # file name: the reader could find which line of which file the figure sat
    # on, but not who published it. These are read off the row, so the list
    # asserts only what the source already stated.
    external = _external_references(evidence)
    if external:
        parts.append(", ".join(external))
    return " — ".join(parts)


#: A URL, and a Chinese source attribution such as "（來源：Fastmarkets，2026）".
_URL_RE = re.compile(r"https?://[^\s)）】\]」』,，。;；]+")
_ATTRIBUTION_RE = re.compile(
    r"[（(]\s*(?:來源|来源|資料來源|资料来源|Source)\s*[:：]\s*([^)）]{2,60})[)）]",
    re.IGNORECASE,
)

#: Enough to name the houses without turning one entry into a paragraph.
MAX_EXTERNAL_REFERENCES = 4


def _external_references(evidence: dict) -> list[str]:
    """Outside sources this evidence row names, in the order it names them."""
    content = str(evidence.get("content") or "")
    found: list[str] = []
    for match in _ATTRIBUTION_RE.finditer(content):
        value = " ".join(match.group(1).split())
        if value and value not in found:
            found.append(value)
    for url in _URL_RE.findall(content):
        if url not in found:
            found.append(url)
    return found[:MAX_EXTERNAL_REFERENCES]


def _format_reference_entry(evidence: dict) -> Optional[str]:
    """Format a full reference list entry, or None to skip.

    Returns None for in-text-only sources:
    - code_artifact
    - graph_analysis
    - derived_summary

    Returns None for internal workflow artifacts (main_report.md, GRAPH_REPORT.md, etc.)
    which are generated by the workflow itself, not external publications.

    Returns APA reference entry for:
    - research_document
    - primary_source
    """
    source_role = evidence.get("source_role", "primary_source")

    if source_role in ("code_artifact", "graph_analysis", "derived_summary", "internal_project_source"):
        return None  # In-text only, no reference entry

    if source_role in ("research_document", "primary_source"):
        file_name = evidence.get("source_file_name", evidence.get("source_id", "unknown"))
        # Skip internal workflow artifacts; these are not external publications.
        internal_artifacts = (
            "main_report.md",
            "GRAPH_REPORT.md",
            "main_report",
            "GRAPH_REPORT",
        )
        stem = Path(file_name).stem
        if stem in internal_artifacts or file_name in internal_artifacts:
            return None
        file_type = evidence.get("file_type", "unknown")
        source_id = evidence.get("source_id", "")
        return _format_apa_reference_entry(file_name, file_type, source_id)

    return None


def _source_reference_key(evidence: dict) -> str:
    return str(
        evidence.get("source_id")
        or evidence.get("source_file_name")
        or evidence.get("evidence_id")
        or "unknown"
    )


def _format_gbt7714_type_code(file_type: str) -> str:
    normalized = str(file_type or "").lower()
    if normalized in {"csv", "xlsx", "json"}:
        return "DS"
    if normalized in {"pdf", "docx", "txt", "md"}:
        return "Z"
    return "Z"


def _format_gbt7714_reference_entry(evidence: dict, number: int, standard: str = "GB/T 7714-2015") -> str:
    """Format a minimal GB/T 7714 numeric reference entry.

    The workflow often receives local sources without full bibliographic
    metadata, so this intentionally uses only available structured fields and
    source filenames. The scholarly quality report separately flags
    metadata-poor references for academic_paper.
    """
    metadata = evidence.get("source_metadata") if isinstance(evidence.get("source_metadata"), dict) else {}
    file_name = str(evidence.get("source_file_name") or evidence.get("source_id") or "Unknown Source")
    title = str(evidence.get("title") or metadata.get("title") or Path(file_name).stem or file_name).strip()
    author = str(evidence.get("author") or metadata.get("author") or "").strip()
    year = str(evidence.get("year") or metadata.get("year") or evidence.get("published_year") or "").strip()
    type_code = _format_gbt7714_type_code(str(evidence.get("file_type") or metadata.get("file_type") or ""))
    source_url = str(evidence.get("url") or evidence.get("source_url") or "").strip()

    prefix = f"[{number}] "
    author_part = f"{author}. " if author else ""
    year_part = f" {year}." if year else ""
    url_part = f" {source_url}" if source_url else ""
    note = f" ({standard})"
    return f"{prefix}{author_part}{title}[{type_code}].{year_part}{url_part}{note}".strip()


# ------------------------------------------------------------------
# Source Appendix builders
# ------------------------------------------------------------------

def _strip_source_markers(
    text: str,
    evidence_ledger: list[dict],
    source_pattern: re.Pattern,
) -> tuple[str, list[dict]]:
    """Strip [Source: ...] markers from body prose.

    Collects each occurrence into a structured list for the Source Appendix.
    Returns (stripped_text, source_entries).

    Each source_entry:
        source_name: the filename/path inside [Source: ...]
        context: surrounding sentence text (for readability)
        matched_evidence: list of evidence_ids that come from this source
    """
    evidence_by_source = _build_source_to_evidence_map(evidence_ledger)

    stripped_text = text
    entries: list[dict] = []

    for match in source_pattern.finditer(text):
        source_name = match.group(1).strip()
        original = match.group(0)

        # Capture surrounding context (up to 200 chars of the containing sentence)
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        snippet = text[start:end].replace("\n", " ").strip()

        # Find evidence IDs from this source
        matched_evidence = evidence_by_source.get(source_name, [])

        entries.append({
            "source_name": source_name,
            "context_snippet": snippet,
            "matched_evidence_ids": matched_evidence,
        })

        # Remove the marker from body prose (replace with empty)
        stripped_text = stripped_text.replace(original, "", 1)

    return stripped_text, entries


def _build_source_to_evidence_map(evidence_ledger: list[dict]) -> dict[str, list[str]]:
    """Build source_name -> list of evidence_ids mapping."""
    source_map: dict[str, list[str]] = {}
    for ev in evidence_ledger:
        src = ev.get("source_file_name", "")
        eid = ev.get("evidence_id", "")
        if src and eid:
            if src not in source_map:
                source_map[src] = []
            source_map[src].append(eid)
    return source_map


def _build_source_appendix(source_entries: list[dict]) -> str:
    """Build human-readable Source Appendix markdown.

    Groups entries by source, shows context and linked evidence IDs.
    Removes fragments with null bytes or replacement characters;
    preserves code snippets with underscores and box-drawing chars.
    """
    if not source_entries:
        return ""

    # Strict binary control characters only; do not treat box-drawing chars or underscores as binary.
    _CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+")
    _REPLACEMENT_CHARS_RE = re.compile(r"\uFFFD")

    def _clean_fragment(text: str) -> str | None:
        """Clean fragment, return None if it looks like garbled binary."""
        if not text or len(text) < 15:
            return None
        # Remove control chars
        text = _CONTROL_RE.sub(" ", text)
        # Reject if it contains Unicode replacement characters.
        if _REPLACEMENT_CHARS_RE.search(text):
            return None
        # Check ratio of printable to total chars
        printable = sum(1 for c in text if c.isprintable() or c in " \t\n")
        if printable / max(len(text), 1) < 0.65:
            return None
        # Truncate at a word boundary near 300 chars to preserve snippet context.
        if len(text) > 300:
            cut = text[:300]
            last_space = cut.rfind(" ")
            if last_space > 200:
                text = cut[:last_space]
            else:
                text = cut
        return text.strip()

    # Group by source name
    by_source: dict[str, list[dict]] = {}
    for entry in source_entries:
        name = entry["source_name"]
        if name not in by_source:
            by_source[name] = []
        by_source[name].append(entry)

    lines = [
        "---\n",
        "\n",
        "## Source Appendix\n\n",
        "_This section is for internal traceability only and does not appear in the published report._\n\n",
        "The following internal source markers were stripped from the report body. "
        "Each entry maps source files to their corresponding evidence IDs used in claims.\n\n",
    ]

    for source_name, entries in sorted(by_source.items()):
        lines.append(f"### Source: `{source_name}`\n\n")

        # Deduplicate evidence IDs
        all_evidence = []
        for e in entries:
            for eid in e.get("matched_evidence_ids", []):
                if eid not in all_evidence:
                    all_evidence.append(eid)

        lines.append(f"**Evidence IDs:** {', '.join(f'`{e}`' for e in all_evidence)}\n\n")

        # Unique clean contexts (up to 4)
        seen_contexts: set[str] = set()
        for e in entries:
            ctx = e.get("context_snippet", "")
            cleaned = _clean_fragment(ctx)
            if cleaned is None:
                continue
            # Deduplicate by first 80 chars
            key = cleaned[:80]
            if key in seen_contexts or len(seen_contexts) >= 4:
                continue
            seen_contexts.add(key)
            lines.append(f"> {cleaned}\n\n")

        lines.append("\n")

    return "".join(lines)


# ------------------------------------------------------------------
# Main citation resolution
# ------------------------------------------------------------------

def _load_jsonl(path: Optional[str]) -> list[dict]:
    """Load evidence ledger from JSONL file."""
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict) and "_contract" in payload:
                    continue
                rows.append(payload)
    return rows


def resolve_citations_publication(
    merged_md: str,
    evidence_ledger: list[dict],
    citation_audit: list[dict],
    citation_style: str = "apa",
    gbt7714_as_of: date | None = None,
) -> tuple[str, list[dict], list[str], list[str], list[str]]:
    """Resolve [CITE:cite_id] references to publication-ready citations.

    Returns:
        - resolved_md: markdown with resolved publication citations
        - new_audit: updated citation audit entries
        - literature_refs: list of formatted reference entries (for reference list)
        - internal_trace_refs: list of internal refs (for audit only)
        - source_trace_refs: generated Sources list, one entry per cited row

    Sources whose citation cannot honestly be author-year — a project markdown
    file, a dataset, anything the bibliography will not carry — used to
    resolve to the empty string. The marker was deleted, the row appeared in
    no list, and the delivered document stated figures the reader could not
    check against anything. They now resolve to a numbered ``[Sn]`` marker
    backed by an entry in the generated Sources list.
    """
    cite_pattern = re.compile(r'\[CITE:([^\]]+)\]')

    resolved_md = merged_md

    # Build evidence lookup by evidence_id and source_id
    evidence_by_id = {e["evidence_id"]: e for e in evidence_ledger}
    source_by_id = {e["source_id"]: e for e in evidence_ledger}

    # Track literature references (unique)
    literature_refs: list[str] = []
    seen_refs: set[str] = set()
    numeric_ref_numbers: dict[str, int] = {}

    # Track internal trace references
    internal_trace_refs: list[str] = []

    # Generated Sources list: numbered once per cited evidence row, so the
    # same row cited twice carries the same marker both times.
    source_trace_numbers: dict[str, int] = {}
    source_trace_refs: list[str] = []

    def trace_marker(evidence: dict, cite_id: str) -> str:
        key = str(evidence.get("evidence_id") or cite_id)
        if key not in source_trace_numbers:
            source_trace_numbers[key] = len(source_trace_numbers) + 1
            source_trace_refs.append(
                _format_source_trace_entry(evidence, source_trace_numbers[key])
            )
        return f"[S{source_trace_numbers[key]}]"

    # Process each citation. Accept both preferred separate markers
    # ([CITE:E1] [CITE:E2]) and older comma-delimited markers
    # ([CITE:E1,E2]) so stale artifacts can still bind cleanly.
    new_audit = []
    for match in cite_pattern.finditer(merged_md):
        cite_ids = _split_cite_ids(match.group(1))
        original = match.group(0)

        replacements: list[str] = []
        all_resolved = bool(cite_ids)
        for cite_id in cite_ids:
            audit_entry = {
                "cite_id": cite_id,
                "evidence_ids": [cite_id],
                "resolved": False,
                "citation_type": "unknown",
            }

            replacement = None

            # Try evidence lookup first
            if cite_id in evidence_by_id:
                evidence = evidence_by_id[cite_id]
                source_role = evidence.get("source_role", "primary_source")
                citation_type = SOURCE_ROLE_CITATION_TYPE.get(source_role, "reference_entry")

                if (
                    citation_style == "gb_t_7714_2015"
                    and citation_type == "reference_entry"
                    and not _is_local_artifact(evidence)
                ):
                    source_key = _source_reference_key(evidence)
                    if source_key not in numeric_ref_numbers:
                        numeric_ref_numbers[source_key] = len(numeric_ref_numbers) + 1
                    number = numeric_ref_numbers[source_key]
                    replacement = f"[{number}]"
                else:
                    replacement = _format_in_text_citation(evidence)
                if not replacement:
                    replacement = trace_marker(evidence, cite_id)
                audit_entry["evidence_ids"] = [cite_id]
                audit_entry["resolved"] = True
                audit_entry["citation_type"] = citation_type

                # Collect reference entries for literature sources
                if citation_type == "reference_entry":
                    if citation_style == "gb_t_7714_2015":
                        # No marker was allocated for a local artifact, and an
                        # entry curation is about to delete would only number
                        # the list past the markers that survive.
                        ref_entry = (
                            ""
                            if _is_local_artifact(evidence)
                            else _format_gbt7714_reference_entry(
                                evidence,
                                numeric_ref_numbers[_source_reference_key(evidence)],
                                default_gbt7714_standard(gbt7714_as_of),
                            )
                        )
                    else:
                        ref_entry = _format_reference_entry(evidence)
                    if ref_entry and ref_entry not in seen_refs:
                        seen_refs.add(ref_entry)
                        literature_refs.append(ref_entry)

                # Track internal refs for audit
                if source_role in ("code_artifact", "graph_analysis", "derived_summary", "internal_project_source"):
                    internal_trace_refs.append(evidence.get("source_file_name", cite_id))

            # Try source lookup
            elif cite_id in source_by_id:
                evidence = source_by_id[cite_id]
                source_role = evidence.get("source_role", "primary_source")
                citation_type = SOURCE_ROLE_CITATION_TYPE.get(source_role, "reference_entry")

                if (
                    citation_style == "gb_t_7714_2015"
                    and citation_type == "reference_entry"
                    and not _is_local_artifact(evidence)
                ):
                    source_key = _source_reference_key(evidence)
                    if source_key not in numeric_ref_numbers:
                        numeric_ref_numbers[source_key] = len(numeric_ref_numbers) + 1
                    number = numeric_ref_numbers[source_key]
                    replacement = f"[{number}]"
                else:
                    replacement = _format_in_text_citation(evidence)
                if not replacement:
                    replacement = trace_marker(evidence, cite_id)
                audit_entry["resolved"] = True
                audit_entry["citation_type"] = citation_type

                if citation_type == "reference_entry":
                    if citation_style == "gb_t_7714_2015":
                        # No marker was allocated for a local artifact, and an
                        # entry curation is about to delete would only number
                        # the list past the markers that survive.
                        ref_entry = (
                            ""
                            if _is_local_artifact(evidence)
                            else _format_gbt7714_reference_entry(
                                evidence,
                                numeric_ref_numbers[_source_reference_key(evidence)],
                                default_gbt7714_standard(gbt7714_as_of),
                            )
                        )
                    else:
                        ref_entry = _format_reference_entry(evidence)
                    if ref_entry and ref_entry not in seen_refs:
                        seen_refs.add(ref_entry)
                        literature_refs.append(ref_entry)

                if source_role in ("code_artifact", "graph_analysis", "derived_summary", "internal_project_source"):
                    internal_trace_refs.append(evidence.get("source_file_name", cite_id))

            else:
                all_resolved = False
                import sys
                print(f"[CITATION_BIND] unresolved cite_id={cite_id!r}", file=sys.stderr)

            if replacement:
                replacements.append(replacement)
            new_audit.append(audit_entry)

        # Apply replacement
        if all_resolved:
            resolved_md = resolved_md.replace(original, "; ".join(dict.fromkeys(replacements)), 1)

    # Add unresolved entries from existing audit
    existing_resolved = {a["cite_id"] for a in new_audit}
    for entry in citation_audit:
        if entry.get("cite_id") not in existing_resolved:
            new_audit.append(entry)

    resolved_md = _collapse_adjacent_duplicate_citations(resolved_md)
    resolved_md = re.sub(r"[ \t]{2,}", " ", resolved_md)
    # Full-width punctuation was missing from this cleanup, so a Chinese
    # sentence whose citation resolved to nothing shipped as "...價格週期支配 。"
    # — a space wedged before the period, visible in the delivered document.
    resolved_md = re.sub(r"[ \t　]+([,.;:，。；：、！？）」』])", r"\1", resolved_md)
    return resolved_md, new_audit, literature_refs, internal_trace_refs, source_trace_refs


def audit_sentence_citations(
    merged_md: str,
    sentence_map: list[dict],
    evidence_ledger: list[dict],
) -> list[dict]:
    """Audit evidence-backed sentence map entries against draft citation placeholders."""
    placeholders = {
        cite_id
        for raw_marker in re.findall(r"\[CITE:([^\]]+)\]", merged_md)
        for cite_id in _split_cite_ids(raw_marker)
    }
    evidence_ids = {item.get("evidence_id") for item in evidence_ledger if item.get("evidence_id")}
    audit = []
    seen = set()

    for sent in sentence_map:
        sent_evidence = [eid for eid in sent.get("evidence_ids", []) if eid]
        if not sent_evidence:
            continue
        expected_citations = sent.get("citation_ids") or sent_evidence
        for cite_id in expected_citations:
            key = (sent.get("sentence_id", ""), cite_id)
            if key in seen:
                continue
            seen.add(key)
            resolved = cite_id in placeholders and (
                cite_id in evidence_ids or cite_id in {item.get("source_id") for item in evidence_ledger}
            )
            if not resolved:
                audit.append({
                    "cite_id": cite_id,
                    "evidence_ids": sent_evidence,
                    "resolved": False,
                    "reason": "evidence-backed sentence has no matching [CITE:<id>] placeholder in merged draft",
                    "sentence_id": sent.get("sentence_id", ""),
                    "section_id": sent.get("section_id", ""),
                })

    return audit


def build_sidecar_traceability_summary(
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict],
) -> dict:
    """Summarize sidecar-based citation traceability for clean revision prose."""
    claim_ids = {
        claim.get("claim_id")
        for claim in claim_matrix.get("claims", [])
        if claim.get("claim_id")
    }
    evidence_ids = {
        evidence.get("evidence_id")
        for evidence in evidence_ledger
        if evidence.get("evidence_id")
    }

    issues: list[str] = []
    evidence_backed_rows = 0
    for index, sent in enumerate(sentence_map):
        sent_claims = [cid for cid in sent.get("claim_ids", []) if cid]
        sent_evidence = [eid for eid in sent.get("evidence_ids", []) if eid]
        if not sent_evidence:
            continue
        evidence_backed_rows += 1
        if not sent_claims:
            issues.append(f"sentence_map row {index} has evidence_ids but no claim_ids")
        unknown_claims = sorted(cid for cid in sent_claims if cid not in claim_ids)
        unknown_evidence = sorted(eid for eid in sent_evidence if eid not in evidence_ids)
        if unknown_claims:
            issues.append(f"sentence_map row {index} references unknown claims: {', '.join(unknown_claims)}")
        if unknown_evidence:
            issues.append(f"sentence_map row {index} references unknown evidence: {', '.join(unknown_evidence)}")

    fulfilled = bool(sentence_map and claim_ids and evidence_ids and evidence_backed_rows and not issues)
    return {
        "mode": "sidecar",
        "fulfilled": fulfilled,
        "issues": issues,
        "sentence_count": len(sentence_map),
        "evidence_backed_sentence_count": evidence_backed_rows,
        "claim_count": len(claim_ids),
        "evidence_count": len(evidence_ids),
    }


def run_citation_bind(state: ReportState) -> ReportState:
    """T18: CITATION_BIND - dual-layer citation system for publication.

    This node performs two functions:

    1. INTERNAL TRACE LAYER (for audit/appendix):
       - Builds claim -> evidence -> source mapping
       - Writes internal_trace_map.json
       - NEVER appears in publication

    2. PUBLICATION LAYER (for document):
       - Resolves [CITE:...] to publication-ready citations
       - code_artifact / graph_analysis / derived_summary -> [Source: ...] in-text only
       - research_document / primary_source -> APA (Author, Year) in-text + reference list
       - Writes publication_reference_list.md and publication_references.bib
       - In-text citations only reference the publication reference list

    Position: After MERGE_DRAFT, before FACTUALITY_CHECK.
    """
    merged_md_path = state.drafts.get("merged_draft_md")
    if not merged_md_path or not Path(merged_md_path).exists():
        state.drafts["merged_draft_cited_md"] = state.drafts.get("merged_draft_md")
        return state

    with open(merged_md_path, encoding="utf-8") as f:
        merged_md = f.read()

    # Load evidence ledger
    evidence_ledger_path = state.sources.get("evidence_ledger_path")
    evidence_ledger = _load_jsonl(evidence_ledger_path)

    citation_audit = state.citations.get("citation_audit", [])
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path"))
    claim_matrix = state.plan.get("claim_matrix", {})
    state.citations["sidecar_traceability"] = build_sidecar_traceability_summary(
        sentence_map, claim_matrix, evidence_ledger
    )

    # ------------------------------------------------------------------
    # Layer 1: Internal trace map (for audit only)
    # ------------------------------------------------------------------
    internal_trace = _build_internal_trace_map(evidence_ledger, claim_matrix, sentence_map)
    trace_path = write_json_artifact(state, "internal_trace_map.json", internal_trace)
    state.citations["internal_trace_path"] = trace_path

    # ------------------------------------------------------------------
    # Layer 2: Publication citation resolution
    # ------------------------------------------------------------------
    citation_style = citation_style_for_profile(state.spec.get("report_profile", ""))
    resolved_md, new_audit, literature_refs, internal_refs, source_trace_refs = resolve_citations_publication(
        merged_md,
        evidence_ledger,
        citation_audit,
        citation_style=citation_style,
        gbt7714_as_of=state.created_at.date(),
    )

    # ------------------------------------------------------------------
    # Layer 2b: Strip [Source: ...] from body prose and move it to Source Appendix.
    # All [Source: filename] markers are internal traceability markers.
    # They must NEVER appear in publication body prose.
    # Strip them and move to a human-readable Source Appendix.
    # ------------------------------------------------------------------
    source_pattern = re.compile(r'\[Source:\s*([^\]]+)\]')
    stripped_md, source_appendix_entries = _strip_source_markers(
        resolved_md, evidence_ledger, source_pattern
    )

    # Build Source Appendix markdown
    source_appendix_md = _build_source_appendix(source_appendix_entries)

    # Add sentence-level citation audit

    # Build publication reference list (Markdown format).
    # References drafted inside the body carry [CITE:] anchors like any other
    # evidence-backed line; those are workflow markers and must never reach
    # the published bibliography (POST_RENDER hard-fails on unresolved CITE).
    def _clean_ref(ref: str) -> str:
        return re.sub(r"\s*\[CITE:[^\]]+\]", "", ref).rstrip()

    # The sources the supplied files themselves cite. They are the reader's
    # only route to the underlying figures, and they used to reach the
    # deliverable nowhere at all: a report citing thirty-nine houses published
    # an empty bibliography, an empty .bib and an empty appendix. Appended
    # after the refs derived from the ledger and deduplicated against them, so
    # a source named both ways is listed once.
    cited_sources = _load_cited_sources(state)
    seen_refs = {ref.strip().casefold() for ref in literature_refs}
    for cited in cited_sources:
        entry = format_cited_reference_entry(cited)
        if entry.strip().casefold() not in seen_refs:
            seen_refs.add(entry.strip().casefold())
            literature_refs.append(entry)

    publication_refs_md = ""
    if literature_refs and citation_style == "gb_t_7714_2015":
        publication_refs_md = f"{REFERENCE_LIST_HEADING}\n\n"
        for ref in literature_refs:
            publication_refs_md += f"{_clean_ref(ref)}\n\n"
    elif literature_refs:
        publication_refs_md = f"{REFERENCE_LIST_HEADING}\n\n"
        for ref in sorted(literature_refs):
            publication_refs_md += f"- {_clean_ref(ref)}\n\n"

    # Build BibTeX file (basic format for academic compatibility)
    publication_bib = _build_bibtex(evidence_ledger, literature_refs)
    if cited_sources:
        extra_bib = "\n\n".join(
            format_cited_bibtex_entry(cited, index)
            for index, cited in enumerate(cited_sources, start=1)
        )
        publication_bib = (publication_bib.rstrip() + "\n\n" + extra_bib).strip() + "\n"

    # ----------------------------------------------------------------------
    # Hard block per policy if any [Source:] remains after stripping.
    # This is the last line of defense before render.
    # ----------------------------------------------------------------------
    family = state.spec.get("report_profile", "academic_paper")
    if get_policy(family).citation.source_marker_hard_block:
        remaining_source = re.findall(r'\[Source:', stripped_md)
        if remaining_source:
            from ..errors import QAHardBlockError
            raise QAHardBlockError(
                f"CITATION_BIND: {len(remaining_source)} [Source:] marker(s) still in publication draft. "
                "These must be stripped before rendering."
            )

    # Write publication outputs
    run_dir = WORKFLOW_RUNS_DIR / state.job_id

    cited_md_path = run_dir / "merged_draft_cited.md"
    with open(cited_md_path, "w", encoding="utf-8") as f:
        f.write(stripped_md)  # Body prose without any [Source: ...] markers

    ref_list_path = run_dir / "publication_reference_list.md"
    with open(ref_list_path, "w", encoding="utf-8") as f:
        f.write(publication_refs_md)

    # The generated Sources list. Kept in its own file because REFERENCE_VERIFY
    # rewrites publication_reference_list.md from the curated publication
    # entries alone, and anything else parked there is discarded.
    source_list_md = ""
    if source_trace_refs:
        source_list_md = f"{SOURCE_LIST_HEADING}\n\n" + "".join(
            f"- {_clean_ref(entry)}\n" for entry in source_trace_refs
        )
    source_list_path = run_dir / "publication_source_list.md"
    with open(source_list_path, "w", encoding="utf-8") as f:
        f.write(source_list_md)

    bib_path = run_dir / "publication_references.bib"
    with open(bib_path, "w", encoding="utf-8") as f:
        f.write(publication_bib)

    # Write Source Appendix (human-readable traceability appendix)
    source_appendix_path = run_dir / "internal_source_appendix.md"
    with open(source_appendix_path, "w", encoding="utf-8") as f:
        f.write(source_appendix_md)

    # Update state
    state.drafts["merged_draft_cited_md"] = str(cited_md_path)
    # publication_draft_md is the canonical publication input for academic mode.
    # RESULTS_SANITY_PASS already set this; CITATION_BIND confirms the stripped
    # version is the final publication draft. This key is read by DOCX_RENDER
    # as the preferred input for academic_paper mode.
    state.drafts["publication_draft_md"] = str(cited_md_path)
    state.citations["citation_audit"] = new_audit
    state.citations["publication_reference_list_path"] = str(ref_list_path)
    state.citations["publication_source_list_path"] = str(source_list_path)
    state.citations["source_trace_count"] = len(source_trace_refs)
    state.citations["publication_references_bib_path"] = str(bib_path)
    state.citations["internal_trace_path"] = trace_path
    state.citations["internal_source_appendix_path"] = str(source_appendix_path)
    state.citations["literature_reference_count"] = len(literature_refs)
    state.citations["cited_source_count"] = len(cited_sources)
    state.citations["publication_citation_style"] = citation_style
    state.citations["internal_ref_count"] = len(internal_refs)

    return state


def _build_bibtex(evidence_ledger: list[dict], literature_refs: list[str]) -> str:
    """Build a basic BibTeX file from evidence ledger.

    Creates @misc entries for research documents since we don't have
    full bibliographic metadata.
    """
    from datetime import datetime

    bib_entries = []

    # Track which files we've already added
    seen_files = set()

    for ev in evidence_ledger:
        source_role = ev.get("source_role", "")
        if source_role not in ("research_document", "primary_source"):
            continue

        file_name = ev.get("source_file_name", "")
        if not file_name or file_name in seen_files:
            continue
        seen_files.add(file_name)

        source_id = ev.get("source_id", "")
        file_type = ev.get("file_type", "unknown")

        # Generate a citekey from filename
        citekey = Path(file_name).stem.replace(" ", "_").replace("-", "_")
        citekey = re.sub(r'[^a-zA-Z0-9_]', '', citekey)

        year = datetime.now().year

        if file_type == "pdf":
            entry_type = "misc"
            fields = f"  author = {{{file_name}}},\n  title = {{{file_name}}},\n  year = {{{year}}},\n  note = {{PDF document}}"
        elif file_type == "csv":
            entry_type = "misc"
            fields = f"  author = {{{file_name}}},\n  title = {{{file_name}}},\n  year = {{{year}}},\n  note = {{Dataset}}"
        else:
            entry_type = "misc"
            fields = f"  author = {{{file_name}}},\n  title = {{{file_name}}},\n  year = {{{year}}}"

        bib_entries.append(f"@{entry_type}{{{citekey},\n{fields}\n}}")

    return "\n\n".join(bib_entries)


# Backward compatibility alias for tests
def resolve_citations(
    merged_md: str,
    evidence_ledger: list[dict],
    citation_audit: list[dict],
) -> tuple[str, list[dict]]:
    """Legacy resolve_citations wrapper for backward compatibility.

    Wraps resolve_citations_publication and returns only the first two values
    (resolved_md, new_audit) that the old API expected.
    """
    resolved_md, new_audit, _, _, _ = resolve_citations_publication(
        merged_md, evidence_ledger, citation_audit
    )
    return resolved_md, new_audit
