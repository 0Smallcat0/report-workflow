# Changelog

## Unreleased

### Changed

- Hardened report-workflow skill guidance for source-role boundaries,
  exact-template visual QA, figure-caption validation, and final DOCX scans for
  internal provenance leaks and user-provided forbidden phrases.
- Added academic figure guidance that separates deterministic source-data
  charts, Mermaid diagrams, and non-quantitative AI-assisted scholarly
  illustrations.
- Added generic guidance for external reference/database lookup: keep external
  references separate from measured/source data, record source/input units and
  assumptions, label derived values as estimates, avoid aggregating per-unit
  values without the required scaling variable, and avoid symbol reuse with
  conflicting units or meanings.
- Prepared the source release hygiene surface by ignoring `.env.*` secrets while
  keeping `.env.example`, adding MIT license text, and replacing provider-shaped
  fake API key examples with placeholder text.

## 4.0.0 - 2026-05-01

### Breaking Changes

- Replaced the public `report_family` / detail / subtype model with the single `report_profile` selector.
- Replaced `--family` with `--profile` in the CLI.
- Removed legacy report family blueprint IDs: `academic_report`, `work_report`, and `hybrid_report`.

### Added

- Added built-in profiles: `engineering_lab_report`, `academic_paper`, `business_report`, `proposal`, `admissions_report`, `admissions_project_report`, and `custom`.
- Added a profile registry and profile contract artifact (`report_profile.json`).
- Added Chinese engineering lab report guidance and the `engineering_lab_report` blueprint.
- Added custom profile defaults for user-defined structures with evidence-backed claims and section contracts, while keeping citation, word count, and figure requirements lenient.

### Changed

- Updated policy lookup, blueprint loading, CLI arguments, agent wrapper inputs, artifact metadata, and render/QA gates to use `report_profile`.
- Updated agent-facing docs and skill metadata to describe the generalized report workflow.
- Updated reference-template handling so exact-format/cover prompts select `fixed_template`; otherwise the default is `style_reference`.

### Verification

- `python -m compileall -q src tests`
- `python -m unittest discover -s tests -v`
- `git diff --check`
