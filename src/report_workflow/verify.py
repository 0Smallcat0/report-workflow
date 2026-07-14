"""Five-line verification for any LLM answer — no pipeline, no schema.

The full report pipeline speaks in artifacts (``claim_matrix.json``,
``sentence_map.jsonl``, an evidence ledger). Most people who need a
hallucination check have neither — they have an answer string and the source
text it was supposed to be grounded in. :func:`verify` bridges that gap:

    from report_workflow import verify

    result = verify(
        answer="The error rate fell to 0.2% [1].",
        sources={"1": "The error rate fell to 3.5% under the structured workflow."},
    )
    result["sentence_results"][0]["status"]   # "blocked"
    result["sentence_results"][0]["checker"]  # "FE"

It is the same deterministic gate stack the pipeline enforces
(``nodes/factuality_check.py``): no LLM, no API key, no network — a pure
function of (answer, sources) that returns the same verdict every run.

Semantics, stated plainly:

* The answer is split into sentences (English ``.!?`` followed by whitespace,
  CJK ``。！？`` anywhere, and newlines).
* ``[id]`` / ``[CITE:id]`` markers scope a sentence to those sources. A marker
  that matches no source id is a fabricated citation and hard-blocks the
  sentence (FA).
* A sentence without markers is tested against every source. It is
  **verified** when at least one single source fully grounds it, mirroring how
  a human checks a citation. (The pipeline's claim matrix is stricter — a
  claim must be grounded in *each* evidence row it cites; aggregate sentences
  should be split there. The adapter documents this divergence instead of
  hiding it.)
* Fail closed: whatever cannot be verified is ``blocked`` with the gate and
  reason, and ``publishable`` is False.
"""
from __future__ import annotations

import re
from typing import Any

from .nodes.factuality_check import (
    run_factuality_check_fa,
    run_factuality_check_fb,
    run_factuality_check_fe,
)

# Sentence boundaries: CJK terminators split unconditionally; ASCII
# terminators only when followed by whitespace (protects "3.5%" decimals and
# most abbreviations); newlines always split.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+|\n+")

# [1], [src_a], [CITE:ev_x] — the pipeline's own citation syntax included.
_MARKER_RE = re.compile(r"\[(?:CITE:)?\s*([^\[\]]{1,64}?)\s*\]")

_WORD_RE = re.compile(r"[A-Za-z0-9㐀-鿿]")


def _normalize_sources(sources: dict[Any, Any] | list[str] | str) -> dict[str, str]:
    if isinstance(sources, str):
        items: list[tuple[str, str]] = [("1", sources)]
    elif isinstance(sources, dict):
        items = [(str(key), str(value)) for key, value in sources.items()]
    else:
        items = [(str(index + 1), str(text)) for index, text in enumerate(sources)]
    normalized = {key: value for key, value in items if value and value.strip()}
    if not normalized:
        raise ValueError("sources must contain at least one non-empty source text")
    return normalized


def _split_sentences(answer: str) -> list[str]:
    pieces = _SENTENCE_SPLIT_RE.split(answer or "")
    sentences = []
    for piece in pieces:
        if piece is None:
            continue
        stripped = piece.strip().lstrip("-*• ").strip()
        # Keep only pieces with real content (letters, digits, or CJK).
        if stripped and _WORD_RE.search(stripped):
            sentences.append(stripped)
    return sentences


def _evaluate_against(
    checked_text: str,
    source_id: str,
    source_text: str,
    index: int,
    deep_audit: bool,
) -> dict[str, Any]:
    """Run the gate stack for one sentence against one candidate source."""
    claim_id = f"c_{index}"
    matrix = {
        "claims": [{
            "claim_id": claim_id,
            "claim_text": checked_text,
            "claim_type": "factual",
            "status": "supported",
            "evidence_ids": [source_id],
        }]
    }
    sentence_map = [{
        "sentence_id": f"s_{index}",
        "text": checked_text,
        "claim_ids": [claim_id],
        "evidence_ids": [source_id],
        "citation_ids": [source_id],
        # No wording-strength metadata exists for a plain answer string, so
        # the FD wording-vs-grade gate stays out of the adapter on purpose.
        "wording_strength": "",
    }]
    ledger = [{
        "evidence_id": source_id,
        "content": source_text,
        "evidence_type": "contextual",
        "source_role": "primary_source",
        "evidence_grade": "high",
    }]
    results = run_factuality_check_fa(sentence_map, matrix, ledger)
    results = run_factuality_check_fb(results, matrix, ledger)
    if deep_audit:
        results = run_factuality_check_fe(results, matrix, ledger)
    return results[0]


def verify(
    answer: str,
    sources: dict[Any, Any] | list[str] | str,
    *,
    deep_audit: bool = True,
) -> dict[str, Any]:
    """Deterministically verify a plain LLM answer against plain source texts.

    Args:
        answer: The generated text to check, as-is.
        sources: The ground truth — a single string, a list of strings
            (auto-numbered ``"1"``, ``"2"``, …), or a mapping of source id to
            source text. ``[id]`` markers in the answer scope sentences to
            these ids.
        deep_audit: Keep the FE content-overlap gate on (default). Turning it
            off leaves only linkage-level checks and is not recommended.

    Returns:
        ``{"publishable", "verified_count", "blocked_count",
        "sentence_results", "deep_audit"}`` where each sentence result carries
        ``sentence`` (original text), ``status`` (``"verified"`` or
        ``"blocked"``), ``checker`` (the gate that fired, or ``None``),
        ``reason``, and ``source_id`` (the source that grounded the sentence,
        or ``None`` when blocked).
    """
    ledger_by_id = _normalize_sources(sources)
    sentence_results: list[dict[str, Any]] = []

    for index, sentence in enumerate(_split_sentences(answer)):
        marker_ids = _MARKER_RE.findall(sentence)
        checked_text = re.sub(r"\s{2,}", " ", _MARKER_RE.sub(" ", sentence)).strip()

        unknown = [mid for mid in marker_ids if mid not in ledger_by_id]
        if unknown:
            sentence_results.append({
                "sentence": sentence,
                "status": "blocked",
                "checker": "FA",
                "reason": "Sentence cites unknown source id(s): " + ", ".join(unknown),
                "source_id": None,
            })
            continue

        candidate_ids = marker_ids or list(ledger_by_id)
        grounded_id: str | None = None
        best_block: dict[str, Any] | None = None
        for source_id in candidate_ids:
            outcome = _evaluate_against(
                checked_text, source_id, ledger_by_id[source_id], index, deep_audit
            )
            if outcome["status"] != "blocked":
                grounded_id = source_id
                break
            # Keep the nearest miss for reporting: the shortest reason string
            # is the candidate that failed on the fewest checks (deterministic
            # tie-break: first candidate in source order wins).
            if best_block is None or len(outcome["reason"]) < len(best_block["reason"]):
                best_block = {**outcome, "source_id": source_id}

        if grounded_id is not None:
            sentence_results.append({
                "sentence": sentence,
                "status": "verified",
                "checker": None,
                "reason": f"Grounded in source {grounded_id!r}",
                "source_id": grounded_id,
            })
        else:
            assert best_block is not None  # candidate_ids is never empty
            sentence_results.append({
                "sentence": sentence,
                "status": "blocked",
                "checker": best_block["checker"],
                "reason": best_block["reason"],
                "source_id": None,
            })

    blocked_count = sum(1 for row in sentence_results if row["status"] == "blocked")
    return {
        "publishable": blocked_count == 0,
        "verified_count": len(sentence_results) - blocked_count,
        "blocked_count": blocked_count,
        "sentence_results": sentence_results,
        "deep_audit": deep_audit,
    }
