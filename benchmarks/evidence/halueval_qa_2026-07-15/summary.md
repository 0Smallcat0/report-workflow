# Out-of-Domain Benchmark: HaluEval QA (2026-07-15)

- Dataset: **10,000 QA pairs** from [HaluEval](https://raw.githubusercontent.com/RUCAIBox/HaluEval/main/data/qa_data.json) (Li et al., EMNLP 2023) — each pair contributes one hallucinated and one right answer, verified against its knowledge passage with the zero-schema `report_workflow.verify()` adapter.
- Dataset sha256 (pinned, verified before every run): `89ed139ec5e3a3169a0b30e45569ac1283846f76f27f7bb5e908ee6deed57e88`
- No LLM, no API key: verdicts are pure functions of (answer, knowledge).

## Results

| Metric | Value |
| --- | --- |
| Recall (hallucinated answers blocked) | 23.2% (2,320/10,000) |
| False-positive rate (right answers blocked) | 0.1% (6/10,000) |
| Precision of a block verdict | 99.7% |
| Numeric-subset recall (681 pairs with number+unit) | 66.7% (454/681) |
| Gate breakdown | FE: 2320 |

## Reading these numbers honestly

HaluEval hallucinations are open-domain **entity swaps** engineered to reuse
the knowledge passage's own vocabulary — the exact class `docs/DESIGN.md` §6
places outside deterministic lexical checking. The headline here is not the
recall; it is the discipline: across 10,000 honest answers the gates
wrongly blocked 6, and every block they did issue
was a real hallucination. Out of domain, with zero tokens spent, the gate
stack behaves like a linter should: it does not catch every bug, and it does
not lie about the ones it flags. In-domain behavior (evidence-bounded
drafting, where claims must reuse ledger vocabulary) is measured by the
adversarial benchmark instead.

The false positives were inspected one by one: five are proper nouns whose
leading numeral parses as a measurement (film titles like *13 Going on 30*,
street addresses like *70 Pine Street*), and one is a dataset concatenation
artifact that glues 'billion' to the first word of the next sentence, so the
unit comparison sees 'billionFranklin'. Distinguishing a title from a
measurement is a semantic call, which the design keeps out of the
deterministic layer on purpose.

Baselines on this data are degenerate by construction: `no_gate` and the
shallow citation-presence check both block nothing (0% recall) because every
answer is 'grounded' in an existing passage.

## Reproduce

```bash
python scripts/run_external_benchmark.py --download   # fetch + sha256-verify the dataset
python scripts/run_external_benchmark.py --check      # recompute all 20,000 verdicts, diff vs this archive
```
