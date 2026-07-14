# Changelog

## 4.4.0 - 2026-07-15

### Added

- Out-of-domain benchmark (`scripts/run_external_benchmark.py`): runs the
  zero-schema `verify()` adapter over the public HaluEval QA dataset
  (Li et al., EMNLP 2023) — 10,000 knowledge-grounded pairs, 20,000 verdicts,
  zero tokens. Measured: 0.06% false-positive rate (6/10,000 right answers
  blocked, each one inspected and characterized: five title/address numerals
  parsed as measurements, one dataset concatenation artifact), 99.7% precision
  per block verdict, 23.2% overall recall, 66.7% recall on the numeric subset
  where the FE gate has purchase. Framing is stated in the script docstring
  before the numbers: HaluEval's entity-swap hallucinations are the documented
  out-of-scope class (docs/DESIGN.md §6), so the out-of-domain claim is the
  fail-closed discipline, not the recall. The 6 MB dataset is fetched on
  demand (`--download`, sha256-pinned, gitignored under
  `benchmarks/external_data/`), archived evidence lives under
  `benchmarks/evidence/halueval_qa_2026-07-15/`, and `--check` recomputes all
  20,000 verdicts against it. Not wired into CI (network dependency); 10 new
  offline contract tests cover the scoring logic and archive consistency
  (368 -> 378 tests).

## 4.3.0 - 2026-07-14

### Added

- Zero-schema verification adapter `report_workflow.verify(answer, sources)`
  (`src/report_workflow/verify.py`): pass a plain LLM answer string plus plain
  source texts (a string, a list, or an `{id: text}` mapping) and get
  per-sentence deterministic verdicts from the same FA/FB/FE gate stack the
  pipeline enforces — no claim matrix, no sentence map, no evidence ledger to
  author. Sentence splitting handles English and CJK terminators, bullets, and
  newlines; `[id]` / `[CITE:id]` markers scope a sentence to the cited
  sources; a marker with no matching source hard-blocks as a fabricated
  citation; unmarked sentences are verified when any single source fully
  grounds them and fail closed otherwise. This is the RAG-answer use case in
  five lines, aimed at CI checks and agent loops that cannot afford
  LLM-as-judge costs or nondeterminism.
- `report_workflow.__version__` now tracks the package version (was stale at
  4.0.0) and `verify` is exported at package top level.
- The Colab quickstart notebook now demos `verify()` instead of the
  structured-claims payload, matching what a first-time user has in hand.

## 4.2.0 - 2026-07-14

### Changed

- Hardened the FE deep-audit content-overlap gate, closing three documented
  evasions from the adversarial corpus and lifting measured recall from 80.0%
  to 89.5% (34/38) at an unchanged 0% false-positive rate:
  - **Precision inflation**: a claim number within the 1% tolerance may no
    longer state more decimal places than the evidence value asserts
    ("3.53%" against evidence "3.5%" now blocks; equal-value roundings such
    as "12.40" vs "12.4" still pass).
  - **Short fabricated quotes**: the quote scanner floor dropped from 10 to
    4 characters, so `"audited"`-style one-word fabrications are checked
    verbatim against evidence like any longer quote.
  - **Cross-language laundering**: a non-CJK claim citing CJK-heavy evidence
    now falls back to the English key-term check instead of passing
    unexamined; bilingual evidence rows still pass via their embedded English
    terms. Deliberate cost, documented in `docs/DESIGN.md`: honest *translated*
    claims block under deep audit — the supported pattern is same-language or
    bilingual evidence rows.
- Adversarial corpus grown from 54 to 58 cases (20 honest controls, 38
  hallucinated claims, 13 attack families): the three closed evasions were
  promoted to regular attack families (`precision_inflation`,
  `cross_language_mismatch`, and two short-quote cases under
  `fabricated_quote`) with paired variants, plus a new honest control pinning
  the 4-character quote floor against false positives. Archived evidence moved
  to `benchmarks/evidence/adversarial_2026-07-14/`; the recall floor asserted
  in tests rose from 0.75 to 0.85. Remaining documented evasions: bare
  numbers without units, negation flips, hedged reinterpretation, value
  misattribution.

## 4.1.0 - 2026-07-10

### Added

- Adversarial anti-hallucination benchmark
  (`scripts/run_adversarial_benchmark.py`): a 54-case hand-audited corpus
  (19 honest controls, 35 hallucinated claims across 11 attack families plus
  7 documented evasion variants) run through the exact factuality gate stack
  (FA/FB/FE/FD). Reports 80% recall at a 0% false-positive rate, catch rate
  per attack family, two baselines on the same corpus (`no_gate`,
  `citation_presence`), and a sha256 determinism proof. Archived evidence
  lives under `benchmarks/evidence/adversarial_2026-07-10/`; `--check`
  re-runs everything from source and fails on any drift (also used as the
  regression gate in CI). Documented evasions (bare numbers without units,
  negation flips, within-tolerance precision fudging, sub-10-character
  quotes, hedged reinterpretation, value misattribution, cross-language
  citations) are kept in the corpus as the measured residual-risk boundary.
- MCP server (`report-workflow-mcp`, `src/report_workflow/mcp_server.py`)
  exposing the deterministic gates to any MCP-capable agent: `verify_claims`
  (full FA/FB/FE/FD verdicts with the gate and reason per claim),
  `list_report_profiles`, and `get_workflow_status`. Installed via the new
  optional extra `report-workflow[mcp]`; documented in `docs/mcp.md`.
- Design document (`docs/DESIGN.md`): hallucination threat model mapped to
  gates, architecture rationale, measured evaluation results, determinism
  properties, and an honest limitations section derived from the documented
  evasions.
- Zero-install entry points: a GitHub Codespaces dev container
  (`.devcontainer/devcontainer.json`, installs pandoc and runs the gate demo
  on create) and a Google Colab quickstart notebook
  (`docs/quickstart_demo.ipynb`).

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
