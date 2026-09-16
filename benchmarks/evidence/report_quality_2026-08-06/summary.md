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
| verifiable_number_ratio | 1.0 | 0.9143 | unassisted |
| tables | 0 | 4 | tool |
| figures | 0 | 1 | tool |
| counter_evidence_paragraphs | 2 | 4 | tool |
| disclosed_derivations | 0 | 6 | tool |
| structured_paragraph_ratio | 0.7143 | 0.6061 | unassisted |

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

## What moved when this arm was re-recorded

The recorded tool document dated from `3fd812c`. The citation work of
`80994fb`, `4d501b8` and `2b5472a` changed what reaches the deliverable, so
it was re-recorded, and two dimensions moved: `verifiable_number_ratio`
0.9014 → 0.9143 and `structured_paragraph_ratio` 0.5714 → 0.6061.
`verifiable_numbers` did not move at all, and the unassisted arm did not
move, because its bytes did not.

Both moves are two blocks leaving the document. It used to carry
`executive_summary` — a bare section id that reached the page, closed in
`0e0a40f` — and a `資料來源` heading over eight `[S1]`–`[S8]` entries; it now
carries one unnumbered `附錄`. That is two fewer blocks the scorer reads as
paragraphs, against an unchanged 20 structured ones. The ratio moved for a
neighbouring reason: the `5` in the old `5. 附錄` heading was a prose figure
the source does not contain, and the appendix is no longer numbered.

The first attempt at this re-recording moved four further dimensions and
banked none of them. The arm's author finds its counter-evidence section by
a blueprint key that `f00f100` renamed, so it found none, handed all eight
claims to all four sections, and wrote 32 claim paragraphs where it writes
20 — which raised four scores on an arm that is supposed to hold still. The
lookup was repaired before this archive was written.

## The two dimensions the tool loses

Both are reported as measured rather than tuned away, because a benchmark
its own author can adjust until it wins is not evidence of anything.

**verifiable_number_ratio.** The baseline scores 1.0 by stating almost no
checkable figures: it writes 八萬 and 兩千四百 where the source writes 80,000
and 2,383, and a Chinese numeral is a paraphrase of a quantity rather than
the quantity. Its perfect ratio is one verifiable number out of one. The
tool arm states 64 and can trace 91% of them; the rest are derived figures, which the derivation dimension covers. Read the
ratio next to the count or the metric rewards vagueness.

**structured_paragraph_ratio.** The tool arm is dragged down by its own
mechanical author, which writes one-line lead-ins before a table ('下表為
來源原始數據。'). The drafting brief tells a real author to give every table
a distinct lead-in that says what to look for — this arm does not, because
rewriting it to score better would be tuning the arm rather than measuring
the harness.
