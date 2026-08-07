# Report-quality benchmark: harness versus unassisted

Same source, same prompt, one scorer, both arms checked in.
Reproduce with `python scripts/run_report_quality_benchmark.py --check`.

- Source: `benchmarks/fixtures/recycling_market_report.md`
- Unassisted arm: `benchmarks/fixtures/unassisted_baseline.md` (recorded sample; see the file header)
- Tool arm: a live run of prepare → author → validate → render

| Dimension | Unassisted | Tool | Winner |
| --- | ---: | ---: | --- |
| external_sources | 0 | 8 | tool |
| verifiable_numbers | 1 | 64 | tool |
| verifiable_number_ratio | 1.0 | 0.9014 | unassisted |
| tables | 0 | 4 | tool |
| figures | 0 | 1 | tool |
| counter_evidence_paragraphs | 2 | 4 | tool |
| disclosed_derivations | 0 | 6 | tool |
| structured_paragraph_ratio | 0.7143 | 0.5714 | unassisted |

Tool wins 6 of 8 dimensions; unassisted wins 2; 0 tie.

## What this claims, and what it does not

It claims the harness makes these properties non-optional: a source table
survives into the document, a cited figure keeps its provenance, and a
number in the prose can be traced back to a row of the ledger. Each is
enforced by a gate, so no run can quietly drop them.

It does not claim the harness writes better prose. The tool arm is authored
mechanically, which is what isolates the harness's contribution from the
writer's. Prose quality comes from the drafting brief, and a deterministic
benchmark is the wrong instrument for measuring it.

The unassisted arm is a recorded artifact rather than a live generation.
That is a limitation, and it is deliberate: a baseline regenerated each run
makes the comparison move for reasons unrelated to the pipeline.

## The two dimensions the tool loses

Both are reported as measured rather than tuned away, because a benchmark
its own author can adjust until it wins is not evidence of anything.

**verifiable_number_ratio.** The baseline scores 1.0 by stating almost no
checkable figures: it writes 八萬 and 兩千四百 where the source writes 80,000
and 2,383, and a Chinese numeral is a paraphrase of a quantity rather than
the quantity. Its perfect ratio is one verifiable number out of one. The
tool arm states 64 and can trace 90% of them; the rest are derived figures, which the derivation dimension covers. Read the
ratio next to the count or the metric rewards vagueness.

**structured_paragraph_ratio.** The tool arm is dragged down by its own
mechanical author, which writes one-line lead-ins before a table ('下表為
來源原始數據。'). The drafting brief tells a real author to give every table
a distinct lead-in that says what to look for — this arm does not, because
rewriting it to score better would be tuning the arm rather than measuring
the harness.
