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
![Tests](https://img.shields.io/badge/tests-798%20passing-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**繁體中文說明 → [README.zh-TW.md](README.zh-TW.md)**

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

The document it produced, and the note that goes with it — both in this
repository, so you can judge the output before running anything:

- **[`examples/output/report.docx`](examples/output/report.docx)** — the
  deliverable: table of contents, page numbers, a real Word table, a chart drawn
  from the source CSV
- **[`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)**
  — every claim in it, the verdict, and the source row it rests on

![Three pages of a pipeline-rendered DOCX report: a title-and-abstract page, a table of contents, and a page with a line chart derived from the source data with a self-contained caption.](docs/sample_report.png)

## Use it

In Claude Code:

```text
/plugin marketplace add 0Smallcat0/report-workflow
```

Then `/plugin install report-workflow@report-workflow`. Any other MCP-capable
agent (Codex, Cursor, your own harness) takes one command instead:

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

Then ask, in your own words:

> Use report-workflow to turn the files in ./data into a business report for the
> operations manager: what changed, what it costs, whether to adopt it.

Seven document types — lab report, academic paper, business report, proposal,
two admissions formats, and a general one. The analysis a grader looks for (a
fitted slope against theory, R², a budget total) is computed from your data and
registered as citable evidence, so your agent never has to invent it. Profiles,
Chinese documents, and your own Word template: **[docs/OUTPUT.md](docs/OUTPUT.md)**.

## What it will not do

It has no semantics. It catches invented numbers, fabricated citations,
misquotes and unit swaps; a fluent paraphrase that reverses your source will get
through. That boundary is measured, not asserted — 69 hand-audited adversarial
cases and 10,000 external HaluEval pairs, with the misses kept in the corpus on
purpose: **[docs/EVIDENCE.md](docs/EVIDENCE.md)**.

It also does not write. Your agent does that; this decides what may ship.

## Other ways to run it

The gate on its own, no pipeline and no schema — two plain arguments, the same
verdict every run, usable in CI:

```python
from report_workflow import verify

verify("The error rate fell to 0.2% [1].",
       {"1": "The error rate fell to 3.5% under the structured workflow."})
# publishable: False — FE: claim number '0.2'% not found in evidence content
```

`pip install "report-workflow[render]"` gets the CLI and the renderer (pandoc
ships in the wheel; without it the fallback loses real tables and your
template). `pip install` ships the package, not the examples — clone for those
and the benchmarks. Runnable with no local install:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/0Smallcat0/report-workflow/blob/master/docs/quickstart_demo.ipynb)

If `report-workflow` fails silently — common on Windows when a stale
`report-workflow.exe` sits on PATH — use `python -m report_workflow`.

## Where to go next

- **Output, profiles, templates, gates** → [docs/OUTPUT.md](docs/OUTPUT.md)
- **Measured catch rates and honest limits** → [docs/EVIDENCE.md](docs/EVIDENCE.md)
- **Why it is built this way, threat model** → [docs/DESIGN.md](docs/DESIGN.md)
- **The MCP tools and their payloads** → [docs/mcp.md](docs/mcp.md)
- **Driving it from an agent** → [skills/report-workflow/SKILL.md](skills/report-workflow/SKILL.md)
- **Developing this repository** → [AGENTS.md](AGENTS.md)
- **Reporting a bug, and what is in scope** → [CONTRIBUTING.md](CONTRIBUTING.md)

Specified, integrated, and verified by its author, with coding agents doing much
of the implementation — the deterministic gates and the benchmark harness exist
so a human, not a model, holds the final "is this correct?" decision.
