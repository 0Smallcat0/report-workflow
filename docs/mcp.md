# MCP Server

`report-workflow-mcp` exposes the deterministic verification gates over the
Model Context Protocol, so any MCP-capable agent (Claude Code, Codex, Cursor,
or a custom harness) can ask the same question the pipeline enforces: *is this
claim allowed to ship?*

The server is deterministic and offline — no LLM, no network, no API key. The
agent drafts; the server verifies.

## Install

```bash
pip install "report-workflow[mcp]"
```

The server lives behind the `[mcp]` extra: the bare package does not pull in the
MCP SDK. To run it without installing anything:

```bash
uvx --from "report-workflow[mcp]" report-workflow-mcp
```

That is the invocation `server.json` declares to the MCP Registry, so a client
installing this server from the registry gets the same command.

## Register

Claude Code:

```bash
claude mcp add report-workflow -- report-workflow-mcp
```

Generic MCP client configuration (stdio):

```json
{
  "mcpServers": {
    "report-workflow": {
      "command": "report-workflow-mcp"
    }
  }
}
```

## Tools

### `verify_claims`

Run the factuality gate stack — FA (claim/evidence/sentence linkage, fabricated
citations), FB (statistical backing), FE (deep-audit content overlap: invented
numbers, wrong units, fabricated quotes, off-topic citations), FD (wording
strength vs evidence grade) — over a claim matrix and evidence ledger.

Input (sentences optional; omitted sentences are synthesized one-per-claim):

```json
{
  "claims": [
    {
      "claim_id": "c_error",
      "claim_text": "The error rate fell to 3.5% under the structured workflow.",
      "claim_type": "statistical",
      "status": "supported",
      "evidence_ids": ["ev_error"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "ev_error",
      "content": "The error rate fell to 3.5% under the structured workflow, down from 9.0% for the manual baseline.",
      "evidence_type": "quantitative",
      "source_role": "primary_source",
      "evidence_grade": "high"
    }
  ]
}
```

Output:

```json
{
  "publishable": true,
  "verified_count": 1,
  "blocked_count": 0,
  "claim_results": [
    {
      "claim_id": "c_error",
      "status": "verified",
      "checker": "FA+FB",
      "reason": "Claim/evidence linkage and quantitative support confirmed"
    }
  ],
  "wording_flags": [],
  "deep_audit": true
}
```

A hallucinated claim comes back `"status": "blocked"` with the gate that fired
(`FA`, `FB`, `FE`, or `FD`) and the concrete reason (for example
`Claim number '0.2'% not found in evidence content`).

### `list_report_profiles`

Enumerates the built-in `report_profile` selectors (the only public
report-shape selector) with display name, description, and strictness.

### `get_workflow_status`

Reads the persisted status and QA decision of a prepared/validated/rendered
job (`job_id`, optional `workspace_root`).

## Scope

The MCP surface is the verification gate, not the full authoring pipeline.
Preparing sources, authoring artifacts, and rendering DOCX stay with the CLI
and the agent skill (see [`skills/report-workflow/SKILL.md`](../skills/report-workflow/SKILL.md)) —
those steps need files on disk and explicit preflight decisions, which are
better handled by the harness's own tools. The measured behavior of the gates
this server exposes is documented in
[`benchmarks/evidence/adversarial_2026-07-14/summary.md`](../benchmarks/evidence/adversarial_2026-07-14/summary.md).
