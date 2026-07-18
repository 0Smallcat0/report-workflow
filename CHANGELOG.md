# Changelog

## 4.8.1 - 2026-07-18

### Fixed — first walls from the journal-paper dogfood

Started the next document-type iteration (an English mini-paper with real
literature citations) and fixed the two ingestion walls it hit immediately:

- **Literature notes classified as internal sources**: md/txt literature
  files landed in `internal_project_source`, so the academic path warned
  "no research_document evidence" forever and literature-backed claims were
  indistinguishable. Files whose name contains literature/reference/
  bibliography/文獻 — or whose blocks carry citation shapes like
  "(2014)." — now classify as `research_document`.
- **Wrapped bullets fragmented citations**: the list parser only absorbed
  lines starting with a bullet marker, so a citation wrapped across indented
  continuation lines split into several evidence blocks (one paper became
  three fragments). Continuation lines now stay in the bullet's block, in
  both list-parsing paths.

Verified on the paper run: literature rows classify as research_document and
each citation is one intact evidence unit. 401 tests and both benchmark
checks pass.

## 4.8.0 - 2026-07-18

### Added — revision plan expressiveness, from the real-proposal case

The real submission build needed three operations the revision contract could
not express: renaming a section heading (had to edit the input file by hand),
dropping a whole section (had to paste its full text into a `delete` change),
and wording-only fixes (had to attach fake claim/evidence links). All three
are now first-class:

- **`retitle` change type**: rename a section heading via `new_text`; applied
  to the original-title sidecar so the merged document renders the new
  heading. No `original_text` required.
- **`remove_section` change type**: drop a whole section, heading included —
  e.g. removing a per-school customization section from a submission copy.
  Explicitly recorded in the revision diff report (`removed_sections`) and
  exempt from the full-rewrite warning.
- **`"editorial": true` changes**: wording/punctuation-only edits carry no
  claim linkage. A deterministic guard holds the boundary — an editorial
  `new_text` may not introduce numbers or quoted spans absent from the text
  it replaces, or the plan hard-blocks with instructions to claim-link the
  change instead. Honest audit trail beats fabricated citations.
- Claim linkage is now enforced for non-editorial `replace`/`insert`/`delete`
  changes (the documented contract, previously unchecked); the revision diff
  report gains `removed_sections`, `retitled_sections`, and
  `editorial_changes` fields. Agent brief and skill reference updated; 8 new
  unit tests (401 total).

Acceptance: the research-proposal submission build now runs entirely on
native operations — `remove_section` for the customization section and two
`editorial` replaces — with zero input-file hacks and zero fake links, and
renders the identical submission DOCX.

## 4.7.0 - 2026-07-17

### Fixed — revise_existing works on real documents

Drove a real Chinese master's research proposal end-to-end through
`revise_existing` (the first real document this mode has seen) and fixed
every wall it hit. The mode's contract says the base document's structure is
authoritative and `revision_plan.json` is the only authoring surface — but
five separate gates still enforced the *new-draft blueprint* contract:

- **Chinese headings collapsed the section parser**: section ids were built
  by stripping to `[a-z0-9]`, so every Chinese heading slugged to empty and
  merged into one giant `preamble` (a heading mentioning "AI" became section
  `ai`). Ids now preserve CJK, strip Chinese ordinal prefixes (「一、」
  「（三）」), and map common Chinese headings (摘要/結論/參考文獻/…) to
  canonical ids.
- **Mangled headings in the revised output**: the merge rebuilt headings from
  slugs (`sid.replace("_"," ").title()`), turning 「一、研究背景與動機」 into
  "1. Introduction" and slug-word soup. The parser now writes a
  `base_document_titles.json` sidecar and the merge restores the original
  heading text.
- **Blueprint enforcement removed from the revision path** (new-draft behavior
  unchanged): OUTLINE_PLAN accepts base-document section ids and skips
  blueprint-required sections; SECTION_PLAN_FREEZE skips required-section and
  claims-per-section checks; SECTION_DRAFT no longer demands per-section
  draft files (revision never merges them); QA_GATE treats absent drafts as
  the contract; HEADING_CONTRACT_CHECK downgrades blueprint heading findings
  to advisory.

Verified end-to-end: prepare → author (`claim_matrix`, `outline`,
`sentence_map`, two-change `revision_plan`) → validate (qa=pass) → render,
with the original Chinese headings, both revisions applied, and all facts
intact in the final DOCX. 393 tests, seven-profile benchmark, and the
adversarial check all pass.

## 4.6.0 - 2026-07-16

### Fixed — pain points from a real end-to-end dogfood run

Walked a realistic Chinese tensile-test lab report (handout + measurement CSV)
from `prepare` through authoring to rendered DOCX, and fixed what actually
hurt:

- **Chinese chart text rendered as tofu boxes**: matplotlib's default font has
  no CJK glyphs, so every Chinese title/axis-label/legend in a generated
  figure was unreadable. The figure builder now prepends a CJK-capable font
  chain (Microsoft JhengHei / Noto Sans CJK / PingFang / SimHei) with DejaVu
  fallback, and disables the U+2212 minus. Verified visually on a rendered
  chart.
- **Measurement data typed as qualitative evidence**: evidence typing was
  English-keyword-only, so CSV rows (JSON-serialized) and Chinese sources fell
  through to "qualitative" — which blocks statistical claims (FB requires
  quantitative backing) and caps wording strength on the user's own
  measurements. Typing now recognizes numeric-dense structured rows as
  quantitative and includes Chinese keyword sets for
  quantitative/methodological/contextual.
- **Every section title rendered twice** ("1. 封面" + "封面"): the merge step
  emitted the canonical heading and kept the draft's own title heading. The
  inner duplicate is now dropped; each section has exactly one heading.
- **`--preflight-decisions` file with a UTF-8 BOM was rejected**: PowerShell
  5.1's `-Encoding utf8` always writes a BOM, so the file a Windows user
  naturally produces failed to parse. Now read with `utf-8-sig`.
- **Preflight error told you the shape but not the how**: the block now ends
  with a copy-paste `how_to_proceed` example (write `preflight.json`, pass
  `--preflight-decisions preflight.json`).
- **Stale console-script shim dies silently** (multi-Python Windows PATH):
  added `python -m report_workflow` as a PATH-independent entry point and a
  README troubleshooting note.

Known issues found in the same run, documented for later: the auto figure
plan can mix units on one axis and titles charts "Bar view of <dataset>"
(agents should edit `figure_plan.json`, as the briefs instruct), and the
auto-generated data-source reference entry is stylistically odd for lab
reports.

## 4.5.0 - 2026-07-16

### Changed — output quality round (rendered documents, not gates)

- Audited real rendered benchmark reports and removed every machine-writing
  tell found, across all seven profiles:
  - **Prose Quality contract** added to the generated agent task briefs and
    `agent_skill/reference/authoring.md`: translate data identifiers into
    plain language with units, state grounded numbers instead of writing
    around them, keep internal ids out of body text and captions, write
    captions that describe the finding (not the chart mechanics), and vary
    figure lead-ins instead of repeating a template sentence.
  - **Benchmark showcase prose rewritten** to follow that contract: real
    measurements in the abstract/results/calculations ("28 to 20 minutes per
    note", "7.5% to 4.1%", "71% to 84%") instead of snake_case field names
    and a phantom "measurement table"; five distinct figure lead-ins and
    human captions written from what each fixture dataset actually contains;
    publication-facing figure ids renumbered to "Figure 1..5" (the
    recommendation id keeps the audit trail) so no `figrec_*` or
    `chart_*_source` token can leak into a rendered document.
  - **Dangling empty References heading fixed for real**: the render-time
    guard now matches the heading at any level (upstream drafts carry
    `# References`, normalized drafts `## References`) and at end-of-file
    without a trailing newline — the exact case that shipped. A report with
    no references now simply has no References section. 10 regression tests
    cover both render paths and the EOF edge (378 -> 388 total).
- Regenerated the full seven-profile benchmark evidence from the new fixtures;
  all profiles pass end-to-end and the rendered documents scan clean for
  snake_case identifiers, internal ids, template repetition, and dangling
  headings.

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

### Packaging

- Prepared PyPI distribution: reframed the package summary to the
  anti-hallucination positioning (was "…NotebookLM integration"), added
  discoverability metadata (keywords, trove classifiers, author, and
  `[project.urls]` for homepage/repo/changelog/design-doc/issues), and
  verified the built sdist + wheel pass `twine check` and install-and-run
  cleanly (`verify()`) in a fresh environment.
- Added a Trusted-Publishing release workflow
  (`.github/workflows/release.yml`): pushing a `vX.Y.Z` tag runs a guard job
  (tag must equal `report_workflow.__version__`; benchmark `--check`s and unit
  tests must pass), builds and `twine check`s the distributions, then publishes
  to PyPI via OIDC — no stored token or secret. One-time PyPI pending-publisher
  setup and the release procedure are documented in `docs/RELEASING.md`.

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
