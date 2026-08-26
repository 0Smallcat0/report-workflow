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
![Tests](https://img.shields.io/badge/tests-1081%20passing-brightgreen)
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
- **[`examples/README.md`](examples/README.md)** — the same run start to
  finish: the three input files, the one command, and the delivered document
  with its QA artifacts

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

## Does it actually help?

That is the question worth asking about a writing tool, and for a while the
honest answer here was no. Someone ran a real 16 KB Chinese market report
through the whole pipeline and compared the delivered document against the one
they had written by hand: 37 source links became 0, 24 rows of tables became 0,
and every citation marker was deleted at render. The gates worked. The document
was worse.

Worse still, the strictest gate had a **100% false-positive rate on Chinese**.
It bound each number to the characters following it, and Chinese has no spaces,
so a claim passed only if it repeated the source's exact character sequence —
one particle (的) was enough to block a true statement. The gate was rewarding
transcription and punishing the synthesis a report exists to do.

Those findings are what the current version was built from. The fixes are in the
history; the evidence they worked is checked in:

| | Before | After |
| --- | ---: | ---: |
| Correct Chinese claims blocked by the FE gate | 3 of 3 | 0 of 3 |
| Hallucination catch rate (73 adversarial cases) | 86.4% | **89.1%** |
| Honest claims wrongly blocked | 0% | 0% |
| Source tables reaching the delivered document | 0 of 4 | **4 of 4** |
| Sources the document cites, reaching the bibliography | 0 of 6 | **6 of 6** |
| Chart recommendations dropped without a word | 3 of 4 | **0** |

The comparison against writing without the tool is a benchmark you can rerun:

```bash
python scripts/run_report_quality_benchmark.py --check
```

Same source, same prompt, two arms, one scorer, both arms in the repository.
The harness wins 6 of 8 dimensions. **It loses 2, and those are reported rather
than tuned away** — one of them because the metric itself rewards vagueness,
which is worth knowing about the metric. See
[the summary](benchmarks/evidence/report_quality_2026-08-06/summary.md).

### The harder comparison: against a person, and against an AI

That benchmark has two arms. The one that answers "is it better than a person,
and better than an AI writing the report directly" has three, and it is a lot
less flattering:

```bash
python scripts/run_drone_market_benchmark.py --check
```

Three CSVs and one market question. Three recorded documents — a hand-written
control, this pipeline's delivered output, and the strongest of four drafts by
an AI given the same files. Three axes: counted (numeric), rule-scored
(layout), and judged against a fixed rubric by three independent blind judges
who are told nothing about how any arm was produced (argument). Every number
below is from
[`benchmarks/evidence/drone_market_2026-08-14/`](benchmarks/evidence/drone_market_2026-08-14/summary.md).
Check the date: the next re-recording moves these, and two checkers landed
after this round that will change what the tool arm contains.

**Read this before the table.** The stop condition is met — the tool arm wins
every axis against the AI-direct arm and loses at most one to the hand-written
control — and **one number decides it, in a document that did not change.**
The AI-direct arm is frozen; it is byte-identical to the round that scored it
4/4/4 on the argument axis, and this panel scored it 4/3/3. Had this panel
returned 4/4/4 again, the tool arm would have been 0–1 on that axis, the axis
would not be won, and the stop condition would not be met. Both of the
AI-direct arm's deductions are earned — three judges independently found an
arithmetic error in its headline figure and a contaminated population under its
strongest counter-evidence — but the same defects were present in the previous
round and that panel did not find them. **So the round-to-round variation
between judging panels is at least one point per dimension, and this round's
winning margin is one point.**

**These scores are this task's ceiling, not a general result.** The tool arm is
the only arm that moves, and this round it was written a *second* time against
the same task, the same three CSVs and the same rubric, by an author holding
the previous round's itemised deductions from three blind judges. Scores rising
under those conditions is close to guaranteed, and this round's design cannot
separate how much of the rise is the pipeline getting better from how much is a
second attempt at one exam.

**This archive has no held-out task** — no second question with new sources and
no prior judging to write against. Building one means commissioning a second
hand-written control and a second AI-direct arm, which is the expensive half of
this benchmark. That is the largest known limitation of these numbers.

| Axis | vs the hand-written control | vs the AI writing directly |
| --- | --- | --- |
| numeric — counted properties of the document | 4–2 won | 4–2 won |
| layout — rule-scored structure and table furniture | 5–1 won | 4–2 won |
| argument — three blind judges against a fixed rubric | **0–1 lost** | 2–1 won |

Argument axis, median of three votes per dimension
(`claim_strength`/`evidence_depth`/`counter_specificity`): hand **4/4/4**,
tool **3/4/4**, AI-direct **4/3/3**. The tool arm still trails a person on
`claim_strength`, and the archive records the defect all three judges found in
it. Every vote, with the passage behind it and a record of who cast it, is in
[`argument_votes.json`](benchmarks/evidence/drone_market_2026-08-14/argument_votes.json).

The layout axis was extended in this same round, by the author of the arm being
measured, after reading all three documents — two of its three new dimensions
are properties the renderer produces by construction and neither hand-written
arm produces at all. That is declared in
[the summary](benchmarks/evidence/drone_market_2026-08-14/summary.md), and it is
a reason to discount that axis rather than a footnote to it.

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
