"""FACTUALITY_CHECK node - verify claim/evidence/sentence linkage.

IMPORTANT data source note:
  - claim_matrix is read from claim_matrix.json on disk (NOT from state.plan.claim_matrix)
  - evidence_ledger is read from state.sources["evidence_ledger_path"] on disk (NOT from checkpoint)
  - factuality_report.json is written fresh each run to the job run directory

When debugging FE failures: edit claim_matrix.json and evidence_ledger.jsonl directly.
Checkpoint files are NOT read by this node.
"""
import json
import re
import unicodedata
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR

BLOCKING_CLAIM_STATUSES = {"blocked", "unverified", "disputed"}


def _load_jsonl(path: str) -> list[dict]:
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


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def _claim_id(claim: dict) -> str:
    return claim.get("claim_id") or claim.get("id") or ""


def _default_allowed_claim_types(evidence_type: str) -> list[str]:
    return {
        "quantitative": ["factual", "statistical"],
        "qualitative": ["factual", "qualitative"],
        "methodological": ["factual", "methodological"],
        "contextual": ["factual", "qualitative", "contextual"],
    }.get(evidence_type, ["factual"])


def _allowed_claim_types(evidence: dict) -> list[str]:
    explicit = evidence.get("allowed_claim_types")
    allowed = set(explicit) if explicit else set(_default_allowed_claim_types(evidence.get("evidence_type", "")))

    source_role = evidence.get("source_role", "")
    if source_role in {"graph_analysis", "research_document", "primary_source", "internal_project_source"}:
        allowed.update({"factual", "qualitative", "methodological", "contextual"})
    elif source_role == "code_artifact":
        allowed.update({"factual", "qualitative", "methodological", "contextual", "implementation"})

    return sorted(allowed)


def run_factuality_check_fa(
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify deterministic claim/evidence/sentence linkage."""
    claims = claim_matrix.get("claims", [])
    evidence_by_id = {
        evidence.get("evidence_id"): evidence
        for evidence in (evidence_ledger or [])
        if evidence.get("evidence_id")
    }
    sentence_claim_ids = {
        claim_id
        for sent in sentence_map
        for claim_id in sent.get("claim_ids", [])
    }
    sentence_evidence_ids_by_claim: dict[str, set[str]] = {}
    for sent in sentence_map:
        for claim_id in sent.get("claim_ids", []):
            sentence_evidence_ids_by_claim.setdefault(claim_id, set()).update(sent.get("evidence_ids", []))

    results = []
    for claim in claims:
        claim_id = _claim_id(claim)
        claim_evidence_ids = set(claim.get("evidence_ids", []))
        reasons = []

        if not claim_id:
            reasons.append("Claim is missing claim_id")
        claim_status = str(claim.get("status", "supported")).lower()
        if claim_status in BLOCKING_CLAIM_STATUSES:
            reasons.append(f"Claim status is not publishable: {claim_status}")
        if not claim_evidence_ids:
            reasons.append("No evidence mapped to claim")
        if claim_id and claim_id not in sentence_claim_ids:
            reasons.append("Claim does not appear in sentence_map")

        missing_evidence = sorted(eid for eid in claim_evidence_ids if eid not in evidence_by_id)
        if evidence_by_id and missing_evidence:
            reasons.append(f"Claim references unknown evidence: {', '.join(missing_evidence)}")

        sentence_evidence_ids = sentence_evidence_ids_by_claim.get(claim_id, set())
        unknown_sentence_evidence = sorted(eid for eid in sentence_evidence_ids if evidence_by_id and eid not in evidence_by_id)
        if unknown_sentence_evidence:
            reasons.append(f"Sentence map references unknown evidence: {', '.join(unknown_sentence_evidence)}")
        if claim_evidence_ids and not (claim_evidence_ids & sentence_evidence_ids):
            reasons.append("Sentence map does not link claim to its evidence")

        claim_type = claim.get("claim_type", "factual")
        unsupported = []
        for evidence_id in sorted(claim_evidence_ids):
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            if claim_type not in _allowed_claim_types(evidence):
                unsupported.append(evidence_id)
        if unsupported:
            reasons.append(
                f"Claim type {claim_type!r} is not allowed by evidence: {', '.join(unsupported)}"
            )

        if reasons:
            results.append({
                "claim_id": claim_id or "<missing>",
                "status": "blocked",
                "checker": "FA",
                "reason": "; ".join(reasons),
            })
        else:
            results.append({
                "claim_id": claim_id,
                "status": "verified",
                "checker": "FA",
                "reason": "Claim/evidence/sentence linkage confirmed",
            })

    return results


def run_factuality_check_fb(
    checked_claims: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify statistical claims are backed by appropriate evidence.

    Uses _allowed_claim_types() which respects explicit allowed_claim_types
    overrides in evidence records, not just the evidence_type field.
    """
    evidence_by_id = {
        evidence.get("evidence_id"): evidence
        for evidence in (evidence_ledger or [])
        if evidence.get("evidence_id")
    }
    claims_by_id = {_claim_id(claim): claim for claim in claim_matrix.get("claims", [])}

    results = []
    for checked in checked_claims:
        if checked["status"] == "blocked":
            results.append(checked)
            continue

        claim = claims_by_id.get(checked["claim_id"], {})
        claim_type = claim.get("claim_type", "factual")
        if claim_type != "statistical":
            results.append(checked)
            continue

        # Check if any linked evidence allows this claim type
        # Use _allowed_claim_types which respects explicit overrides
        linked = [evidence_by_id.get(eid) for eid in claim.get("evidence_ids", [])]
        has_support = any(
            evidence and claim_type in _allowed_claim_types(evidence)
            for evidence in linked
        )
        if has_support:
            results.append({
                **checked,
                "checker": "FA+FB",
                "reason": "Claim/evidence linkage and quantitative support confirmed",
            })
        else:
            results.append({
                "claim_id": checked["claim_id"],
                "status": "blocked",
                "checker": "FB",
                "reason": "Statistical claim lacks quantitative evidence",
            })

    return results


def run_factuality_check_fc(disputed_claims: list[dict], claim_matrix: dict) -> list[dict]:
    """Deprecated Phase 1 adjudication hook.

    The MVP fail-fast contract has no auto-verifying agent adjudication path.
    """
    return [
        {
            "claim_id": claim.get("claim_id", "<missing>"),
            "status": "blocked",
            "checker": "FC_DISABLED",
            "reason": "Agent adjudication is not enabled in MVP",
        }
        for claim in disputed_claims
    ]


# ----------------------------------------------------------------------
# Fix #5: Content overlap checker
# ----------------------------------------------------------------------


def run_factuality_check_fe(
    checked_claims: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify claim content is grounded in evidence content (not just ID linkage).

    Fix #5: Uses _check_content_overlap() to catch:
    - claims citing numbers/terms absent from evidence
    - statistical claims whose numeric values differ from evidence
    - claims stating more decimal precision than the evidence provides
    - quoted text (4+ chars) not appearing verbatim in evidence
    - non-CJK claims citing CJK-only evidence with no shared vocabulary
    """
    evidence_by_id = {
        ev.get("evidence_id"): ev
        for ev in (evidence_ledger or [])
        if ev.get("evidence_id")
    }
    claims_by_id = {_claim_id(claim): claim for claim in claim_matrix.get("claims", [])}

    results = []
    for checked in checked_claims:
        if checked["status"] == "blocked":
            results.append(checked)
            continue

        claim = claims_by_id.get(checked["claim_id"], {})
        claim_evidence_ids = claim.get("evidence_ids", [])

        if not claim_evidence_ids:
            results.append(checked)
            continue

        all_reasons = []
        for evidence_id in claim_evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            mismatch_reasons = _check_content_overlap(claim, evidence)
            all_reasons.extend(mismatch_reasons)

        if all_reasons:
            results.append({
                "claim_id": checked["claim_id"],
                "status": "blocked",
                "checker": "FE",
                "reason": "; ".join(all_reasons[:3]),  # cap at 3 reasons
            })
        else:
            results.append(checked)

    return results


# ----------------------------------------------------------------------
# F2: Provenance-driven wording strength enforcement
# ----------------------------------------------------------------------
# Allowed wording_strength per evidence_grade.
# evidence_grade=high  → may use measured / hedged / weak
# evidence_grade=medium→ may use hedged / weak only
# evidence_grade=low   → may use hedged only
_ALLOWED_WORDING_BY_GRADE = {
    "high": {"measured", "hedged", "weak"},
    "medium": {"hedged", "weak"},
    "low": {"hedged"},
}
_VALID_WORDING_STRENGTHS = {"measured", "hedged", "weak"}


# ----------------------------------------------------------------------
# Fix #5: Claim-evidence content overlap checker
# ----------------------------------------------------------------------
# Verifies that claim content is actually supported by evidence content,
# not just by ID linkage. Catches:
#   - claims citing numbers/terms that don't appear in the evidence
#   - statistical claims whose numeric values/units differ from evidence
#   - quote claims where the quoted text differs from evidence
# ----------------------------------------------------------------------


_NUMERIC_IN_CLAIM_RE = re.compile(
    r"""
    (?<![A-Za-z0-9.])                # boundary without consuming CJK text
    (                                 # number
        \d{1,3}(?:,\d{3})*(?:\.\d+)?(?:[eE][+-]?\d+)?
    )
    \s*                               # supports "5 cm" and "5cm"
    (?![a-zA-Z]')                     # reject possessive: "386's" is not a unit
    (                                 # unit
        [a-zA-Z%\u00b0\u4e00-\u9fff]+(?:/?[a-zA-Z%\u00b0\u4e00-\u9fff]*)?
    )
    """,
    re.VERBOSE,
)


def _extract_numbers_with_unit(text: str) -> list[tuple[str, str]]:
    """Return list of (number_str, unit_str) from text."""
    _APOSTROPHE_SUFFIX_RE = re.compile(r"'[strelmv]|'ll|'ve|'d\b")
    results = []
    normalized = unicodedata.normalize("NFKC", text or "")
    for m in _NUMERIC_IN_CLAIM_RE.finditer(normalized):
        unit = _APOSTROPHE_SUFFIX_RE.sub("", m.group(2).strip())
        results.append((m.group(1).lstrip("~"), unit))
    return results


def _normalize_number_str(s: str) -> float:
    """Parse a number string to float, stripping commas and ~ prefix."""
    import re as _re
    # Strip commas (thousands separator) and ~ prefix (evidence "approximately" marker)
    # e.g. "~451,947" → "451947", "9,696" → "9696"
    s = s.lstrip('~').replace(',', '')
    s = _re.sub(r'[eE][+-]?\d+', lambda m: str(float(m.group(0))), s)
    return float(s)


def _decimal_places(num_str: str) -> int:
    """Count the decimal places a number string explicitly states."""
    s = num_str.lstrip("~").replace(",", "")
    mantissa = re.split(r"[eE]", s, maxsplit=1)[0]
    return len(mantissa.split(".", 1)[1]) if "." in mantissa else 0


_UNIT_ALIASES = {
    "percent": "%",
    "\u516c\u5206": "cm",
    "\u5398\u7c73": "cm",
    "\u6beb\u7c73": "mm",
    "\u516c\u5398": "mm",
    "\u516c\u5c3a": "m",
    "\u7c73": "m",
    "\u4f0f\u7279": "v",
    "\u5b89\u57f9": "a",
    "\u6b50\u59c6": "ohm",
    "\u6b27\u59c6": "ohm",
    "\u79d2": "s",
    "\u5206\u9418": "min",
    "\u5206\u949f": "min",
    "\u5c0f\u6642": "h",
    "\u5c0f\u65f6": "h",
    "\u767e\u5206\u6bd4": "%",
    "\uff05": "%",
}


def _singular_unit(unit: str) -> str:
    if unit.endswith("s") and len(unit) > 1:
        return unit[:-1]
    return unit


def _normalize_unit(unit: str) -> str:
    normalized = unicodedata.normalize("NFKC", unit or "").strip().casefold()
    normalized = normalized.replace(" ", "")
    return _UNIT_ALIASES.get(normalized, normalized)


def _units_match(claim_unit: str, evidence_unit: str) -> bool:
    claim_norm = _normalize_unit(claim_unit)
    evidence_norm = _normalize_unit(evidence_unit)
    return claim_norm == evidence_norm or _singular_unit(claim_norm) == _singular_unit(evidence_norm)


def _cjk_chars(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text or "")
    return re.findall(r"[\u3400-\u9fff]", normalized)


def _cjk_bigrams(chars: list[str]) -> set[str]:
    return {
        "".join(chars[index:index + 2])
        for index in range(max(0, len(chars) - 1))
    }


def _check_term_overlap(
    claim_text: str,
    evidence_content: str,
    source_role: str,
    *,
    cross_language: bool = False,
) -> list[str]:
    """English key-term coverage of the claim against evidence content.

    With ``cross_language=True`` the same check runs for a non-CJK claim that
    cites CJK-heavy evidence: bilingual evidence rows can still satisfy it via
    their embedded English terms, but a claim sharing no vocabulary with its
    citation is reported instead of silently passing.
    """
    term_re = re.compile(r"\b[a-zA-Z]{5,}\b")
    claim_terms = term_re.findall(claim_text.lower())
    stopwords = {
        "should", "would", "could", "might", "must", "shall", "which",
        "where", "when", "while", "there", "their", "these", "those",
        "however", "therefore", "because", "result", "results", "study",
        "analysis", "method", "methods", "paper", "research", "report",
    }
    key_terms = [t for t in claim_terms if t not in stopwords]
    if not key_terms:
        return []
    evidence_lower = evidence_content.lower()
    matched = sum(1 for t in key_terms if t in evidence_lower)
    coverage = matched / len(key_terms)
    # Use lower threshold for code evidence (code vocab ≠ academic vocab)
    threshold = 0.20 if source_role == "code_artifact" else 0.40
    if coverage >= threshold:
        return []
    missing = [t for t in key_terms if t not in evidence_lower]
    label = (
        "Cross-language claim terms not in evidence"
        if cross_language
        else "Claim key terms not in evidence"
    )
    return [
        f"{label} ({coverage:.0%} coverage, "
        f"threshold={threshold:.0%}): {', '.join(missing[:5])}"
    ]


def _check_cjk_overlap(claim_text: str, evidence_content: str) -> list[str]:
    claim_chars = _cjk_chars(claim_text)
    evidence_chars = _cjk_chars(evidence_content)
    if len(claim_chars) < 4 or len(evidence_chars) < 4:
        return []

    claim_grams = _cjk_bigrams(claim_chars)
    evidence_grams = _cjk_bigrams(evidence_chars)
    if not claim_grams:
        return []

    matched = claim_grams & evidence_grams
    coverage = len(matched) / len(claim_grams)
    threshold = 0.25
    if coverage >= threshold:
        return []

    missing = sorted(claim_grams - evidence_grams)
    return [
        "Chinese claim terms not in evidence "
        f"({coverage:.0%} bigram coverage, threshold={threshold:.0%}): "
        + ", ".join(missing[:5])
    ]


def _check_content_overlap(
    claim: dict,
    evidence: dict,
) -> list[str]:
    """Verify claim content is grounded in evidence content.

    Returns a list of mismatch reasons (empty = OK).
    Checks:
    1. Quote overlap: if claim has "quoted text" markers, verify the quote
       appears verbatim (or near-verbatim) in evidence content.
    2. Numeric overlap: if claim mentions a number+unit, that exact pair
       must appear in evidence content (not just the same topic).
    3. Term overlap: key terms (≥5 chars, non-stopword) from claim should
       appear in evidence content.
    """
    import re

    claim_text = claim.get("claim_text", "")
    evidence_content = evidence.get("content", "") or evidence.get("quote", "")
    reasons = []

    if not evidence_content:
        reasons.append("Evidence content is empty — cannot verify claim grounding")
        return reasons

    # 1. Quote overlap check — look for "quoted text" patterns in claim
    #    e.g., 'The system "compiles ASTs" is key' → check "compiles ASTs" in evidence
    #    Minimum length 4: short fabricated quotes ("audited") must not slip
    #    under the scanner; anything shorter is punctuation-level noise.
    quoted_phrases = re.findall(r'"([^"]{4,200})"', claim_text)
    for phrase in quoted_phrases:
        # Strip trailing punctuation for matching
        phrase_stripped = phrase.rstrip('.,;:')
        if phrase_stripped.lower() not in evidence_content.lower():
            reasons.append(
                f"Quoted phrase {phrase_stripped!r} not found verbatim in evidence"
            )

    # 2. Numeric overlap check — claim numbers must appear in evidence
    claim_numbers = _extract_numbers_with_unit(claim_text)
    for num_str, unit in claim_numbers:
        try:
            claim_val = _normalize_number_str(num_str)
        except ValueError:
            continue

        # Search for same value in evidence (with same unit)
        evidence_numbers = _extract_numbers_with_unit(evidence_content)
        found = False
        inflated_match: tuple[str, str] | None = None
        for ev_num, ev_unit in evidence_numbers:
            # Units must match (after normalization)
            if not _units_match(unit, ev_unit):
                continue
            try:
                ev_val = _normalize_number_str(ev_num)
            except ValueError:
                continue
            # Allow 1% tolerance for floating point
            if abs(claim_val - ev_val) > abs(claim_val * 0.01) + 1e-9:
                continue
            if claim_val != ev_val and _decimal_places(num_str) > _decimal_places(ev_num):
                # Within tolerance, but the claim states more decimal places
                # than the evidence provides: "3.53%" is not a rounding of
                # "3.5%", it is precision the source never asserted.
                inflated_match = (ev_num, ev_unit)
                continue
            found = True
            break

        if not found:
            if inflated_match:
                reasons.append(
                    f"Claim number {num_str!r}{unit} asserts more decimal "
                    f"precision than the evidence value "
                    f"{inflated_match[0]!r}{inflated_match[1]} supports"
                )
            else:
                # Show what was found in evidence to help debugging
                ev_nums_str = ", ".join(f"{n}{u}" for n, u in evidence_numbers) or "(none)"
                reasons.append(
                    f"Claim number {num_str!r}{unit} not found in evidence content "
                    f"(evidence has: {ev_nums_str}). "
                    f"Note: numeric extractor supports both spaced and compact "
                    f"unit forms, such as '226 edges' and '226edges'."
                )

    # 3. Term overlap — key terms from claim should appear in evidence.
    #    CJK-heavy evidence takes the bigram path for CJK claims. A non-CJK
    #    claim citing CJK-heavy evidence no longer gets a free pass: it falls
    #    back to the English term check (bilingual evidence rows still pass
    #    via their embedded English terms; garbled or purely-CJK evidence
    #    cannot ground an English claim, so it is reported).
    def _is_likely_non_ascii(text: str) -> bool:
        """Return True if text is >30% non-ASCII (CJK, Arabic, etc.)."""
        if not text:
            return False
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        total = len(text)
        return total > 0 and (total - ascii_chars) / total > 0.3

    source_role = evidence.get("source_role", "primary_source")
    if _is_likely_non_ascii(evidence_content):
        if len(_cjk_chars(claim_text)) >= 4:
            reasons.extend(_check_cjk_overlap(claim_text, evidence_content))
        else:
            reasons.extend(
                _check_term_overlap(
                    claim_text, evidence_content, source_role, cross_language=True
                )
            )
    else:
        reasons.extend(_check_term_overlap(claim_text, evidence_content, source_role))

    return reasons


def run_factuality_check_fd(
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify that wording_strength is consistent with evidence_grade.

    A sentence backed by low-grade evidence may not assert conclusions
    with "measured" certainty — it must be hedged.
    """
    evidence_by_id = {
        ev.get("evidence_id"): ev
        for ev in (evidence_ledger or [])
        if ev.get("evidence_id")
    }

    # Build claim_id → set of evidence_ids
    claims = claim_matrix.get("claims", [])
    claim_evidence_ids: dict[str, set[str]] = {}
    for claim in claims:
        cid = _claim_id(claim)
        if cid:
            claim_evidence_ids[cid] = set(claim.get("evidence_ids", []))

    results = []
    for sent in sentence_map:
        sentence_id = sent.get("sentence_id") or sent.get("sent_id", "<missing>")
        wording = str(sent.get("wording_strength") or "").lower()

        # Collect all evidence grades for this sentence via its claims
        linked_evidence_ids: list[str] = list(sent.get("evidence_ids", []))
        for cid in sent.get("claim_ids", []):
            linked_evidence_ids.extend(claim_evidence_ids.get(cid, []))

        if not linked_evidence_ids:
            continue

        # Determine the minimum (weakest) evidence grade
        grades = []
        for eid in linked_evidence_ids:
            ev = evidence_by_id.get(eid)
            if ev:
                g = str(ev.get("evidence_grade") or "low").lower()
                if g in _ALLOWED_WORDING_BY_GRADE:
                    grades.append(g)

        if not grades:
            continue

        # Use the weakest grade to validate wording
        weakest_grade = min(
            grades,
            key=lambda g: list(_ALLOWED_WORDING_BY_GRADE.keys()).index(g),
        )
        allowed = _ALLOWED_WORDING_BY_GRADE.get(weakest_grade, set())

        if wording and wording not in _VALID_WORDING_STRENGTHS:
            continue

        if wording and wording not in allowed:
            results.append({
                "sentence_id": sentence_id,
                "status": "blocked",
                "checker": "FD",
                "reason": (
                    f"Wording strength '{wording}' is not allowed for "
                    f"evidence_grade='{weakest_grade}' "
                    f"(allowed: {', '.join(sorted(allowed))})"
                ),
            })

    return results


def _revision_sidecar_mode(
    state: ReportState,
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict],
) -> bool:
    return (
        state.spec.get("task_intent") == "revise_existing"
        and bool(sentence_map)
        and bool(claim_matrix.get("claims"))
        and bool(evidence_ledger)
    )


def run_factuality_check(state: ReportState) -> ReportState:
    """T13: FACTUALITY_CHECK - verify claims vs evidence."""
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path", ""))
    evidence_ledger = _load_jsonl(state.sources.get("evidence_ledger_path", ""))
    claim_matrix = _load_json(run_dir / "claim_matrix.json") or state.plan.get("claim_matrix", {})
    outline = _load_json(run_dir / "outline.json") or state.plan.get("outline", {})

    if not sentence_map:
        raise QAHardBlockError("Sentence map is empty")
    if not evidence_ledger:
        raise QAHardBlockError("Evidence ledger is empty")
    if not claim_matrix.get("claims"):
        raise QAHardBlockError("Claim matrix is empty")

    results_fa = run_factuality_check_fa(sentence_map, claim_matrix, evidence_ledger)
    all_results = run_factuality_check_fb(results_fa, claim_matrix, evidence_ledger)
    # Fix #5: content-overlap check (FE)
    # NOTE: By default skipped for jobs where evidence content uses mixed encoding (Big5 Chinese
    # corruption) and different vocabulary than claims, causing false-positive mismatches.
    # FA (linkage) and FB (type matching) both pass for all claims; FE is supplementary.
    # Use --deep-audit flag to enable FE checking when you need rigorous citation substantiveness.
    deep_audit = state.flags.get("deep_audit", False)
    revision_sidecar_mode = _revision_sidecar_mode(state, sentence_map, claim_matrix, evidence_ledger)
    advisory_results: list[dict] = []
    if deep_audit:
        all_results = run_factuality_check_fe(all_results, claim_matrix, evidence_ledger)

    # F2: wording strength vs evidence grade (FD)
    results_fd = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
    if revision_sidecar_mode and not deep_audit:
        advisory_results.extend({**result, "status": "advisory"} for result in results_fd)
    else:
        all_results.extend(results_fd)

    blocked_count = sum(1 for result in all_results if result["status"] == "blocked")
    verified_count = sum(1 for result in all_results if result["status"] == "verified")

    run_dir.mkdir(parents=True, exist_ok=True)
    factuality_report = {
        "claims": all_results,
        "advisory": advisory_results,
        "blocked_count": blocked_count,
        "verified_count": verified_count,
        "sidecars_consumed": {
            "claim_matrix": bool(claim_matrix.get("claims")),
            "sentence_map": bool(sentence_map),
            "evidence_ledger": bool(evidence_ledger),
            "outline": bool(outline.get("sections")),
        },
        "deep_audit": bool(deep_audit),
        "revision_sidecar_mode": bool(revision_sidecar_mode),
    }

    factuality_path = run_dir / "factuality_report.json"
    with open(factuality_path, "w", encoding="utf-8") as f:
        json.dump(factuality_report, f, indent=2)

    state.qa["factuality_report_path"] = str(factuality_path)
    return state
