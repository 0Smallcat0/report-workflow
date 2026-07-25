# Report Workflow

[![CI](https://github.com/0Smallcat0/report-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/0Smallcat0/report-workflow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-463%20passing-brightgreen)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Turns your source material into a finished report — and refuses to ship a
single claim it cannot trace back to that material.**

Getting the document *graded well* is the job: a lab report a professor marks
highly, a status report a manager can act on in half a page, an application a
committee remembers. Report Workflow drives the whole route — it parses your
sources, tells the writing agent what that document's reader actually rewards,
computes the analysis a grader looks for, and renders a submission-ready DOCX
with a table of contents, page numbers, real Word tables, and your department's
own template, in English or Chinese.

Traceability is the floor, not the pitch. Every publishable sentence has to link
to registered evidence, so the document that comes out carries no invented
numbers, no fabricated citations, and no misquotes — the price of entry for
anything you put your name on, not the reason to use it.

The Python package **does not call an LLM and needs no API key.** It owns source
parsing, the evidence ledger, artifact contracts, validation gates, DOCX
rendering, and traceability packaging. The external agent (Codex, Claude Code,
Hermes, …) owns judgment and drafting.

```bash
pip install report-workflow
```

That is everything except DOCX rendering, which needs pandoc — see
[Install](#install).

## What a graded document reads like

The discussion section of a cantilever-beam lab report, rendered by the pipeline
from a course handout and a five-row measurement CSV:

> Fitting the measurements puts a number on how closely they track the model. A
> least-squares fit of measured deflection against load gives a slope of 0.298
> with R² = 0.9999, against the theoretical slope of 0.29. [1] Across the five
> steps the error ranges from 2.6 to 4.8 with a mean of 3.5. [1] The coefficient
> of determination is high enough that the linear assumption is not in question,
> and the excess slope is consistent across the range — the deviation is
> systematic, not scatter.
>
> Two features of the apparatus explain a systematic excess of this kind. The
> model assumes a perfectly rigid fixed end, whereas the clamp has finite
> stiffness and rotates slightly under load. The dial indicator also rests
> against the beam with a small contact force. Both add deflection the
> rigid-clamp model does not account for, and both act at every load — which is
> why the offset appears at all five steps rather than at isolated points.

The slope and R² are not the agent's own arithmetic: the pipeline computed them
from the CSV and registered them as evidence, so the quantitative analysis a
grader looks for is citable instead of unsupported. Each paragraph opens with
its point and closes with the takeaway, and the discussion runs result →
quantitative comparison → mechanism → verdict — the shape university lab rubrics
grade against.

## How it aims at "good", not just "not wrong"

Passing the gates means a document is not *wrong*. Three mechanisms aim it at a
document its reader rates highly. All three are guidance, not gates:

- **Reader rubrics.** Each profile's authoring brief states what its reader
  rewards: quantified comparison over description for a lab professor,
  conclusion-first for a manager, concrete incidents over adjectives for an
  admissions committee, one plainly stated contribution for a reviewer.
- **Structure discipline**, distilled from published standards — every paragraph
  Context → Content → Conclusion ([Kording & Mensh, *PLOS Comput Biol* 2017](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005619));
  figures carrying the results and prose explaining them ([Whitesides, *Adv.
  Mater.* 2004](https://www.gmwgroup.harvard.edu/publications/whitesides-group-writing-paper));
  answer-first with an SCQA opening for business writing (Minto's Pyramid
  Principle); depth on a few defining experiences for admissions documents
  ([MIT CommLab](https://mitcommlab.mit.edu/eecs/commkit/graduate-school-statement-of-purpose/),
  [Cornell](https://gradschool.cornell.edu/inclusion/recruitment/prospective-students/writing-your-statement-of-purpose/)).
- **Derived statistics as citable evidence.** Least-squares slope against the
  theoretical slope, R², and the error range and mean are computed from
  structured measurement data and registered as ledger entries — because a
  number the agent worked out by itself has nothing to cite, and is exactly what
  the factuality gates block.

## Verify any LLM answer in five lines

**Scope, stated plainly.** The gate is a *fidelity gate* for evidence-backed
writing, not a general hallucination detector. Because the checks are
mechanical, they reliably catch invented numbers, fabricated citations,
misquotes, and unit swaps — but they do not judge meaning, so a fluent
paraphrase that quietly reverses the source ("A before B" → "B before A") is
out of scope. That boundary is not hidden; it is measured on outside data
below (§[out-of-domain](#out-of-domain-halueval-qa-10000-pairs-nobody-here-wrote)).

The same gate stack runs standalone. No pipeline, no schema, no API key — pass
the answer and the source text it was supposed to be grounded in:

```python
from report_workflow import verify

result = verify(
    answer="The error rate fell to 0.2% [1].",
    sources={"1": "The error rate fell to 3.5% under the structured workflow."},
)
result["publishable"]                      # False
result["sentence_results"][0]["checker"]   # "FE"
result["sentence_results"][0]["reason"]    # "Claim number '0.2'% not found in evidence content (evidence has: 3.5%)..."
```

`verify()` splits the answer into sentences (English and CJK), scopes each one
to the sources its `[id]` markers cite (a marker that matches no source is a
fabricated citation and blocks), tests unmarked sentences against every source
and passes them when any single source fully grounds them, and fails closed on
everything else. Same deterministic gate stack as the full pipeline and the
MCP server: a pure function of `(answer, sources)` — same verdict every run,
zero tokens, works offline and in CI.

## See it in 30 seconds

The gate is real code, not a description. This demo runs the exact factuality
checkers the pipeline uses against a tiny evidence ledger — no LLM, no network:

```bash
python examples/anti_hallucination_gate.py
```

![Anti-hallucination gate demo — an honest draft passes every check; a hallucinated draft with an invented statistic and a fabricated citation is each hard-blocked, tagged with the gate that caught it.](docs/demo.svg)

Two failure modes an LLM ships silently — an **invented statistic** that cites
real evidence, and a **fabricated citation** to a source that does not exist —
are both caught with the specific gate and reason that stopped them. The honest,
well-grounded claim passes untouched, so the gate is discriminating, not merely
strict. Source: [`examples/anti_hallucination_gate.py`](examples/anti_hallucination_gate.py).

No local install needed:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/0Smallcat0/report-workflow/blob/master/docs/quickstart_demo.ipynb)
runs the gate in the browser, or open the repo in GitHub Codespaces (the
[dev container](.devcontainer/devcontainer.json) installs everything and runs
the demo on create).

## Red-team evidence: the catch rate is measured, not asserted

A gate that only sees honest drafts proves nothing. The adversarial benchmark
runs **58 hand-audited cases** — 20 honest controls and 38 hallucinated claims
across 13 attack families (fabricated citations, invented statistics, unit
swaps, fabricated quotes, precision inflation, cross-language laundering,
off-topic citations, status laundering, Chinese-text fabrication,
overclaiming, …) — through the exact gate stack, and compares two baselines on
the same corpus:

| Checker | Recall (hallucinations blocked) | False positives (honest blocked) | Precision |
| --- | --- | --- | --- |
| No gate (publish everything) | 0.0% | 0.0% | — |
| Citation-presence check (shallow RAG-style) | 10.5% | 0.0% | 100% |
| **Full deterministic gate stack** | **89.5%** (34/38) | **0.0%** (0/20) | **100%** |

All 13 targeted attack families are caught at 100%, with zero honest claims
wrongly blocked. The 2026-07-14 gate hardening closed three formerly documented
evasions (within-tolerance precision fudging, sub-10-character fabricated
quotes, cross-language citation laundering) and promoted them to regular attack
families. The remaining 4 misses are **documented evasions** (negation flips,
bare numbers without units, hedged reinterpretation, value misattribution) kept
in the corpus deliberately as the measured residual-risk boundary — see the
limitations section of [`docs/DESIGN.md`](docs/DESIGN.md). The corpus doubles
as a regression suite: expected verdicts are asserted in CI, and a sha256
verdict hash proves the stack is deterministic and reproduces cross-platform.

```bash
python scripts/run_adversarial_benchmark.py --check   # re-run from source, diff vs archive
```

Full tables: [`benchmarks/evidence/adversarial_2026-07-14/summary.md`](benchmarks/evidence/adversarial_2026-07-14/summary.md).

### Out-of-domain: HaluEval QA, 10,000 pairs nobody here wrote

The corpus above was authored for this project. To measure behavior on data
nobody here controls, `verify()` runs over the public
[HaluEval](https://github.com/RUCAIBox/HaluEval) QA benchmark (Li et al.,
EMNLP 2023): 10,000 knowledge-grounded pairs, each with one right and one
hallucinated answer — 20,000 verdicts, zero tokens.

| Metric | Value |
| --- | --- |
| False-positive rate (right answers blocked) | **0.06%** (6/10,000) |
| Precision of a block verdict | **99.7%** |
| Recall — all hallucinations | 23.2% (2,320/10,000) |
| Recall — numeric subset (answers carrying a number+unit) | 66.7% |

Read it honestly: HaluEval hallucinations are open-domain *entity swaps*
engineered to reuse the passage's own vocabulary — the class
[`docs/DESIGN.md`](docs/DESIGN.md) explicitly places outside deterministic
lexical checking. The out-of-domain claim is the **discipline**, not the
recall: the gates almost never cry wolf (all six false positives are
characterized in the archive — film titles and street addresses whose leading
numeral parses as a measurement), and every block they issue is near-certain
to be a real hallucination. A linter does not catch every bug; it must not
lie about the ones it flags.

```bash
python scripts/run_external_benchmark.py --download   # fetch + sha256-verify the dataset (6 MB)
python scripts/run_external_benchmark.py --check      # recompute all 20,000 verdicts, diff vs archive
```

Full analysis: [`benchmarks/evidence/halueval_qa_2026-07-15/summary.md`](benchmarks/evidence/halueval_qa_2026-07-15/summary.md).

## How it relates to LLM-as-judge tools

This is **not** a competitor to RAGAS, TruLens, DeepEval, or Guardrails — it
does a different, narrower job. Those tools ask a model (an LLM or a trained
classifier) *"is this output grounded?"* and get a semantic opinion: they can
judge paraphrase and meaning, at the cost of an API key or GPU, per-call
latency, and verdicts that can change between runs. This project does no
judging at all. It mechanically checks one thing — **do the numbers,
citations, and quotes in the text actually appear in the source?** — as a pure
function, so the answer is the same every run and you can see exactly why a
sentence was blocked.

|  | LLM-as-judge tools | this fidelity gate |
| --- | --- | --- |
| Question it answers | "is this grounded / faithful?" (semantic) | "do the numbers/citations/quotes match the source?" (mechanical) |
| Verdict source | model opinion (prompted or trained) | pure function of (claim, evidence) |
| Same input → same verdict | not guaranteed | guaranteed, sha256-proven in CI |
| Offline / no API key / no GPU | usually no | always |
| Cost & latency per 10,000 checks | per-call LLM pricing, seconds each | zero tokens, milliseconds each |
| Catches paraphrase / entity-swap meaning | yes — that is what they are for | no — needs semantics it does not have |
| Catches invented numbers, fabricated citations, misquotes, unit swaps | depends on the prompt | deterministically, with the reason |

They are complementary, and the honest way to use both is to run this cheap
deterministic check first and spend judge calls only on what passes. It is a
floor, not a replacement for semantic judgement.

## Who is this for

- **Anyone who has to hand in a document that gets judged.** Lab reports,
  research proposals, journal manuscripts, status and business reports,
  admissions documents, technical documentation — seven built-in profiles, each
  carrying its reader's rubric, rendered as a submission-ready DOCX in English
  or Chinese, optionally following a template you supply.
- **RAG / agent pipelines that need a CI gate.** `verify(answer, sources)`
  in a test means a grounding regression fails the build — like a linter,
  with no eval budget and no flaky judge. The MCP server gives any agent the
  same gate at runtime before output reaches a user.
- **Evidence-bounded documents.** Where every claim must trace to a registered
  source — financial memos, regulatory drafts — the pipeline renders auditable
  DOCX with a QA pack that can prove, per sentence, why it was allowed to ship.
- **Anyone who must explain a publish decision later.** Verdicts are pure
  functions: cacheable, diffable, re-testable after an edit, and the block
  reason names the gate and the evidence. "The model felt it was grounded"
  is not an audit trail; this is.

**Who it is not for:** open-domain chat where hallucinations are fluent
paraphrases sharing the source's vocabulary — that is semantic entailment
territory (the documented evasions), where an NLI model or LLM judge earns
its cost. Use both layers; this one is the cheap, honest floor.

## Evidence it runs end-to-end

The seven-profile benchmark prepares, authors (with a deterministic synthetic
author), validates, and renders a report for every built-in profile from one
controlled source. The archived run is reproducible and machine-checkable:

```bash
python scripts/run_report_benchmarks.py --check   # validate archived evidence
python scripts/run_report_benchmarks.py           # regenerate from scratch
```

Archived results ([`benchmarks/evidence/full_benchmark_2026-05-13/summary.md`](benchmarks/evidence/full_benchmark_2026-05-13/summary.md)):

| Metric | Result |
| --- | --- |
| Profiles passing end-to-end | **7 / 7** |
| Claims verified against evidence | **42** (6 per profile), **0 blocked** |
| Unresolved citation-audit entries | **0** |
| Delivery QA decision | `pass` on every profile |
| Unit tests at the time of the archived run | **351 passing** (463 today) |

Each report is packaged with its QA pack (`final_qa_summary`, factuality,
scholarly-quality, figure-visual, template-style, and render-layout reports) so
the publish decision is auditable after the fact, not just asserted.

Pages from a rendered engineering lab report produced by that benchmark — table of
contents, title and abstract, and a figure derived from the source data:

![Three pages of a pipeline-rendered DOCX report: a title-and-abstract page, a table of contents, and a page with a line chart derived from the source data with a self-contained caption.](docs/sample_report.png)

## How it works

```mermaid
flowchart LR
    SRC[Sources<br/>text - csv - pdf - docx] --> PREP

    subgraph PREP[1 - Prepare - deterministic]
        EV[Evidence ledger]
        TB[Agent task briefs]
    end

    PREP --> AUTH

    subgraph AUTH[2 - Author - external LLM agent]
        CM[claim_matrix]
        DR[section drafts +<br/>sentence_map]
    end

    AUTH --> VAL

    subgraph VAL[3 - Validate and Render - deterministic gates]
        G1[Citation linkage]
        G2[Factuality FA FB FE FD]
        G3[Profile + QA gates]
    end

    VAL -->|qa_decision = pass| PUB[Published DOCX<br/>+ traceability pack]
    VAL -->|claim not grounded| BLK[Hard block]
```

1. **Prepare** parses sources and writes deterministic artifacts
   (`report_spec.json`, `report_profile.json`, `blueprint.json`,
   `source_registry.json`, `evidence_ledger.jsonl`, and `agent_tasks/*.md`).
2. **Author** — the external agent writes `claim_matrix.json`, `outline.json`,
   `section_drafts/*.md` (or `structured_drafts.json`), and `sentence_map.jsonl`.
3. **Validate and render** checks artifact completeness, section contracts,
   citation linkage, factuality, profile policy, figure contracts, and QA gates,
   then renders. `render` runs only after the validated checkpoint records
   `qa_decision=pass`, a passing `qa_summary.json`, a clean
   `factuality_report.json`, and no unresolved citation audit entries.

The factuality gate is layered: **FA** confirms claim/evidence/sentence linkage
and rejects fabricated citations; **FB** requires quantitative evidence for
statistical claims; **FE** (deep-audit) compares claim content against evidence
content and catches invented numbers and quoted phrases that are not in the
source; **FD** checks wording strength against evidence grade. See
[`src/report_workflow/nodes/factuality_check.py`](src/report_workflow/nodes/factuality_check.py).

## Install

The verification gates (`verify()`, the factuality checkers, the MCP server)
need only the package — no external tools:

```bash
pip install report-workflow
```

Releases are published to PyPI through GitHub trusted publishing (OIDC, no
tokens); see [`docs/RELEASING.md`](docs/RELEASING.md).

For the full source-to-DOCX pipeline, install from a clone and add pandoc:

```powershell
pip install -r requirements.txt
pip install -e .
```

If the `report-workflow` command fails silently (common on Windows when
several Python installs leave a stale `report-workflow.exe` on PATH), use the
PATH-independent form — it always runs against the interpreter you invoke:

```bash
python -m report_workflow prepare --help
```

Required external tool for full-fidelity rendering:

```powershell
pandoc --version
```

Pandoc 3.x is the primary DOCX renderer. Without pandoc, the workflow falls back
to a limited `python-docx` renderer and output may have degraded table, list, and
layout fidelity.

Optional integrations:

- `mmdc` (`npm install -g @mermaid-js/mermaid-cli`) for Mermaid diagrams.
- `TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY` for optional web research.
- `notebooklm-py` for optional NotebookLM sync.
- `pip install -e .[mcp]` for the MCP server (`report-workflow-mcp`).

## CLI

```powershell
report-workflow prepare `
  --prompt "write an engineering lab report from these sources" `
  --source C:\path\to\source.txt `
  --output C:\path\to\out `
  --profile engineering_lab_report `
  --preflight-decisions C:\path\to\preflight_decisions.json `
  --template-field course_name="Control Systems"

report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id>
```

`prepare` requires a `--preflight-decisions` JSON record confirming the user's
install, degraded-render, and optional-feature decisions. Required dependencies
must actually pass preflight before start; a decision string alone does not
override a still-missing dependency. This mirrors the agent-skill
`preflight_decisions` contract instead of silently starting from the raw CLI.

`--source PATH:ROLE` may be repeated. Valid roles are `source_data` and
`base_document`. The role suffix is parsed only when the trailing token exactly
matches a valid role, so Windows paths such as `C:\path\to.txt` are safe.

CLI exit codes:

- `0`: success
- `1`: crash
- `2`: hard-block validation failure
- `3`: waiting for user decisions or agent-authored artifacts

## MCP server

Any MCP-capable agent (Claude Code, Codex, Cursor, custom harnesses) can call
the same deterministic gates as tools — draft with its own judgment, then ask
`verify_claims` whether each claim is allowed to ship:

```bash
pip install "report-workflow[mcp] @ git+https://github.com/0Smallcat0/report-workflow"
claude mcp add report-workflow -- report-workflow-mcp
```

Tools: `verify_claims` (per-claim verdict with the gate and reason),
`list_report_profiles`, `get_workflow_status`. Details and payload examples:
[`docs/mcp.md`](docs/mcp.md).

## Report profiles

`report_profile` is the only public report-shape selector. Built-in profiles:
`engineering_lab_report`, `academic_paper`, `business_report`, `proposal`,
`admissions_report`, `admissions_project_report`, and `custom`. The pipeline
infers a profile from the prompt unless `--profile` or `report_profile` is given.

Profile purposes and strictness are documented in
`agent_skill/reference/profiles.md`; the registry lives in
`src/report_workflow/profiles.py`.

### Chinese documents

Document language is detected deterministically from the source evidence.
Chinese-dominant sources produce a fully Chinese deliverable: every blueprint
section carries a `title_zh`, so headings render as 「1. 執行摘要 … 參考文獻」
instead of leaking English defaults; the abstract word gate counts CJK
characters; figure references (「如圖 1」) and Chinese ordinal headings
(「一、」「（三）」) are recognized by the quality gates. English documents are
byte-for-byte unchanged. Each built-in profile has been exercised end-to-end
with a Chinese document (lab report, research proposal revision, work report,
business proposal, admissions report, and technical document) plus an English
journal paper.

## Reference templates

Bring your own formatting: pass `--reference-docx your.docx` on `prepare`,
`render`, or `run` (agent tools accept `reference_docx`) and the output
follows that document's styles — fonts, sizes, margins, header/footer
(including its page-number setup), and table styles. Section structure still
comes from the report profile, every content gate still applies, and an
unusable template hard-blocks the render instead of silently falling back to
the built-in look.

Profiles control reference-template behavior. The default mode is
`style_reference` (use a DOCX as a style/layout reference); if the user asks to
exactly preserve the cover or format, the workflow upgrades to `fixed_template`.
A profile contract has priority over prompt and template hints. Engineering
exact-cover handling is detailed in `agent_skill/reference/engineering-lab.md`.

## Quality gates

Core hard gates: sources must register and parse; the evidence ledger must be
non-empty; claims must cite valid evidence IDs; claim status cannot be `blocked`,
`unverified`, or `disputed`; evidence-backed sentences must contain matching
`[CITE:<id>]` placeholders; citation audits must resolve; placeholder prose and
fake metadata are blocked; and render requires `qa_decision=pass`. Profile
policies adjust strictness for front matter, abstract structure, citation style,
reference verification, and figure/table contracts. The authoritative gate list
lives in [AGENTS.md](AGENTS.md).

## Benchmarks

Use `benchmarks/` when improving report quality across profiles. Run
`python scripts/run_report_benchmarks.py` for the seven-profile
prepare-author-validate-render benchmark, or
`python scripts/run_report_benchmarks.py --check` to validate archived evidence
without rerunning. `python scripts/run_adversarial_benchmark.py` regenerates
the adversarial catch-rate evidence (`--check` verifies it from source). The
benchmark-first optimization method and gap taxonomy are documented in
`agent_skill/reference/benchmarking.md`.

## Tests

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

## Design philosophy

Report Workflow is one instance of a general idea: **evidence-bounded
generation.** Wherever a claim must trace to a source — an engineering lab
report, a financial memo where every number cites a filing, a regulatory
document, an admissions essay grounded in a real project — the trustworthy part
is not the fluent draft but the layer that can *prove* each statement and refuse
the ones it cannot. Keeping that layer deterministic (no LLM in the checker)
makes the verdict reproducible and auditable rather than another probabilistic
opinion.

That layer is the floor, and a floor is not a destination. A document that
merely refuses to lie is not yet a document worth handing in, so the same
deterministic machinery is used to raise the ceiling: it puts the reader's
grading criteria in front of the writer before drafting, and it computes the
quantitative analysis a grader expects — a fitted slope against theory, a
coefficient of determination — and registers it as evidence, because analysis
nobody can cite is analysis the gates would have to block.

This repository was specified, integrated, and verified by its author with heavy
use of coding agents for implementation. The deterministic gates and the
benchmark harness exist precisely so that the human, not the model, holds the
final "is this correct?" decision — the same principle the tool enforces on the
documents it produces.

## Repository guide

- **Why it is built this way + measured limits** → [`docs/DESIGN.md`](docs/DESIGN.md)
  (threat model, architecture rationale, evaluation, honest limitations).
- **Operating the skill to generate a report** → [`agent_skill/SKILL.md`](agent_skill/SKILL.md)
  and its `reference/` files.
- **Developing this repository** → [AGENTS.md](AGENTS.md) (authoritative contract:
  layout, stage lists, artifact contract, hard gates, extension points).
- **Contributor entry point** → [AGENT_ONBOARDING.md](AGENT_ONBOARDING.md).

Final artifacts are packaged under `output/<slug>--<job_id>/published/`, with
delivery QA in `published/qa/`. See [AGENTS.md](AGENTS.md) for the canonical stage
lists and the full QA artifact contract.
