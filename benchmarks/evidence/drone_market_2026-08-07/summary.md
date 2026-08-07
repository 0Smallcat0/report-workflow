# Drone-market benchmark: harness versus the hand-built control

Three raw CSVs, one task statement, one scorer, both arms checked in.
Reproduce with `python scripts/run_drone_market_benchmark.py --check`.

- Source: `benchmarks/fixtures/drone_market/amazon_classified.csv`, `benchmarks/fixtures/drone_market/amazon_products.csv`, `benchmarks/fixtures/drone_market/amazon_reviews.csv`
- Unassisted arm: `benchmarks/fixtures/drone_market_unassisted.md` (recorded sample; see the file header)
- Tool arm: a live run of prepare -> author -> validate -> render

| Dimension | Unassisted | Tool | Winner |
| --- | ---: | ---: | --- |
| external_sources | 0 | 2 | tool |
| verifiable_numbers | 121 | 45 | unassisted |
| verifiable_number_ratio | 0.7035 | 0.4091 | unassisted |
| tables | 13 | 7 | unassisted |
| figures | 0 | 0 | tie |
| counter_evidence_paragraphs | 0 | 1 | tool |
| disclosed_derivations | 0 | 0 | tie |
| structured_paragraph_ratio | 0.3784 | 0.7143 | tool |

Tool wins 3 of 8 dimensions; unassisted wins 3; 2 tie.

## What the run itself shows

- Cross tabulations the pipeline built at intake: **7**
- Placed in the document: **7**
- Tables in the delivered DOCX: **7**
- Derivations the author had to register by hand: **0**
- Questions extracted from the task statement, each bound to a claim in the conclusion: **2**

The last three are the round's subject. The tables were computed whether or not
anyone asked; before this round an author could leave them unmentioned, and three
runs of this task placed four of them, then three, then two. The outline now
refuses to load until each is either placed or waived by name with a reason, so
the number above is a floor rather than an average.

## What this claims, and what it does not

It claims the harness carries checkable material into the document without the
author having to build it: every table above is computed from the rows, keeps its
provenance, and is cited by a claim the gates check.

It does not claim the harness writes better prose. The tool arm is authored
mechanically - one lead-in sentence per table, no argument between them - which
is what isolates the harness's contribution from the writer's. Rewriting that
author to score better would be tuning the arm rather than measuring the harness.

The unassisted arm is a recorded artifact rather than a live generation. That is
a limitation and it is deliberate: it is one write-up by one author on one day,
and regenerating it would move the baseline for reasons unrelated to the
pipeline. It is also not a strawman - it is the arm that was ahead.

## The dimensions the tool loses

Reported as measured rather than tuned away, because a benchmark its own
author can adjust until it wins is not evidence of anything.

- **verifiable_numbers**: unassisted 121, tool 45.
- **verifiable_number_ratio**: unassisted 0.7035, tool 0.4091.
- **tables**: unassisted 13, tool 7.

All three come from the same property of this arm: it registers nothing. It
places the tables the pipeline built and states no figures beyond what those
tables' evidence text already contains, where the unassisted arm computed
whatever its argument needed and typed the result into a sentence.

`tables` is the clearest reading of that. The tool arm carries the built
tables and no others; the three real acceptance runs of this same task
registered six, five and four grouped tables of their own on top of them.
The gap is what an author adds, and this arm has no author.

`verifiable_numbers` and its ratio are counted over prose paragraphs, and the
paragraph filter excludes table rows from *both* arms — so a figure the tool
puts in a checked table is not counted, while the same figure typed into a
sentence by the unassisted arm is. Read beside it: every number this arm
states is traceable to a ledger row, and none of the unassisted arm's 121 is
traceable to anything at all. That is the trade, and this scorer is not the
instrument that shows it.
