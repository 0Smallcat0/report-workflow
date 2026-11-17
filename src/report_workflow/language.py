"""Document-language helpers shared across pipeline nodes.

The blueprint carries canonical section titles. English-language profiles ship
English ``title`` values; each section may also declare ``title_zh`` so a
Chinese-language document renders Chinese headings instead of leaking the
English defaults into an otherwise-Chinese deliverable.

Detection is deterministic: the same text always yields the same language, so
merge/normalize stages that run in different processes agree without passing
state through checkpoints.
"""
from __future__ import annotations

import re

CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
# Chinese ordinal heading prefixes: 「一、」「十二、」「（三）」
ZH_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:[（(][一二三四五六七八九十百]+[)）]|[一二三四五六七八九十百]+[、.．])\s*"
)

# Any ordinal an author may already have typed in front of a heading: 一、 /
# 第一章 / 第3節 / （一） / 1. / 1.2 / 2、 . The renderer numbers headings
# itself, so a title that carries one must not get a second.
HEADING_ORDINAL_RE = re.compile(
    r"^\s*(?:"
    r"[（(][一二三四五六七八九十百]+[)）]"
    r"|[一二三四五六七八九十百]+[、.．]"
    r"|第\s*[一二三四五六七八九十百零\d]+\s*[章節节篇部分]"
    r"|\d+(?:\.\d+)*[.、．)）]\s*"
    r"|\d+(?:\.\d+)+\s+"
    r")"
)


def has_heading_ordinal(title: str) -> bool:
    """Does this heading title already begin with its own number?"""
    text = (title or "").strip()
    # 「2025 年回顧」 is a year, not an ordinal.
    if re.match(r"\d+\s*[年月日]", text):
        return False
    return bool(HEADING_ORDINAL_RE.match(text))


_CJK_RE = CJK_RE
_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z0-9]+\b")

# Minimum CJK characters before a sample can flip to "zh": guards against an
# English document that mentions a couple of Chinese proper nouns.
_MIN_CJK_CHARS = 20
# CJK share of (CJK + latin letters) required to call the document Chinese.
# CJK carries roughly 2x information per character, so 0.25 is already a
# solidly Chinese-dominant document.
_ZH_RATIO = 0.25


def detect_document_language(text: str) -> str:
    """Return ``"zh"`` when CJK characters dominate the sample, else ``"en"``."""
    sample = (text or "")[:20000]
    if not sample:
        return "en"
    cjk = len(_CJK_RE.findall(sample))
    if cjk < _MIN_CJK_CHARS:
        return "en"
    latin = len(_LATIN_RE.findall(sample))
    if cjk / max(1, cjk + latin) >= _ZH_RATIO:
        return "zh"
    return "en"


def count_words(text: str) -> int:
    """CJK-aware word count: each CJK character counts as one word.

    ``\\b\\w+\\b`` alone counts an entire Chinese clause as a single "word",
    so any length gate built on it rejects normal-length Chinese text.
    """
    cjk = len(CJK_RE.findall(text or ""))
    latin = len(_LATIN_WORD_RE.findall(text or ""))
    return cjk + latin


def derived_section_title(section_id: str) -> str:
    """Fallback display title derived from the section id."""
    return section_id.replace("_", " ").title()


def localized_section_title(section: dict, section_id: str, language: str) -> str:
    """Pick the blueprint section title for the document language.

    ``title_zh`` wins for Chinese documents when the blueprint provides it;
    otherwise the plain ``title`` and finally the derived id-based title.
    A Chinese-only ``title`` on a non-Chinese document falls back to the
    derived English title instead of leaking CJK headings into an English
    document (the mirror of the pre-4.10 English-headings-in-Chinese wall).
    """
    section = section or {}
    if language == "zh":
        title_zh = str(section.get("title_zh") or "").strip()
        if title_zh:
            return title_zh
    title = str(section.get("title") or "").strip()
    if (
        language != "zh"
        and title
        and CJK_RE.search(title)
        and not _LATIN_RE.search(title)
    ):
        return derived_section_title(section_id)
    return title or derived_section_title(section_id)
