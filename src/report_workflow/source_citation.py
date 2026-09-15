"""Bibliographic metadata an author declares for a source file.

A source file is not a publication, and the pipeline refuses to pretend it is:
a file name says nothing about who wrote the thing or when, so a Markdown
transcription of a government report used to resolve to an ``[S3]`` marker and
a line in the generated Sources list, and a PDF to a citation tag cut from its
file name. That is the honest default. It also meant a course report or a
paper could not cite its literature the way its reader expects — ``(Negri &
Bieker, 2025)`` in the text and an APA entry in the reference list — no matter
how completely the author knew the details, because there was nowhere to say
them.

This module is that place. The author states the metadata beside the file
(``source_files=[{"path": ..., "role": "source_data", "citation": {...}}]``),
and the citation layer formats only what was stated: no field is guessed from a
file name, a missing year prints as ``n.d.``, and an author list the formatter
cannot split into surnames is refused with a message asking for ``in_text``
rather than turned into a name nobody wrote.
"""
from __future__ import annotations

import re
from typing import Any

#: Fields a declared citation may carry. Anything else is refused, so a typo
#: ("auther") fails at prepare time instead of silently dropping the author.
CITATION_FIELDS = (
    "author",       # "Negri, M., & Bieker, G." / "經濟部能源署"
    "year",         # "2025", "2024a", "n.d."
    "title",
    "container",    # journal, newspaper or website the title appeared in
    "volume",
    "issue",
    "pages",
    "publisher",
    "description",  # "Data set", "Press release", "Report No. C 444"
    "doi",
    "url",
    "in_text",      # the author part of the in-text citation, when not derivable
    "reference",    # a complete reference entry to use verbatim
)

_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
#: "Negri, M." / "de Chalendar, J. A." — a surname, a comma, initials.
_PERSON_RE = re.compile(r"\s*(?:&\s*)?([^,&]+?),\s*((?:[A-Z][a-z]?\.(?:\s*-?\s*[A-Z]\.)*\s*)+)(?:,|$)")
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


class CitationMetadataError(ValueError):
    """A declared citation that cannot be formatted without inventing a field."""


def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def normalize_citation(raw: Any, where: str = "citation") -> dict[str, str] | None:
    """Validate a declared citation and return it with string values.

    ``None`` and an empty mapping mean "nothing declared". A mapping with
    unknown keys, or with neither an author nor a verbatim reference, is an
    error: the caller meant to declare something and the message says what.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CitationMetadataError(f"{where} must be an object with fields such as author, year, title")
    unknown = sorted(str(key) for key in raw if key not in CITATION_FIELDS)
    if unknown:
        raise CitationMetadataError(
            f"{where} has unknown field(s) {', '.join(unknown)}; "
            f"allowed fields are {', '.join(CITATION_FIELDS)}"
        )
    citation = {
        key: " ".join(str(value).split())
        for key, value in raw.items()
        if value is not None and str(value).strip()
    }
    if not citation:
        return None
    if not citation.get("author") and not citation.get("reference"):
        raise CitationMetadataError(
            f"{where} needs an author (a person, several people, or an organization); "
            "a source whose author is unknown should not be declared as a citation"
        )
    if citation.get("reference") and not (citation.get("in_text") or citation.get("author")):
        raise CitationMetadataError(
            f"{where} gives a verbatim reference but no author or in_text, so the "
            "in-text citation would have to be invented"
        )
    if citation.get("author") and not citation.get("in_text"):
        # Fail at prepare time, not at render time, when the author list is
        # not one this module can reduce to surnames.
        in_text_author(citation, where)
    return citation


def in_text_author(citation: dict[str, str], where: str = "citation") -> str:
    """The author part of an in-text citation: "Negri & Bieker", "Machala et al."."""
    if citation.get("in_text"):
        return citation["in_text"]
    author = citation.get("author", "")
    if _is_cjk(author):
        names = [part.strip() for part in re.split(r"[、，,]", author) if part.strip()]
        if len(names) >= 3:
            return f"{names[0]}等人"
        if len(names) == 2:
            return f"{names[0]}與{names[1]}"
        return author
    if "," not in author:
        # A group author: "International Energy Agency", "Tesla, Inc." has a
        # comma and is handled by the surname parse failing below.
        return author
    surnames = [match.group(1).strip() for match in _PERSON_RE.finditer(author)]
    rebuilt = len("".join(match.group(0) for match in _PERSON_RE.finditer(author)).replace(" ", ""))
    if not surnames or rebuilt < len(author.replace(" ", "")) * 0.8:
        raise CitationMetadataError(
            f"{where}: cannot split author {author!r} into surnames; add "
            "\"in_text\" with the author part of the in-text citation, for example "
            "\"Negri & Bieker\" or \"Tesla\""
        )
    if len(surnames) >= 3:
        return f"{surnames[0]} et al."
    if len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}"
    return surnames[0]


def _year(citation: dict[str, str]) -> str:
    year = citation.get("year", "")
    if year:
        return year
    return "無日期" if _is_cjk(citation.get("author", "") + citation.get("in_text", "")) else "n.d."


def format_in_text(citation: dict[str, str]) -> str:
    """A parenthetical citation. Full-width punctuation for a CJK author."""
    author = in_text_author(citation)
    year = _year(citation)
    if _is_cjk(author):
        return f"（{author}，{year}）"
    return f"({author}, {year})"


def _doi_or_url(citation: dict[str, str]) -> str:
    doi = citation.get("doi", "")
    if doi:
        return "https://doi.org/" + _DOI_PREFIX_RE.sub("", doi)
    return citation.get("url", "")


#: An element that already ends in one of these takes no second mark. The
#: reference list printed "gasoline cars?.", "VDI e.V.." and "減碳足跡？。".
_ENDING_MARKS = (".", "?", "!", "。", "？", "！")


def _mark_after(text: str, mark: str) -> str:
    return "" if text.endswith(_ENDING_MARKS) else mark


def format_reference(citation: dict[str, str]) -> str:
    """One reference-list entry in APA shape, from declared fields only.

    The title (or the container, for an article) is italicised: that marks the
    entry as a publication to reference curation, which deletes entries it
    cannot recognise as one.
    """
    if citation.get("reference"):
        return citation["reference"]
    author = citation.get("author", "")
    year = _year(citation)
    title = citation.get("title", "")
    container = citation.get("container", "")
    publisher = citation.get("publisher", "")
    description = citation.get("description", "")
    link = _doi_or_url(citation)
    zh = _is_cjk(author + title + container)

    if zh:
        parts = [f"{author}（{year}）。"]
        if container:
            if title:
                parts.append(title + _mark_after(title, "。"))
            locator = f"*{container}*"
            if citation.get("volume"):
                locator += f"，{citation['volume']}"
            if citation.get("issue"):
                locator += f"（{citation['issue']}）"
            if citation.get("pages"):
                locator += f"，{citation['pages']}"
            parts.append(f"{locator}。")
        elif title:
            label = f"〔{description}〕" if description else ""
            parts.append(f"*{title}*{label}" + ("。" if label else _mark_after(title, "。")))
        if publisher and publisher != author:
            parts.append(publisher + _mark_after(publisher, "。"))
        if link:
            parts.append(link)
        return "".join(parts).strip()

    # APA ends the author element with a period: "Bieker, G. (2021)." already
    # has one from the initial, a group author needs one added —
    # "International Energy Agency. (2021)."
    parts = [f"{author if author.endswith('.') else author + '.'} ({year})."]
    if container:
        if title:
            parts.append(title + _mark_after(title, "."))
        locator = f"*{container}"
        if citation.get("volume"):
            locator += f", {citation['volume']}*"
        else:
            locator += "*"
        if citation.get("issue"):
            locator += f"({citation['issue']})"
        if citation.get("pages"):
            locator += f", {citation['pages']}"
        parts.append(f"{locator}.")
    elif title:
        label = f" [{description}]" if description else ""
        parts.append(f"*{title}*{label}" + ("." if label else _mark_after(title, ".")))
    if publisher and publisher != author:
        parts.append(publisher + _mark_after(publisher, "."))
    if link:
        parts.append(link)
    return " ".join(parts).strip()


def format_bibtex(citation: dict[str, str], key: str) -> str:
    """A BibTeX record carrying exactly the declared fields."""
    clean = {name: value.replace("{", "").replace("}", "") for name, value in citation.items()}
    entry_type = "article" if clean.get("container") else "misc"
    fields = [f"  author = {{{clean.get('author') or clean.get('in_text', '')}}}"]
    if clean.get("title"):
        fields.append(f"  title = {{{clean['title']}}}")
    fields.append(f"  year = {{{clean.get('year') or 'n.d.'}}}")
    for bib_name, name in (("journal", "container"), ("volume", "volume"), ("number", "issue"),
                           ("pages", "pages"), ("publisher", "publisher"), ("doi", "doi"), ("url", "url")):
        if clean.get(name):
            fields.append(f"  {bib_name} = {{{clean[name]}}}")
    safe_key = re.sub(r"[^A-Za-z0-9_]", "", key) or "source"
    return f"@{entry_type}{{{safe_key},\n" + ",\n".join(fields) + "\n}"


# "n.d.-a" is how two undated works by one author are told apart, and the
# shape missed it: four citations of two U.S. DOE pages printed side by side.
_LATIN_PAREN = r"\([^()（）]*?,\s*(?:\d{4}[a-z]?|n\.d\.(?:-[a-z])?)\)"
_CJK_PAREN = r"（[^()（）]*?，\s*(?:\d{4}[a-z]?|無日期(?:-?[a-z])?)）"
_ADJACENT_LATIN_RE = re.compile(rf"({_LATIN_PAREN})(?:\s*;?\s*({_LATIN_PAREN}))+")
_ADJACENT_CJK_RE = re.compile(rf"({_CJK_PAREN})(?:\s*[;；]?\s*({_CJK_PAREN}))+")


def merge_adjacent_parentheticals(text: str) -> str:
    """"(A, 2025) (B, 2021)" becomes "(A, 2025; B, 2021)"; duplicates are dropped.

    Two sentences' worth of evidence from two sources resolve to two separate
    parentheticals side by side, which APA writes as one. Only the plain
    author-year shape is merged, in one bracket style at a time.
    """

    def merge(match: re.Match, opener: str, closer: str, separator: str, inner_re: str) -> str:
        items: list[str] = []
        for token in re.findall(inner_re, match.group(0)):
            inner = token[1:-1].strip()
            if inner not in items:
                items.append(inner)
        return opener + separator.join(items) + closer

    text = _ADJACENT_LATIN_RE.sub(lambda m: merge(m, "(", ")", "; ", _LATIN_PAREN), text)
    return _ADJACENT_CJK_RE.sub(lambda m: merge(m, "（", "）", "；", _CJK_PAREN), text)
