"""Check a finished draft's figures and quotations against the files it cites.

``report-workflow check-draft draft.docx --source a.pdf --source b.pdf`` is for
the report that was already written -- by hand, with ChatGPT, with NotebookLM --
and now has to be checked before it is handed in. It does not ask whether a
sentence is true. It asks the two questions a marker asks with the PDF open:
is this number on a page of the source, next to the words the sentence uses,
and is this quotation in the source word for word. Each answer comes back with
the file, the page and the source's own sentence, so the reader checks one
page instead of the whole paper.

Only the sentences that can be checked this way are read: those that state a
figure and those that quote. The rest are counted and left alone.

No model and no network: the same draft and the same sources give the same
answers on every run.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .nodes.factuality_check import (
    _QUOTED_PHRASE_RE,
    _REPORTED_SPEECH_RE,
    _decimal_comma_to_point,
    _decimal_places,
    _extract_numbers_with_unit,
    _normalize_for_numbers,
    _normalize_number_str,
    _normalize_unit,
    numbers_with_spans,
)
from .reference_list import _HEADING_RE as _REFERENCES_HEADING_RE

FOUND = "found"
NOT_FOUND = "not_found"

SOURCE_SUFFIXES = (".pdf", ".docx", ".md", ".txt")

#: How far either side of a figure the source is read for the sentence's words.
#: A table row sits a line or two from its header and its caption, and prose
#: states a figure and what it measures within a sentence; 250 characters
#: covers both in the papers measured.
CONTEXT_CHARS = 250
#: A source of at least this many pages has words common enough to ignore...
COMMON_MIN_PAGES = 5
#: ...namely those on more than this share of its pages.
COMMON_PAGE_SHARE = 0.5

#: Shared words a source passage needs before a figure in it counts as the one
#: the sentence states. Two, or every word the sentence has when it has fewer.
REQUIRED_TERMS = 2
#: A figure of this many significant digits, printed exactly, needs only one.
DISTINCTIVE_DIGITS = 4


# ----------------------------------------------------------------------
# Reading the draft
# ----------------------------------------------------------------------

_MD_CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MD_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_MD_TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|`)")


def _table_rows_as_text(rows: list[list[str]]) -> list[str]:
    """A table as one line per data row, each cell beside its column's header.

    A row of bare cells ("LLaMA-65B | 63.4") states a figure without saying
    what it measures, and the header is what does.
    """
    rows = [[" ".join(str(cell or "").split()) for cell in row] for row in rows if any(str(c or "").strip() for c in row)]
    if len(rows) < 2:
        return [" ".join(rows[0])] if rows else []
    header, body = rows[0], rows[1:]
    lines = []
    for row in body:
        cells = [f"{name} {value}".strip() if name and name != value else value for name, value in zip(header, row)]
        lines.append("; ".join(cell for cell in cells if cell))
    return lines


def _docx_body(path: Path) -> list[str]:
    from docx import Document

    document = Document(str(path))
    paragraphs: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if not text:
            continue
        if _REFERENCES_HEADING_RE.match(text):
            break
        if style.startswith("heading") or style == "title":
            continue
        paragraphs.append(text)
    for table in document.tables:
        paragraphs.extend(_table_rows_as_text([[cell.text for cell in row.cells] for row in table.rows]))
    return paragraphs


def _markdown_body(text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    table: list[list[str]] = []
    in_code = False

    def flush() -> None:
        if current:
            paragraphs.append(" ".join(current))
            current.clear()
        if table:
            paragraphs.extend(_table_rows_as_text(table))
            table.clear()

    for line in text.splitlines():
        if _MD_CODE_FENCE_RE.match(line):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if _REFERENCES_HEADING_RE.match(stripped):
            break
        if not stripped or _MD_HEADING_RE.match(line) or stripped.startswith("<!--"):
            flush()
            continue
        if stripped.startswith("|"):
            if current:
                paragraphs.append(" ".join(current))
                current.clear()
            if not _MD_TABLE_RULE_RE.match(stripped):
                table.append([cell.strip() for cell in stripped.strip("|").split("|")])
            continue
        if table:
            flush()
        stripped = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*)", "", stripped)
        current.append(stripped)
    flush()
    return [_MD_EMPHASIS_RE.sub("", _MD_LINK_RE.sub(r"\1", paragraph)) for paragraph in paragraphs]


def read_draft(path: str | Path) -> list[str]:
    """The draft's body text as paragraphs: no headings, nothing after the references."""

    path = Path(path)
    if path.suffix.lower() == ".docx":
        return _docx_body(path)
    return _markdown_body(path.read_text(encoding="utf-8-sig", errors="replace"))


#: Where a full stop does not end a sentence.
_ABBREVIATION_RE = re.compile(
    r"(?:\bet al|\be\.g|\bi\.e|\bcf|\bvs|\bFigs?|\bEqs?|\bNo|\bapprox|\bresp|\bSec|\bTab|\bca|\bal"
    r"|\bpp?|\bvol|\bch|\bDr|\bMr|\bMs|\bProf|\b[A-Z])\.$"
)
_SENTENCE_END_RE = re.compile(r"[。！？]|[.!?][\"”’)\]]*(?=\s+)")


def split_sentences(paragraph: str) -> list[str]:
    """Sentences, without splitting at "et al.", "e.g.", initials or inside a quotation."""

    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(paragraph):
        end = match.end()
        piece = paragraph[start:end]
        if match.group(0)[0] == "." and _ABBREVIATION_RE.search(paragraph[start:match.start() + 1]):
            continue
        # An open quotation continues past its own full stop.
        if (piece.count("“") > piece.count("”")) or (piece.count('"') % 2 == 1):
            continue
        sentences.append(piece.strip())
        start = end
    tail = paragraph[start:].strip()
    if tail:
        sentences.append(tail)
    return [sentence for sentence in sentences if re.search(r"[A-Za-z0-9一-鿿]", sentence)]


# ----------------------------------------------------------------------
# What in a sentence is checkable
# ----------------------------------------------------------------------

#: (Touvron et al., 2023), (Brown et al., 2020; Rae et al., 2021), （王，2020）.
_PAREN_CITATION_RE = re.compile(r"[(（][^()（）]*?(?:19|20)\d{2}[a-z]?[^()（）]*[)）]")
_CITATION_NAME_RE = re.compile(r"[A-Z][a-z]|et al|等|[一-鿿]{1,4}\s*[，,]\s*(?:19|20)\d{2}")
#: Hoffmann et al. (2022), Wei 等人（2022）, 王小明（2020）: the year belongs to
#: the citation, the name to the sentence.
_NARRATIVE_YEAR_RE = re.compile(r"(?<=[A-Za-z.一-鿿])\s*[(（]\s*(?:19|20)\d{2}[a-z]?\s*[)）]")
_BRACKET_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,–—-]\s*\d+)*\s*\]")
#: Table 3, Fig. 2, Section 4.1, Eq. (5), p. 12: a pointer into a document, not a figure.
_CROSS_REFERENCE_RE = re.compile(
    r"\b(?:Tables?|Tab\.|Figures?|Figs?\.|Sections?|Sec\.|Eqs?\.|Equations?|Appendix|Appendices"
    r"|Chapters?|Algorithms?|Steps?|pp?\.|pages?|lines?|footnotes?|Theorem|Lemma|Definition)"
    r"\s*[(（]?\d+(?:\.\d+)*[a-z]?[)）]?"
    r"(?:\s*(?:and|,|–|-|to)\s*[(（]?\d+(?:\.\d+)*[a-z]?[)）]?)*",
    re.IGNORECASE,
)
_CJK_CROSS_REFERENCE_RE = re.compile(r"[表圖图式]\s*\d+(?:[.-]\d+)*|第\s*\d+\s*[章節节頁页條条項项段]|§\s*\d+(?:\.\d+)*")
#: A name with a digit in it -- GPT-3, LLaMA-65B, A100, GSM8k -- names a thing;
#: its digits are not a figure the sentence states.
#: β1 and pass@1 are names too.
_IDENTIFIER_RE = re.compile(r"(?<![\w\-‐@])[A-Za-zα-ωΑ-Ω][A-Za-z\-‐_@]*\d[\w\-‐@]*")
_CHEMICAL_RE = re.compile(r"^(?:CO2|CH4|N2O|H2O|O2|NO2|SO2|PM2|PM10)", re.IGNORECASE)
_SINGLE_QUOTED_RE = re.compile(r"‘([^’]{4,200})’")
_ELLIPSIS_RE = re.compile(r"…|\.\s?\.\s?\.|\[[^\]]*\]")


def _strip_citations(text: str) -> str:
    def paren(match: re.Match) -> str:
        return " " if _CITATION_NAME_RE.search(match.group(0)) else match.group(0)

    text = _PAREN_CITATION_RE.sub(paren, text)
    text = _NARRATIVE_YEAR_RE.sub(" ", text)
    return _BRACKET_CITATION_RE.sub(" ", text)


def _blank(text: str, pattern: re.Pattern, keep=None) -> str:
    """Blank out every match, keeping the length so offsets still point where they did."""

    def repl(match: re.Match) -> str:
        if keep is not None and keep(match.group(0)):
            return match.group(0)
        return " " * len(match.group(0))

    return pattern.sub(repl, text)


def _mask_non_figures(text: str) -> str:
    text = _blank(text, _CROSS_REFERENCE_RE)
    text = _blank(text, _CJK_CROSS_REFERENCE_RE)
    return _blank(text, _IDENTIFIER_RE, keep=lambda token: bool(_CHEMICAL_RE.match(token)))


def _quotations(sentence: str) -> list[tuple[str, int, int]]:
    """Quoted passages with their spans; a phrase in quotation marks of under three words is not a quotation."""

    found = []
    for pattern in (_QUOTED_PHRASE_RE, _SINGLE_QUOTED_RE):
        for match in pattern.finditer(sentence):
            group = next((index for index in range(1, (match.lastindex or 0) + 1) if match.group(index)), None)
            if group is None:
                continue
            found.append((match.group(group), match.start(), match.end()))
    for match in _REPORTED_SPEECH_RE.finditer(sentence):
        found.append((match.group(1), match.start(1) - 1, match.end(1) + 1))
    kept = []
    for phrase, start, end in found:
        latin_words = re.findall(r"[A-Za-z0-9]+", phrase)
        cjk = re.findall(r"[一-鿿]", phrase)
        if len(cjk) >= 4 or len(latin_words) >= 3:
            kept.append((phrase.strip(), start, end))
    return sorted(kept, key=lambda item: item[1])


_STOPWORDS = frozenset("""
about above according across after again against also although among another
around because been before being below between both cannot could does doing
done down during each either even every from further have having here however
into itself just least less like made make makes many more most much must near
nearly only other others otherwise over paper papers per perhaps rather report
reported reports same several should show showed shown shows since some such
than that their them then there these they this those though through thus
together under unlike until upon very what when where whereas which while
whose will with within without would your study studies authors author find
finds found finding note notes noted state states stated claim claims says
said write writes wrote writing table figure section result results using used
uses use roughly approximately around nearly almost about over under
""".split())


def _sentence_terms(text: str) -> tuple[list[str], list[str]]:
    """(Latin terms, CJK bigrams) a source passage is compared on.

    A Latin word is cut to its first six letters so "outperforms" meets
    "outperform" and "competitive" meets "competition"; a name with a digit in
    it is kept whole, because "llama65b" and "llama13b" are different models.
    Terms are compared with the passage's spaces and punctuation removed, which
    is what lets a page whose words came out glued together still be read.
    """
    text = unicodedata.normalize("NFKC", text)
    latin: list[str] = []
    for token in _IDENTIFIER_RE.findall(text):
        key = "".join(char for char in token.lower() if char.isalnum())
        if key and key not in latin:
            latin.append(key)
    for word in re.findall(r"[A-Za-z][A-Za-z'’\-]*", _IDENTIFIER_RE.sub(" ", text)):
        key = re.sub(r"[^a-z]", "", word.lower())
        if len(key) < 4 or key in _STOPWORDS:
            continue
        key = key[:6]
        if key not in latin:
            latin.append(key)
    bigrams: list[str] = []
    for run in re.findall(r"[一-鿿]+", text):
        for index in range(len(run) - 1):
            bigram = run[index:index + 2]
            if bigram not in bigrams:
                bigrams.append(bigram)
    return latin, bigrams


@dataclass
class DraftSentence:
    number: int
    text: str
    figures: list[tuple[str, str]]
    quotes: list[str]
    latin_terms: list[str]
    cjk_terms: list[str]


def checkable_sentences(paragraphs: list[str]) -> tuple[list[DraftSentence], int]:
    """The sentences that state a figure or quote, and how many others there were."""

    picked: list[DraftSentence] = []
    others = 0
    for paragraph in paragraphs:
        for sentence in split_sentences(paragraph):
            quotes = _quotations(sentence)
            body = sentence
            for _phrase, start, end in reversed(quotes):
                body = body[:start] + " " * (end - start) + body[end:]
            body = _strip_citations(body)
            figures: list[tuple[str, str]] = []
            for figure in _extract_numbers_with_unit(_mask_non_figures(_normalize_for_numbers(body))):
                if figure not in figures:
                    figures.append(figure)
            if not figures and not quotes:
                others += 1
                continue
            latin, cjk = _sentence_terms(_strip_citations(sentence))
            picked.append(DraftSentence(
                number=len(picked) + 1,
                text=sentence,
                figures=figures,
                quotes=[phrase for phrase, _s, _e in quotes],
                latin_terms=latin,
                cjk_terms=cjk,
            ))
    return picked, others


# ----------------------------------------------------------------------
# Reading the sources
# ----------------------------------------------------------------------

def _squash(text: str) -> tuple[str, list[int]]:
    """Lower-cased letters and digits only, and for each kept character its offset.

    Spaces, punctuation and line-end hyphens are what differ between a PDF's
    text layer and the sentence copied from it -- "founda-\\ntion",
    "WeintroduceLLaMA" -- and none of them carries the wording.
    """
    kept: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        lowered = char.lower()
        if lowered.isalnum():
            kept.append(lowered)
            offsets.append(index)
    return "".join(kept), offsets


@dataclass
class Reading:
    """One way of reading one page: its text, and the figures in it."""

    text: str
    squashed: str
    offsets: list[int]
    prefix: list[int]
    figures: list[tuple[str, str, int, int]]

    @classmethod
    def of(cls, raw: str) -> "Reading":
        text = _decimal_comma_to_point(_normalize_for_numbers(raw or ""))
        masked = _mask_non_figures(text)
        normalized, figures = numbers_with_spans(masked)
        if len(normalized) != len(text):
            text = normalized
        squashed, offsets = _squash(text)
        prefix = [0] * (len(text) + 1)
        position = 0
        for index in range(len(text)):
            prefix[index] = position
            if position < len(offsets) and offsets[position] == index:
                position += 1
        prefix[len(text)] = position
        return cls(text, squashed, offsets, prefix, figures)

    def window(self, start: int, end: int) -> str:
        """The squashed text within CONTEXT_CHARS of [start, end)."""
        low = self.prefix[max(0, start - CONTEXT_CHARS)]
        high = self.prefix[min(len(self.text), end + CONTEXT_CHARS)]
        return self.squashed[low:high]


@dataclass
class SourcePage:
    number: int | None
    readings: list[Reading]


@dataclass
class Source:
    path: Path
    pages: list[SourcePage]
    sha256: str
    is_pdf: bool = False
    has_cjk: bool = False
    _page_counts: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def name(self) -> str:
        return self.path.name

    def is_common(self, term: str) -> bool:
        """Is the term on more than half the pages -- "model" in a paper about models?

        Such a word sits beside almost every figure in the document, so finding
        it beside one says nothing about which figure the sentence meant.
        """
        if len(self.pages) < COMMON_MIN_PAGES:
            return False
        if term not in self._page_counts:
            self._page_counts[term] = sum(
                1 for page in self.pages if any(term in reading.squashed for reading in page.readings)
            )
        return self._page_counts[term] > COMMON_PAGE_SHARE * len(self.pages)


class SourceError(Exception):
    """A source that cannot be read, with the reason in the reader's words."""


#: At most this share of a page's words may cross the gap between two columns.
_GUTTER_CROSSING_SHARE = 0.04


def column_split(page) -> float | None:
    """The x at which a two-column page divides, or None for a single column.

    Read in storage order, the first page of the LLaMA paper still alternates
    lines of the abstract with lines of the introduction beside it, so a
    sentence quoted from the abstract is on that page and in no reading of it.
    The gap between the columns is found from the words themselves: the line
    down the middle third of the page that the fewest words cross.
    """
    words = page.extract_words(x_tolerance=1)
    if len(words) < 80:
        return None
    width = float(page.width)
    best = None
    for step in range(35, 66):
        x = width * step / 100
        crossing = sum(1 for word in words if word["x0"] < x < word["x1"])
        left = sum(1 for word in words if word["x1"] <= x)
        if left < 0.25 * len(words) or len(words) - left - crossing < 0.25 * len(words):
            continue
        if best is None or crossing < best[0]:
            best = (crossing, x)
    if best is None or best[0] > _GUTTER_CROSSING_SHARE * len(words):
        return None
    return best[1]


def _column_text(page, split: float) -> str:
    left = page.crop((0, 0, split, page.height)).extract_text(x_tolerance=1) or ""
    right = page.crop((split, 0, page.width, page.height)).extract_text(x_tolerance=1) or ""
    return left + "\n\n" + right


def load_source(path: str | Path) -> Source:
    from .parsers.semi_structured_parser import _page_text, parse_pdf, parse_semi_structured

    path = Path(path)
    if not path.is_file():
        raise SourceError(f"No such file: {path}")
    suffix = path.suffix.lower()
    if suffix not in SOURCE_SUFFIXES:
        raise SourceError(f"{path.name}: a source must be one of {', '.join(SOURCE_SUFFIXES)}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if suffix == ".pdf":
        parsed = parse_pdf(str(path))
        if not parsed.get("success"):
            raise SourceError(f"{path.name}: {parsed.get('error') or 'could not be read'}")
        by_page: dict[int, list[str]] = {}
        for block in parsed["blocks"]:
            by_page.setdefault(int(block["page_number"]), []).append(block.get("content") or "")
        import pdfplumber

        pages: list[SourcePage] = []
        with pdfplumber.open(str(path)) as pdf:
            for number, page in enumerate(pdf.pages, 1):
                # Several readings of the page. pdfplumber's default orders a
                # two-column paper line by line across both columns and runs
                # tightly set words together; read in the order the PDF stores
                # its text, with a narrower gap for a space, the same page
                # mostly comes out column by column with its spaces, and read
                # one column at a time it does throughout. The default is kept
                # beside them because a PDF that stores its text out of order
                # reads worse the other ways, and a table or title that spans
                # both columns is cut in two by the column reading. The column
                # reading goes first where there is one: a match tied between
                # readings is shown from it, in the source's own sentence order.
                texts = [_page_text(page, use_text_flow=True, x_tolerance=1)]
                split = column_split(page)
                if split is not None:
                    texts.insert(0, _column_text(page, split))
                texts += by_page.get(number, [])
                readings = [Reading.of(text) for text in texts if text and text.strip()]
                if readings:
                    pages.append(SourcePage(number, readings))
        source = Source(path, pages, digest, is_pdf=True)
    else:
        parsed = parse_semi_structured(str(path), suffix.lstrip("."))
        if not parsed.get("success"):
            raise SourceError(f"{path.name}: {parsed.get('error') or 'could not be read'}")
        text = "\n\n".join(block.get("content") or "" for block in parsed["blocks"])
        source = Source(path, [SourcePage(None, [Reading.of(text)])], digest)
    if not any(page.readings for page in source.pages):
        raise SourceError(f"{path.name}: no text could be read from it")
    sample = "".join(page.readings[0].text for page in source.pages[:5])
    source.has_cjk = len(re.findall(r"[一-鿿]", sample)) > 0.05 * max(1, len(sample))
    return source


# ----------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------

#: Units a figure is measured in, after FE's own folding. Anything else written
#: after a number -- "20 benchmarks", "2,048 GPUs" -- is what was counted, and a
#: paraphrase is free to call it something else.
_MEASURES = frozenset("""
% usd eur gbp jpy cny twd krw hkd aud cad sgd kg g mg t lb km m cm mm nm mi ft
s ms min h day week month year v mv kv a ma w kw mw gw kwh mwh j kj mj pa kpa
mpa bar psi c f k rpm hz khz mhz ghz db l ml kb mb gb tb pb b
年 月 日 天 週 周 季 季度 公斤 公克 克 毫克 公噸 噸 吨 公里 公尺 公分 毫米 公升
美元 元 歐元 欧元 日圓 日元 人民幣 人民币 新臺幣 新台幣 港幣 港币 萬元 万元 億元 亿元
倍 成 百分點 百分点 度 千瓦 瓦 伏特 安培
""".split())

_UNIT_FOLD = {
    "percent": "%", "pct": "%", "percentage": "%",
    "thousand": "k", "million": "m", "mn": "m", "billion": "b", "bn": "b", "trillion": "t",
    "sec": "s", "second": "s", "seconds": "s", "mins": "min", "minute": "min", "minutes": "min",
    "hr": "h", "hrs": "h", "hour": "h", "hours": "h", "days": "day", "weeks": "week",
    "months": "month", "years": "year", "yr": "year", "yrs": "year",
    "天": "day", "日": "day", "年": "year", "月": "month", "週": "week", "周": "week",
}


def _unit_parts(unit: str) -> list[str]:
    parts = []
    for part in _normalize_unit(unit).split("/"):
        part = _UNIT_FOLD.get(part, part)
        if part not in _MEASURES and part.endswith("s") and part[:-1] in _MEASURES:
            part = part[:-1]
        parts.append(part)
    return parts


def units_agree(claim_unit: str, source_unit: str) -> bool:
    """Do these units say the same thing, where both name a unit at all?"""

    claim, source = _unit_parts(claim_unit), _unit_parts(source_unit)
    if claim[0] not in _MEASURES or source[0] not in _MEASURES:
        return True
    if claim[0] != source[0]:
        return False
    if len(claim) > 1 and len(source) > 1 and claim[1] in _MEASURES and source[1] in _MEASURES:
        return claim[1] == source[1]
    return True


def states(claim_number: str, source_number: str) -> bool:
    """Does the source figure say what the sentence says, at the sentence's precision?

    "69%" is 68.9 rounded and "68.9%" is 68.9; "68.0%" is not 68.9, although
    FE's one-percent tolerance would let it through. That tolerance is for a
    claim citing a computed value; here the sentence and the page are meant to
    print the same figure, and a single wrong digit is exactly the error.
    """
    try:
        claimed = _normalize_number_str(claim_number)
        stated = _normalize_number_str(source_number)
    except ValueError:
        return False
    places = _decimal_places(claim_number)
    if places > _decimal_places(source_number):
        return abs(claimed - stated) <= 1e-9 * max(1.0, abs(claimed))
    return abs(claimed - stated) <= 0.5 * 10 ** -places + 1e-9 * max(1.0, abs(claimed))


@dataclass
class Location:
    source: Source
    page: int | None
    reading: Reading
    start: int
    end: int
    end_page: int | None = None

    def label(self) -> str:
        if self.page is None:
            return self.source.name
        if self.end_page and self.end_page != self.page:
            return f"{self.source.name} pp. {self.page}–{self.end_page}"
        return f"{self.source.name} p. {self.page}"


@dataclass
class ItemResult:
    kind: str  # "figure" or "quote"
    text: str
    status: str
    location: Location | None = None
    matched_terms: list[str] = field(default_factory=list)
    figure_only: bool = False
    message: str = ""


def _terms_for(sentence: DraftSentence, source: Source) -> list[str]:
    terms = sentence.latin_terms + (sentence.cjk_terms if source.has_cjk else [])
    specific = [term for term in terms if not source.is_common(term)]
    return specific or terms


def unit_supports(claim_unit: str, source_unit: str) -> bool:
    """units_agree, and a figure measured in hours or terabytes needs the page to say so.

    A table cell of scores or percentages is printed bare, with the unit in
    the column heading, so a bare figure still supports "68.9%"; "21 hours"
    met by a bare 21.7 in a score table is a different figure.
    """
    if not units_agree(claim_unit, source_unit):
        return False
    claim = _unit_parts(claim_unit)[0] if claim_unit else ""
    if claim in _MEASURES and claim != "%":
        return bool(source_unit) and _unit_parts(source_unit)[0] in _MEASURES
    return True


def _matched(terms: list[str], window: str) -> list[str]:
    return [term for term in terms if term in window]


def _significant_digits(number: str) -> int:
    return len(re.sub(r"\D", "", number).lstrip("0"))


def _figure_label(number: str, unit: str) -> str:
    """68.9%, 65B, 1.4T, but 21 days and 63 g; a counted noun is left off."""
    if not unit or _unit_parts(unit)[0] not in _MEASURES:
        return number
    spaced = unit[:1].isascii() and unit[:1].isalpha() and len(unit) > 2
    return f"{number}{' ' if spaced else ''}{unit}"


def check_figure(number: str, unit: str, sentence: DraftSentence, sources: list[Source]) -> ItemResult:
    """Find the figure on a page whose surrounding words are the sentence's own."""

    label = _figure_label(number, unit)
    best: tuple[int, Location, list[str], bool] | None = None
    elsewhere: Location | None = None
    distinctive = _significant_digits(number) >= DISTINCTIVE_DIGITS
    for source in sources:
        terms = _terms_for(sentence, source)
        all_terms = sentence.latin_terms + (sentence.cjk_terms if source.has_cjk else [])
        for page in source.pages:
            for reading in page.readings:
                for source_number, source_unit, start, end in reading.figures:
                    if not states(number, source_number) or not unit_supports(unit, source_unit):
                        continue
                    window = reading.window(start, end)
                    location = Location(source, page.number, reading, start, end)
                    if distinctive and _decimal_places(source_number) == _decimal_places(number):
                        # 1,022,362 printed digit for digit is not a coincidence;
                        # one shared word, however common, places it.
                        matched, required = _matched(all_terms, window), min(1, len(all_terms))
                    else:
                        matched, required = _matched(terms, window), min(REQUIRED_TERMS, len(terms))
                    if len(matched) < required:
                        elsewhere = elsewhere or location
                        continue
                    if best is None or len(matched) > best[0]:
                        best = (len(matched), location, matched, required == 0)
    if best is not None:
        return ItemResult("figure", label, FOUND, best[1], best[2], best[3])
    message = f"{label} is not stated beside these words in any source"
    near = _nearest_in_context(number, unit, sentence, sources)
    if near is not None:
        value, location = near
        message += f"; {location.label()} states {value} there"
    elif elsewhere is not None:
        message += f"; {elsewhere.label()} has {label}, but in a passage that shares none of the sentence's words"
    return ItemResult("figure", label, NOT_FOUND, near[1] if near else None, message=message)


def _nearest_in_context(number: str, unit: str, sentence: DraftSentence, sources: list[Source]):
    """The closest figure in a passage that does share the sentence's words: the likely typo."""

    try:
        target = _normalize_number_str(number)
    except ValueError:
        return None
    best = None
    for source in sources:
        terms = _terms_for(sentence, source)
        required = min(REQUIRED_TERMS, len(terms))
        if not required:
            continue
        for page in source.pages:
            for reading in page.readings[:1]:
                for source_number, source_unit, start, end in reading.figures:
                    if not units_agree(unit, source_unit):
                        continue
                    try:
                        value = _normalize_number_str(source_number)
                    except ValueError:
                        continue
                    distance = abs(value - target)
                    if distance == 0 or distance > 0.5 * max(abs(target), 1e-9):
                        continue
                    if best is not None and distance >= best[0]:
                        continue
                    if len(_matched(terms, reading.window(start, end))) >= required:
                        best = (distance, source_number, Location(source, page.number, reading, start, end))
    return (best[1], best[2]) if best else None


def _quote_segments(quote: str) -> list[str]:
    segments = []
    for piece in _ELLIPSIS_RE.split(unicodedata.normalize("NFKC", quote)):
        squashed, _ = _squash(piece)
        if len(squashed) >= 3:
            segments.append(squashed)
    return segments


def _find_segments(haystack: str, segments: list[str]) -> tuple[int, int] | None:
    position = 0
    first = None
    for segment in segments:
        found = haystack.find(segment, position)
        if found < 0:
            return None
        first = found if first is None else first
        position = found + len(segment)
    return (first, position) if first is not None else None


def check_quote(quote: str, sources: list[Source]) -> ItemResult:
    """Find the quotation word for word, on one page or running onto the next."""

    segments = _quote_segments(quote)
    if not segments:
        return ItemResult("quote", quote, NOT_FOUND, message="the quotation has no words to look for")
    for source in sources:
        for index, page in enumerate(source.pages):
            for reading_index, reading in enumerate(page.readings):
                span = _find_segments(reading.squashed, segments)
                if span:
                    start, end = reading.offsets[span[0]], reading.offsets[span[1] - 1] + 1
                    return ItemResult("quote", quote, FOUND, Location(source, page.number, reading, start, end))
                following = source.pages[index + 1] if index + 1 < len(source.pages) else None
                if following is None or reading_index >= len(following.readings):
                    continue
                joined = reading.squashed + following.readings[reading_index].squashed
                span = _find_segments(joined, segments)
                if span and span[0] < len(reading.squashed) < span[1]:
                    start = reading.offsets[span[0]]
                    return ItemResult(
                        "quote", quote, FOUND,
                        Location(source, page.number, reading, start, len(reading.text), end_page=following.number),
                    )
    return ItemResult("quote", quote, NOT_FOUND, message=_closest_quote(segments, sources))


def _closest_quote(segments: list[str], sources: list[Source]) -> str:
    """Where the longest run of the quotation's own words does appear."""

    from difflib import SequenceMatcher

    needle = "".join(segments)
    best = (0, None, None, 0)
    for source in sources:
        for page in source.pages:
            reading = page.readings[0]
            matcher = SequenceMatcher(None, needle, reading.squashed, autojunk=False)
            match = matcher.find_longest_match(0, len(needle), 0, len(reading.squashed))
            if match.size > best[0]:
                best = (match.size, Location(source, page.number, reading, 0, 0), reading, match.b)
    size, location, reading, at = best
    message = "not found word for word in any source"
    if location is not None and size >= max(12, len(needle) // 3):
        start = reading.offsets[at]
        location.start, location.end = start, reading.offsets[at + size - 1] + 1
        message += (
            f"; the longest stretch that is ({size} of {len(needle)} letters) is on {location.label()}: "
            f"“{source_sentence(location)}”"
        )
    return message


def source_sentence(location: Location, limit: int = 320) -> str:
    """The source's own sentence around a match, joined across its line breaks."""

    text = location.reading.text
    start, end = location.start, location.end
    left = max(text.rfind(". ", 0, start), text.rfind("\n\n", 0, start), text.rfind("。", 0, start))
    left = 0 if left < 0 or start - left > limit else left + 1
    stops = [index for index in (text.find(". ", end), text.find("。", end), text.find("\n\n", end)) if index >= 0]
    right = min(stops) + 1 if stops and min(stops) - end <= limit else min(len(text), end + 120)
    if start - left > limit:
        left = max(0, start - 120)
    snippet = text[left:right]
    snippet = re.sub(r"(\w)[-‐]\n(\w)", r"\1\2", snippet)
    snippet = " ".join(snippet.split())
    if len(snippet) > limit:
        offset = max(0, (start - left) - limit // 3)
        snippet = ("…" if offset else "") + snippet[offset:offset + limit].strip() + "…"
    return snippet


@dataclass
class SentenceResult:
    sentence: DraftSentence
    items: list[ItemResult]

    @property
    def status(self) -> str:
        return FOUND if all(item.status == FOUND for item in self.items) else NOT_FOUND


def check_draft(paragraphs: list[str], sources: list[Source]) -> tuple[list[SentenceResult], int]:
    sentences, others = checkable_sentences(paragraphs)
    results = []
    for sentence in sentences:
        items = [check_quote(quote, sources) for quote in sentence.quotes]
        items += [check_figure(number, unit, sentence, sources) for number, unit in sentence.figures]
        results.append(SentenceResult(sentence, items))
    return results, others


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------

def result_to_dict(result: SentenceResult) -> dict:
    return {
        "number": result.sentence.number,
        "sentence": result.sentence.text,
        "status": result.status,
        "items": [
            {
                "kind": item.kind,
                "text": item.text,
                "status": item.status,
                "source": item.location.source.name if item.location and item.status == FOUND else None,
                "page": item.location.page if item.location and item.status == FOUND else None,
                "source_sentence": source_sentence(item.location) if item.location and item.status == FOUND else None,
                "matched_terms": item.matched_terms,
                "figure_only": item.figure_only,
                "message": item.message,
            }
            for item in result.items
        ],
    }


def is_chinese(paragraphs: list[str]) -> bool:
    sample = "".join(paragraphs)[:4000]
    return len(re.findall(r"[一-鿿]", sample)) > 0.2 * max(1, len(re.findall(r"\S", sample)))


_LABELS = {
    "en": {
        "title": "Source check", "intro": (
            "Every sentence of the draft that states a figure or quotes a source is listed below with the "
            "page of the source it was found on and the source's own sentence. Checked by report-workflow "
            "check-draft {version}: a figure is found when a page prints it, at the precision the draft "
            "gives, within a few lines of the sentence's own words; a quotation is found when a page holds "
            "it word for word. Nothing here judges whether the sentence's meaning follows from the source."),
        "draft": "Draft", "sources": "Sources", "file": "File", "pages": "Pages", "summary": "Result",
        "found": "found", "not_found": "not found", "sentences": "sentences checked",
        "unchecked": "other sentences state no figure or quotation and were not checked",
        "figure": "Figure", "quote": "Quotation", "figure_only": "matched on the figure alone; "
        "the sentence shares no words with the source's language",
        "missing": "Not found", "page_image": "highlighted",
    },
    "zh": {
        "title": "原件對照", "intro": (
            "下列為本文中寫到數字或直接引文的每一句，逐條附上在原件中的檔名、頁碼與原文句子。"
            "以 report-workflow check-draft {version} 比對：數字須在同一頁、以本文寫出的精度印出，"
            "且附近幾行有本句用到的字詞，才算找到；引文須在原件中逐字出現，才算找到。"
            "本表不判斷句意是否能由原件推得。"),
        "draft": "本文", "sources": "原件", "file": "檔名", "pages": "頁數", "summary": "結果",
        "found": "找到", "not_found": "找不到", "sentences": "句已比對",
        "unchecked": "句沒有數字或引文，未比對",
        "figure": "數字", "quote": "引文", "figure_only": "只比對到數字：本句與原件語言不同，沒有共用字詞",
        "missing": "找不到", "page_image": "劃線處",
    },
}


def write_appendix(
    path: str | Path,
    draft_path: str | Path,
    sources: list[Source],
    results: list[SentenceResult],
    others: int,
    *,
    chinese: bool,
    images: bool = True,
) -> int:
    """Write the appendix; return how many page images were written beside it."""

    from . import __version__

    labels = _LABELS["zh" if chinese else "en"]
    path = Path(path)
    image_dir = path.with_name(path.stem + "_files")
    draft_path = Path(draft_path)
    found = sum(1 for result in results if result.status == FOUND)
    lines = [
        f"# {labels['title']}",
        "",
        labels["intro"].format(version=__version__),
        "",
        f"**{labels['draft']}:** {draft_path.name} (SHA-256 `{hashlib.sha256(draft_path.read_bytes()).hexdigest()[:16]}`)",
        "",
        f"| {labels['sources']} | {labels['pages']} | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    for source in sources:
        pages = str(len(source.pages)) if source.is_pdf else "—"
        lines.append(f"| {source.name} | {pages} | `{source.sha256[:16]}` |")
    lines += [
        "",
        f"**{labels['summary']}:** {found} {labels['found']}, {len(results) - found} {labels['not_found']} "
        f"({len(results)} {labels['sentences']}; {others} {labels['unchecked']})",
        "",
    ]
    written = 0
    for result in results:
        status = labels["found"] if result.status == FOUND else labels["not_found"]
        lines += [f"## {result.sentence.number}. {status.upper() if not chinese else status}", "",
                  f"> {result.sentence.text}", ""]
        for item in result.items:
            kind = labels["figure"] if item.kind == "figure" else labels["quote"]
            shown = item.text if item.kind == "figure" else f"“{item.text}”"
            if item.status == FOUND and item.location is not None:
                lines.append(f"- **{kind} {shown}** — {item.location.label()}: “{source_sentence(item.location)}”")
                if item.figure_only:
                    lines.append(f"  *{labels['figure_only']}*")
                if images and item.location.source.is_pdf and item.location.page is not None:
                    image = _page_image(item.location, image_dir, written + 1)
                    if image is not None:
                        written += 1
                        lines.append(f"\n  ![{item.location.label()} — {labels['page_image']}]({image_dir.name}/{image.name})")
            else:
                lines.append(f"- **{kind} {shown}** — {labels['missing']}: {item.message}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return written


def _page_image(location: Location, image_dir: Path, index: int) -> Path | None:
    """A band of the source page around the match, with the match highlighted.

    The match is found again on the page itself so it can be drawn: the
    figure as printed, or the quotation's letters with anything between them.
    A page it cannot be found on again gets no picture rather than a wrong one.
    """
    import pdfplumber

    needle = location.reading.text[location.start:location.end]
    squashed, _ = _squash(needle)
    if not squashed:
        return None
    if re.fullmatch(r"[-\d.,]+", needle.strip()):
        pattern = r"(?<![\d.])" + re.escape(needle.strip()) + r"(?![\d])"
        nth = location.reading.text[:location.start].count(needle.strip())
    else:
        pattern = r"[^0-9A-Za-z一-鿿]*".join(re.escape(char) for char in squashed[:400])
        nth = location.reading.squashed[:location.reading.prefix[location.start]].count(squashed)
    try:
        with pdfplumber.open(str(location.source.path)) as pdf:
            page = pdf.pages[location.page - 1]
            match = None
            regions = [(page, {"use_text_flow": True})]
            split = column_split(page)
            if split is not None:
                regions += [
                    (page.crop((0, 0, split, page.height)), {}),
                    (page.crop((split, 0, page.width, page.height)), {}),
                ]
            for region_index, (region, options) in enumerate(regions):
                matches = region.search(pattern, regex=True, case=False, return_chars=True,
                                        return_groups=False, x_tolerance=1, **options)
                if matches:
                    match = matches[min(nth, len(matches) - 1)] if region_index == 0 else matches[0]
                    break
            if match is None:
                return None
            rects: dict[int, list[float]] = {}
            for char in match.get("chars") or [match]:
                key = round(char["top"])
                box = rects.setdefault(key, [char["x0"], char["top"], char["x1"], char["bottom"]])
                box[0], box[1] = min(box[0], char["x0"]), min(box[1], char["top"])
                box[2], box[3] = max(box[2], char["x1"]), max(box[3], char["bottom"])
            top = max(0, match["top"] - 110)
            bottom = min(page.height, match["bottom"] + 110)
            band = page.crop((0, top, page.width, bottom))
            image = band.to_image(resolution=130)
            image.draw_rects([tuple(box) for box in rects.values()], fill=(255, 214, 0, 70), stroke=(220, 60, 0), stroke_width=2)
            image_dir.mkdir(parents=True, exist_ok=True)
            out = image_dir / f"{index:02d}-{location.source.path.stem}-p{location.page}.png"
            image.save(str(out))
            return out
    except Exception:
        return None
