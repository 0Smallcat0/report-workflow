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
from ..source_citation import (
    format_bibtex as format_declared_bibtex,
    format_in_text as format_declared_in_text,
    format_reference as format_declared_reference,
    merge_adjacent_parentheticals,
)


def _declared_citation(evidence: dict) -> dict | None:
    """The bibliographic record the author declared for this row's source."""
    citation = evidence.get("citation")
    return citation if isinstance(citation, dict) and citation else None


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
    if _declared_citation(evidence):
        # The author said what this file is a copy of; the reference list
        # carries that publication, not the file.
        return False
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

#: Heading for the generated appendix, and its Chinese title.
#:
#: Separate from References on purpose. A figure the report computed, or a row
#: of the author's own sheet, is not a publication, and the formatter one
#: function up refuses to dress one as another — but the reader still has to be
#: able to check the number. It used to be a "Sources" list of ``[S1]``–
#: ``[S24]`` entries naming CSV files and row counts, which a reviewer read as
#: local files listed where sources belong; each entry now gives the result,
#: its formula and every input with where that input came from. It is generated
#: from the ledger, so no author writes it.
#:
#: Rendered as its own document beside the report. Closing the report on it
#: gave a course report seven pages of program variables, 0/1 switches and the
#: same parameters repeated under every formula; the report's appendix is the
#: author's to write — formulas, parameters, a worked example — and this is the
#: complete record behind it.
SOURCE_LIST_HEADING = "# Calculation Record"
SOURCE_LIST_HEADING_ZH = "# 計算附件　完整運算紀錄"

#: The sentence under that heading, saying what the entries are.
SOURCE_LIST_INTRO = (
    "The complete record of the figures the report marks \"calculated in this study\" or "
    "\"compiled in this study\": each entry gives the formula, every input with its value and "
    "unit, and where each input comes from. The publications named are in the report's References."
)
SOURCE_LIST_INTRO_ZH = (
    "本附件是報告中標示「本研究計算」或「本研究整理」之數值的完整運算紀錄：每一項列出計算式、"
    "每個輸入的數值與單位，以及各輸入的出處；所引文獻見報告的參考文獻。"
)

#: How a label names an entry of that record: "計算附件 C8".
RECORD_POINTER_ZH = "計算附件 C"
RECORD_POINTER_EN = "calculation record C"

#: What a figure no publication states is, in the sentence that uses it:
#: (language, computed) -> label.
_TRACE_LABELS = {
    ("zh", True): "本研究計算",
    ("zh", False): "本研究整理",
    ("en", True): "calculated in this study",
    ("en", False): "compiled in this study",
}

#: The items a citation bracket holds: an author-year citation, or a label
#: for a figure no publication states.
_AUTHOR_YEAR_ITEM = r"[^（）()；;]+?[，,]\s*(?:\d{4}[a-z]?|n\.d\.(?:-[a-z])?|無日期(?:-?[a-z])?)"
#: A label and where it points: a table, the report's appendix, an entry of
#: the calculation record — "本研究計算，表 6、附錄 A.4、計算附件 C3".
_TRACE_ITEM_ZH = r"本研究(?:計算|整理)，[^（）()；;]+"
_TRACE_ITEM_EN = r"(?:calculated|compiled) in this study, [^（）()；;]+"
_CITATION_ITEM = rf"(?:{_TRACE_ITEM_ZH}|{_TRACE_ITEM_EN}|{_AUTHOR_YEAR_ITEM})"
_CITATION_BRACKET = rf"(?:（{_CITATION_ITEM}(?:；{_CITATION_ITEM})*）|\({_CITATION_ITEM}(?:; {_CITATION_ITEM})*\))"
_CITATION_RUN_RE = re.compile(rf"([ \t]*)({_CITATION_BRACKET}(?:\s*[;；]?\s*{_CITATION_BRACKET})+)")
_TRACE_ITEM_RE = re.compile(r"^(?:(本研究(?:計算|整理))，|((?:calculated|compiled) in this study), )(.+)$")
_RECORD_TOKEN_RE = re.compile(r"^(?:計算附件 |calculation record )?C(\d+)(?:–C(\d+))?$")
#: A Chinese label closes up to what it follows: "CO2e（本研究計算…" not "CO2e （本研究計算…".
_SPACE_BEFORE_TRACE_LABEL_RE = re.compile(r"[ \t]+(?=（[^（）]*?本研究(?:計算|整理)，)")

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
    declared = _declared_citation(evidence)
    if declared:
        return format_declared_in_text(declared)

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


def _is_computed(evidence: dict) -> bool:
    """A figure the pipeline computed rather than one a source states."""
    return str(evidence.get("block_type") or "") == "derived_statistic"


def _document_language(text: str) -> str:
    return "zh" if re.search(r"[一-鿿]", text or "") else "en"


def record_pointer(number: int, language: str) -> str:
    """An entry of the calculation record, as a label names it: "計算附件 C8"."""
    return f"{RECORD_POINTER_ZH if language == 'zh' else RECORD_POINTER_EN}{number}"


def trace_label(evidence: dict, pointer: str, language: str) -> str:
    """The in-text label for a figure no publication states: what it is, and where to check it."""
    label = _TRACE_LABELS[(language, _is_computed(evidence))]
    if language == "zh":
        return f"（{label}，{pointer}）"
    return f"({label}, {pointer})"


def _with_trace_label(citation: str, label: str) -> str:
    """A publication's citation and the note that the figure was computed from it.

    Knobloch et al. state g CO2e/km per region; the report computes the
    percentage between two of them. Citing the percentage to Knobloch alone
    said they had stated it.
    """
    citation = citation.strip()
    if citation.startswith("["):
        return f"{citation}{label}"
    inner, note = citation[1:-1].strip(), label[1:-1].strip()
    if label.startswith("（"):
        return f"（{inner}；{note}）"
    return f"({inner}; {note})"


def _pointer_tokens(raw: str, zh: bool) -> tuple[list[str], list[int]]:
    """A label's pointers split into places — "表 6", "附錄 A.4" — and record entry numbers."""
    places: list[str] = []
    numbers: list[int] = []
    for part in re.split(r"、" if zh else r",\s*", raw):
        part = part.strip()
        record = _RECORD_TOKEN_RE.match(part)
        if record:
            first = int(record.group(1))
            last = int(record.group(2) or first)
            numbers.extend(range(first, last + 1))
        elif part and part not in places:
            places.append(part)
    return places, numbers


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def _joined_places(places: list[str], zh: bool) -> list[str]:
    """Places grouped by what they name and in order: "附錄 A.3、A.4、表 5、表 6".

    Merging labels printed "附錄 A.4、附錄 A.3". A part that carries its own
    letter keeps only the first prefix of its group; a bare number keeps its
    prefix, since "6" alone does not say it is a table.
    """
    groups: dict[str, list[str]] = {}
    prefix = ""
    for place in places:
        head, _space, item = place.rpartition(" ")
        if head:
            prefix = head
        else:
            item = place
        items = groups.setdefault(prefix, [])
        if item not in items:
            items.append(item)
    parts: list[str] = []
    for prefix, items in groups.items():
        for index, item in enumerate(sorted(items, key=_natural_key)):
            parts.append(f"{prefix} {item}".strip() if index == 0 or item.isdigit() else item)
    return parts


def _record_range(numbers: list[int], zh: bool) -> str:
    """[1, 2, 3, 7] as "計算附件 C1–C3、C7": three or more in a row collapse, two stay listed."""
    ordered = sorted(set(numbers))
    parts: list[str] = []
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        if end - index >= 2:
            parts.append(f"C{ordered[index]}–C{ordered[end]}")
        else:
            parts.extend(f"C{number}" for number in ordered[index:end + 1])
        index = end + 1
    if not parts:
        return ""
    prefix = RECORD_POINTER_ZH if zh else RECORD_POINTER_EN
    return prefix[:-1] + ("、" if zh else ", ").join(parts)


def merge_adjacent_trace_labels(text: str) -> str:
    """Adjacent citation brackets that include a trace label become one bracket.

    Two computed figures in one sentence resolved to two labels side by side,
    and a figure cited to a publication and computed from a second one
    resolved to three brackets in a row: "（本研究計算，附錄 A.2）（環境部氣候
    變遷署，2025d） (Ember, 2026)". A reader takes that for three citation
    systems. The run becomes one bracket — publications first, then each label
    with its places and record entries — in the bracket style of the label it
    holds. A run of author-year citations alone is left to
    ``merge_adjacent_parentheticals``.
    """

    def merge(match: re.Match) -> str:
        brackets = re.findall(_CITATION_BRACKET, match.group(2))
        publications: list[str] = []
        traces: dict[str, tuple[list[str], list[int]]] = {}
        zh = False
        for bracket in brackets:
            inner = bracket[1:-1]
            for item in re.split(r"；|; ", inner):
                item = item.strip()
                trace = _TRACE_ITEM_RE.match(item)
                if trace:
                    label = trace.group(1) or trace.group(2)
                    zh = zh or bool(trace.group(1))
                    places, numbers = traces.setdefault(label, ([], []))
                    new_places, new_numbers = _pointer_tokens(trace.group(3), bool(trace.group(1)))
                    places.extend(place for place in new_places if place not in places)
                    numbers.extend(new_numbers)
                elif item and item not in publications:
                    publications.append(item)
        if not traces:
            return match.group(0)
        labels = []
        for label, (places, numbers) in traces.items():
            pointers = _joined_places(places, zh) + ([_record_range(numbers, zh)] if numbers else [])
            labels.append(label + ("，" if zh else ", ") + ("、" if zh else ", ").join(pointers))
        if zh:
            # A full-width bracket closes up to the text before it.
            return "（" + "；".join(publications + labels) + "）"
        return match.group(1) + "(" + "; ".join(publications + labels) + ")"

    return _CITATION_RUN_RE.sub(merge, text)


_UNIT_HEADER_RE = re.compile(r"^(?:單位|单位|計量單位|计量单位|units?|uom)$", re.IGNORECASE)
_SOURCE_HEADER_RE = re.compile(r"(?:出處|出处|來源|来源|source|reference|citation)", re.IGNORECASE)


def _row_note(fields: dict, value_column: str, zh: bool, citation: dict | None = None) -> tuple[str, str]:
    """What names a sheet row for a reader: its label and its source, and separately its unit.

    Every column used to be printed — year, notes and all — for every input of
    every formula, which made the appendix of a 25-page report eleven pages of
    repeated rows. The row's label and its source column say which figure it
    is and where it came from; the sheet itself is where the rest lives. A
    wide sheet — one row per vehicle, a column per quantity — puts the unit in
    the column header and its source in a declared publication, and its
    figure is named by row and column: "汽油車 實際油耗".
    """
    unit = ""
    source = ""
    label = ""
    for key, value in fields.items():
        text = " ".join(str(value if value is not None else "").split())
        if not text or key == value_column:
            continue
        if not unit and _UNIT_HEADER_RE.match(str(key).strip()):
            unit = "" if text in {"—", "-", "–"} else text
        elif not source and _SOURCE_HEADER_RE.search(str(key)):
            source = text
        elif not label:
            label = text
    header_unit = re.search(r"\s*\(([^()]+)\)\s*$", value_column)
    if not unit and header_unit:
        unit = header_unit.group(1).strip()
        column_name = value_column[:header_unit.start()].strip()
        if label and column_name:
            label = f"{label} {column_name}"
    if not source and isinstance(citation, dict) and citation.get("author"):
        from ..source_citation import in_text_author

        year = str(citation.get("year") or "").strip() or ("無日期" if zh else "n.d.")
        source = f"{in_text_author(citation)} ({year})"
    if not (label or source):
        joined = ("，" if zh else ", ").join(
            (f"{key}：{value}" if zh else f"{key}: {value}")
            for key, value in fields.items()
            if key != value_column and str(value if value is not None else "").strip()
        )
        return joined, unit
    return ("；" if zh else "; ").join(part for part in (label, source) if part), unit


def _readable_expression(expression: object) -> str:
    """A formula as a reader writes it: × and ÷ rather than * and /."""
    text = str(expression or "")
    text = text.replace("**", "^")
    text = re.sub(r"\s*\*\s*", " × ", text)
    return re.sub(r"\s*/\s*", " ÷ ", text)


def _names_in_order(expression: object) -> list[str]:
    """The names a formula uses, in the order they are written."""
    from ..derived_evidence import formula_names

    text = str(expression or "")
    try:
        names = formula_names(text)
    except Exception:
        return []
    positions = {}
    for name in names:
        match = re.search(rf"(?<![\w.]){re.escape(name)}(?!\w)", text)
        positions[name] = match.start() if match else len(text)
    return sorted(names, key=lambda name: positions[name])


def _operand_notes(operands: object, zh: bool, number_for) -> tuple[list[str], list[str]]:
    """Each input of a formula as the reader redoes it: name, value, and where it came from.

    Returns the notes and the names they cover, so a table's per-row columns
    can be told apart from its shared inputs.
    """
    from ..derived_evidence import format_operand

    notes: list[str] = []
    names: list[str] = []
    for name, record in (operands or {}).items() if isinstance(operands, dict) else []:
        if not isinstance(record, dict):
            continue
        names.append(str(name))
        value = record.get("value")
        shown = format_operand(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else ""
        where = ""
        if record.get("row_column"):
            notes.append(f"{name} 取各列的 {record['row_column']}" if zh else f"{name} is each row's {record['row_column']}")
            continue
        if record.get("derivation") or record.get("table"):
            referenced = number_for(str(record.get("derivation") or record.get("table"))) if number_for else None
            pointer = f"C{referenced}" if referenced else ""
            if record.get("table"):
                cell = (
                    f"{record.get('row')} 列的 {record.get('column')}" if zh
                    else f"{record.get('column')} of row {record.get('row')}"
                )
                where = f"{pointer} {cell}".strip() if zh else ", ".join(part for part in (cell, pointer) if part)
            else:
                where = pointer
        else:
            fields = record.get("fields")
            if isinstance(fields, dict) and fields:
                where, unit = _row_note(
                    fields, str(record.get("column") or ""), zh,
                    record.get("citation") if isinstance(record.get("citation"), dict) else None,
                )
                if unit and shown:
                    shown = f"{shown} {unit}"
            elif record.get("row_filter") or record.get("column"):
                where = (
                    f"{record.get('row_filter')} 的 {record.get('column')}" if zh
                    else f"{record.get('column')} where {record.get('row_filter')}"
                )
        equation = f"{name} = {shown}".strip() if shown else str(name)
        if where:
            equation += f"（{where}）" if zh else f" ({where})"
        notes.append(equation)
    return notes, names


def _repeats_labels(values: list, labels: list[str]) -> bool:
    """Whether each row's value is only its label again, as a number."""
    try:
        return all(
            float(str(value).replace(",", "")) == float(str(label).replace(",", ""))
            for value, label in zip(values, labels)
        )
    except ValueError:
        return False


def _format_source_trace_entry(
    evidence: dict,
    number: int,
    language: str | None = None,
    number_for=None,
) -> str:
    """One entry of the generated appendix: what the figure is and how to check it.

    Everything here is read off the ledger row, so nothing is asserted that
    the pipeline did not parse out of the source itself — no invented author,
    no invented year. ``number_for`` numbers an input computed earlier, so the
    entry can point at the entry that computes it.
    """
    zh = (language == "zh") if language else _document_language(str(evidence.get("content") or "")) == "zh"
    lang = "zh" if zh else "en"
    label = _TRACE_LABELS[(lang, _is_computed(evidence))]
    head = f"**C{number}**　" if zh else f"**C{number}.** "
    stop, joiner = ("。", "；") if zh else (". ", "; ")

    if _is_computed(evidence):
        result = _derived_result(evidence) or ""
        parts = [f"{result}（{label}）" if zh else f"{result} ({label})"]
        derivation = evidence.get("derivation") if isinstance(evidence.get("derivation"), dict) else {}
        notes, names = _operand_notes(derivation.get("operands"), zh, number_for)
        method = derivation.get("method")
        if method == "formula" and derivation.get("expression"):
            parts.append(("計算式：" if zh else "Formula: ") + _readable_expression(derivation["expression"]))
            if notes:
                parts.append(("其中 " if zh else "where ") + joiner.join(notes))
        elif method == "formula_table" and derivation.get("formulas"):
            formulas = [item for item in derivation["formulas"] if isinstance(item, dict)]
            parts.append(("計算式：" if zh else "Formulas: ") + joiner.join(
                f"{item.get('label')} = {_readable_expression(item.get('expression'))}" for item in formulas
            ))
            if notes:
                parts.append(("共用輸入：" if zh else "Shared inputs: ") + joiner.join(notes))
            per_row: list[str] = []
            for item in formulas:
                used = _names_in_order(item.get("expression"))
                per_row.extend(name for name in used if name not in names and name not in per_row)
            row_inputs = derivation.get("row_inputs") if isinstance(derivation.get("row_inputs"), dict) else {}
            row_values = derivation.get("row_values") if isinstance(derivation.get("row_values"), dict) else {}
            grid = evidence.get("table_grid") if isinstance(evidence.get("table_grid"), dict) else {}
            row_labels = [str(row[0]) for row in grid.get("rows") or [] if row]
            described = []
            given = False
            for name in per_row:
                record = row_inputs.get(name) or {}
                referenced = number_for(str(record["table"])) if record.get("table") and number_for else None
                column = str(record.get("column") or "")
                taken = row_values.get(name)
                if referenced:
                    described.append(
                        f"{name} 取 C{referenced} 表中各列的 {column}" if zh
                        else f"{name} is each row's {column} in C{referenced}"
                    )
                elif column and column != name:
                    described.append(f"{name} 取各列的 {column}" if zh else f"{name} is each row's {column}")
                elif (
                    row_labels and isinstance(taken, list) and len(taken) == len(row_labels)
                    # The rows are already named by it: "各列依序為 0、50…：電網碳強度 0、50…".
                    and not _repeats_labels(taken, row_labels)
                ):
                    described.append(f"{name} " + ("、" if zh else ", ").join(str(value) for value in taken))
                    given = True
                else:
                    described.append(name)
            if described and given:
                parts.append(
                    (f"各列輸入（各列依序為 {'、'.join(row_labels)}）：" if zh
                     else f"Per-row inputs (rows in order: {', '.join(row_labels)}): ")
                    + joiner.join(described)
                )
            elif described:
                parts.append(("各列輸入：" if zh else "Per-row inputs: ") + ("、" if zh else ", ").join(described))
        declared = _declared_citation(evidence)
        if declared:
            from ..source_citation import in_text_author

            year = str(declared.get("year") or "").strip() or ("無日期" if zh else "n.d.")
            parts.append(("資料出處：" if zh else "Data from: ") + f"{in_text_author(declared)} ({year})")
        text = stop.join(part.rstrip("。. ") for part in parts if part) + ("。" if zh else ".")
        return head + text

    shown = _source_trace_statement(evidence)
    if shown:
        body = f"{shown}（{label}）" if zh else f"{shown} ({label})"
    else:
        file_name = str(evidence.get("source_file_name") or evidence.get("source_id") or "")
        span = str(evidence.get("source_span") or "").strip()
        # The span usually opens with the file name already — "products.csv
        # (544 rows)" — so joining the two printed it twice.
        locator = " ".join(
            part for part in (("" if span.startswith(file_name) else file_name), span) if part
        ) or file_name
        quote = " ".join(str(evidence.get("quote") or evidence.get("content") or "").split())
        quote = _clip_at_boundary(quote, SOURCE_TRACE_QUOTE_CHARS)
        quoted = f"“{quote}”" if quote else ""
        if zh:
            body = f"{quoted}（{label}自 {locator}）" if locator else f"{quoted}（{label}）"
        else:
            note = f"({label} from {locator})" if locator else f"({label})"
            body = f"{quoted} {note}" if quoted else note

    # A cited row often carries the outside source it was taken from — a URL,
    # or a house named in a parenthetical. The source document had 37 such
    # links and the deliverable had none. These are read off the row, so the
    # entry asserts only what the source already stated.
    external = _external_references(evidence)
    if external:
        body += joiner + ", ".join(external)
    return head + body


def _derived_result(evidence: dict) -> str | None:
    """A computed figure's result sentence, without the pipeline's file label."""
    content = " ".join(str(evidence.get("content") or "").split())
    body = _DERIVED_LABEL_RE.sub("", content)
    match = re.match(r"(.+?)(?:。|\.(?=\s|$))", body)
    result = (match.group(1) if match else body).strip()
    return _clip_at_boundary(result, SOURCE_TRACE_QUOTE_CHARS) if result else None


#: The label a derived statistic opens with, which names the file the entry
#: already names: "衍生計算(來源:params.csv):", "Derived calculation from params.csv:".
_DERIVED_LABEL_RE = re.compile(
    r"^(?:衍生(?:統計|計算)\s*[(（]來源[:：][^)）]*[)）]\s*[:：]|Derived (?:statistics|calculation) from [^:]+:)\s*"
)


def _clip_at_boundary(text: str, limit: int) -> str:
    """Shorten to ``limit`` characters at a clause boundary, never mid-word."""
    if text.endswith("..."):
        text = text[:-3].rstrip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind(mark) for mark in ("。", "；", ";", "，", ",", "、", " "))
    if boundary >= limit // 2:
        cut = cut[:boundary]
    return cut.rstrip(" ，,、；;：:") + "…"


def _source_trace_statement(evidence: dict) -> str | None:
    """What a data row says, written for a reader.

    None for prose, which is quoted as it stands. The list used to quote every
    entry the same way, so a Chinese course report closed on three pages of
    raw JSON — “{“參數”: “汽油車保養”, “數值”: “5”…}”. A row is its fields.
    A computed figure is written by ``_format_source_trace_entry`` from its
    derivation instead: the result, the formula and every input.
    """
    content = " ".join(str(evidence.get("content") or "").split())
    zh = bool(re.search(r"[一-鿿]", content))
    if _is_computed(evidence):
        return None
    try:
        record = json.loads(str(evidence.get("content") or ""))
    except (ValueError, TypeError):
        return None
    if not isinstance(record, dict) or not record:
        return None
    joiner, pair = ("；", "{}：{}") if zh else ("; ", "{}: {}")
    fields = [pair.format(key, value) for key, value in record.items() if str(value).strip()]
    return _clip_at_boundary(joiner.join(fields), SOURCE_TRACE_QUOTE_CHARS)


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
    declared = _declared_citation(evidence)
    if declared:
        return format_declared_reference(declared)

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
    declared = _declared_citation(evidence)
    if declared:
        metadata = {**metadata, **{k: v for k, v in declared.items() if k in ("title", "author", "year")}}
        if declared.get("url") or declared.get("doi"):
            evidence = {**evidence, "url": declared.get("url") or f"https://doi.org/{declared['doi']}"}
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
    table_evidence_ids: list[str] | tuple[str, ...] = (),
    entry_numbers: dict[str, int] | None = None,
    table_pointers: dict[str, str] | None = None,
) -> tuple[str, list[dict], list[str], list[str], list[str]]:
    """Resolve [CITE:cite_id] references to publication-ready citations.

    Returns:
        - resolved_md: markdown with resolved publication citations
        - new_audit: updated citation audit entries
        - literature_refs: list of formatted reference entries (for reference list)
        - internal_trace_refs: list of internal refs (for audit only)
        - source_trace_refs: the calculation record, one entry per figure it explains

    Sources whose citation cannot honestly be author-year — a project markdown
    file, a dataset, a figure the pipeline computed — used to resolve to the
    empty string, and later to a bare ``[Sn]`` marker beside author-year
    citations. They now resolve to a label saying what the figure is —
    本研究計算 / 本研究整理 — and where the reader can check it: the table the
    document prints it in, the place the author's appendix explains it
    (``explained_in``), or else its entry in the calculation record.

    ``table_evidence_ids`` are the computed tables the draft places: they are
    numbered after the figures the text cites, and ``table_pointers``, when
    given, is filled with where each one's calculation is shown, for its
    attribution line. ``entry_numbers``, when given, is filled with the record
    entry each evidence id received.
    """
    cite_pattern = re.compile(r'\[CITE:([^\]]+)\]')

    resolved_md = merged_md
    language = _document_language(merged_md)

    # Build evidence lookup by evidence_id and source_id
    evidence_by_id = {e["evidence_id"]: e for e in evidence_ledger}
    source_by_id = {e["source_id"]: e for e in evidence_ledger}

    # Track literature references (unique)
    literature_refs: list[str] = []
    seen_refs: set[str] = set()
    numeric_ref_numbers: dict[str, int] = {}

    # Track internal trace references
    internal_trace_refs: list[str] = []

    # Generated appendix: numbered once per evidence row, so the same row cited
    # twice carries the same label both times. Entries are written at the end,
    # because writing one can number the inputs it was computed from.
    source_trace_numbers: dict[str, int] = {}
    source_trace_order: list[str] = []
    source_trace_evidence: dict[str, dict] = {}

    def number_for(evidence_id: str, evidence: dict | None = None) -> int | None:
        row = evidence or evidence_by_id.get(evidence_id)
        if row is None:
            return None
        if evidence_id not in source_trace_numbers:
            source_trace_numbers[evidence_id] = len(source_trace_numbers) + 1
            source_trace_order.append(evidence_id)
            source_trace_evidence[evidence_id] = row
        return source_trace_numbers[evidence_id]

    from .source_tables import placed_table_numbers

    table_numbers = placed_table_numbers(merged_md, evidence_ledger)

    def pointer_for(evidence: dict, key: str, *, table: bool = True) -> str:
        number = number_for(key, evidence)
        if table and key in table_numbers:
            return f"表 {table_numbers[key]}" if language == "zh" else f"Table {table_numbers[key]}"
        derivation = evidence.get("derivation") if isinstance(evidence.get("derivation"), dict) else {}
        explained = str(derivation.get("explained_in") or "").strip()
        return explained or record_pointer(number, language)

    def trace_marker(evidence: dict, cite_id: str) -> str:
        key = str(evidence.get("evidence_id") or cite_id)
        return trace_label(evidence, pointer_for(evidence, key), language)

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
                elif _is_computed(evidence):
                    replacement = _with_trace_label(replacement, trace_marker(evidence, cite_id))
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
                elif _is_computed(evidence):
                    replacement = _with_trace_label(replacement, trace_marker(evidence, cite_id))
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

    # A placed table is numbered after everything the text cites, so its
    # attribution line can name where its calculation is shown — never the
    # table itself.
    for evidence_id in table_evidence_ids or ():
        row = evidence_by_id.get(str(evidence_id))
        if row is None:
            continue
        pointer = pointer_for(row, str(evidence_id), table=False)
        if table_pointers is not None:
            table_pointers[str(evidence_id)] = pointer

    source_trace_refs: list[str] = []
    index = 0
    while index < len(source_trace_order):
        key = source_trace_order[index]
        source_trace_refs.append(_format_source_trace_entry(
            source_trace_evidence[key], source_trace_numbers[key], language, number_for
        ))
        index += 1
    if entry_numbers is not None:
        entry_numbers.update(source_trace_numbers)

    resolved_md = _collapse_adjacent_duplicate_citations(resolved_md)
    resolved_md = merge_adjacent_parentheticals(resolved_md)
    resolved_md = merge_adjacent_trace_labels(resolved_md)
    resolved_md = re.sub(r"[ \t]{2,}", " ", resolved_md)
    resolved_md = _SPACE_BEFORE_TRACE_LABEL_RE.sub("", resolved_md)
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


def _placed_computed_tables(markdown: str, evidence_ledger: list[dict]) -> list[str]:
    """Evidence ids of the computed tables a draft places, in reading order."""
    from .source_tables import TABLE_PLACEHOLDER_RE, collect_source_tables

    markers = [match.group(1).strip() for match in TABLE_PLACEHOLDER_RE.finditer(markdown or "")]
    if not markers:
        return []
    tables = collect_source_tables(evidence_ledger)
    placed: list[str] = []
    for table_id in markers:
        table = tables.get(table_id)
        if table and table.get("computed"):
            for evidence_id in table.get("evidence_ids") or []:
                if evidence_id and evidence_id not in placed:
                    placed.append(evidence_id)
    return placed


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
    entry_numbers: dict[str, int] = {}
    table_pointers: dict[str, str] = {}
    resolved_md, new_audit, literature_refs, internal_refs, source_trace_refs = resolve_citations_publication(
        merged_md,
        evidence_ledger,
        citation_audit,
        citation_style=citation_style,
        gbt7714_as_of=state.created_at.date(),
        table_evidence_ids=_placed_computed_tables(merged_md, evidence_ledger),
        entry_numbers=entry_numbers,
        table_pointers=table_pointers,
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

    # The calculation record. Kept in its own file because REFERENCE_VERIFY
    # rewrites publication_reference_list.md from the curated publication
    # entries alone, and anything else parked there is discarded. The heading
    # stays English here; DOCX_RENDER swaps heading and intro for a Chinese
    # document and renders it as a document of its own.
    source_list_md = ""
    if source_trace_refs:
        source_list_md = f"{SOURCE_LIST_HEADING}\n\n{SOURCE_LIST_INTRO}\n\n" + "".join(
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
    state.citations["record_entry_numbers"] = entry_numbers
    state.citations["table_pointers"] = table_pointers
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

        declared = _declared_citation(ev)
        if declared:
            bib_entries.append(format_declared_bibtex(declared, citekey or source_id))
            continue

        # A file has no publication year. The reference entry for the same
        # source prints "(n.d.)"; this record used to print the year the
        # pipeline happened to run, which is the invented date that rule
        # exists to prevent — in the one artifact a reader imports wholesale.
        year = "n.d."

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
