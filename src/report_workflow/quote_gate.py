"""Quote gate: an evidence quote must be a contiguous verbatim run of its source.

The provenance gate (``validate_evidence_ledger_provenance``) only asked whether
a ledger row *has* a trace. This asks whether the text the row carries is really
the source's text, in one unbroken run:

* ``quote`` (minus the trailing ``...`` that marks truncation) is a contiguous
  prefix of the row's own ``content``;
* ``content`` of a row from a plain-text source (.md/.txt) is a contiguous run
  of that file. Comparison keeps only letters, digits and CJK, so markup and
  line breaks the parser removes do not matter, but a dropped, reordered or
  invented word does.

Two failed validations in a row for one run stop blocking and fall back to
statistics only: claims resting on unverified rows are removed unless their
claim_type is ``statistical``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

TEXT_SOURCE_SUFFIXES = {".md", ".txt"}
MAX_ATTEMPTS = 2
_KEEP = re.compile(r"[^0-9a-z㐀-鿿]+")


def squash(text: str) -> str:
    return _KEEP.sub("", unicodedata.normalize("NFKC", str(text or "")).lower())


def ledger_quote_problems(entries: list[dict]) -> dict[str, str]:
    """Map evidence_id -> reason for each row whose text is not contiguous source text."""
    problems: dict[str, str] = {}
    cache: dict[str, str | None] = {}
    for item in entries:
        if item.get("source_role") in {"derived_summary", "agent_supplied"}:
            continue
        eid = str(item.get("evidence_id") or "<missing>")
        content = str(item.get("content") or "")
        quote = str(item.get("quote") or "")
        if quote.endswith("..."):
            quote = quote[:-3]
        if quote and squash(quote) not in squash(content):
            problems[eid] = "quote is not a contiguous run of the row's content"
            continue
        # Table rows are re-keyed by the parser ({header: value}), so their text
        # is a reading of the source, not a run of it; prose rows are checked.
        if "table" in str(item.get("block_type", "")) or "row" in str(item.get("block_type", ""))                 or item.get("table_data") or content.lstrip().startswith("{"):
            continue
        path = str(item.get("source_file_path") or "")
        if not path or Path(path).suffix.lower() not in TEXT_SOURCE_SUFFIXES:
            continue
        if path not in cache:
            try:
                cache[path] = squash(Path(path).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                cache[path] = None
        source = cache[path]
        if source is not None and content and squash(content) not in source:
            problems[eid] = "content is not a contiguous run of the source file"
    return problems


def record_attempt(run_dir: str | Path, problems: dict[str, str]) -> dict:
    """Persist the attempt count; status is ok, retry, or stats_only."""
    path = Path(run_dir) / "quote_gate.json"
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    failures = 0 if not problems else int(previous.get("failures", 0)) + 1
    status = "ok" if not problems else ("stats_only" if failures >= MAX_ATTEMPTS else "retry")
    state = {"status": status, "failures": failures, "problems": problems}
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def degrade_claims(claims: list[dict], problems: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Statistics-only fallback: drop non-statistical claims citing an unverified row."""
    kept, dropped = [], []
    for claim in claims:
        bad = any(e in problems for e in claim.get("evidence_ids", []))
        if bad and claim.get("claim_type") != "statistical":
            dropped.append(str(claim.get("claim_id")))
        else:
            kept.append(claim)
    return kept, dropped
