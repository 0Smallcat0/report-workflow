# Drone-market benchmark: three reports, one source, three axes

Same three CSVs, same task statement, all three arms recorded, one set of
scorers. Reproduce with `python scripts/run_drone_market_benchmark.py --check`.

## What changed this round

**The tool arm was re-recorded and the argument axis was re-judged.** The
previous recording could no longer be reproduced at all: `e401849` added the
FL checker, which hard-blocks three of the arm's own claims for calling a
table row labelled `1–2` 「1–3 星區間」 — the defect the 2026-08-14 archive
recorded and deliberately left unrepaired. From that commit onward the
recording script failed at validate and CI's re-record job was red. The three
labels now name the row FL points at, which is what its message prescribes,
and that is the only change to the author's prose.

**What moved on the counted axes is the citation apparatus, not the writing.**
`80994fb`, `4d501b8` and `2b5472a` moved the derivations out of the report
into `published/calculation_record.docx` and replaced the `[S1]` markers with
「（本研究計算，表 N）」:

- `external_sources` 12 → 0. All twelve lived in the old `# 資料來源` list:
  six Amazon URLs and six quoted `(來源:…csv)` strings naming the input files.
  Not one of them was a source outside this data set — the dimension was
  counting the pipeline's own record of its own derivations.
- `verifiable_numbers` 137 → 167. Thirty numbers added, none removed, and all
  thirty are digits inside `表 N` pointers. The arm states no more checkable
  figures than it did before.
- `verifiable_number_ratio` 0.5269 → 0.5759, on those same thirty digits —
  which is what turns that dimension from a loss into a win against the
  AI-direct arm.
- `paragraph_length_fitness` 0.5333 → 0.4074. The authored paragraphs are
  unchanged in shape: 22 fit, 31 under 60 characters, 1 over 500, before and
  after. The twenty-one source-list entries that left the document took 18
  fit paragraphs out of the denominator with them.

Two of those dimensions do not measure what their names say, and both move
when the citation format changes. That is a defect in the instrument. It is
recorded here rather than banked as a result.

**The argument axis tied on every dimension.** Three blind judges returned
hand 4/4/4, tool 4/4/4, AI-direct 4/4/4; one judge scored the tool arm 3 on
`claim_strength` and was outvoted by the median. An axis is won by leading on
more dimensions than you trail, so 0–0 is not a win and **the stop condition
is not met this round** — not because anything was lost, but because the
rubric's top band no longer separates these three documents.

Two things about this panel belong in the record. All three judges found the
AI-direct arm's arithmetic error (544 − 148 − 63 − 46 − 8 = 279, printed as
267) and the contaminated table under its strongest counter-evidence, which
are the two defects the previous panel docked it two points for — and this
panel docked it nothing, taking them as not overturning its conclusions. The
measurement that keeps reproducing here is the panel's own variance. And the
judging prompt carried one sentence earlier rounds may not have had: that the
three documents need not be spread across the scale. It was there to stop
forced differentiation, and one judge differentiated anyway, but it is a
deviation from whatever the earlier prompt said and it points toward the
ceiling this round hit.

- **hand** — `benchmarks/fixtures/drone_market_unassisted.md`
- **tool** — `benchmarks/fixtures/drone_market_tool_arm.md`
- **llm_direct** — `benchmarks/fixtures/drone_market_llm_direct.md`
- Argument rubric: `benchmarks/rubrics/argument_rubric.md`

| Axis | Dimension | hand | tool | llm_direct |
| --- | --- | ---: | ---: | ---: |
| numeric | external_sources | 0 | 0 | 0 |
| numeric | verifiable_numbers | 121 | 167 | 72 |
| numeric | verifiable_number_ratio | 0.7035 | 0.5759 | 0.5714 |
| numeric | tables | 13 | 10 | 11 |
| numeric | figures | 0 | 0 | 0 |
| numeric | counter_evidence_paragraphs | 0 | 4 | 0 |
| numeric | disclosed_derivations | 0 | 0 | 0 |
| numeric | structured_paragraph_ratio | 0.3784 | 0.6765 | 0.3548 |
| layout | heading_informativeness | 0.3571 | 0.8 | 0.3333 |
| layout | table_lead_in_ratio | 0.9231 | 1.0 | 0.8182 |
| layout | paragraph_length_fitness | 0.5172 | 0.4074 | 0.8 |
| layout | table_caption_ratio | 0.0 | 1.0 | 0.0 |
| layout | table_provenance_ratio | 0.0 | 1.0 | 0.0 |
| layout | table_size_fitness | 1.0 | 0.8 | 1.0 |
| argument | claim_strength | 4 | 4 | 4 |
| argument | evidence_depth | 4 | 4 | 4 |
| argument | counter_specificity | 4 | 4 | 4 |

## Where the tool arm stands

The stop condition for this round: the tool arm wins every axis against the
AI-direct arm, and loses at most one axis to the hand-written control.

| Axis | vs llm_direct | vs hand |
| --- | --- | --- |
| numeric | 4W 1L won | 3W 2L won |
| layout | 4W 2L won | 4W 2L won |
| argument | 0W 0L not yet | 0W 0L not yet |

Beats the AI-direct arm on every axis: **False**. Axes lost to the hand-written control: **1**. Stop condition met: **False**.

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

## The instrument, and the round it changed in

This round did not touch it: the scorers, the axes and the rubric are the
ones the 2026-08-14 archive used, which is what makes the two comparable.

In that round the layout axis went from three dimensions to six. The first
three read prose; the deliverable is a DOCX and nothing was looking at the
furniture around a table. Added: `table_caption_ratio`,
`table_provenance_ratio`, `table_size_fitness`.

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

## What these scores are an upper bound on

The tool arm is the only arm that moves. Its prose was written against the
same task, the same three CSVs and the same rubric by an author holding three
blind judges' itemised deductions on the previous version, and this round
repaired the one defect that panel found in it. Scores holding up under those
conditions is close to guaranteed.

How much of that is the pipeline and how much is a second attempt at one exam,
**this design cannot separate**. Read the numbers as this task's ceiling for
this pipeline, not as what it would score on a task it has not seen.

What would separate them is a held-out task: new sources, a new question, no
prior judging to write against. There is not one, and there will not be one
soon — building it means a second hand-written control and a second AI-direct
arm, which is the expensive half of this benchmark. That is the largest known
limitation of this archive, and it is a limitation rather than a to-do.

