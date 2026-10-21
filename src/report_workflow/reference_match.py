"""Does a reference name the work its identifier points at?

A DOI that resolves proves a DOI exists. It says nothing about whether the
work behind it is the one the reference names, and an invented reference with
a real DOI pasted in is the commonest kind a reader catches: "DOIs were either
fabricated or they linked to another article." This module fetches the
record behind the identifier and compares it with the reference text, the
same way a reader would:

* **title** -- how much of the record's title appears, in order, inside the
  reference. A reference is written in some citation style, so the title is
  located inside it rather than parsed out of it.
* **authors** -- the surnames written before that title, against the record's
  author names. A real title under invented authors is the second commonest
  kind.
* **year** -- within one year of any date the record carries (online first,
  print, posted).
* **retraction** -- Crossref carries Retraction Watch's notices on the record.

A reference with no identifier is searched by its text in Crossref and
OpenAlex, and, when that settles nothing, by its likely title in OpenAlex's
title index. Only a record whose title appears in the reference nearly whole is
taken as the work it names, and it verifies the reference only when its
authors agree too, since nothing but the text ties the two together.

The comparison is lexical and deterministic: the same reference and the same
record give the same verdict. It does not judge whether the work supports the
sentence that cites it; that needs the work itself. The verdicts:

``verified``   the record's title, and its authors or year, are in the reference
               (for a record found by search: its title, authors and year)
``mismatch``   the identifier points at a different work, or the authors differ
``not_found``  the identifier is not registered, or is a placeholder
``retracted``  the work was retracted and the reference does not say so
``needs_review`` nothing could be confirmed or refuted; a person has to look
``unreachable`` the registry could not be asked, so nothing is known yet

Absence from two indexes is not evidence of fabrication -- reports, standards,
web pages and books are often in neither -- so a reference no search finds is
``needs_review``, never ``mismatch``.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

VERIFIED = "verified"
MISMATCH = "mismatch"
NOT_FOUND = "not_found"
RETRACTED = "retracted"
NEEDS_REVIEW = "needs_review"
UNREACHABLE = "unreachable"

#: Share of the record's title tokens that must appear, in order, in the
#: reference. Above STRONG the reference names this title; below WEAK it names
#: something else.
TITLE_STRONG = 0.85
TITLE_WEAK = 0.5
#: How alike two surnames must be to count as the same name, so that
#: "Kruger" and "Krüger" or a mis-encoded "Aky?rek" still match.
SURNAME_SIMILARITY = 0.85

USER_AGENT = "report-workflow (https://github.com/0Smallcat0/report-workflow)"


class LookupUnavailable(Exception):
    """The registry could not be asked; nothing is known about the reference."""


class NotRegistered(Exception):
    """The registry answered that the identifier does not exist."""


@dataclass(frozen=True)
class WorkRecord:
    """What a registry says about a work."""

    title: str
    authors: tuple[str, ...]
    years: tuple[int, ...]
    source: str
    identifier: str = ""
    retracted: bool = False
    retraction_notice: str = ""


@dataclass(frozen=True)
class ReferenceCheck:
    """The verdict on one reference, and the evidence for it."""

    status: str
    message: str
    identifier: str = ""
    record: WorkRecord | None = None
    title_score: float | None = None
    unmatched_authors: tuple[str, ...] = field(default_factory=tuple)
    authors_match: bool | None = None
    year_matches: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        record = self.record
        return {
            "status": self.status,
            "message": self.message,
            "identifier": self.identifier,
            "title_score": None if self.title_score is None else round(self.title_score, 3),
            "unmatched_authors": list(self.unmatched_authors),
            "authors_match": self.authors_match,
            "year_matches": self.year_matches,
            "record": None
            if record is None
            else {
                "title": record.title,
                "authors": list(record.authors[:10]),
                "years": list(record.years),
                "source": record.source,
                "identifier": record.identifier,
                "retracted": record.retracted,
            },
        }


# ---------------------------------------------------------------------------
# Text normalization


def _fold(text: str) -> str:
    """Lowercase, strip accents, keep letters, digits and CJK characters."""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _tokens(text: str) -> list[str]:
    """Words for Latin script, one token per character for CJK."""

    folded = _fold(text)
    out: list[str] = []
    for word in re.findall(r"[a-z0-9]+|[^\sa-z0-9]", folded):
        if _CJK_RE.match(word) or word.isalnum():
            out.append(word)
    return out


def _title_tokens(title: str) -> list[str]:
    title = re.sub(r"^\s*(retracted|withdrawn)\s*(article)?\s*[:.\-]\s*", "", title, flags=re.I)
    return _tokens(title)


def _align_compounds(have: list[str], wanted: list[str]) -> list[str]:
    """Spell the reference's compounds the way the title does.

    "knowledgebase" against "Knowledge-Base", or "pre training" against
    "Pretraining", is one word written two ways, not a different title.
    """

    wanted_set = set(wanted)
    split = {a + b: (a, b) for a, b in zip(wanted, wanted[1:])}
    out: list[str] = []
    i = 0
    while i < len(have):
        token = have[i]
        if token not in wanted_set and token in split:
            out.extend(split[token])
        elif (
            i + 1 < len(have)
            and token + have[i + 1] in wanted_set
            and not (token in wanted_set and have[i + 1] in wanted_set)
        ):
            out.append(token + have[i + 1])
            i += 1
        else:
            out.append(token)
        i += 1
    return out


def _title_match(reference: str, title: str) -> tuple[float, int, list[str]]:
    wanted = _title_tokens(title)
    if not wanted:
        return 0.0, -1, []
    have = _align_compounds(_tokens(reference), wanted)
    matcher = SequenceMatcher(None, have, wanted, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    matched = sum(block.size for block in blocks)
    start = blocks[0].a if blocks else -1
    return matched / len(wanted), start, have


def title_score(reference: str, title: str) -> tuple[float, int]:
    """Share of the title's tokens found in order in the reference, and where it starts.

    The start is a token offset into the reference, or -1 when nothing matched.
    """

    share, start, _ = _title_match(reference, title)
    return share, start


_INITIALS_RE = re.compile(r"^(?:[A-ZÀ-ɏ]\.?[\s\-]*){1,4}$")
_AUTHOR_STOP = {"and", "et", "al", "in", "eds", "ed", "editor", "editors", "with", "others"}


def cited_surnames(author_text: str) -> list[str]:
    """Surnames in the author part of a reference, in any common style.

    "Atanassova, I., Bertin, M., & Mayr, P." and "Ilaria Atanassova, Marc
    Bertin and Philipp Mayr" both give Atanassova, Bertin, Mayr.
    """

    # "(2025, October)" is a date, closed or cut off where the title starts.
    text = re.sub(r"\([^)]*(?:\)|$)", " ", author_text)
    text = re.sub(r"\bet\s+al\b\.?", ",", text, flags=re.I)
    parts = re.split(r",|;|&|\band\b|\bund\b|\bet\b|、|，", text)
    surnames: list[str] = []
    for part in parts:
        part = part.strip(" .:\"'“”‘’?")
        if not part or _INITIALS_RE.match(part):
            continue
        if _CJK_RE.search(part):
            surnames.append(part)
            continue
        words = [w.strip("()[]") for w in re.split(r"\s+", part)]
        words = [w for w in words if w and not _INITIALS_RE.match(w) and not re.search(r"\d", w)]
        words = [w for w in words if _fold(w).strip(".") not in _AUTHOR_STOP]
        if not words:
            continue
        # "Hugo Touvron" -> Touvron; "Atanassova" -> Atanassova. A last word
        # in lower case is the tail of a name a lost character split
        # ("Szepesv ri"), so it keeps the word before it.
        name = words[-1].strip(".")
        if len(words) >= 2 and name[:1].islower():
            name = f"{words[-2]} {name}"
        if len(_fold(name)) >= 2:
            surnames.append(name)
    return surnames


def _name_tokens(names: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for name in names:
        out.update(_tokens(name))
        folded = "".join(_tokens(name))
        if _CJK_RE.search(name):
            out.add(folded)
    return out


def unmatched_surnames(author_text: str, record_authors: tuple[str, ...]) -> tuple[list[str], int]:
    """Cited surnames that are not among the record's author names, and how many were cited."""

    cited = cited_surnames(author_text)
    known = _name_tokens(record_authors)
    joined_cjk = "".join(t for t in known if _CJK_RE.search(t))
    missing: list[str] = []
    for surname in cited:
        if _CJK_RE.search(surname):
            if all(ch in joined_cjk for ch in "".join(_tokens(surname))):
                continue
            missing.append(surname)
            continue
        pieces = _tokens(surname)
        if not pieces:
            continue
        # "van der Berg" is three tokens of the record; a mis-encoded
        # "Aky?rek" is two pieces of one name, compared joined.
        joined = "".join(pieces)
        if all(piece in known for piece in pieces) or joined in known:
            continue
        if any(SequenceMatcher(None, joined, name).ratio() >= SURNAME_SIMILARITY for name in known):
            continue
        missing.append(surname)
    return missing, len(cited)


def cited_years(reference: str) -> list[int]:
    years = [int(y) for y in re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", reference)]
    return years


# ---------------------------------------------------------------------------
# Identifiers

_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_ARXIV_RE = re.compile(r"arxiv(?:\.org/(?:abs|pdf)/|\s*:\s*|\s+preprint\s+arxiv:\s*)(\d{4}\.\d{4,5})(v\d+)?", re.I)
_ARXIV_PLACEHOLDER_RE = re.compile(r"arxiv:\s*\d{4}\.(?:x{3,}|\?{3,})", re.I)
_DOI_PLACEHOLDER_RE = re.compile(r"\b10\.(?:x{4}|\d{4,9}/x{3,})", re.I)


def extract_doi(reference: str) -> str:
    match = _DOI_RE.search(reference)
    if not match:
        return ""
    return match.group(1).rstrip(".,;)]}>")


def extract_arxiv(reference: str) -> str:
    match = _ARXIV_RE.search(reference)
    return match.group(1) if match else ""


def has_placeholder_identifier(reference: str) -> bool:
    return bool(_ARXIV_PLACEHOLDER_RE.search(reference) or _DOI_PLACEHOLDER_RE.search(reference))


# ---------------------------------------------------------------------------
# Registries

HttpGet = Callable[[str, dict[str, str]], tuple[int, str]]


#: arXiv asks for one request every three seconds.
_MIN_INTERVAL = {"export.arxiv.org": 3.0}
_last_request: dict[str, float] = {}


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    host = urllib.parse.urlsplit(url).hostname or ""
    wait = _MIN_INTERVAL.get(host, 0.0) - (time.monotonic() - _last_request.get(host, float("-inf")))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LookupUnavailable(str(getattr(exc, "reason", exc))) from exc


def _mailto() -> str:
    return os.environ.get("REPORT_WORKFLOW_MAILTO", "")


#: OpenAlex gives every IP without a key a small shared daily budget (about a
#: hundred searches) and a free key ten times that.
OPENALEX_KEY_ENV = "OPENALEX_API_KEY"


def _csl_years(item: dict[str, Any]) -> tuple[int, ...]:
    years: set[int] = set()
    for key in ("issued", "published-print", "published-online", "published", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            years.add(parts[0][0])
    return tuple(sorted(years))


def _csl_authors(item: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for author in item.get("author") or []:
        name = " ".join(str(author.get(k, "")) for k in ("given", "family")).strip()
        name = name or str(author.get("literal") or author.get("name") or "")
        if name:
            names.append(name)
    return tuple(names)


def _csl_title(item: dict[str, Any]) -> str:
    title = item.get("title") or ""
    if isinstance(title, list):
        title = title[0] if title else ""
    return str(title)


def _retraction(item: dict[str, Any]) -> tuple[bool, str]:
    for update in item.get("updated-by") or []:
        if str(update.get("type", "")).lower() in {"retraction", "withdrawal", "removal"}:
            when = ((update.get("updated") or {}).get("date-parts") or [[None]])[0][0]
            return True, f"{update.get('label') or 'Retraction'} {update.get('DOI', '')} ({when})".strip()
    return False, ""


def fetch_doi(doi: str, get: HttpGet = _http_get) -> WorkRecord | None:
    """The DOI's metadata by content negotiation at doi.org, or None when it has none.

    Crossref, DataCite and mEDRA DOIs answer with CSL JSON; Crossref's carries
    Retraction Watch notices in ``updated-by``.
    """

    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/:;()")
    status, body = get(url, {"Accept": "application/vnd.citationstyles.csl+json"})
    if status == 404:
        raise NotRegistered(f"DOI {doi} is not registered (doi.org 404)")
    if status >= 500 or status == 429:
        raise LookupUnavailable(f"doi.org answered {status}")
    if status != 200 or not body.lstrip().startswith("{"):
        return None
    item = json.loads(body)
    retracted, notice = _retraction(item)
    return WorkRecord(
        title=_csl_title(item),
        authors=_csl_authors(item),
        years=_csl_years(item),
        source="doi.org",
        identifier=f"doi:{doi}",
        retracted=retracted,
        retraction_notice=notice,
    )


_ATOM = "{http://www.w3.org/2005/Atom}"


def fetch_arxiv(arxiv_id: str, get: HttpGet = _http_get) -> WorkRecord:
    url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
    status, body = get(url, {})
    if status != 200:
        raise LookupUnavailable(f"arXiv answered {status}")
    root = ET.fromstring(body)
    entry = root.find(f"{_ATOM}entry")
    title = entry.findtext(f"{_ATOM}title") if entry is not None else None
    if entry is None or not title or entry.findtext(f"{_ATOM}id", "").endswith("api/errors"):
        raise NotRegistered(f"arXiv {arxiv_id} does not exist")
    authors = tuple(
        (author.findtext(f"{_ATOM}name") or "").strip() for author in entry.findall(f"{_ATOM}author")
    )
    years = {int(text[:4]) for text in (entry.findtext(f"{_ATOM}published"), entry.findtext(f"{_ATOM}updated")) if text}
    return WorkRecord(
        title=" ".join(title.split()),
        authors=authors,
        years=tuple(sorted(years)),
        source="arxiv.org",
        identifier=f"arXiv:{arxiv_id}",
    )


def _search_text(reference: str) -> str:
    text = re.sub(r"https?://\S+|\bdoi:\s*\S+|\b10\.\d{4,9}/\S+", " ", reference, flags=re.I)
    text = re.sub(r"\bpp?\.\s*[\d\s\-–?]+", " ", text)
    return " ".join(text.split())[:300]


def search_crossref(reference: str, get: HttpGet = _http_get) -> list[WorkRecord]:
    params = {"query.bibliographic": _search_text(reference), "rows": "5"}
    if _mailto():
        params["mailto"] = _mailto()
    status, body = get("https://api.crossref.org/works?" + urllib.parse.urlencode(params), {})
    if status != 200:
        raise LookupUnavailable(f"Crossref answered {status}")
    records = []
    for item in json.loads(body).get("message", {}).get("items", []):
        retracted, notice = _retraction(item)
        records.append(
            WorkRecord(
                title=_csl_title(item),
                authors=_csl_authors(item),
                years=_csl_years(item),
                source="crossref",
                identifier=f"doi:{item.get('DOI', '')}",
                retracted=retracted,
                retraction_notice=notice,
            )
        )
    return records


def search_openalex(reference: str, get: HttpGet = _http_get) -> list[WorkRecord]:
    # OpenAlex reads &, ?, |, ! and quotes as search syntax and answers 400.
    query = " ".join(re.sub(r"[^\w\s.,'\-]", " ", _search_text(reference)).split())
    return _openalex_works({"search": query, "per_page": "5"}, get)


#: Where one part of a reference ends and the next begins: a full stop, or the
#: question mark that ends a quoted title, then a space. Not the stop after an
#: initial ("M. Gales") or after "et al".
_PART_SPLIT_RE = re.compile(r"(?<![\s.][A-Z])(?<!\bet al)[.?!]\s+(?=\S)")


def guess_title(reference: str) -> str:
    """The part of a reference that is most likely its title, or "" when none is.

    Only used to ask OpenAlex's title index. What decides a verdict is still
    where the record's title sits in the whole reference.
    """

    text = re.sub(r"https?://\S+|\bdoi:\s*\S+", " ", reference, flags=re.I)
    parts = [part.strip(" \"'“”‘’?") for part in _PART_SPLIT_RE.split(text)]
    for part in [part for part in parts if part][1:]:
        # "In Proceedings of ...", "In: Poster abstracts ...", "(2025)".
        if re.match(r"in\b", part, re.I) or re.fullmatch(r"\(?\d{4}[a-z]?\)?", part):
            continue
        if len(re.findall(r"[^\W\d_]{2,}", part)) >= 3:
            return part[:200]
    return ""


def search_openalex_title(reference: str, get: HttpGet = _http_get) -> list[WorkRecord]:
    """Works whose title matches the reference's guessed title.

    A search on the whole reference -- authors, venue, pages and all -- often
    misses a conference paper that has no DOI; its title alone finds it.
    """

    guess = guess_title(reference)
    if not guess:
        return []
    # A comma separates filters and a pipe means "or" inside one.
    query = " ".join(re.sub(r"[^\w\s'\-]", " ", guess).split())
    return _openalex_works({"filter": f"title.search:{query}", "per_page": "5"}, get)


def _openalex_works(params: dict[str, str], get: HttpGet) -> list[WorkRecord]:
    if _mailto():
        params["mailto"] = _mailto()
    headers = {}
    if os.environ.get(OPENALEX_KEY_ENV):
        headers["Authorization"] = f"Bearer {os.environ[OPENALEX_KEY_ENV]}"
    status, body = get("https://api.openalex.org/works?" + urllib.parse.urlencode(params), headers)
    if status == 429:
        raise LookupUnavailable(
            f"OpenAlex's daily budget is used up (it resets at midnight UTC; a free key in {OPENALEX_KEY_ENV} raises it)"
        )
    if status != 200:
        raise LookupUnavailable(f"OpenAlex answered {status}")
    records = []
    for item in json.loads(body).get("results", []):
        authors = tuple(
            str((authorship.get("author") or {}).get("display_name") or "")
            for authorship in item.get("authorships") or []
        )
        year = item.get("publication_year")
        records.append(
            WorkRecord(
                title=str(item.get("title") or item.get("display_name") or ""),
                authors=authors,
                years=(year,) if isinstance(year, int) else (),
                source="openalex",
                identifier=str(item.get("doi") or item.get("id") or ""),
                retracted=bool(item.get("is_retracted")),
                retraction_notice="retracted (OpenAlex)" if item.get("is_retracted") else "",
            )
        )
    return records


# ---------------------------------------------------------------------------
# Verdicts


def compare(reference: str, record: WorkRecord, *, identifier: str = "") -> ReferenceCheck:
    """Judge one reference against the record its identifier (or a search) returned."""

    score, start, have = _title_match(reference, record.title)
    ref_tokens_text = reference
    if start > 0:
        # Everything before the title is the author list (and a year, which
        # cited_surnames ignores).
        ref_tokens_text = _author_prefix(reference, have[:start])
    elif start == 0:
        ref_tokens_text = ""
    missing, cited = unmatched_surnames(ref_tokens_text, record.authors) if record.authors else ([], 0)
    years = cited_years(reference)
    year_ok: bool | None = None
    if years and record.years:
        year_ok = any(abs(y - r) <= 1 for y in years for r in record.years)
    authors_ok: bool | None = None if cited == 0 else not missing
    first_author_missing = bool(missing) and bool(cited) and missing[0] == cited_surnames(ref_tokens_text)[0]

    shown = f"“{record.title}”"
    if record.authors:
        shown += f" by {_short_authors(record.authors)}"
    if record.years:
        shown += f" ({record.years[0]})"
    where = record.identifier or record.source
    common = {
        "identifier": identifier or record.identifier,
        "record": record,
        "title_score": score,
        "unmatched_authors": tuple(missing),
        "authors_match": authors_ok,
        "year_matches": year_ok,
    }

    if score < TITLE_WEAK and authors_ok is not True:
        return ReferenceCheck(
            MISMATCH,
            f"{where} is {shown}, which is not the work this reference names",
            **common,
        )
    # The authors differ when the first cited author, two cited authors, or
    # half of them are not the record's. One stray name among several is more
    # often a typo than an invention, and is left to a person.
    if score >= TITLE_STRONG and missing and (
        first_author_missing or len(missing) >= 2 or len(missing) * 2 >= cited
    ):
        return ReferenceCheck(
            MISMATCH,
            f"{where} is {shown}; {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not among its authors",
            **common,
        )
    if score >= TITLE_STRONG and record.retracted:
        if re.search(r"retract", reference, re.I):
            return ReferenceCheck(VERIFIED, f"matches {where}; retracted, as the reference says", **common)
        return ReferenceCheck(
            RETRACTED,
            f"{where} was retracted ({record.retraction_notice or 'notice on record'}) "
            "and the reference does not say so",
            **common,
        )
    if score >= TITLE_STRONG and not missing and (authors_ok or year_ok):
        return ReferenceCheck(VERIFIED, f"matches {where}: title, {'authors' if authors_ok else 'year'}", **common)
    reasons = []
    if score < TITLE_STRONG:
        reasons.append(f"only {score:.0%} of the title of {shown} appears in it")
    if missing:
        reasons.append(f"{', '.join(missing)} not among the authors of {where}")
    if year_ok is False:
        reasons.append(f"year differs from {where} ({', '.join(map(str, record.years))})")
    if not reasons:
        reasons.append(f"title matches {where} but neither authors nor year could be compared")
    return ReferenceCheck(NEEDS_REVIEW, "; ".join(reasons), **common)


def _author_prefix(reference: str, prefix_tokens: list[str]) -> str:
    """The original text of the reference up to where the title starts."""

    if not prefix_tokens:
        return ""
    folded = _fold(reference)
    position = 0
    for token in prefix_tokens:
        found = folded.find(token, position)
        if found < 0:
            break
        position = found + len(token)
    return reference[:position]


def _short_authors(authors: tuple[str, ...]) -> str:
    def surname(name: str) -> str:
        return name.split()[-1] if name.split() else name

    if len(authors) == 1:
        return surname(authors[0])
    if len(authors) == 2:
        return f"{surname(authors[0])} and {surname(authors[1])}"
    return f"{surname(authors[0])} et al."


def check_reference(reference: str, *, get: HttpGet = _http_get, search: bool = True) -> ReferenceCheck:
    """Verdict on one reference string, asking doi.org, arXiv, Crossref and OpenAlex as needed."""

    if has_placeholder_identifier(reference):
        return ReferenceCheck(NOT_FOUND, "the identifier is a placeholder (XXXX), not a real one")

    doi = extract_doi(reference)
    arxiv = "" if doi else extract_arxiv(reference)
    try:
        if doi:
            try:
                record = fetch_doi(doi, get)
            except NotRegistered as exc:
                return ReferenceCheck(NOT_FOUND, str(exc), identifier=f"doi:{doi}")
            if record is None:
                return ReferenceCheck(
                    NEEDS_REVIEW,
                    f"DOI {doi} resolves but its registry returns no metadata to compare",
                    identifier=f"doi:{doi}",
                )
            return compare(reference, record, identifier=f"doi:{doi}")
        if arxiv:
            try:
                record = fetch_arxiv(arxiv, get)
            except NotRegistered as exc:
                return ReferenceCheck(NOT_FOUND, str(exc), identifier=f"arXiv:{arxiv}")
            return compare(reference, record, identifier=f"arXiv:{arxiv}")
        if not search:
            return ReferenceCheck(NEEDS_REVIEW, "no DOI or arXiv identifier to check")
        return _check_by_search(reference, get)
    except LookupUnavailable as exc:
        identifier = f"doi:{doi}" if doi else f"arXiv:{arxiv}" if arxiv else ""
        return ReferenceCheck(UNREACHABLE, f"could not be checked: {exc}", identifier=identifier)


def _check_by_search(reference: str, get: HttpGet) -> ReferenceCheck:
    candidates: list[WorkRecord] = []
    errors: list[str] = []
    for searcher in (search_crossref, search_openalex):
        try:
            candidates.extend(searcher(reference, get))
        except LookupUnavailable as exc:
            errors.append(str(exc))
    verdict = _best_search_verdict(reference, candidates)
    if verdict is None or verdict.status != VERIFIED:
        try:
            candidates.extend(search_openalex_title(reference, get))
        except LookupUnavailable as exc:
            errors.append(str(exc))
        verdict = _best_search_verdict(reference, candidates)
    if verdict is None:
        if errors and not candidates:
            return ReferenceCheck(UNREACHABLE, f"could not be checked: {'; '.join(errors)}")
        return ReferenceCheck(
            NEEDS_REVIEW,
            "no DOI or arXiv identifier, and no Crossref or OpenAlex record carries its title",
        )
    return verdict


def _best_search_verdict(reference: str, candidates: list[WorkRecord]) -> ReferenceCheck | None:
    named = [
        (title_score(reference, record.title)[0], index, record)
        for index, record in enumerate(candidates)
        if len(_title_tokens(record.title)) >= 2
    ]
    named = [item for item in named if item[0] >= TITLE_STRONG]
    # Prefer the closest title, and a record with authors over one without.
    best: ReferenceCheck | None = None
    for _, _, record in sorted(named, key=lambda item: (-item[0], not item[2].authors, item[1])):
        verdict = _searched(compare(reference, record))
        if verdict.status == VERIFIED:
            return verdict
        if best is None:
            best = verdict
    return best


#: Words of a title that do not tell one work from another.
_TITLE_STOP = {"a", "an", "the", "of", "and", "in", "on", "for", "to", "with", "by", "from", "at", "as", "or", "via"}
#: A searched title with fewer informative words than this ("The XML Markup
#: Evaluation Corpus") can belong to several works -- a blog post and a
#: report, a chapter and a paper -- so an author disagreement with one of
#: them is not a verdict.
SEARCH_MISMATCH_MIN_TITLE = 5


def _searched(verdict: ReferenceCheck) -> ReferenceCheck:
    """A search hit is tied to the reference by its text alone, so it must agree on more.

    With an identifier the reference itself names the record. A hit found by
    title verifies only when the authors agree and the year does not differ:
    a proceedings volume carries the venue's title and no authors, and a short
    title can sit inside a longer one by the same person. It is called a
    mismatch or a retraction only when its title is distinctive.
    """

    record = verdict.record
    if record is None:
        return verdict
    shown = record.identifier or record.source
    if verdict.status in (VERIFIED, RETRACTED) and not verdict.authors_match:
        return ReferenceCheck(
            NEEDS_REVIEW,
            f"{shown} carries this title, but its authors could not be compared with the reference's",
            **_evidence(verdict),
        )
    if verdict.status == VERIFIED and verdict.year_matches is False:
        return ReferenceCheck(
            NEEDS_REVIEW,
            f"{shown} carries this title and authors, but its year ({', '.join(map(str, record.years))}) differs",
            **_evidence(verdict),
        )
    informative = [t for t in _title_tokens(record.title) if t not in _TITLE_STOP]
    if verdict.status == MISMATCH and len(informative) < SEARCH_MISMATCH_MIN_TITLE:
        return ReferenceCheck(NEEDS_REVIEW, verdict.message, **_evidence(verdict))
    return verdict


def _evidence(check: ReferenceCheck) -> dict[str, Any]:
    return {
        "identifier": check.identifier,
        "record": check.record,
        "title_score": check.title_score,
        "unmatched_authors": check.unmatched_authors,
        "authors_match": check.authors_match,
        "year_matches": check.year_matches,
    }
