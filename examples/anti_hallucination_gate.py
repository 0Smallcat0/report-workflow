"""Anti-hallucination gate demo - run the real factuality checkers on honest vs. fabricated claims.

Report Workflow's thesis: an LLM drafts, a *deterministic* layer decides what is
publishable. A claim ships only if it is linked to evidence that actually
supports it; anything else is hard-blocked before it can reach the document.

This script exercises the exact checker functions the pipeline runs
(`report_workflow.nodes.factuality_check`) against a tiny, self-contained
evidence ledger. No LLM, no network, no API key. It prints two runs:

  1. HONEST   — every claim cites evidence whose content backs it -> all verified.
  2. HALLUCINATED — a fabricated citation and an invented statistic -> both blocked,
     with the specific gate and reason that caught each one.

Run:
    python examples/anti_hallucination_gate.py
"""
from __future__ import annotations

from report_workflow.nodes.factuality_check import (
    run_factuality_check_fa,
    run_factuality_check_fb,
    run_factuality_check_fe,
)

# --- A tiny evidence ledger (the only "ground truth" a claim may rest on) -----
# In a real run this is built deterministically from the user's sources. Every
# number and phrase below is something the source actually says.
EVIDENCE: list[dict] = [
    {
        "evidence_id": "ev_processing",
        "content": "Median processing time was 12.4 minutes for the manual baseline "
        "and 7.8 minutes for the structured workflow.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_error",
        "content": "The error rate fell to 3.5% under the structured workflow, "
        "down from 9.0% for the manual baseline.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_scope",
        "content": "The result is a single pilot and should not be generalized "
        "beyond the tested intake workflow.",
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
]


def _sentence(claim_id: str, evidence_ids: list[str], strength: str = "hedged") -> dict:
    return {
        "sentence_id": f"s_{claim_id}",
        "claim_ids": [claim_id],
        "evidence_ids": evidence_ids,
        "citation_ids": evidence_ids,
        "wording_strength": strength,
    }


# --- Run 1: HONEST — claims a careful analyst could defend ---------------------
HONEST_CLAIMS = [
    {
        "claim_id": "c_processing",
        "claim_text": "The structured workflow cut median processing time to 7.8 minutes.",
        "claim_type": "statistical",
        "status": "supported",
        "evidence_ids": ["ev_processing"],
    },
    {
        "claim_id": "c_error",
        "claim_text": "The error rate under the structured workflow was 3.5%.",
        "claim_type": "statistical",
        "status": "supported",
        "evidence_ids": ["ev_error"],
    },
    {
        "claim_id": "c_scope",
        "claim_text": "The finding is a pilot and should not be generalized beyond the tested workflow.",
        "claim_type": "factual",
        "status": "supported",
        "evidence_ids": ["ev_scope"],
    },
]
HONEST_SENTENCES = [
    _sentence("c_processing", ["ev_processing"]),
    _sentence("c_error", ["ev_error"]),
    _sentence("c_scope", ["ev_scope"]),
]

# --- Run 2: HALLUCINATED — the two failure modes an LLM ships silently ---------
HALLUCINATED_CLAIMS = [
    # Same honest, well-grounded claim — should still pass, proving the gate is
    # not just rejecting everything.
    {
        "claim_id": "c_processing",
        "claim_text": "The structured workflow cut median processing time to 7.8 minutes.",
        "claim_type": "statistical",
        "status": "supported",
        "evidence_ids": ["ev_processing"],
    },
    # Failure mode 1 — INVENTED STATISTIC. Cites real evidence, but the number
    # is made up: the source says 3.5%, the claim says 0.2%.
    {
        "claim_id": "c_error_inflated",
        "claim_text": "The structured workflow drove the error rate down to just 0.2%.",
        "claim_type": "statistical",
        "status": "supported",
        "evidence_ids": ["ev_error"],
    },
    # Failure mode 2 — FABRICATED CITATION. A confident sentence resting on an
    # evidence id that does not exist in the ledger.
    {
        "claim_id": "c_ghost_audit",
        "claim_text": "An independent third party audited and certified the pilot results.",
        "claim_type": "factual",
        "status": "supported",
        "evidence_ids": ["ev_external_audit"],
    },
]
HALLUCINATED_SENTENCES = [
    _sentence("c_processing", ["ev_processing"]),
    _sentence("c_error_inflated", ["ev_error"]),
    _sentence("c_ghost_audit", ["ev_external_audit"]),
]


def _check(claims: list[dict], sentences: list[dict]) -> list[dict]:
    """Run the real pipeline checkers in the same order the workflow does."""
    matrix = {"claims": claims}
    results = run_factuality_check_fa(sentences, matrix, EVIDENCE)
    results = run_factuality_check_fb(results, matrix, EVIDENCE)
    # FE is the deep-audit content-overlap pass (`validate --deep-audit`); it is
    # what catches an invented number that survives ID-linkage checks.
    results = run_factuality_check_fe(results, matrix, EVIDENCE)
    return results


def _print_run(label: str, results: list[dict]) -> int:
    print(f"\n{'=' * 74}\n{label}\n{'=' * 74}")
    blocked = 0
    for row in results:
        mark = "PASS " if row["status"] == "verified" else "BLOCK"
        print(f"  [{mark}] {row['claim_id']:<18} ({row['checker']})")
        if row["status"] != "verified":
            blocked += 1
            print(f"          reason: {row['reason']}")
    print(f"\n  -> {len(results) - blocked} verified, {blocked} blocked.")
    return blocked


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    honest_blocked = _print_run("RUN 1 - HONEST DRAFT", _check(HONEST_CLAIMS, HONEST_SENTENCES))
    hall_blocked = _print_run(
        "RUN 2 - HALLUCINATED DRAFT (invented statistic + fabricated citation)",
        _check(HALLUCINATED_CLAIMS, HALLUCINATED_SENTENCES),
    )
    print(f"\n{'=' * 74}")
    ok = honest_blocked == 0 and hall_blocked == 2
    if ok:
        print("RESULT: honest draft published clean; both hallucinations hard-blocked. [OK]")
    else:
        print(
            f"RESULT: unexpected — honest_blocked={honest_blocked} (want 0), "
            f"hallucinations_blocked={hall_blocked} (want 2)."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
