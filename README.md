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
![Tests](https://img.shields.io/badge/tests-797%20passing-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Give your coding agent a folder of sources and one sentence. Get back a DOCX
you can hand in — and a refusal for every claim that cannot be traced to those
sources.**

**What you bring**: files you already have — a CSV of measurements, a Word
handout, a page of notes — and one sentence saying what to write. **What you
get**: a `.docx` with a table of contents, page numbers, real Word tables, and
charts drawn from your own numbers, following your department's or your
company's template if you point at one. English or Chinese.

Two lines to install, nothing to configure, no API key. Your agent does the
writing; this decides what may ship.

## Look before you install

This is the document it produced, and the note that goes with it. Both are in
this repository, so you can judge the output before running anything:

- **[`examples/output/report.docx`](examples/output/report.docx)** — the
  deliverable: table of contents, page numbers, a real Word table, a chart drawn
  from the source CSV
- **[`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)**
  — every claim in it, the verdict, and the source row it rests on

![Three pages of a pipeline-rendered DOCX report: a title-and-abstract page, a table of contents, and a page with a line chart derived from the source data with a self-contained caption.](docs/sample_report.png)

Seven document types — lab report, academic paper, business report, proposal,
two admissions formats, and a general one. The quantitative analysis a grader
looks for (a fitted slope against theory, R², a budget total) is computed from
your data and registered as citable evidence, so the agent never has to invent
it. Nothing it drafts reaches the page unless the numbers, quotes, and citations
appear in your material — an invented statistic or a fabricated reference is
blocked, with the gate and the reason that stopped it.

Profiles, Chinese-document handling, templates, and the gate list:
**[docs/OUTPUT.md](docs/OUTPUT.md)**.

## Drive it from your agent

In Claude Code, install the plugin — it brings the skill and the tool server
together, and nothing needs cloning:

```text
/plugin marketplace add 0Smallcat0/report-workflow
```

Then `/plugin install report-workflow@report-workflow`. Any other MCP-capable
agent (Codex, Cursor, your own harness) gets the same tools with one command:

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

Then ask in your own words:

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

The whole pipeline is exposed as tools, not just the gate: `start_report` →
`get_next_action` / `submit_action` → `publish_report`, with `verify_claims`,
`query_evidence`, and `lint_artifacts` alongside. An agent with the server
installed can take a folder of sources to a finished DOCX without a copy of
this repository. Payloads: [docs/mcp.md](docs/mcp.md).

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
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
`report-workflow` CLI — the whole source-to-DOCX pipeline. Rendering wants
pandoc; `pip install "report-workflow[render]"` carries it in the wheel, so
there is nothing to install by hand. Without pandoc the renderer falls back to
`python-docx`, with no real Word tables and none of the template's layout. The
skill and the tool server arrive with the plugin, so cloning is only for the
example scripts and the benchmarks:
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
- **Driving it from an agent** → [skills/report-workflow/SKILL.md](skills/report-workflow/SKILL.md)
- **Developing this repository** → [AGENTS.md](AGENTS.md) (authoritative contract)
- **Reporting a bug, and what is in scope** → [CONTRIBUTING.md](CONTRIBUTING.md)

Specified, integrated, and verified by its author, with coding agents doing much
of the implementation — the deterministic gates and the benchmark harness exist
so a human, not a model, holds the final "is this correct?" decision.
