# Report Profiles

`report_profile` is the single public report-shape contract. It replaces the old
`report_family` / detail / subtype model. Do not use `report_family`, `--family`,
`--detail`, variant, or subtype naming.

Pass `report_profile` when the user specifies a report type. Otherwise the
pipeline infers one from the prompt, then falls back to `academic_paper`.

## Built-in Profiles

- `engineering_lab_report`: engineering experiment reports, including Chinese
  engineering report requirements, requirement matrices, formula/unit audits,
  calculation audits, figure/table contracts, and render QA. See
  [engineering-lab.md](engineering-lab.md).
- `academic_paper`: IMRaD-style academic papers with strict abstract,
  front-matter, citation, and reference expectations.
- `business_report`: executive/work reports with findings and recommendations.
- `proposal`: proposals with problem, objectives, approach, scope, timeline,
  budget/resources, risks, and evaluation sections.
- `admissions_report`: admissions-facing scholarly reports.
- `admissions_project_report`: admissions-facing project reports with relaxed
  publication metadata requirements.
- `custom`: user-defined or mixed reports with medium strictness. Claims and
  section contracts stay evidence-backed; citation format, word counts, and
  figure rules default to lenient.

## What a Profile Controls

Profiles control section contracts, front matter, abstract policy, citation
style, figure/table requirements, word-count strictness, tone policy, and render
QA expectations. They do **not** change the deterministic DAG shape; nodes read
profile policy.

## Custom Profile Guidance

`custom` is intentionally medium strictness: evidence-backed claims and section
contracts are required, while citation style, word-count, and figure rules stay
lenient unless the user supplies a stricter structure.

For `custom`, choose one dominant report convention from the prompt and source
material, then use any secondary conventions only as supporting cues. Do not
blend every built-in profile into one report shape.

## Admissions Profiles

For admissions profiles, pass explicit `project_identity` when the report must
preserve named project terms, domain context, forbidden drift terms, or author
metadata. Do not infer an admissions project spine from a previous benchmark or
unrelated project. Keep the supplied identity terms visible in the title/thesis,
introduction, and conclusion.

Keep admissions evidence anchored to the supplied source record: research fit,
readiness, project significance, and contribution claims need concrete source
support, not committee flattery or unsupported autobiography.

## Template Priority

Reference/template mode is a separate axis from the profile:

- Default mode is `style_reference`: use a DOCX as a style/layout reference.
- If the prompt asks to exactly preserve the cover or format, intake upgrades to
  `fixed_template`.
- An explicit user mode wins.
- The profile contract still has priority over prompt and template hints. For
  example, `engineering_lab_report` keeps its engineering contract even when a
  school/company template DOCX is supplied.
