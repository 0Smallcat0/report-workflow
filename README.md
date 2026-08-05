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

**Give your AI the files you already have and one sentence about what you need.
Get back a Word document you can hand in.**

If the AI writes a number that is not in your files, that number does not reach
the document. Same for a quote it reworded, or a paper it cited that does not
exist. It gets stopped, and you are told which sentence and why.

**You bring**: a spreadsheet of measurements, a Word handout, a page of notes —
whatever you already have. Plus one sentence, like "write a lab report on this".

**You get**: a `.docx` with a table of contents, page numbers, real Word tables,
and charts drawn from your own numbers. It can follow your department's or your
company's template. Chinese or English.

Two lines to install. No API key. Nothing to configure.

## Look before you install

Here is a document it made, and the note that comes with it. Both are in this
repository, so you can see the output before you run anything:

- **[`examples/output/report.docx`](examples/output/report.docx)** — the file
  you would hand in: contents page, page numbers, a real Word table, a chart
  drawn from the source spreadsheet
- **[`examples/output/client_readable_qa_note.md`](examples/output/client_readable_qa_note.md)**
  — every sentence that made a factual point, and the row of your data it came
  from

![Three pages of a pipeline-rendered DOCX report: a title-and-abstract page, a table of contents, and a page with a line chart derived from the source data with a self-contained caption.](docs/sample_report.png)

## Use it

In Claude Code:

```text
/plugin marketplace add 0Smallcat0/report-workflow
```

Then `/plugin install report-workflow@report-workflow`. Using something else
that speaks MCP (Codex, Cursor, your own setup)? One command instead:

```bash
claude mcp add report-workflow -- uvx --from "report-workflow[mcp,render]" report-workflow-mcp
```

Then just ask, in your own words:

> Use report-workflow to turn the files in ./data into a business report for the
> operations manager: what changed, what it costs, whether to adopt it.

Seven kinds of document: lab report, academic paper, business report, proposal,
two admissions formats, and a general one. **The maths a marker looks for — how
close your measurements came to theory, an R², a budget total — is worked out by
the tool from your own data**, so the AI never has to make a number up. Formats,
Chinese documents, and using your own Word template:
**[docs/OUTPUT.md](docs/OUTPUT.md)**.

## What it cannot do

**It cannot read meaning.** It checks whether the numbers, quotes and references
in the text really appear in your files. It cannot tell whether the AI
understood your data. If the AI writes a smooth sentence that gets your result
backwards, that sentence goes through.

We measured that limit instead of talking around it: 69 hand-checked attempts to
sneak something false past it, plus 10,000 test pairs from a public dataset
nobody here wrote. **The cases it still misses are kept in the test set on
purpose** — [docs/EVIDENCE.md](docs/EVIDENCE.md).

**It does not write.** Your AI writes; this decides what stays. So you need an
AI agent to use it.

## Other ways to run it

Just the checker, on any two pieces of text — no setup, same answer every time,
fine to put in a test suite:

```python
from report_workflow import verify

verify("The error rate fell to 0.2% [1].",
       {"1": "The error rate fell to 3.5% under the structured workflow."})
# publishable: False — 0.2% is nowhere in the source; the source says 3.5%
```

`pip install "report-workflow[render]"` gets you the command-line version and
the Word renderer (it comes with the wheel; without it, tables and templates
come out worse). `pip install` ships the package, not the examples — clone the
repository for those and the test data. Or try it with nothing installed:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/0Smallcat0/report-workflow/blob/master/docs/quickstart_demo.ipynb)

If the `report-workflow` command does nothing — usually an old
`report-workflow.exe` left on your PATH on Windows — run
`python -m report_workflow` instead.

## Where to go next

- **What comes out, formats, templates, checks** → [docs/OUTPUT.md](docs/OUTPUT.md)
- **What it catches, and what it misses** → [docs/EVIDENCE.md](docs/EVIDENCE.md)
- **Why it is built this way** → [docs/DESIGN.md](docs/DESIGN.md)
- **The MCP tools** → [docs/mcp.md](docs/mcp.md)
- **Driving it from an agent** → [skills/report-workflow/SKILL.md](skills/report-workflow/SKILL.md)
- **Working on this repository** → [AGENTS.md](AGENTS.md)
- **Reporting a bug** → [CONTRIBUTING.md](CONTRIBUTING.md)

I wrote the spec, put the pieces together, and checked the results; coding
agents wrote most of the code. The checks and the test set exist so that a
person, not a model, decides whether the answer is right.
