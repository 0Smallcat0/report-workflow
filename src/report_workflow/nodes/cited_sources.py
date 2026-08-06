"""The sources a source file cites.

Ingestion treated one file as one source. A 53,000-character market report
citing thirty-nine outside houses therefore entered the pipeline as a single
entry named after itself, and every downstream consumer agreed: the reference
list was empty, the BibTeX file was empty, the appendix was empty, and the
delivered document told its reader nothing about where any figure came from.

Nothing was broken. The path did not exist — a tree-wide search for anything
reading URLs out of ``parsed_content`` found no such code. This module is that
path.

Three shapes are read, because real documents use all three:

* a Markdown link — ``[Black mass prices](https://fastmarkets.com/...)``
* a bare URL on its own
* a Chinese attribution with no URL at all — ``（來源：Fastmarkets，2026）``

The third is the one worth being careful about. It carries no link, so it is
tempting to drop; but a named house and a year is exactly what a reader needs
in order to go and check, and dropping it would lose most of what a Chinese
business report states about its own provenance.
"""
from __future__ import annotations

import hashlib
import re

#: A Markdown link. The title is taken verbatim — inventing one would be the
#: same failure as inventing an author.
_MD_LINK_RE = re.compile(r"\[([^\]\n]{1,200})\]\((https?://[^\s)]+)\)")

#: A bare URL. Trailing CJK and ASCII punctuation is excluded so a sentence
#: ending "…/prices/。" does not carry the full stop into the address.
_BARE_URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"'）】」』，。；、]+")

#: "（來源：Fastmarkets，2026）", "(Source: OECD, 2026)", "資料來源：CRU". The
#: publisher runs until a closing bracket or the end of the line.
_ATTRIBUTION_RE = re.compile(
    r"[（(]?\s*(?:資料來源|资料来源|來源|来源|出處|出处|Source)\s*[:：]\s*"
    r"([^)）\n]{2,80})",
    re.IGNORECASE,
)

#: A year inside an attribution, so "Fastmarkets，2026" separates cleanly into
#: a publisher and a date rather than being filed as one long name.
_YEAR_RE = re.compile(r"(?:^|[\s,，、（(])((?:19|20)\d{2})(?:[\s,，、）)]|$)")

#: Punctuation a publisher name should not end with.
_TRAILING_PUNCT = " \t，,、。.；;：:）)】」』"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _normalize_url(url: str) -> str:
    """A comparison key, so one source cited twice is listed once."""
    cleaned = url.strip().rstrip("/").rstrip(_TRAILING_PUNCT)
    lowered = cleaned.lower()
    for prefix in ("https://", "http://"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
            break
    if lowered.startswith("www."):
        lowered = lowered[4:]
    return lowered


def _split_publisher_and_year(raw: str) -> tuple[str, str]:
    """Separate "Fastmarkets，2026" into its two halves."""
    text = " ".join(raw.split()).strip(_TRAILING_PUNCT)
    match = _YEAR_RE.search(text)
    if not match:
        return text, ""
    year = match.group(1)
    publisher = (text[: match.start(1)] + " " + text[match.end(1):]).strip(_TRAILING_PUNCT)
    return " ".join(publisher.split()), year


def _blocks(entry: dict) -> list[dict]:
    parsed = entry.get("parsed_content") or []
    return [block for block in parsed if isinstance(block, dict)]


def extract_cited_sources(source_registry: list[dict]) -> list[dict]:
    """Every outside source the supplied files cite, deduplicated.

    Order is the order of first appearance, which is the order a reader met
    them in. Each entry records the file and block it was found in, so a
    reference can always be walked back to the sentence that made it.
    """
    by_key: dict[str, dict] = {}

    def record(
        key: str,
        *,
        kind: str,
        title: str,
        url: str,
        publisher: str,
        year: str,
        raw: str,
        entry: dict,
        block: dict,
    ) -> None:
        existing = by_key.get(key)
        if existing is not None:
            existing["occurrences"] += 1
            # A bare URL seen earlier gains a title when a linked mention of
            # the same address turns up later.
            if title and not existing["title"]:
                existing["title"] = title
                existing["kind"] = kind
            return
        by_key[key] = {
            "cited_source_id": f"CS_{_digest(key)}",
            "kind": kind,
            "title": title,
            "url": url,
            "publisher": publisher,
            "year": year,
            "raw": raw,
            "source_id": str(entry.get("source_id") or ""),
            "source_file_name": str(entry.get("file_name") or ""),
            "block_id": str(block.get("block_id") or ""),
            "line_start": block.get("line_start"),
            "line_end": block.get("line_end"),
            "occurrences": 1,
        }

    for entry in source_registry or []:
        for block in _blocks(entry):
            content = str(block.get("content") or "")
            if not content:
                continue

            linked: set[str] = set()
            for match in _MD_LINK_RE.finditer(content):
                title, url = match.group(1).strip(), match.group(2)
                linked.add(url)
                record(
                    _normalize_url(url),
                    kind="link",
                    title=title,
                    url=url.rstrip(_TRAILING_PUNCT),
                    publisher="",
                    year="",
                    raw=match.group(0),
                    entry=entry,
                    block=block,
                )

            for match in _BARE_URL_RE.finditer(content):
                url = match.group(0)
                if url in linked:
                    continue
                record(
                    _normalize_url(url),
                    kind="url",
                    title="",
                    url=url.rstrip(_TRAILING_PUNCT),
                    publisher="",
                    year="",
                    raw=url,
                    entry=entry,
                    block=block,
                )

            for match in _ATTRIBUTION_RE.finditer(content):
                publisher, year = _split_publisher_and_year(match.group(1))
                if not publisher or _BARE_URL_RE.match(publisher):
                    # An attribution that is itself a URL was already recorded
                    # as one; recording it again would list it twice.
                    continue
                record(
                    f"{publisher.casefold()}|{year}",
                    kind="attribution",
                    title="",
                    url="",
                    publisher=publisher,
                    year=year,
                    raw=match.group(0).strip(),
                    entry=entry,
                    block=block,
                )

    return list(by_key.values())


def _display_name(cited: dict) -> str:
    """What to call this source, using only what the document stated."""
    if cited.get("publisher"):
        return cited["publisher"]
    if cited.get("title"):
        return cited["title"]
    url = cited.get("url") or ""
    host = re.sub(r"^https?://(?:www\.)?", "", url).split("/", 1)[0]
    return host or "Unknown source"


def format_reference_entry(cited: dict) -> str:
    """One bibliography line, asserting nothing the source did not state.

    No invented author and no invented year: a source cited only as a URL is
    dated "(n.d.)", the same rule the file-derived formatter follows. The
    title is italicised because that is what marks an entry as a publication
    to the curation filter — an entry failing it is deleted, and deleting a
    real citation is the failure this module exists to end.
    """
    name = _display_name(cited)
    year = cited.get("year") or "n.d."
    title = cited.get("title") or _display_name(cited)
    parts = [f"{name}. ({year}). *{title}*."]
    if cited.get("url"):
        parts.append(cited["url"])
    return " ".join(parts)


def format_bibtex_entry(cited: dict, index: int) -> str:
    """A BibTeX record for the same source, for a reader who wants the file."""
    key = cited.get("cited_source_id") or f"cited{index}"
    name = _display_name(cited).replace("{", "").replace("}", "")
    title = (cited.get("title") or name).replace("{", "").replace("}", "")
    fields = [
        f"  author = {{{name}}}",
        f"  title = {{{title}}}",
        f"  year = {{{cited.get('year') or 'n.d.'}}}",
    ]
    if cited.get("url"):
        fields.append(f"  url = {{{cited['url']}}}")
    return "@misc{" + key + ",\n" + ",\n".join(fields) + "\n}"
