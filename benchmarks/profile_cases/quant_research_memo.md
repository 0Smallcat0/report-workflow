# Benchmark Case: quant_research_memo

## Reference Signals

- A research memo is read by a colleague deciding whether to act on a result,
  so what held and what did not lead the document, before the method.
- A backtest result is only as credible as the number of configurations tried
  to reach it; the memo states the trials, the sample, and the window rather
  than presenting the best configuration alone.
- A result that holds in one setting and reverses in the next is not a result.
  The robustness section shows the other settings, and the limitations section
  names what the sample cannot support.

Primary rubric source:

- Bailey, Borwein, López de Prado and Zhu, "Pseudo-Mathematics and Financial
  Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample
  Performance", Notices of the AMS 61(5), 2014:
  https://www.ams.org/notices/201405/rnoti-p458.pdf

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write an internal research memo on what the structured workflow pilot tested, what held, and what the sample cannot support.`
- Profile: `quant_research_memo`
- Required QA to inspect: `final_qa_summary.json`,
  `figure_visual_quality_report.json`, `template_style_map.json`, and whether
  the summary states what held and what did not before the method.

## Expected Output

- Opens with a summary that says what was tested, what held, what did not, and
  the main caveat.
- States the question, the sample, and the window before the method.
- Carries a robustness section; a single favourable setting is not presented as
  the finding.
- Names what the sample cannot support in the limitations section.
- Has no thesis to defend and no literature review.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `profile_policy_gap`, or
`agent_authoring_gap`.
