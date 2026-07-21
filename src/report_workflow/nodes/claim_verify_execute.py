"""CLAIM_VERIFY_EXECUTE node — verify blocked claims with external evidence.

This node extends the research pipeline by taking the output of
RESEARCH_EXECUTE and cross-referencing it with blocked claims from
the factuality report. When research results provide supporting
evidence for a blocked claim, the claim status is upgraded to
"externally_verified" in a supplementary report.

This node is OPTIONAL and only runs when:
  1. state.flags["enable_claim_verification"] is True
  2. RESEARCH_EXECUTE has already produced results

Ported from report-from-notebooklm's audit_claims.py + execute_claim_verification.py.
"""
import json
import logging
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)


def _compute_claim_coverage(
    claim: dict,
    research_result: dict,
) -> dict:
    """Evaluate how well a research result covers a claim.

    Returns a coverage assessment dict with:
      - coverage_score: 0.0-1.0
      - supporting_sources: list of relevant sources
      - verdict: "supported" / "partially_supported" / "unsupported"
    """
    claim_text = (claim.get("claim_text") or claim.get("text") or "").lower()
    if not claim_text:
        return {"coverage_score": 0.0, "supporting_sources": [], "verdict": "unsupported"}

    # Extract key terms from claim (5+ char non-stopwords)
    import re
    stopwords = {
        "should", "would", "could", "might", "which", "where", "there",
        "their", "these", "those", "however", "therefore", "because",
        "result", "results", "study", "paper", "research", "report",
    }
    claim_terms = set(
        t for t in re.findall(r"\b[a-zA-Z]{5,}\b", claim_text)
        if t not in stopwords
    )

    if not claim_terms:
        return {"coverage_score": 0.0, "supporting_sources": [], "verdict": "unsupported"}

    # Check answer coverage
    answer = (research_result.get("answer") or "").lower()
    answer_matched = sum(1 for t in claim_terms if t in answer)
    answer_coverage = answer_matched / len(claim_terms) if claim_terms else 0.0

    # Check source coverage
    supporting_sources = []
    for source in research_result.get("sources", []):
        snippet = (
            source.get("verification_note") or source.get("snippet") or ""
        ).lower()
        title = (source.get("title") or "").lower()
        combined = f"{title} {snippet}"
        matched = sum(1 for t in claim_terms if t in combined)
        if matched >= 2 or (matched >= 1 and len(claim_terms) <= 3):
            supporting_sources.append(source)

    # Compute overall score
    source_score = min(len(supporting_sources) / 3.0, 1.0) if supporting_sources else 0.0
    backend_confidence = research_result.get("confidence", 0.5)
    coverage_score = (answer_coverage * 0.4 + source_score * 0.4 + backend_confidence * 0.2)

    if coverage_score >= 0.6:
        verdict = "supported"
    elif coverage_score >= 0.3:
        verdict = "partially_supported"
    else:
        verdict = "unsupported"

    return {
        "coverage_score": round(coverage_score, 3),
        "supporting_sources": supporting_sources,
        "verdict": verdict,
        "answer_coverage": round(answer_coverage, 3),
        "source_count": len(supporting_sources),
    }


def run_claim_verify_execute(state: ReportState) -> ReportState:
    """Verify blocked claims against research results.

    Skips gracefully if:
      - enable_claim_verification flag is not set
      - No research results exist
      - No factuality report exists
    """
    if not state.flags.get("enable_claim_verification"):
        logger.info("[CLAIM_VERIFY] Skipped — enable_claim_verification flag not set")
        return state

    run_dir = WORKFLOW_RUNS_DIR / state.job_id

    # Load research results
    research_path = state.research.get("results_path", "")
    if not research_path or not Path(research_path).exists():
        logger.info("[CLAIM_VERIFY] Skipped — no research results found")
        return state

    with open(research_path, encoding="utf-8") as f:
        research_data = json.load(f)

    research_results = research_data.get("results", [])
    if not research_results:
        logger.info("[CLAIM_VERIFY] Skipped — research results are empty")
        return state

    # Load factuality report
    factuality_path = state.qa.get("factuality_report_path", "")
    if not factuality_path or not Path(factuality_path).exists():
        logger.info("[CLAIM_VERIFY] Skipped — no factuality report found")
        return state

    with open(factuality_path, encoding="utf-8") as f:
        factuality_report = json.load(f)

    # Load claim matrix for full claim text
    claim_matrix_path = run_dir / "claim_matrix.json"
    claim_matrix = {}
    if claim_matrix_path.exists():
        with open(claim_matrix_path, encoding="utf-8") as f:
            claim_matrix = json.load(f)

    claims_by_id = {
        (c.get("claim_id") or c.get("id", "")): c
        for c in claim_matrix.get("claims", [])
    }

    # Map research results by claim_id
    research_by_claim: dict[str, dict] = {}
    for result in research_results:
        task_id = result.get("task_id", "")
        # task_id format: "research_{claim_id}"
        if task_id.startswith("research_"):
            claim_id = task_id[len("research_"):]
            research_by_claim[claim_id] = result

    # Verify each blocked claim
    verifications: list[dict] = []
    upgraded_count = 0

    for factuality_result in factuality_report.get("claims", []):
        claim_id = factuality_result.get("claim_id", "")
        status = factuality_result.get("status", "")

        if status not in ("blocked", "disputed", "unverified"):
            continue

        research_result = research_by_claim.get(claim_id)
        if not research_result:
            verifications.append({
                "claim_id": claim_id,
                "original_status": status,
                "verification_status": "no_research",
                "coverage": None,
            })
            continue

        claim = claims_by_id.get(claim_id, {})
        coverage = _compute_claim_coverage(claim, research_result)

        new_status = status
        if coverage["verdict"] == "supported":
            new_status = "externally_verified"
            upgraded_count += 1
        elif coverage["verdict"] == "partially_supported":
            new_status = "partially_verified"

        verifications.append({
            "claim_id": claim_id,
            "original_status": status,
            "verification_status": new_status,
            "coverage": coverage,
            "research_backend": research_result.get("backend", ""),
            "research_answer_snippet": (research_result.get("answer") or "")[:200],
        })

        logger.info(
            f"[CLAIM_VERIFY] Claim {claim_id}: {status} → {new_status} "
            f"(score={coverage['coverage_score']}, sources={coverage['source_count']})"
        )

    # Write verification report
    verification_report = {
        "total_verified": len(verifications),
        "upgraded_count": upgraded_count,
        "verifications": verifications,
    }

    report_path = run_dir / "claim_verification_results.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(verification_report, f, indent=2, default=str)

    state.qa["claim_verification_path"] = str(report_path)
    state.qa["claim_verification_upgraded"] = upgraded_count

    logger.info(
        f"[CLAIM_VERIFY] Done — {upgraded_count}/{len(verifications)} claims upgraded"
    )

    return state
