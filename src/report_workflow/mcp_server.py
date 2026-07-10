"""MCP server exposing the deterministic verification gates to any agent.

The Python package never calls an LLM; the external agent drafts and this
server answers one question deterministically: *is this claim allowed to
ship?* Running it over MCP (Model Context Protocol) lets any MCP-capable
agent — Claude Code, Codex, Cursor, a custom harness — call the same
factuality gate stack the report pipeline enforces, without shelling out to
the CLI.

Tools:
  * ``verify_claims`` — run FA (linkage), FB (statistical backing),
    FE (deep-audit content overlap), and FD (wording vs evidence grade) over
    a claim matrix, sentence map, and evidence ledger. Pure function of its
    inputs: no network, no API key, same verdict every run.
  * ``list_report_profiles`` — enumerate the built-in ``report_profile``
    selectors and their strictness.
  * ``get_workflow_status`` — read the persisted state of a prepared job.

The ``mcp`` dependency is optional (``pip install report-workflow[mcp]``);
everything except ``main``/``build_server`` works without it, which keeps the
payload functions unit-testable in the minimal environment.

Run (stdio transport):
    report-workflow-mcp
"""
from __future__ import annotations

from typing import Any

from .nodes.factuality_check import (
    run_factuality_check_fa,
    run_factuality_check_fb,
    run_factuality_check_fd,
    run_factuality_check_fe,
)
from .profiles import PROFILE_REGISTRY


def _default_sentences(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Synthesize a one-sentence-per-claim map when the caller has none yet.

    Agents that only want the gate verdict (not full report authoring) can
    pass claims + evidence and let the server anchor each claim to a synthetic
    sentence that cites the claim's own evidence.
    """
    sentences = []
    for claim in claims:
        claim_id = claim.get("claim_id") or claim.get("id") or ""
        evidence_ids = list(claim.get("evidence_ids", []))
        sentences.append({
            "sentence_id": f"s_{claim_id}",
            "claim_ids": [claim_id],
            "evidence_ids": evidence_ids,
            "citation_ids": evidence_ids,
            "wording_strength": claim.get("wording_strength", "hedged"),
        })
    return sentences


def verify_claims_payload(
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None = None,
    deep_audit: bool = True,
) -> dict[str, Any]:
    """Run the deterministic factuality gate stack and return all verdicts."""
    if not claims:
        raise ValueError("claims must be a non-empty list of claim objects")
    if not evidence:
        raise ValueError("evidence must be a non-empty evidence ledger")

    sentence_map = sentences if sentences else _default_sentences(claims)
    matrix = {"claims": claims}

    results = run_factuality_check_fa(sentence_map, matrix, evidence)
    results = run_factuality_check_fb(results, matrix, evidence)
    if deep_audit:
        results = run_factuality_check_fe(results, matrix, evidence)
    wording_flags = run_factuality_check_fd(sentence_map, matrix, evidence)

    blocked = [row for row in results if row["status"] == "blocked"]
    verified = [row for row in results if row["status"] == "verified"]
    return {
        "publishable": not blocked and not wording_flags,
        "verified_count": len(verified),
        "blocked_count": len(blocked) + len(wording_flags),
        "claim_results": results,
        "wording_flags": wording_flags,
        "deep_audit": deep_audit,
    }


def list_profiles_payload() -> dict[str, Any]:
    """Enumerate built-in report profiles (the only public shape selector)."""
    return {
        "selector": "report_profile",
        "profiles": [
            {
                "profile_id": profile.profile_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "strictness": profile.strictness,
                "evidence_backed_claims": profile.evidence_backed_claims,
            }
            for profile in PROFILE_REGISTRY.values()
        ],
    }


def workflow_status_payload(job_id: str, workspace_root: str | None = None) -> dict[str, Any]:
    """Read the persisted status of a prepared/validated/rendered job."""
    from .run_workflow import status_workflow

    try:
        state = status_workflow(job_id, workspace_root=workspace_root)
    except Exception as exc:  # surface a clean, agent-readable failure
        raise ValueError(f"cannot load job {job_id!r}: {exc}") from exc
    return {
        "job_id": state.job_id,
        "status": state.status,
        "qa_decision": (state.qa or {}).get("qa_decision"),
    }


def build_server():
    """Construct the FastMCP server (requires the optional ``mcp`` extra)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise SystemExit(
            "The MCP server needs the optional dependency: pip install report-workflow[mcp]"
        ) from exc

    server = FastMCP(
        "report-workflow",
        instructions=(
            "Deterministic anti-hallucination gates for evidence-bounded report "
            "generation. Draft with your own judgment, then call verify_claims "
            "before publishing: any claim that cannot be traced to the supplied "
            "evidence ledger is hard-blocked with the gate and reason."
        ),
    )

    @server.tool()
    def verify_claims(
        claims: list[dict],
        evidence: list[dict],
        sentences: list[dict] | None = None,
        deep_audit: bool = True,
    ) -> dict:
        """Verify claims against an evidence ledger with the deterministic gate stack.

        Each claim needs: claim_id, claim_text, claim_type
        (factual|statistical|qualitative|methodological|contextual), status,
        and evidence_ids. Each evidence row needs: evidence_id, content,
        evidence_type, and optionally source_role / evidence_grade
        (high|medium|low). Sentences are optional; if omitted, each claim is
        anchored to a synthetic sentence citing its own evidence. Returns
        per-claim verdicts (verified/blocked), the gate that fired (FA, FB,
        FE, FD), and an overall publishable flag.
        """
        return verify_claims_payload(claims, evidence, sentences, deep_audit)

    @server.tool()
    def list_report_profiles() -> dict:
        """List built-in report profiles selectable via report_profile."""
        return list_profiles_payload()

    @server.tool()
    def get_workflow_status(job_id: str, workspace_root: str | None = None) -> dict:
        """Get the persisted status and QA decision of a report workflow job."""
        return workflow_status_payload(job_id, workspace_root)

    return server


def main() -> None:
    """Entry point for the ``report-workflow-mcp`` console script (stdio)."""
    build_server().run()


if __name__ == "__main__":
    main()
