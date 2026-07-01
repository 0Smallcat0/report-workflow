# Changelog

## Unreleased

### Changed

- Restructured the agent skill for progressive disclosure and multi-harness use.
  `agent_skill/SKILL.md` is now a ~220-line navigation hub (down from ~628) that
  links one-level-deep `agent_skill/reference/` files
  (`setup-and-preflight`, `profiles`, `tools`, `authoring`, `figures`,
  `engineering-lab`, `revision`, `benchmarking`), matching Anthropic's Agent
  Skills 500-line and single-source-of-truth guidance. Removed the duplicated
  `agent_skill/agent_instructions.md`; its content now lives once in the
  reference files. Made the skill harness-neutral (Codex, Claude Code, or any
  shell agent) with an explicit "Invoking the Tools" section and a
  harness-neutral `description`, and generate `reference/tools.md` from
  `skill.yaml` via `scripts/render_skill_docs.py`. Updated `sync_codex_skill.py`
  to sync the `reference/` tree and refreshed documentation contract tests.
- Consolidated the repository docs to a single source of truth. `AGENTS.md` is
  now the authoritative development guide (concepts, layout, commands, stage
  lists, artifact contract, hard gates, extension points); `CLAUDE.md` and
  `AGENT_ONBOARDING.md` are thin pointers to it, and `README.md` was trimmed to a
  human-facing overview that links `AGENTS.md` and the skill. Removed the
  duplicated profile/stage/gate copies across those files (top-level docs
  ~817 -> ~450 lines) and dropped `CLAUDE.md` from the generated tool-surface
  targets.
- Hardened report-workflow skill guidance for source-role boundaries,
  exact-template visual QA, figure-caption validation, and final DOCX scans for
  internal provenance leaks and user-provided forbidden phrases.
- Added academic figure guidance that separates deterministic source-data
  charts, Mermaid diagrams, and non-quantitative AI-assisted scholarly
  illustrations.
- Updated non-quantitative figure guidance so suitable engineering schematics,
  method diagrams, and concept illustrations are proactively considered instead
  of only allowed on request.
- Expanded the compact visual taxonomy for proactive non-quantitative
  academic, engineering, and business-report/corporate-report schematic assets.
- Clarified generated illustration insertion rules and business-report trigger
  wording so direct image assets do not conflict with figure manifests.
- Narrowed schematic guidance wording so business visuals remain report-bound
  and standalone image/diagram work routes to visual skills instead.
- Fixed controlled authoring so deterministic starter chart plans generated
  during prepare do not trigger future-stage scope violations, while manually
  preloaded future-stage figure plans remain blocked.
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
