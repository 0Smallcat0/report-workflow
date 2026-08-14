"""MCP server exposing the deterministic verification gates to any agent.

The Python package never calls an LLM; the external agent drafts and this
server answers one question deterministically: *is this claim allowed to
ship?* Running it over MCP (Model Context Protocol) lets any MCP-capable
agent — Claude Code, Codex, Cursor, a custom harness — call the same
factuality gate stack the report pipeline enforces, without shelling out to
the CLI.

The gate answers that question on its own, and the rest of the pipeline is
here too, so an MCP client with no copy of this repository can take a folder
of sources to a finished DOCX. Installing the server is the whole install.

Gate tools:
  * ``verify_claims`` — run FA (linkage), FB (statistical backing),
    FE (deep-audit content overlap), and FD (wording vs evidence grade) over
    a claim matrix, sentence map, and evidence ledger. Pure function of its
    inputs: no network, no API key, same verdict every run.
  * ``list_report_profiles`` — enumerate the built-in ``report_profile``
    selectors and their strictness.
  * ``get_workflow_status`` — read the persisted state of a prepared job.

Pipeline tools (delegating to ``agent_wrapper``, the same entry points the CLI
and the agent skill use):
  * ``check_environment`` → ``start_report`` → ``get_next_action`` /
    ``submit_action`` (repeat) → ``publish_report``.
  * ``query_evidence``, ``lint_artifacts``, ``audit_engineering_report`` for
    looking things up and catching artifact errors early.
  * ``submit_revision_plan`` / ``preview_revision_diff`` for editing an
    existing document rather than drafting one.

Authoring stays with the caller: the agent writes ``claim_matrix.json``,
``outline.json``, ``section_drafts/*.md`` and ``sentence_map.jsonl`` into the
run directory, and ``get_next_action`` says which of those is due and where
writing is permitted.

The ``mcp`` dependency is optional (``pip install report-workflow[mcp]``);
everything except ``main``/``build_server`` works without it, which keeps the
payload functions unit-testable in the minimal environment.

Run (stdio transport):
    report-workflow-mcp
"""
from __future__ import annotations

from typing import Any

from . import agent_wrapper
from .nodes.factuality_check import (
    run_factuality_check_fa,
    run_factuality_check_fb,
    run_factuality_check_fd,
    run_factuality_check_fe,
    run_factuality_check_ft,
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
    # FT runs unconditionally: it only has anything to say when the caller
    # supplied a computed group table, and a caller who did supply one is
    # exactly the caller who can read a direction out of two of its rows.
    # There is no merged draft on this surface, so the claim text is the
    # whole of what it reads.
    results.extend(run_factuality_check_ft("", matrix, evidence))
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
        # Quote the real failure. This used to say only "install the extra",
        # which is what someone reads after installing the extra: mcp 2.0
        # removed mcp.server.fastmcp, `mcp>=1.2` resolved to it in any clean
        # environment, and the advice sent them back to the step they had just
        # completed. The version bound now excludes 2.x; if this fires anyway,
        # the reason is in the message rather than in a traceback nobody sees.
        raise SystemExit(
            "The MCP server could not start: " + str(exc)
            + ". It needs the optional dependency at a supported version: "
            'pip install "report-workflow[mcp]" (mcp>=1.2,<2).'
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

    # The whole pipeline, not just the gate. These delegate to the same
    # functions the CLI and the agent skill call, so an MCP client alone can
    # take a folder of sources to a finished DOCX without cloning anything.
    # Authoring stays the caller's job: the agent writes claim_matrix.json,
    # outline.json, section_drafts/*.md and sentence_map.jsonl into the run
    # directory, and get_next_action says which one is due.

    @server.tool()
    def check_environment() -> dict:
        """Check renderer and optional-tool availability. Call before start_report.

        Reports what is installed (pandoc, mermaid, research keys), what each
        missing item costs, and which decisions start_report needs recorded in
        `preflight_decisions` before it will run.
        """
        return agent_wrapper.check_setup()

    @server.tool()
    def start_report(
        prompt: str,
        source_files: list[str | dict],
        output_dir: str | None = None,
        report_profile: str | None = None,
        task_intent: str = "new_draft",
        title: str | None = None,
        reference_docx: str | None = None,
        preflight_confirmed: bool = False,
        preflight_decisions: dict | None = None,
        allow_degraded_render: bool = False,
        enable_research: bool | None = None,
        enable_notebook_sync: bool | None = None,
    ) -> dict:
        """Step 1. Parse sources into an evidence ledger and write the task briefs.

        `source_files` takes paths, or `{"path": ..., "role": "source_data"}` /
        `{"path": ..., "role": "base_document"}`. `report_profile` is the only
        report-shape selector; omit it to infer one. Set `task_intent` to
        "revise_existing" to edit a base document instead of drafting.
        `reference_docx` follows your own Word template's styles.

        Optional features follow `preflight_decisions.feature_decisions`:
        recording `{"web_research": "enable"}` turns web research on. Pass
        `enable_research` / `enable_notebook_sync` only to override what was
        recorded. Returns the job_id, the run directory, and the briefs to
        read next.
        """
        return agent_wrapper.start_report_task(
            enable_research=enable_research,
            enable_notebook_sync=enable_notebook_sync,
            prompt=prompt,
            source_files=source_files,
            output_dir=output_dir,
            report_profile=report_profile,
            task_intent=task_intent,
            title=title,
            reference_docx=reference_docx,
            preflight_confirmed=preflight_confirmed,
            preflight_decisions=preflight_decisions,
            allow_degraded_render=allow_degraded_render,
        )

    @server.tool()
    def get_next_action(job_id: str, workspace_root: str | None = None) -> dict:
        """Step 2. Ask what to author next, what to read first, and where you may write.

        The authoritative answer to "what now" for a run. Returns the current
        stage, the files to read before writing, and the paths this stage is
        allowed to write; writing outside that scope is refused.
        """
        return agent_wrapper.get_controlled_next_action(job_id, workspace_root)

    @server.tool()
    def submit_action(job_id: str, workspace_root: str | None = None) -> dict:
        """Step 3. Validate what you just wrote for the current stage and advance.

        Call after writing the files get_next_action asked for. A rejection
        names the artifact, the JSON path, and how to repair it.
        """
        return agent_wrapper.submit_controlled_action(job_id, workspace_root)

    @server.tool()
    def query_evidence(
        job_id: str,
        evidence_ids: list[str] | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 20,
        workspace_root: str | None = None,
    ) -> dict:
        """Look up evidence rows without loading the whole ledger into context.

        Filter by `evidence_ids`, or search `query` across content. Use this to
        find the row that supports a claim rather than reading the ledger file.
        """
        return agent_wrapper.query_evidence(
            job_id, evidence_ids, query, offset, limit, workspace_root
        )

    @server.tool()
    def register_derived_evidence(
        job_id: str,
        derivations: list[dict],
        workspace_root: str | None = None,
    ) -> dict:
        """Make a statistic over the source rows citable.

        The ledger holds one row per record, so a sample size, a median, a
        share or a concentration index has no evidence id — and the sentence
        that needs one goes unwritten. Register the derivation instead:
        `{"id": "photo_count", "source": "products.csv",
        "rows": "category=攝影", "op": "count"}`. Ops are count, sum, mean,
        median, min, max, distinct, share, hhi, top_share. The value is
        computed from the rows here rather than supplied by you; `expect` is
        checked against it, never trusted. Cite the returned evidence_id.

        Two shapes beyond that scalar, and a report that never reaches for
        them is the poorer for it:

        `group_by` plus `measures` returns a whole table — one row per group,
        one column per measure — registered as a single evidence entry a
        `[TABLE:<id>]` marker can place:
        `{"id": "price_band_reliability", "source": "products.csv",
        "group_by": {"column": "price", "buckets": [0, 30, 50, 100],
        "label": "Price band"}, "measures": [{"op": "count"},
        {"op": "mean", "column": "rating"},
        {"op": "share", "rows": "rating < 4"}]}`. Omit `buckets` for a
        categorical column. Bucket edges are never guessed: where a numeric
        axis is cut is the finding, not an input to it.

        `source` also takes two files with a `join`, which is the only way to
        reach a finding neither file states alone:
        `{"id": "band_review_rating",
        "source": ["reviews.csv", "products.csv"],
        "join": {"on": "asin", "how": "inner"},
        "group_by": {"column": "price", "buckets": [0, 30, 50, 100]},
        "measures": [{"op": "mean", "column": "review_rating"}]}`. Rows that
        find no partner are counted and reported in the evidence text, and a
        column name present on both sides is renamed rather than overwritten.
        Check two tables for a shared key before writing that they cannot be
        crossed: saying so when they share one is a false statement about the
        data.
        """
        return agent_wrapper.register_derived_evidence(
            job_id, derivations, workspace_root
        )

    @server.tool()
    def lint_artifacts(job_id: str, workspace_root: str | None = None) -> dict:
        """Check the artifacts you authored for shape errors before publishing.

        Cheaper than a full validate: returns artifact names, JSON paths,
        severity, and repair hints.
        """
        return agent_wrapper.lint_agent_artifacts(job_id, workspace_root)

    @server.tool()
    def remap_agent_artifacts(
        job_id: str,
        previous_job_id: str,
        write: bool = False,
        workspace_root: str | None = None,
    ) -> dict:
        """Rewrite evidence ids in artifacts reused from an earlier run.

        The task briefs and the artifact linter both tell an author to run
        this when they carry a claim matrix or drafts over from a previous
        job; it was not callable over MCP, so that instruction could not be
        followed. Call with `write=false` first to see the mapping.
        """
        return agent_wrapper.remap_agent_artifacts(
            job_id, previous_job_id, write, workspace_root
        )

    @server.tool()
    def audit_engineering_report(job_id: str, workspace_root: str | None = None) -> dict:
        """Measurement, unit, and calculation audit for engineering_lab_report runs."""
        return agent_wrapper.run_engineering_audit(job_id, workspace_root)

    @server.tool()
    def publish_report(
        job_id: str,
        workspace_root: str | None = None,
        reference_docx: str | None = None,
    ) -> dict:
        """Final step. Validate everything, render the DOCX, and package the QA pack.

        Runs the gates: every publishable claim must cite evidence that
        supports it, citations must resolve, and rendering is refused unless
        the QA decision passes. Returns the delivered document path and the QA
        artifacts recording why each sentence was allowed to ship.
        """
        return agent_wrapper.submit_and_publish_report(job_id, workspace_root, reference_docx)

    @server.tool()
    def submit_revision_plan(job_id: str, workspace_root: str | None = None) -> dict:
        """Validate revision_plan.json for a revise_existing run."""
        return agent_wrapper.submit_revision_plan(job_id, workspace_root)

    @server.tool()
    def preview_revision_diff(job_id: str, workspace_root: str | None = None) -> dict:
        """Show what revision_plan.json would change, without applying it."""
        return agent_wrapper.preview_revision_diff(job_id, workspace_root)

    return server


def main() -> None:
    """Entry point for the ``report-workflow-mcp`` console script (stdio)."""
    build_server().run()


if __name__ == "__main__":
    main()
