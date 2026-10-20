# Measured evidence

Every number here is reproducible from this repository. Commands re-run the
measurement from source and diff against the archived result.

## Does the harness produce a better report?

```bash
python scripts/run_report_quality_benchmark.py --check
```

The catch rate below says the gates block fabrication. It does not say the
deliverable is any good, and for a while it was not: a real run of a 16 KB
Chinese market report produced a document with none of its source's 37 links,
none of its 24 table rows, and no citation markers at all — the gates passed
and the document was worse than the hand-written original.

The report-quality benchmark measures that directly. Same source, same prompt,
two arms — a live pipeline run, and a recorded write-up produced without the
harness — scored by one implementation across eight dimensions. The harness
wins six: external sources, checkable figures, tables, figures,
counter-evidence, and disclosed derivations. It loses two, kept in the archive
with an explanation rather than tuned out; one of them,
`verifiable_number_ratio`, rewards a document for stating nothing checkable,
and that is a fact about the metric worth recording.

Both arms and the scorer are in the repository, so the result can be argued
with:
[`benchmarks/evidence/report_quality_2026-08-06/summary.md`](../benchmarks/evidence/report_quality_2026-08-06/summary.md).

## Red-team: the catch rate is measured, not asserted

A gate that only sees honest drafts proves nothing. The adversarial benchmark
runs **73 hand-audited cases** — 27 honest controls and 46 hallucinated claims
across 14 attack families (fabricated citations, invented statistics, unit
swaps, fabricated quotes, precision inflation, cross-language laundering,
off-topic citations, status laundering, Chinese-text fabrication,
overclaiming, …) — through the exact gate stack, and compares two baselines on
the same corpus:

| Checker | Recall (hallucinations blocked) | False positives (honest blocked) | Precision |
| --- | --- | --- | --- |
| No gate (publish everything) | 0.0% | 0.0% | — |
| Citation-presence check (shallow RAG-style) | 9.1% (4/44) | 0.0% | 100% |
| **Full deterministic gate stack** | **89.1%** (41/46) | **0.0%** (0/27) | **100%** |

All 15 targeted attack families are caught at 100%, with zero honest claims
wrongly blocked. The 2026-07-14 gate hardening closed three formerly documented
evasions (within-tolerance precision fudging, sub-10-character fabricated
quotes, cross-language citation laundering) and the 2026-08 CJK tokenisation fix
closed a fourth (invented bare quantities); all were promoted to regular attack
families. The remaining 5 misses are **documented evasions** (negation flips,
hedged reinterpretation, value misattribution) kept
in the corpus deliberately as the measured residual-risk boundary — see the
limitations section of [`DESIGN.md`](DESIGN.md). The corpus doubles as a
regression suite: expected verdicts are asserted in CI, and a sha256 verdict
hash proves the stack is deterministic and reproduces cross-platform.

```bash
python scripts/run_adversarial_benchmark.py --check   # re-run from source, diff vs archive
```

Full tables: [`benchmarks/evidence/adversarial_2026-07-14/summary.md`](../benchmarks/evidence/adversarial_2026-07-14/summary.md).

## Out-of-domain: HaluEval QA, 10,000 pairs nobody here wrote

The corpus above was authored for this project. To measure behavior on data
nobody here controls, `verify()` runs over the public
[HaluEval](https://github.com/RUCAIBox/HaluEval) QA benchmark (Li et al.,
EMNLP 2023): 10,000 knowledge-grounded pairs, each with one right and one
hallucinated answer — 20,000 verdicts, zero tokens.

| Metric | Value |
| --- | --- |
| False-positive rate (right answers blocked) | **0.11%** (11/10,000) |
| Precision of a block verdict | **99.6%** |
| Recall — all hallucinations | 25.6% (2,557/10,000) |
| Recall — numeric subset (answers carrying a number+unit) | 39.8% |

Read it honestly: HaluEval hallucinations are open-domain *entity swaps*
engineered to reuse the passage's own vocabulary — the class
[`DESIGN.md`](DESIGN.md) explicitly places outside deterministic lexical
checking. The out-of-domain claim is the **discipline**, not the recall: the
gates almost never cry wolf (all eleven false positives are characterized in the
archive — film titles and street addresses whose leading numeral parses as a
measurement), and every block they issue is near-certain to be a real
hallucination. A linter does not catch every bug; it must not lie about the
ones it flags.

```bash
python scripts/run_external_benchmark.py --download   # fetch + sha256-verify the dataset (6 MB)
python scripts/run_external_benchmark.py --check      # recompute all 20,000 verdicts, diff vs archive
```

Full analysis: [`benchmarks/evidence/halueval_qa_2026-07-15/summary.md`](../benchmarks/evidence/halueval_qa_2026-07-15/summary.md).

## End-to-end: eight profiles, one controlled source

The eight-profile benchmark prepares, authors (with a deterministic synthetic
author), validates, and renders a report for every built-in profile from one
controlled source. The archived run is reproducible and machine-checkable:

```bash
python scripts/run_report_benchmarks.py --check   # validate archived evidence
python scripts/run_report_benchmarks.py           # regenerate from scratch
```

Archived results ([`benchmarks/evidence/full_benchmark_2026-05-13/summary.md`](../benchmarks/evidence/full_benchmark_2026-05-13/summary.md)):

| Metric | Result |
| --- | --- |
| Profiles passing end-to-end | **8 / 8** (re-run 2026-10-16) |
| Claims verified against evidence | **80** (10 per profile, `verified_count` in each `factuality_report.json`), **0 blocked** |
| Unresolved citation-audit entries | **0** |
| Delivery QA decision | `pass` on every profile |
| Unit tests at the time of the archived run | **1260 passing** (1329 today) |

Each report is packaged with its QA pack (`final_qa_summary`, factuality,
figure-visual, template-style, and render-layout reports) so
the publish decision is auditable after the fact, not just asserted.

Beyond the synthetic benchmark, every built-in profile has also been run on a
realistic hand-written case — a cantilever-beam lab report, a capstone research
proposal, a production-line defect analysis, a hardware selection evaluation, a
capstone project report for graduate applications — in Chinese and English.
Those rounds are what the recent CHANGELOG entries record.

## check-draft: false alarms and planted errors, on three public papers

```bash
python scripts/run_draft_benchmark.py --check   # rerun from the PDFs, diff vs archive
```

`check-draft` was measured in both directions on three CC BY 4.0 arXiv papers
([`benchmarks/check_draft/SOURCES.md`](../benchmarks/check_draft/SOURCES.md)).
For each paper there are two drafts written by hand: a correct one, every figure
and quotation copied from the paper plus a few the writer worked out (a ratio, a
difference), and a planted one, the same text with errors put in. A correct
item reported NOT_FOUND is a false alarm; a planted error is caught when its
item is NOT_FOUND. LLaMA is the development case the matching rules were
tuned on. The QLoRA draft (English) and the Chain-of-Thought draft (Chinese,
about the English paper) were committed before check-draft was first run on
them (`54129c2`) and are reported as they came out. Afterwards the label files
were corrected where a label named an item the command splits differently, and
one QLoRA plant was moved: a model swap (Guanaco 33B → 13B) sat on the same
figure as an added decimal (97.83%), so it was replaced by 5 GB → 10 GB, the
13B model's footprint — which is missed, like the other moved figures. One fix to the command came after that run: the year in
「Wei 等人（2022）」 was being read as a figure. It took that one correct item
out of the held-out count (142 to 141) and changed no verdict.

| | Correct items flagged | Planted errors caught | Worked-out figures NOT_FOUND |
| --- | ---: | ---: | ---: |
| dev (LLaMA) | 0 / 59 | 17 / 20 | 2 / 2 |
| held out (QLoRA, CoT in Chinese) | **8 / 141** (5.7%) | **32 / 39** (82%) | 5 / 5 |

By type, held out: altered quotations 8/8, invented quotations 2/2, wrong unit
or scale 5/5, more decimals than the paper prints 3/3, wrong digit 14/17, and a
figure moved to another model or setting **0/4**.

What it does not do, read off the misses:

- **A figure moved within one table is not caught** (0/6 over both splits).
  Swapping two models' scores, or two metrics in one sentence, leaves every
  figure printed on the page beside the sentence's words.
- **A wrong digit that is another figure in the same table passes** (45.3 for
  43.5, both in QLoRA's Table 8; 64% and 27% are elsewhere in the CoT paper).
- **The false alarms are sentences whose own words are not the page's.** Five
  of the eight restate a table whose column header sits further from the figure
  than the 250 characters read around it (CoT's Table 2, QLoRA's Table 8);
  two are figures repeated in a sentence of the writer's own ("going from 780
  GB to under 48 GB is a reduction of over 16 times"); one is a figure whose
  sentence names other models. A NOT_FOUND says "look at this one", with the
  nearest figure the page does print beside it.
- **A translated quotation is not checked.** 「」 counts as quotation marks
  only after a reporting verb (寫道, 指出…), the rule FE already uses; the CoT
  draft's 坦言「…」 is left out and reported as neither found nor missing.

Every item, page and message:
[`benchmarks/evidence/check_draft_2026-10-21/summary.md`](../benchmarks/evidence/check_draft_2026-10-21/summary.md).

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

## Who it is and is not for

- **Anyone who has to hand in a document that gets judged.** Lab reports,
  research proposals, journal manuscripts, status and business reports,
  admissions documents, technical documentation.
- **RAG / agent pipelines that need a CI gate.** `verify(answer, sources)` in a
  test means a grounding regression fails the build — like a linter, with no
  eval budget and no flaky judge.
- **Evidence-bounded documents** — financial memos, regulatory drafts — where
  the QA pack can prove, per sentence, why a claim was allowed to ship.

**Not for** open-domain chat where hallucinations are fluent paraphrases sharing
the source's vocabulary. That is semantic entailment territory (the documented
evasions), where an NLI model or LLM judge earns its cost.

## Why the checker holds no model

Report Workflow is one instance of a general idea: **evidence-bounded
generation.** Wherever a claim must trace to a source, the trustworthy part is
not the fluent draft but the layer that can *prove* each statement and refuse
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

## Reproducing everything

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
python scripts/run_report_benchmarks.py --check
python scripts/run_adversarial_benchmark.py --check
python scripts/run_draft_benchmark.py --check
```

The benchmark-first optimization method and gap taxonomy are documented in
`skills/report-workflow/reference/benchmarking.md`.
