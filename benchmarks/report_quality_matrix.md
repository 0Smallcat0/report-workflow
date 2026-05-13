# Report Quality Benchmark Matrix

Research snapshot: 2026-05-13.

This matrix turns public report guidance into benchmark criteria for
`report-workflow`. It does not introduce new public selectors; `report_profile`
remains the only report-shape selector.

Latest full benchmark: `scripts/run_report_benchmarks.py` passed all seven
built-in profiles on 2026-05-13 using both
`benchmarks/fixtures/controlled_source.md` and
the `benchmarks/fixtures/chart_*.csv` fixture set for bar, line, scatter,
boxplot, and table-fallback figure coverage. Compact QA evidence is archived under
`benchmarks/evidence/full_benchmark_2026-05-13/`; use
`python scripts/run_report_benchmarks.py --check` to validate the archived
evidence without rerunning the workflow.

## Source Register

| Source | Applies To | Benchmark Signal |
| --- | --- | --- |
| [BCcampus Technical Writing Essentials: Lab Reports](https://opentextbc.ca/technicalwritingh5p/chapter/lab-reports/) | `engineering_lab_report` | Hypothesis/question, methods, results, discussion, conclusion, honest data display, appendices for full data. |
| [GMU Writing Center: IMRaD Research Reports](https://writingcenter.gmu.edu/writing-resources/imrad/writing-an-imrad-report) | `academic_paper`, `engineering_lab_report` | Introduction/gap, reproducible methods, results vs discussion separation, labeled figures/tables. |
| [Purdue OWL: Organization and Structure](https://owl.purdue.edu/owl/graduate_writing/graduate_writing_topics/graduate_writing_organization_structure_new.html) | `academic_paper` | IMRaD as a common base, reader-responsible organization, signposting. |
| [Nature Scientific Reports: Submission Guidelines](https://www.nature.com/srep/author-instructions/submission-guidelines) | `academic_paper` | Concise article structure, methods reproducibility, references, data availability, competing interests, figure standards. |
| [Monash: Business Report Writing](https://www.monash.edu/student-academic-success/excel-at-writing/annotated-assessment-samples/business-and-economics/buseco-report-writing) | `business_report` | Executive summary with aim, work performed, findings, conclusions, recommendations; body and appendices. |
| [BCcampus Technical Writing Essentials: Proposals](https://opentextbc.ca/technicalwritingh5p/chapter/proposals/) | `proposal` | Problem definition, scope, benefits, budget, timeline, risks, logical persuasive tone. |
| [Harvard Griffin GSAS: Statement of Purpose](https://gsas.harvard.edu/apply/applying-degree-programs/statement-purpose-personal-statement-and-writing-sample) | `admissions_report`, `admissions_project_report` | Focused research interests, qualifications, motivation, career objectives, complementary personal context. |
| [Harvard SEAS: Graduate CS Application Advice](https://seas.harvard.edu/news/what-know-you-apply-graduate-school-computer-science) | `admissions_report`, `admissions_project_report` | Evidence of research potential, meaningful project experience, direction without rigidity. |
| [GMU Writing Center: White Papers](https://writingcenter.gmu.edu/writing-resources/different-genres/white-papers) | `custom`, `business_report` | Problem-solution structure, objective tone, authoritative evidence, optional recommendations. |
| [BCcampus: Recommendation and Feasibility Reports](https://opentextbc.ca/technicalwritingh5p/chapter/long-reports-recommendation-reports-and-feasibility-studies/) | `business_report`, `custom` | Criteria, options, systematic comparison, conclusions, recommendation logic. |

## Profile Matrix

| `report_profile` | Dominant Quality Criteria | QA Artifacts To Inspect | First-Pass Optimization Bias |
| --- | --- | --- | --- |
| `engineering_lab_report` | Replicable procedure, apparatus/units/formulas, honest data, calculations, results-discussion split, technical conclusion. | `engineering_audit_report.json`, `scholarly_quality_report.json`, `figure_visual_quality_report.json`, `final_qa_summary.json`, rendered pages. | Strengthen author guidance and benchmark cases before adding more hard gates. |
| `academic_paper` | IMRaD/gap spine, methods reproducibility, objective results, discussion interpretation, references and publication metadata where supported. | `scholarly_quality_report.json`, `reference_reality_report.json`, `figure_visual_quality_report.json`, `final_qa_summary.json`. | Prefer scholarly QA refinements only when repeated benchmark failures show false pass/fail behavior. |
| `business_report` | Decision-maker summary, findings-to-recommendations logic, audience fit, evidence-backed options, concise visuals. | `final_qa_summary.json`, `figure_visual_quality_report.json`, `template_style_map.json`, executive summary text. | Add skill guidance for executive summary and recommendation logic before workflow changes. |
| `proposal` | Problem definition, scope, feasibility, benefits, budget, timeline, risks, evaluation plan, credible persuasive tone. | `final_qa_summary.json`, `figure_visual_quality_report.json`, `template_style_map.json`, timeline/budget sections. | Keep proposal-specific requirements mostly in guidance unless deterministic artifacts can validate missing budget/timeline. |
| `admissions_report` | Research interests, qualifications, motivation, career direction, serious scholarly tone, admissions fit without flattery. | `scholarly_quality_report.json`, `admissions_tone_report.json`, `project_identity_report.json`, `final_qa_summary.json`. | Use explicit `project_identity` terms when a project spine must be preserved; do not hardcode one prior project into the profile. |
| `admissions_project_report` | Concrete project evidence, research readiness, limitations, future direction, relaxed publication metadata. | `reference_relevance_report.json`, `project_identity_report.json`, `final_qa_summary.json`. | Keep internal-source allowance explicit, read outline thesis for identity, and avoid forcing academic-paper reference strictness. |
| `custom` | One dominant rhetorical purpose, clear criteria, evidence/interpretation/recommendation separation, medium strictness. | `final_qa_summary.json`, `figure_visual_quality_report.json`, `template_style_map.json`. | Add guidance that chooses a dominant rubric rather than mixing all profiles. |

## Ranking

1. Implemented: add benchmark-first guidance to the skill and repo artifacts so
   future `/goal` runs classify gaps before changing code.
2. Implemented: encode one benchmark packet per built-in profile, with stable
   rubric sources and QA artifacts to inspect.
3. Implemented: run full end-to-end controlled benchmarks for all profiles,
   including deterministic bar, line, scatter, boxplot, and table-fallback
   recommendation/build/visual-quality coverage, and archive representative QA
   outputs outside ignored runtime folders.
4. Implemented: add `--check` mode for archived benchmark evidence.
5. Implemented: remove project-specific admissions hardcoding and make
   project-identity validation use explicit identity terms plus outline thesis
   when applicable.
6. Implemented: strengthen benchmark-authored academic/engineering methods,
   introduction spine cues, figure labels, and calibrated wording; current
   scholarly benchmark snapshots pass with zero review issues for both profiles.
7. Not recommended: copying a high-quality sample's prose, exact headings, or
   visual style as a universal workflow template.

## Gap Taxonomy

All findings must use one of:

- `skill_guidance_gap`
- `profile_policy_gap`
- `deterministic_pipeline_gap`
- `render_template_gap`
- `agent_authoring_gap`
- `external_reference_gap`
