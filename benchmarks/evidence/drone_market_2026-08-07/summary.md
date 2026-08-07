# Drone-market benchmark: three reports, one source, three axes

Same three CSVs, same task statement, all three arms recorded, one set of
scorers. Reproduce with `python scripts/run_drone_market_benchmark.py --check`.

- **hand** — `benchmarks/fixtures/drone_market_unassisted.md`
- **tool** — `benchmarks/fixtures/drone_market_tool_arm.md`
- **llm_direct** — `benchmarks/fixtures/drone_market_llm_direct.md`
- Argument rubric: `benchmarks/rubrics/argument_rubric.md`

| Axis | Dimension | hand | tool | llm_direct |
| --- | --- | ---: | ---: | ---: |
| numeric | external_sources | 0 | 6 | 0 |
| numeric | verifiable_numbers | 121 | 52 | 72 |
| numeric | verifiable_number_ratio | 0.7035 | 0.486 | 0.5714 |
| numeric | tables | 13 | 9 | 11 |
| numeric | figures | 0 | 0 | 0 |
| numeric | counter_evidence_paragraphs | 0 | 3 | 0 |
| numeric | disclosed_derivations | 0 | 0 | 0 |
| numeric | structured_paragraph_ratio | 0.3784 | 0.6774 | 0.3548 |
| layout | heading_informativeness | 0.3571 | 0.6667 | 0.3333 |
| layout | table_lead_in_ratio | 0.9231 | 1.0 | 0.8182 |
| layout | paragraph_length_fitness | 0.5172 | 0.541 | 0.8 |
| argument | claim_strength | 3 | 3 | 4 |
| argument | evidence_depth | 3 | 2 | 3 |
| argument | counter_specificity | 4 | 3 | 4 |

## Where the tool arm stands

The stop condition for this round: the tool arm wins every axis against the
AI-direct arm, and loses at most one axis to the hand-written control.

| Axis | vs llm_direct | vs hand |
| --- | --- | --- |
| numeric | 3W 3L not yet | 3W 3L not yet |
| layout | 2W 1L won | 3W 0L won |
| argument | 0W 3L not yet | 0W 2L not yet |

Beats the AI-direct arm on every axis: **False**. Axes lost to the hand-written control: **2**. Stop condition met: **False**.

## What this claims, and what it does not

It claims the delivered document can be compared to a person's and to an
AI's on the same three axes, and reports where it leads and where it trails.

It does not claim the argument scores are impartial. The judge is the same
agent that wrote the harness one of the arms belongs to; the rubric was fixed
before any arm was judged, every vote records the passage it rests on, and the
votes are archived so a third party can re-read a document and disagree with a
specific score. That is mitigation, not independence.

The hand-written and AI-direct arms are recorded artifacts rather than live
generations. That is deliberate: a baseline regenerated each run makes the
comparison move for reasons unrelated to the pipeline. Neither is a strawman —
the hand-written arm was ahead of the pipeline when it was recorded, and the
AI-direct arm is the strongest of four independent drafts.
