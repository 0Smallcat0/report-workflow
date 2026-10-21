# MCP Server

`report-workflow-mcp` exposes the whole pipeline over the Model Context
Protocol, so any MCP-capable agent (Claude Code, Codex, Cursor, or a custom
harness) can take a folder of sources to a finished DOCX, and ask the question
the pipeline enforces at every step: *is this claim allowed to ship?*

The server calls no LLM and needs no API key, and it stays offline unless the
run turns web research on. The agent drafts; the server verifies.

## Install

```bash
pip install "report-workflow[mcp,render]"
```

The server lives behind the `[mcp]` extra: the bare package does not pull in the
MCP SDK. To run it without installing anything:

```bash
uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

That is the invocation `server.json` declares to the MCP Registry, so a client
installing this server from the registry gets the same command.

## Register

The Claude Code plugin registers the server itself (see the README). Otherwise,
with [uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```bash
# Claude Code
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
# Codex
codex mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

Cursor (`.cursor/mcp.json` in the project, or `~/.cursor/mcp.json`) and other
stdio clients:

```json
{
  "mcpServers": {
    "report-workflow": {
      "command": "uvx",
      "args": ["--from", "report-workflow[mcp,render]", "report-workflow-mcp"]
    }
  }
}
```

After `pip install "report-workflow[mcp,render]"`, the command can be plain
`report-workflow-mcp` instead.

## Tools

Fifteen tools. The pipeline, in the order a run calls them:
`check_environment` → `start_report` → `get_next_action` / `submit_action`
(repeat) → `publish_report`. Helpers along the way: `query_evidence`,
`register_derived_evidence` (makes a count, mean, share or formula over the
source rows citable), `lint_artifacts`, `remap_agent_artifacts`,
`audit_engineering_report`. Revising an existing document:
`submit_revision_plan`, `preview_revision_diff`. Each tool's description in
the server says what it takes. The three below also work on their own, with no
run at all.

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

Authoring stays with the agent: it writes `claim_matrix.json`, `outline.json`,
`section_drafts/*.md` and `sentence_map.jsonl` into the run directory, and
`get_next_action` says which one is due and where writing is allowed. How to
drive a run: [`skills/report-workflow/SKILL.md`](../skills/report-workflow/SKILL.md).
The measured behavior of the gates is in
[`benchmarks/evidence/adversarial_2026-07-14/summary.md`](../benchmarks/evidence/adversarial_2026-07-14/summary.md).
