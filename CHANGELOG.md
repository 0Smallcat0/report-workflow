# Changelog

## 4.23.0 - 2026-07-25

### Fixed — Chinese documents no longer carry English sentence spacing

Running the Chinese half of the guidance loop (the beam lab report
rewritten to the reader rubric and the structure discipline) exposed a
typography defect that only becomes visible once paragraphs hold several
sentences: Chinese sentences were separated by a space.

Each authored sentence is its own markdown line, and pandoc turns an
intra-paragraph newline into a space — correct for English, wrong for
Chinese, which takes no inter-sentence spacing. Stripped internal-source
markers left the same gap mid-line ("轉動。 千分錶"), as did authored
citation markers ("4.8%。 [1]"). Chinese documents now get a typography
normalization pass before rendering: CJK-to-CJK gaps close, spacing
between Chinese and Latin ("撓度 1.52 mm") is left alone, and tables,
headings, lists, and code fences are untouched. English documents skip
the pass entirely and render byte-identically.

Also verified in this pass: Chinese derived statistics (4.21.0) reach a
rendered document for the first time — the discussion cites the
least-squares slope, R², and mean error in Chinese — and the 4.22.1
duplicate-citation fix holds on the Chinese path.

463 tests, both benchmark --checks, and native end-to-end reruns of both
the Chinese and English lab reports pass.

## 4.22.1 - 2026-07-25

### Fixed — doubled citation markers, found by writing to the new guidance

The 4.21/4.22 quality guidance had only been verified as far as "the text
appears in the brief". Closing that loop — authoring the beam lab report
*following* the reader rubric and the structure discipline, then rendering
it — surfaced a defect the old list-style prose never triggered.

A sentence citing two evidence rows from the same source carries two
separate `[CITE:...]` markers. Each resolves independently, so the
document rendered "[1] [1]". The existing deduplication only covered ids
inside a single marker, which is why the duplicate survived. Adjacent
identical citations — numeric, author-year, or `[Source: ...]` — now
collapse to one marker.

The loop itself closed cleanly otherwise: 24 synthesis sentences (topic
and concluding sentences carrying no citation of their own) passed the
gates untouched, so the evidence contract does not stand in the way of
paragraphs built Context → Content → Conclusion. The discussion now runs
result → quantitative comparison → mechanism → verdict, citing the
derived slope, R², and error statistics from 4.21.0.

456 tests and both benchmark --checks pass.

## 4.22.0 - 2026-07-22

### Added — structure discipline from published writing standards

The reader rubrics shipped in 4.21.0 were professional judgment; this
release grounds the quality guidance in published, citable standards and
adds the piece none of the gates could give: how paragraphs and sections
should be *built*. Every authoring brief now carries a "Structure
Discipline" section:

- **The paragraph rule** (Kording & Mensh, *Ten simple rules for
  structuring papers*, PLOS Comput Biol 2017): every paragraph runs
  Context → Content → Conclusion — first sentence says what it is about,
  last sentence says what to remember. A run of parallel evidence
  sentences with no concluding sentence reads as a list, not an argument.
- **Per-profile recipes**: lab discussions follow the university-rubric
  pattern (result → quantitative comparison → mechanism → verdict against
  the acceptance threshold; ASEE/WSU/NC State LabWrite); papers build each
  results paragraph around its figure (Whitesides, Adv. Mater. 2004) with
  one central contribution; proposals and business reports lead with the
  answer and open as SCQA (Minto, The Pyramid Principle); admissions
  documents develop 2-4 defining experiences in depth instead of listing
  everything (MIT EECS CommLab, Cornell Graduate School).

The web research also validated the 4.21.0 rubrics themselves — quantified
comparison, mechanism over restatement, answer-first, incidents over
adjectives all match the published guidance; sources are now cited in the
code. Guidance only: no new gates. 451 tests and both benchmark --checks
pass.

## 4.21.0 - 2026-07-22

### Added — aim at "good", not just "not wrong"

Direction correction from the maintainer: traceable-to-evidence is the
entry ticket, not the goal — the goal is a document the reader rates
highly (a professor grading a lab report, a manager reading a status
report, a committee reading an application). Two mechanisms push toward
that, neither of them a gate:

- **Reader rubrics in the authoring brief.** Every profile's brief now
  carries a "How the Reader Grades This" section: what the course
  professor, peer reviewer, decision-maker, manager, or admissions
  committee actually rewards (quantified comparison over description,
  mechanisms over restated numbers, conclusion-first for managers,
  incidents over adjectives for admissions). The writing is aimed at a
  grade, not just at passing the gates.
- **Derived statistics as citable evidence.** The quantitative analysis a
  grader looks for — least-squares slope versus the theoretical slope, R²,
  error range and mean — cannot come from the authoring agent, because a
  number with no evidence behind it is exactly what the factuality gates
  block. EVIDENCE_BUILD now computes these from structured measurement
  rows (columns matching measured/實測, theoretical/理論, error/誤差) and
  records them as regular high-grade ledger entries with the method noted;
  the brief lists them under "Derived Statistics (citable)". Chinese
  columns produce Chinese entries.

End-to-end on the beam case: the final document's discussion now states
the fitted slope (0.298 vs 0.29 theoretical), R² = 0.9999, and the mean
error of 3.5% — all through the citation and factuality gates. Sources
with no matching columns are byte-unchanged. 448 tests and both benchmark
--checks pass.

## 4.20.0 - 2026-07-22

### Fixed — the English revise dogfood: a revision keeps the base document's shape

An English revise case (an old lab-report draft: correct a wrong error
figure against the CSV, retitle, drop a "Notes for Instructor" section,
polish informal wording — with a user template) found the sixth and seventh
members of the "revise wrongly inherits the new-draft blueprint contract"
family from 4.7.0. Chinese revisions never tripped them because Chinese
section ids share nothing with the blueprint; a partially-overlapping
English document did:

- SECTION_DRAFT rejected sentence-map entries anchored to base-document
  sections (`results`) because its section universe was
  blueprint ∩ outline; base sections are now registered in revise mode
  (the same guard outline_plan already had).
- REVISION_APPLY emitted blueprint-matching sections first, so the base
  document's Conclusion was hoisted above its Introduction. Revised
  documents now keep the base document's own section order.
- HEADING_CONTRACT_CHECK still ran the canonical rewrite in revise mode,
  renumbering whichever base sections happened to share blueprint ids
  ("9. Conclusion"). Revise mode now keeps base headings verbatim.
- The revised document's title (the base H1, retitle-aware) is emitted
  again — it vanished whenever the profile had no required front matter —
  and the TOC now follows the title instead of sitting on top of it.

Verified end-to-end: all four change types applied (claim-linked number
correction, retitle, remove_section, two editorial rewrites), base order
preserved (title → TOC → Introduction → … → Conclusion), template fonts/
header/page numbers carried, zero CJK leakage. 443 tests and both
benchmark --checks pass.

## 4.19.1 - 2026-07-21

### Fixed — English lab reports no longer carry Chinese headings

The question "does the English side work too?" found the mirror of the
pre-4.10 wall: six blueprints are English-native with `title_zh` for
Chinese documents, but engineering_lab_report was Chinese-native — an
English lab report rendered "1. 封面" and friends into an otherwise
English document (confirmed in the archived English benchmark output).

- engineering_lab_report.yaml is now bilingual like the other six:
  `title` in English, `title_zh` carrying the exact Chinese strings the
  Chinese path always produced — Chinese output is unchanged.
- `localized_section_title` gained the symmetric defense: a Chinese-only
  `title` on a non-Chinese document falls back to the id-derived English
  title instead of leaking CJK headings.

Verified both ways end-to-end: the English benchmark lab case now renders
"1. Objectives … 4. Apparatus and Materials" with zero CJK paragraphs,
and the Chinese beam case is unchanged (centered cover, 目錄,
"1. 實驗目的", 表 1). 442 tests and both benchmark --checks pass.

## 4.19.0 - 2026-07-21

### Changed — the cover is a title page, not "1. 封面"

Cover-led profiles (the engineering lab report) rendered their cover as a
numbered body section: a "1. 封面" heading, listed in the TOC, pushing real
sections' numbers up by one. Now:

- Section numbering skips the cover (same convention as Abstract and
  References), so the first real section is "1." again.
- The renderer promotes a leading cover section to a title-page block: the
  heading is dropped (a cover page does not label itself, and without a
  Heading 1 it stays out of the TOC field) and its paragraphs render
  centered. The TOC follows the cover, then the body starts on a new page.
- Front-matter documents and coverless documents are unchanged.

Verified end-to-end on the beam lab case with a user template: centered
cover text first, 目錄 second, "1. 實驗目的" third; native table and
caption conventions from 4.18.0 unaffected; QA pass. 439 tests and both
benchmark --checks pass.

## 4.18.0 - 2026-07-21

### Changed — table figures are real Word tables now

Table-type figures used to render as matplotlib PNGs: not selectable, not
copyable, and blind to the reference template's table styles. FIGURE_BUILD
now emits a native-table manifest entry (`render_mode: "native_table"`, no
rasterization) and DOCX_RENDER turns it into a markdown pipe table, so
pandoc produces a real `w:tbl` that follows the document's table style.
Captions follow table convention — 「表 N.」 for Chinese documents,
"Table N." for English — placed above the table.

POST_RENDER_VALIDATE's embed accounting understands the split: native
tables are expected as Word tables rather than embedded images, and the
outline-declared figure bound is reduced accordingly.

Fallback: a table figure whose data lacks columns/rows still renders
through the matplotlib path.

Verified end-to-end on the beam-deflection lab case with a user template:
final.docx carries one w:tbl (TableGrid style), a 「表 1.」 caption,
correct cells, zero embedded images, QA pass. 439 tests and both benchmark
--checks pass.

## 4.17.0 - 2026-07-21

### Fixed — template dogfood round

A realistic department-format template (標楷體, 2.5 cm margins, course-name
header, page footer) went through the full pipeline on a beam-deflection lab
case. Template fidelity held — fonts, margins, header/footer, and the
localized TOC all carry into the output. Four walls fell along the way:

- **The user's own measurements could never grade high.** Provenance scoring
  only rewarded publication signals (peer review, citations, PDF/DOCX
  first-hand bonus), so a CSV of the user's measured data capped at
  evidence_grade=medium and the FD gate forbade measured wording on the very
  numbers the report exists to state — while the agent brief promised the
  opposite for quantitative evidence. Structured numeric rows now earn the
  same language-neutral quantitative bonus `determine_evidence_type` already
  uses (score 0.6 → 0.75 = high). Same root-cause family as 4.6.0's P5,
  thirty lines away in the same file.
- **TOC placement for cover-led documents.** Engineering lab reports open
  with a 封面 section instead of front matter; the TOC field now lands after
  the cover section rather than on top of it.
- **Figure captions hardcoded "Figure N."** Chinese documents now get
  「圖 N.」 — both the placeholder path and the mermaid path.
- **Table figures fell back to "Table view of X" titles.** Tables carry no
  series or axis labels, so the title humanizer now reads the column names:
  「實測撓度(mm), 理論撓度(mm)(依荷重(N))」.
- CLAIM_PLAN's claim-role errors named academic_paper regardless of the
  actual profile; they now report the run's profile.

Verification: fresh prepare→author→validate→render with zero authoring
workarounds; 437 tests; both benchmark --checks pass.

### Known items

- Table-type figures render as PNG images, not native docx tables, so a
  user template's table styles do not apply to them.
- The cover section renders as a numbered body section ("1. 封面"), not a
  standalone title page.

## 4.16.2 - 2026-07-21

### Removed — the unwired quality gates, resolved

Decision on the 4.16.1 open question: deleted rather than wired.

- `consistency_check` + `guideline_check` and their 14 tests. Functional but
  unreachable, and wiring them was rejected on three grounds: the project's
  standing "improve output quality, don't stack more verification" ruling;
  CONSORT/PRISMA/SRQR are clinical/systematic-review reporting guidelines
  none of the seven supported document types belong to; and cross-section
  numeric consistency is already enforced by evidence binding (every number
  must trace to evidence, so two disagreeing sections cannot both pass).
- The write-only severity chain that existed only to feed them:
  `ReportPolicy.load_hard_guidelines`, `GuidelinePolicy.hard_guideline_ids`
  (constructed four times, read zero times), and
  `configs/guideline_severity_policy.json`.
- Four remediation-router rows that routed failure reasons to stages that
  do not exist (CONSISTENCY_CHECK, GUIDELINE_CHECK, STYLE_LINT,
  RESEARCH_RETRIEVE), plus stale stage-position comments in
  section_role_check.

Kept: `guideline_select` and the `guidelines/*.json` packs — they are wired
into prepare and feed agent-visible authoring guidance, which serves writing
quality rather than post-hoc verification.

- README test badge 445 → 431.

## 4.16.1 - 2026-07-21

### Removed — debt sweep after two same-day releases

- `_render_via_pandoc`'s dead `toc` / `number_sections` parameters: the TOC
  moved to injected-field form in 4.15.0, leaving `--toc` branches that no
  caller ever enabled.
- 22 unused imports across 18 modules (AST scan; zero textual references
  each). That includes run_workflow's imports of `run_consistency_check` /
  `run_guideline_check`, whose comment claimed they were "kept for explicit
  quality command" — no such command exists.
- CLI: the `--reference-docx` validation block was pasted three times; now
  one `_reject_invalid_reference_docx` helper.

Known state, documented rather than hidden: `consistency_check` and
`guideline_check` are functional, tested library modules that no pipeline
stage runs. Wiring or removing them is a product decision, not a cleanup.

## 4.16.0 - 2026-07-21

### Added — bring your own template

`--reference-docx your.docx` on CLI `prepare`/`render`/`run`, and
`reference_docx` on the agent tools `start_report_task` /
`submit_and_publish_report`: the rendered document follows the user-supplied
Word template's styles — fonts, sizes, margins, header/footer (including its
page-number setup), and table styles — instead of the built-in look. Section
structure still comes from the report profile and every content gate still
applies.

Fail-closed by design: a missing or unreadable template, or a pandoc-less
environment (the python-docx fallback cannot apply templates), hard-blocks
the render rather than silently shipping the default formatting. The
template path persists in the run spec, so later re-renders keep it.

### Changed

- README "Reference templates" documents the flag; README test badge
  440 → 445.

## 4.15.0 - 2026-07-21

### Added — baseline manuscript formatting

An audit of shipped documents against real-world document standards found
the content layer solid and the formatting layer missing three basics:

- **Page numbers.** The pandoc reference template now carries a centered
  PAGE-field footer; every rendered document gets page numbers.
- **Table of contents in the right place, in the right language.** `--toc`
  placed the TOC ahead of the title page and hardcoded "Table of Contents".
  The renderer now injects the TOC field after the front matter instead:
  title page first, heading localized (目錄) for Chinese documents, page
  breaks around the TOC.
- **TeX math verified.** `$...$` renders to native OMML equations through
  pandoc; a regression test pins it (skipped where pandoc is absent).
- **CJK front matter parsing.** `作者:`/`標題:`/`單位:` labels now parse
  from Chinese prompts; dense CJK titles are no longer rejected by
  latin-length thresholds. English parsing unchanged.

### Fixed

- `__version__` had drifted to 4.9.0 while pyproject said 4.14.0 — the
  release-tag guard would have refused the next tag. Both now read 4.15.0
  and a version-sync test pins them together.

### Changed

- DESIGN.md documents the formatting boundary: venue templates (two-column
  layouts, LaTeX, per-school thesis rules, non-APA citation engines) are
  explicitly out of scope; the contract is that content survives the pour
  into a venue template.
- README test badge 430 → 440.

## 4.14.0 - 2026-07-20

### Fixed — one more place the CJK word count was wrong

`SCHOLARLY_QUALITY` counted academic title length with `\b\w+\b`, the same
pattern that broke Chinese abstracts in 4.11.0. A Chinese academic title
scored 1 "word" against a 5-22 range and was flagged on every run. Both call
sites now share one CJK-aware `count_words` in `report_workflow.language`.

### Removed — dead code audit

An AST + whole-repo reference audit found nine modules and ~30 symbols with no
reference anywhere in `src/`, `tests/`, `scripts/`, `examples/`, or
`benchmarks/`. All removed:

- `citation_formatters/` — a **second, stale APA formatter**. It predates the
  4.9.0 fabricated-citation fixes (no `(n.d.)` years, no bracketed file
  labels), so importing it would have reintroduced the exact bug that release
  closed. The live formatter is in `citation_bind.py`.
- `connectors/{arxiv,openalex,pubmed}_adapter.py` — superseded by the
  `ResearchBackend` ABC in `research_backends.py`.
- `prompts/{analyst,writer}_prompt.py` — pre-agent-era LLM templates; the
  workflow no longer calls models itself.
- `schemas/` — including a dead `ReportProfile` enum duplicating the live
  `profiles.py` selector, against the single-selector contract.
- `state.py`: `PlanState`, `SourcesState`, `SourceRegistryEntry`,
  `DraftsState`, `QAState`, `OutputState`, `workspace_root_for` — models that
  had drifted out of use while `ReportState` moved to plain dicts, plus a
  stale comment in `front_matter_build.py` explaining behavior via one of them.
- `project_identity_gate.DEFAULT_ADMISSIONS_PROJECT_IDENTITY` — an unused
  default that hard-coded one author's project vocabulary into a
  general-purpose tool.
- `factuality_check.run_factuality_check_fc` (self-described deprecated hook),
  two abandoned `heading_dedup` helpers (one documented itself as not
  working), nine unused pre-compiled regexes in `code_parser.py`, and unused
  helpers in `abstract_check`, `agent_tasks`, `reference_relevance_gate`,
  `research_backends`, `parse_validator`, and `intake_prompt`.

### Changed

- CJK character and Chinese-ordinal-prefix regexes lived in six modules in two
  different spellings; both now come from `report_workflow.language`.
- README test badge tracks the suite again (393 -> 430).

430 tests, both benchmark checks, and a native end-to-end revalidate/rerender
of the Chinese admissions document all pass.

## 4.13.0 - 2026-07-19

### Fixed — the starter figure plan no longer needs hand-repair

Backlog sweep after the document-type iteration closed. Every dogfood round
rewrote the auto-generated figure plan by hand for the same two reasons —
that repeated workaround was the last live product debt:

- **Machine-tell starter titles**: recommendations shipped
  "Bar view of chart_source"-style titles, which the prose-quality contract
  itself forbids in captions. Titles are now built from the chart's own
  series names and axis labels ("Effort hours by phase",
  「誤報率 (%)(依階段)」), falling back to the filename form only when no
  labels exist.
- **`figrec_N` shipped as the publication figure id**: the starter plan now
  renumbers figures `1..N` (the id agents must reference and captions must
  show), keeping `figrec_N` in `recommendation_id` as the audit link. The
  drafting brief's usage map numbers entries with the same shared validity
  rule, so brief guidance and starter plan always agree.

### Verified dead — two long-carried Windows quirks

- cp950 console crashes (P4): `main()` already reconfigures stdout/stderr to
  UTF-8 with replacement at entry; re-verified against a Chinese-path run.
- `python -m report_workflow --help` exit 255: not reproducible on the
  current entry point (`--help` exits 0, argparse errors exit 2); the
  original report traced to the stale-exe era. Both items are closed.

### Added

- README documents the Chinese-document capability (deterministic language
  detection, `title_zh` headings, CJK-aware gates) and the seven
  end-to-end-dogfooded document types.

426 tests and both benchmark checks pass.

## 4.12.0 - 2026-07-19

### Fixed — technical-document dogfood: internal references are legitimate outside academia

Technical-document dogfood round (a Chinese post-deployment system doc on the
`custom` profile — the last document type in the iteration queue) rendered
with its entire References section silently dropped: the body-reference
filter required publication-shaped entries (DOI / arXiv / venue token /
italics), and the body-refs fallback additionally required the citation
chain to have curated at least one publication reference. Both rules are
right for academic papers, where internal-file citations are junk — but a
technical document legitimately cites the approved proposal, the monthly
operations report, and the internal handbook.

- The strict publication-shape filter now applies only to academic profiles
  (`academic_paper`, `admissions_report`, `admissions_project_report`);
  other profiles keep authored reference entries (internal-artifact junk
  patterns still apply to every profile).
- For non-academic profiles the authored body references no longer depend
  on `curated_reference_count > 0` to survive into the rendered document.

Verified end-to-end: the technical document renders 摘要 / 1. 緒論 … 5.
建議事項 / 參考文獻 with all three internal references, the tuning figure,
and every grounded number (25→4 minutes, 18%→5% false alerts); no empty
appendix section. Academic-profile behavior unchanged. 423 tests and both
benchmark checks pass.

This closes the document-type iteration queue: lab report, research
proposal (revise), journal paper, work report, business proposal,
admissions report, and technical document have each been produced
end-to-end, with every wall converted into a product fix.

## 4.11.0 - 2026-07-19

### Fixed — admissions dogfood: Chinese abstracts and the last two English headings

Admissions-report dogfood round (a Chinese 備審 project report on
`admissions_project_report`, with a real HaluEval citation) hit two walls:

- **Chinese abstracts always "too short"**: the abstract word counter used
  `\b\w+\b`, which counts an entire Chinese clause as one word — a
  normal-length Chinese abstract scored 39 "words" against a 150 minimum and
  hard-blocked at METADATA_GATE. The counter is now CJK-aware (each CJK
  character counts as one word; English counting unchanged).
- **Abstract/References were the last English headings** in an otherwise
  fully Chinese document (the 4.10.0 known limitation). The canonical
  rewriter now emits the localized blueprint title for both (`# 摘要`,
  `## 參考文獻`); the citation chain keeps writing its internal
  `## References` marker, which DOCX_RENDER localizes at the final append,
  and every References-section matcher (body split, hanging-indent
  fallback, legacy strip) accepts the Chinese heading variants.

Verified end-to-end: the admissions docx renders 摘要 / 1. 緒論 … 7. 結論 /
參考文獻 with the HaluEval reference entry, embedded figure, all grounded
numbers, and zero marker leaks. English documents render byte-identically.
422 tests and both benchmark checks pass.

## 4.10.0 - 2026-07-19

### Added — Chinese documents get Chinese section headings

Business-proposal dogfood round (a Chinese pipeline-monitoring proposal on the
`proposal` profile) shipped a fully Chinese document wearing English headings
("1. Executive Summary" over Chinese prose) — and there was no way to fix it
from the authoring side, because MERGE_DRAFT derived headings from section ids
and HEADING_CONTRACT_CHECK's normalizer stripped CJK to empty slugs, so
Chinese headings could never even be recognized:

- **`title_zh` on every blueprint section** (proposal, business_report,
  academic_paper, admissions ×2, custom; engineering_lab_report was already
  Chinese-native). The blueprint stays the single source of heading truth.
- **Deterministic document-language detection** (`report_workflow/language.py`):
  CJK-dominant text → `zh`, same input → same answer in every stage, no
  checkpoint coupling.
- **MERGE_DRAFT and HEADING_CONTRACT_CHECK render localized titles**: a
  Chinese document now gets 「1. 執行摘要 … 10. 附錄」, an English document is
  byte-for-byte unchanged. The heading normalizer preserves CJK and strips
  Chinese ordinal prefixes (「一、」「（三）」), so agent-authored Chinese
  headings are recognized and the required-section check works for Chinese
  documents. Abstract/References headings keep their English special-case
  (citation-chain writers depend on the literal), noted as a limitation.
- **The drafting brief announces the document language** and lists the
  canonical Chinese headings, so agents write prose in the evidence's
  language instead of guessing.

Verified end-to-end: the same authoring artifacts that produced English
headings before the fix render the full Chinese heading set after it, with
all grounded numbers, the embedded figure, and zero marker leaks intact.

### Fixed — carried from the work-report dogfood (previously unreleased)

- **Chinese figure references counted**: figure-quality prose detection
  understands 「如圖 1」/「圖 2:」 forms, not just "Figure N".
- **Silent figure-build failures hard-block**: the rendered-manifest reality
  check now runs for every profile, so a figure plan whose build died no
  longer sails through validate with an empty figure.

415 tests and both benchmark checks pass.

## 4.9.0 - 2026-07-19

### Fixed — the anti-hallucination tool was fabricating a citation

Journal-paper dogfood round 3, closing the bibliography and re-authoring
backlog:

- **Fabricated bibliography entry**: the auto reference formatter cited
  project source files pseudo-APA style with the file stem as author AND
  title and `datetime.now().year` as the publication year — and "md" was
  missing from its type map, so markdown sources fell through to an
  unlabeled format that slipped past the publication curation filter and
  landed in a rendered paper as "literature. (2026). *literature*.". Years
  are now honest `(n.d.)`, every format carries the bracketed file label the
  curation filter keys off, and md is mapped.
- **Real citations silently dropped**: publication candidacy required a
  venue token (journal/press/…), DOI, or arXiv id, so "Notices of the AMS,
  61(5), 458-471." was discarded. An article-shaped reference — "(year)."
  plus volume(issue), pages — now qualifies.
- **Re-authoring now takes effect** (the four-manual-workarounds trap): when
  `structured_drafts.json` is newer than the compiled `sentence_map.jsonl`,
  SECTION_DRAFT recompiles instead of letting stale compiled drafts stay
  canonical.

Verified end-to-end on the paper run with no manual cache surgery: exactly
the three authored citations render (junk entry gone, Pseudo-mathematics
restored), zero CITE leaks. 401 tests and both benchmark checks pass.

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
