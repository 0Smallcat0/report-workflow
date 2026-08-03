# Report Workflow

<!--
MCP Registry ownership marker. The registry verifies a PyPI package by looking
for this line in the published README, so it has to ship in the release, not
just sit in the repository. Both casings are present because the namespace is
derived from a GitHub login and only one of them will match.
mcp-name: io.github.0smallcat0/report-workflow
mcp-name: io.github.0Smallcat0/report-workflow
-->

[![CI](https://github.com/0Smallcat0/report-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/0Smallcat0/report-workflow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-789%20passing-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Give your coding agent a folder of sources and one sentence. Get back a DOCX
you can hand in — and a refusal for every claim that cannot be traced to those
sources.**

The package **calls no LLM and needs no API key.** It owns source parsing, the
evidence ledger, the gates, and rendering; your agent (Claude Code, Codex, …)
owns the judgment and the writing. Nothing the agent drafts reaches the page
unless the numbers, quotes, and citations in it appear in your material — so an
invented statistic or a fabricated reference is blocked, with the gate and the
reason that stopped it.

## What comes out

![Three pages of a pipeline-rendered DOCX report: a title-and-abstract page, a table of contents, and a page with a line chart derived from the source data with a self-contained caption.](docs/sample_report.png)

A finished document, and the audit trail that says why each sentence was allowed
to ship. Both are in this repository, produced by the example below:

- [`examples/output/report.docx`](examples/output/report.docx) — table of
  contents, page numbers, a real Word table, a chart drawn from the source CSV
- [`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)
  — every claim, its verdict, and the source row it rests on

Seven document types — lab report, academic paper, business report, proposal,
two admissions formats, and a general one — in English or Chinese, optionally
following your own Word template. The quantitative analysis a grader looks for
(a fitted slope against theory, R², a budget total) is computed from your data
and registered as citable evidence, so the agent never has to invent it.

Profiles, Chinese-document handling, templates, and the gate list:
**[docs/OUTPUT.md](docs/OUTPUT.md)**.

## Drive it from your agent

```bash
pip install report-workflow
git clone https://github.com/0Smallcat0/report-workflow
cp -r report-workflow/agent_skill ~/.claude/skills/report-workflow
```

That last line installs the skill for Claude Code (on Windows, copy the same
folder to `%USERPROFILE%\.claude\skills\report-workflow`). Then ask in your own
words:

> Use report-workflow to turn the files in ./data into a business report for
> the operations manager: what changed, what it costs, whether to adopt it.

The skill hands the agent the contract — prepare the sources, write claims and
prose against the evidence ledger, submit for validation — and the pipeline
answers. A claim it cannot support comes back blocked with the gate that caught
it, so the agent has to fix the sentence, not the verdict.

No agent to hand? The same path runs offline with a scripted author standing in
for one:

```bash
python examples/source_to_report.py
```

Three files and one sentence in, the DOCX and QA pack above out. Swap the paths
at the top of that script for your own material; the honest note about what it
does on your agent's behalf is in [examples/README.md](examples/README.md).

## The CLI

The same pipeline, driven by hand or from a script:

```bash
report-workflow prepare --prompt "write an engineering lab report" \
  --source source.txt --output out --profile engineering_lab_report \
  --preflight-decisions preflight.json
report-workflow validate --job-id <job_id>
report-workflow render   --job-id <job_id>
```

Exit codes: `0` success, `1` crash, `2` hard-block, `3` waiting for user
decisions or agent-authored artifacts. Add `--reference-docx your.docx` to
follow your own Word template. Between `prepare` and `validate` something has to
write the claims, outline, and drafts — that is the agent's half.

## MCP server

Any MCP-capable agent can call the gates as tools — draft with its own
judgment, then ask `verify_claims` whether each claim may ship. This is the
gate surface, not the whole pipeline: rendering a DOCX still goes through the
skill or the CLI. Payloads: [docs/mcp.md](docs/mcp.md).

```bash
claude mcp add report-workflow -- report-workflow-mcp
```

## The gate on its own

No pipeline, no schema, no API key — pass an answer and the source it was
supposed to be grounded in:

```python
from report_workflow import verify

result = verify(
    answer="The error rate fell to 0.2% [1].",
    sources={"1": "The error rate fell to 3.5% under the structured workflow."},
)
result["publishable"]                      # False
result["sentence_results"][0]["checker"]   # "FE"
result["sentence_results"][0]["reason"]    # "Claim number '0.2'% not found in evidence content..."
```

A pure function of `(answer, sources)`: same verdict every run, zero tokens,
works offline and in CI. **Scope, stated plainly:** a *fidelity gate*, not a
general hallucination detector. It catches invented numbers, fabricated
citations, misquotes, and unit swaps; it does not judge meaning, so a fluent
paraphrase that reverses the source is out of scope. That boundary is measured
on 10,000 outside pairs, with catch rates, baselines, and the comparison to
LLM-as-judge tools: **[docs/EVIDENCE.md](docs/EVIDENCE.md)**.

Runnable, no local install:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/0Smallcat0/report-workflow/blob/master/docs/quickstart_demo.ipynb)

## Install

`pip install report-workflow` covers the gates, `verify()`, and the
`report-workflow` CLI — the whole source-to-DOCX pipeline. Add pandoc 3.x for
full rendering; without it the renderer falls back to `python-docx` with
degraded table and layout fidelity. Clone the repository for the agent skill,
the example scripts, and the benchmarks:
`pip install` ships the package, not the examples.

```powershell
pip install -r requirements.txt
pip install -e .
pandoc --version
```

Optional: `pip install -e .[mcp]` for the MCP server, `mmdc` for Mermaid
diagrams, `TAVILY_API_KEY` / `SERPER_API_KEY` / `SERPAPI_API_KEY` for web
research, `notebooklm-py` for NotebookLM sync.

If the `report-workflow` command fails silently — common on Windows when a stale
`report-workflow.exe` sits on PATH — use `python -m report_workflow`, which
always runs against the interpreter you invoke.

## Where to go next

- **What the output looks like, profiles, templates, gates** → [docs/OUTPUT.md](docs/OUTPUT.md)
- **Measured catch rates and honest limits** → [docs/EVIDENCE.md](docs/EVIDENCE.md)
- **Why it is built this way, threat model** → [docs/DESIGN.md](docs/DESIGN.md)
- **Driving it from an agent** → [agent_skill/SKILL.md](agent_skill/SKILL.md)
- **Developing this repository** → [AGENTS.md](AGENTS.md) (authoritative contract)

Specified, integrated, and verified by its author, with coding agents doing much
of the implementation — the deterministic gates and the benchmark harness exist
so a human, not a model, holds the final "is this correct?" decision.
