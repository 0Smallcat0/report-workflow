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

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
_LATIN_RE = re.compile(r"[A-Za-z]")

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


def derived_section_title(section_id: str) -> str:
    """Fallback display title derived from the section id."""
    return section_id.replace("_", " ").title()


def localized_section_title(section: dict, section_id: str, language: str) -> str:
    """Pick the blueprint section title for the document language.

    ``title_zh`` wins for Chinese documents when the blueprint provides it;
    otherwise the plain ``title`` (which profiles like engineering_lab_report
    already author in Chinese) and finally the derived id-based title.
    """
    section = section or {}
    if language == "zh":
        title_zh = str(section.get("title_zh") or "").strip()
        if title_zh:
            return title_zh
    title = str(section.get("title") or "").strip()
    return title or derived_section_title(section_id)
