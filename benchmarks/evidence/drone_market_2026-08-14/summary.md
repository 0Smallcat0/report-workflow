# Drone-market benchmark: three reports, one source, three axes

Same three CSVs, same task statement, all three arms recorded, one set of
scorers. Reproduce with `python scripts/run_drone_market_benchmark.py --check`.

## Read this before the table

**The stop condition is met, and one number decides it.** On the argument axis
the tool arm reads 3/4/4 and the AI-direct arm 4/3/3, so the tool arm wins that
axis 2–1. The AI-direct arm is frozen: its bytes are identical to the round
that scored it 4/4/4. Had this panel returned 4/4/4 again, the tool arm would
have been 0–1 on the argument axis, the axis would not be won, and the stop
condition would not be met.

So a two-point move on a document that did not change is what carries the
verdict. Both drops are attributable — all three judges independently found
that the AI-direct arm's headline figure is wrong (544 - 148 - 63 - 46 - 8 =
279, written as 267) and that the table carrying its strongest counter-evidence
is contaminated: its top two review counts are a pair of binoculars and a
telescope, 51.9% of the total it quotes, from the 46 rows that arm itself
excluded as keyword contamination. Those are real defects and the deductions
are earned. But they were equally present in the previous round and that panel
did not find them, which is the measurement this archive can actually make:
**the round-to-round noise on the argument axis is at least one point per
dimension, and this round's margin is one point.**

The tool arm has its own defect this round, found by all three judges: the
pain-point section calls a table row labelled `1–2` 「1–3 星區間 49 則評論」
three times. The row and the 49 are right; 1–3 stars is 68 reviews. It is the
same class of error the band-label repair was for, one layer up — the labels
were corrected and the prose quoting the old ones was not. Not repaired here,
because repairing it means re-recording and re-judging, and a round re-run
until it comes out better is not a measurement.

## What these scores are an upper bound on

The tool arm is the only arm that moves. This round it was written a second
time against the same task, the same three CSVs and the same rubric, by an
author holding the previous round's itemised deductions from three blind
judges. Scores going up under those conditions is close to guaranteed.

How much of the rise is the pipeline getting better and how much is a second
attempt at one exam, **this round's design cannot separate**. Read the
numbers as this task's ceiling for this pipeline, not as what it would score
on a task it has not seen.

What would separate them is a held-out task: new sources, a new question, no
prior judging to write against. There is not one, and there will not be one
soon — building it means a second hand-written control and a second AI-direct
arm, which is the expensive half of this benchmark. That is the largest known
limitation of this archive, and it is a limitation rather than a to-do.

- **hand** — `benchmarks/fixtures/drone_market_unassisted.md`
- **tool** — `benchmarks/fixtures/drone_market_tool_arm.md`
- **llm_direct** — `benchmarks/fixtures/drone_market_llm_direct.md`
- Argument rubric: `benchmarks/rubrics/argument_rubric.md`

| Axis | Dimension | hand | tool | llm_direct |
| --- | --- | ---: | ---: | ---: |
| numeric | external_sources | 0 | 12 | 0 |
| numeric | verifiable_numbers | 121 | 137 | 72 |
| numeric | verifiable_number_ratio | 0.7035 | 0.5269 | 0.5714 |
| numeric | tables | 13 | 10 | 11 |
| numeric | figures | 0 | 0 | 0 |
| numeric | counter_evidence_paragraphs | 0 | 4 | 0 |
| numeric | disclosed_derivations | 0 | 0 | 0 |
| numeric | structured_paragraph_ratio | 0.3784 | 0.6765 | 0.3548 |
| layout | heading_informativeness | 0.3571 | 0.8 | 0.3333 |
| layout | table_lead_in_ratio | 0.9231 | 1.0 | 0.8182 |
| layout | paragraph_length_fitness | 0.5172 | 0.5333 | 0.8 |
| layout | table_caption_ratio | 0.0 | 1.0 | 0.0 |
| layout | table_provenance_ratio | 0.0 | 1.0 | 0.0 |
| layout | table_size_fitness | 1.0 | 0.8 | 1.0 |
| argument | claim_strength | 4 | 3 | 4 |
| argument | evidence_depth | 4 | 4 | 3 |
| argument | counter_specificity | 4 | 4 | 3 |

## Where the tool arm stands

The stop condition for this round: the tool arm wins every axis against the
AI-direct arm, and loses at most one axis to the hand-written control.

| Axis | vs llm_direct | vs hand |
| --- | --- | --- |
| numeric | 4W 2L won | 4W 2L won |
| layout | 4W 2L won | 5W 1L won |
| argument | 2W 1L won | 0W 1L not yet |

Beats the AI-direct arm on every axis: **True**. Axes lost to the hand-written control: **1**. Stop condition met: **True**.

## What this claims, and what it does not

It claims the delivered document can be compared to a person's and to an
AI's on the same three axes, and reports where it leads and where it trails.

The argument votes are no longer the authoring agent's own. Each is cast by a
separate judge given the three documents relabelled and shuffled, the rubric,
and the CSVs — and told nothing about how any arm was produced.

That change was not cosmetic. Under self-scoring the arms read hand 3/3/4,
tool 4/3/4, AI-direct 4/3/4. The first blind round returned hand 4/4/4, tool
3/3/4, AI-direct 4/4/4 — the tool arm inflated, the hand-written control
deflated, and the verdict on the argument axis reversed. A score can be raised
by writing to the anchor when the same agent writes the anchor, the paragraph
and the vote; that is what had happened.

It still does not claim the scores are objective. Three judges reading one
rubric disagree by a point on most dimensions, which is why the median of
three is recorded rather than any single vote. What the archive gives is a
passage per score, so a fourth reader can disagree with a specific one.

The hand-written and AI-direct arms are recorded artifacts rather than live
generations. That is deliberate: a baseline regenerated each run makes the
comparison move for reasons unrelated to the pipeline. Neither is a strawman —
the hand-written arm was ahead of the pipeline when it was recorded, and the
AI-direct arm is the strongest of four independent drafts.

## The instrument changed this round

The layout axis went from three dimensions to six. The first three read prose;
the deliverable is a DOCX and nothing was looking at the furniture around a
table. Added: `table_caption_ratio`, `table_provenance_ratio`,
`table_size_fitness`.

Declared because of who added them. The same author who rewrote the tool arm
chose these three, after reading all three documents. Two of them — caption and
attribution — are properties the renderer produces by construction and neither
hand-written arm produces at all, so they run 1.0 against 0.0 and are closer to
"did the renderer run" than to "is this better laid out". The third,
`table_size_fitness`, is the one the pipeline loses, to both other arms; it is
in the axis for that reason. Discount the layout axis accordingly.

The numeric and argument axes were not touched, and the rubric was not touched.
The tool arm was measured on the unchanged three-dimension layout axis before
these were added, and that measurement is in the commit that introduced them.
