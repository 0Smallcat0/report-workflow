# Measured evidence

Every number here is reproducible from this repository. Commands re-run the
measurement from source and diff against the archived result.

## Red-team: the catch rate is measured, not asserted

A gate that only sees honest drafts proves nothing. The adversarial benchmark
runs **69 hand-audited cases** — 25 honest controls and 44 hallucinated claims
across 14 attack families (fabricated citations, invented statistics, unit
swaps, fabricated quotes, precision inflation, cross-language laundering,
off-topic citations, status laundering, Chinese-text fabrication,
overclaiming, …) — through the exact gate stack, and compares two baselines on
the same corpus:

| Checker | Recall (hallucinations blocked) | False positives (honest blocked) | Precision |
| --- | --- | --- | --- |
| No gate (publish everything) | 0.0% | 0.0% | — |
| Citation-presence check (shallow RAG-style) | 9.1% (4/44) | 0.0% | 100% |
| **Full deterministic gate stack** | **86.4%** (38/44) | **0.0%** (0/25) | **100%** |

All 14 targeted attack families are caught at 100%, with zero honest claims
wrongly blocked. The 2026-07-14 gate hardening closed three formerly documented
evasions (within-tolerance precision fudging, sub-10-character fabricated
quotes, cross-language citation laundering) and promoted them to regular attack
families. The remaining 6 misses are **documented evasions** (negation flips,
bare numbers without units, hedged reinterpretation, value misattribution) kept
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
| False-positive rate (right answers blocked) | **0.06%** (6/10,000) |
| Precision of a block verdict | **99.7%** |
| Recall — all hallucinations | 23.2% (2,320/10,000) |
| Recall — numeric subset (answers carrying a number+unit) | 66.7% |

Read it honestly: HaluEval hallucinations are open-domain *entity swaps*
engineered to reuse the passage's own vocabulary — the class
[`DESIGN.md`](DESIGN.md) explicitly places outside deterministic lexical
checking. The out-of-domain claim is the **discipline**, not the recall: the
gates almost never cry wolf (all six false positives are characterized in the
archive — film titles and street addresses whose leading numeral parses as a
measurement), and every block they issue is near-certain to be a real
hallucination. A linter does not catch every bug; it must not lie about the
ones it flags.

```bash
python scripts/run_external_benchmark.py --download   # fetch + sha256-verify the dataset (6 MB)
python scripts/run_external_benchmark.py --check      # recompute all 20,000 verdicts, diff vs archive
```

Full analysis: [`benchmarks/evidence/halueval_qa_2026-07-15/summary.md`](../benchmarks/evidence/halueval_qa_2026-07-15/summary.md).

## End-to-end: seven profiles, one controlled source

The seven-profile benchmark prepares, authors (with a deterministic synthetic
author), validates, and renders a report for every built-in profile from one
controlled source. The archived run is reproducible and machine-checkable:

```bash
python scripts/run_report_benchmarks.py --check   # validate archived evidence
python scripts/run_report_benchmarks.py           # regenerate from scratch
```

Archived results ([`benchmarks/evidence/full_benchmark_2026-05-13/summary.md`](../benchmarks/evidence/full_benchmark_2026-05-13/summary.md)):

| Metric | Result |
| --- | --- |
| Profiles passing end-to-end | **7 / 7** |
| Claims verified against evidence | **42** (6 per profile), **0 blocked** |
| Unresolved citation-audit entries | **0** |
| Delivery QA decision | `pass` on every profile |
| Unit tests at the time of the archived run | **351 passing** (496 today) |

Each report is packaged with its QA pack (`final_qa_summary`, factuality,
scholarly-quality, figure-visual, template-style, and render-layout reports) so
the publish decision is auditable after the fact, not just asserted.

Beyond the synthetic benchmark, every built-in profile has also been run on a
realistic hand-written case — a cantilever-beam lab report, a capstone research
proposal, a production-line defect analysis, a hardware selection evaluation, a
capstone project report for graduate applications — in Chinese and English.
Those rounds are what the recent CHANGELOG entries record.

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
```

The benchmark-first optimization method and gap taxonomy are documented in
`agent_skill/reference/benchmarking.md`.
