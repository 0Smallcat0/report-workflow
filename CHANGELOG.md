# Changelog

## 4.34.0 - 2026-08-07

### Added — one request now returns a whole table, and two files can be joined first

Every derivation operation returned a single number, so a six-band price table
with three columns cost eighteen registrations. A real run spent 117 of them to
produce three tables; an unassisted write-up of the same three CSVs built
thirteen tables by hand and put 703 numbers in the body against the tool's 238.
The shape of the request was the cost, not the analysis.

`register_derived_evidence` now takes `group_by` and `measures` and returns a
grid — one row per group, one column per measure — registered as a single
evidence entry:

```json
{"id": "price_band_reliability", "source": "products.csv",
 "group_by": {"column": "price", "buckets": [0, 30, 50, 100, 200, 400]},
 "measures": [{"op": "count"},
              {"op": "mean", "column": "rating"},
              {"op": "share", "rows": "rating < 4"}]}
```

Bucket edges stay the author's. Where a price axis is cut is an analytical
judgement and a tool that guesses it is wrong in a way the reader cannot see.

`source` also accepts two files with a `join`, which is the only route to a
finding neither file states alone. Joining 473 reviews back to the product
catalogue on `asin` shows the $100–200 band averaging 4.09 stars — the worst of
six — from buyers' own words rather than from listing metadata. Rows that find
no partner are counted and reported in the evidence text; a column name present
on both sides is renamed rather than silently overwritten.

### Added — the crossings nobody had to ask for

Each categorical column is now crossed with the numeric ones at intake: counts,
share, mean and median per group. Numeric axes are never auto-binned, for the
reason above. Every derived entry records `origin` (`auto` or `requested`), so
how much aggregation the author still had to register by hand is measurable
rather than anecdotal.

A grouped table carries its grid, so `[TABLE:<id>]` places it in the document
as a real Word table with its provenance underneath, instead of the author
retyping numbers that would then be backed by nothing.

### Fixed — the brief described a world with no derived evidence in it

Derived rows are appended to the ledger, so they land past the twenty-row
sample the brief shows — every one of them, always. An author reading only
that table saw a ledger in which the sole citable thing was one product row.
They are now listed in full, in their own section, split by `origin`, in the
claim brief as well as the drafting brief, each with the exact `[CITE:]` and
`[TABLE:]` markers to use; and both briefs now state that
`register_derived_evidence` exists, with a worked `group_by` and `join` example.

### Fixed — registering evidence no longer strands the run that registered it

Registering appends to the ledger, which moves the ledger hash, which made
every already-accepted artifact stale — and the stage that owns those files was
behind the current one, so the only advice on offer was to restore the stale
content. A run died there and had to be restarted. Accepted artifacts stamped
with this same job are now re-stamped against the current ledger and the
harness is told the re-stamped file is the accepted one.

The message for that case also prescribed
`remap-evidence --from-job <old>`, which is advice for a different situation:
there is no old job when the evidence was added minutes ago by the same run.
A stamp naming a genuinely different job still gets the remap advice.

### Fixed — the drafting brief omitted the figure placement contract

A planned figure that no section places does not render, and the run came back
`expected 3 Word table(s), found 0`. The three-part contract — plan entry,
`figure_ids` in the outline, literal `[FIGURE:<id>]` marker in the Markdown —
is now stated in `03_section_draft.md`, where it was documented only in
`reference/figures.md`.

### Fixed — a Chinese word is not a quantity

A lone 一/兩/三 with no unit after it was read as a number, so 「兩者」,
「三欄」 and 「一致」 became claim values 2, 3 and 1 that no evidence stated,
and correct sentences were blocked. The same character in front of a unit —
三筆, 兩年 — still counts. On the adversarial corpus one block loses its
spurious numeric reason and keeps its real one; recall and false-positive rate
are unchanged.

### Fixed — the starter figure plan was the ledger reprinted as a picture

The default plan proposed charts titled `title and 10 other measures by asin`
whose series were Amazon tracking URLs and thumbnail links. Identifier and link
columns are now dropped from chart candidates — but only when at least two
columns survive, so a reading indexed by sample id or a single column of
observations is still charted — and the derived cross tables are offered ahead
of raw per-record rows.

### Fixed — five false blocks the acceptance run walked into

An independent run of the full pipeline over the three fixture CSVs hit nine
factuality blocks. Four were the gate doing its job, including one where the
author's own arithmetic gave 27.20% and the rows gave 27.21%. The other five
were the checker being wrong:

- **A number written straight after a Chinese comma was invisible.** The text
  is NFKC-normalised, which folds `，` to `,`, and the lookbehind that stops
  "1,234" matching at "234" then swallowed it. A draft that literally read
  「544 筆商品列，其中 119 筆…」 was reported as not stating 544 — in the single
  most common position a number appears in Chinese prose. Only a comma with a
  digit in front of it is a thousands separator now.
- **「DJI 一家就佔 92 筆」** was read as the quantity 1 with unit 家. 一 before a
  counter and then 就/獨/便 is a quantifier idiom meaning *alone*.
- **「六個價格帶」 was refused against evidence saying 「6組」.** 個, 組, 項, 筆 and
  種 state that something was counted and nothing else; the author was being
  required to adopt the pipeline's measure word to describe the pipeline's own
  table. A reading in 座 still does not support a claim in 公噸.

Adversarial recall stays at 88.6% with zero false positives.

### Fixed — the briefs stopped describing the ledger they were describing

After twenty-one registrations `01_claim_plan.md` still read
`Registered by request: none yet` and still carried a ledger hash two calls out
of date — the hash the brief tells the author to copy into `_contract`. The
briefs are now regenerated when evidence is registered, and whatever that
rewrites is re-accepted with the artifacts.

### Added — the fixtures the comparison runs on

`benchmarks/fixtures/drone_market/` holds the three CSVs the hand-written and
tool-written arms were both measured on: 544 products, 544 classified rows, 473
reviews. The measurement was unrepeatable while they lived in a scratch
directory.

The ledger-determinism repair shipped in 4.33.0 now has a test: the same
requests applied twice must leave the ledger's bytes identical.

## 4.33.0 - 2026-08-07

### Fixed — the timestamp moved, so the ledger hash moved, so nothing could publish

`apply_derived_evidence` recomputes each derived unit from the source rows every
run. That is deliberate: nothing on disk is trusted. But the run also minted a
fresh `created_at` each time, so every derived line was rewritten with only the
timestamp differing. The ledger hash moved with them, and each artifact stamped
against the previous hash was hard-blocked. Publishing chased a hash that changed
every time it was checked, so any run that called `register_derived_evidence`
could not reach a published document.

A timestamp is not a value. Regenerating it buys no safety and turns the hash
into a moving target, so an `evidence_id` now keeps the `created_at` it was first
registered with. The values are still recomputed from the rows on every run.

Found by running the tool end to end over raw CSVs — the path where a report is
written from data rather than from another report.

### Note on 4.32.0

4.32.0 was tagged with this defect and never reached PyPI: its release build
failed during a GitHub outage. Nobody could install it. It carries the derived
evidence, tabular-source citation exclusion and currency-prefix parsing added
since 4.31.0, and this release supersedes it.

## 4.31.0 - 2026-08-06

Ships everything in 4.30.0 below. That version was committed and tagged and
never reached PyPI — its release build failed, the tag was retired rather than
left pointing at a version nobody could install, and the work is released here
instead. Read the 4.30.0 section as part of this release.

### Fixed — a sentence that does not state what its claim asserts

A claim asserting "需約 US$500/噸的產品售價才達 10% IRR，capex 約 US$1,000/噸年
產能" was drafted as "需約 US/噸的產品售價 ... 資本支出約 US,000", the amounts
eaten by a shell expanding `$500` and `$1` as variables. FA checks that claim,
evidence and sentence are linked; FE checks the claim's numbers against its
evidence; nothing checked the leg the reader actually reads. Every gate passed
and it reached the delivered document.

Worse than a wrong number, because the sentence stays fluent. "每噸年產能約
US,000 的資本門檻" reads like finished prose and nobody stops on it; "US$9,999"
would have been caught.

FS compares per claim, not per sentence, against the union of the passages
carrying that claim's citation plus any figure or table its sections carry. A
claim is often written as two or three sentences and a sentence may set up
rather than restate, so demanding that each repeat every figure would recreate
the "copy the source or be blocked" failure FE was just repaired for.

Beside it, a lint for the fingerprint a lost substitution leaves — a currency
marker with no amount. It needs no claim binding, so it also guards prose that
no claim covers. Only the symbol-prefix forms are flagged: `US$500/噸` mangles
to `US/噸`, while `USD/噸` is how a column header legitimately names a unit.

### Fixed — Chinese writes a rate with the denominator first

`每噸 500 美元`. The unit reader looked only at what follows a number, which is
where English puts it, so the numerator was found and the denominator dropped —
and a claim stating `500 美元/噸` did not match a draft saying `成本為每噸五百
美元`. Nothing about it was specific to Chinese numerals; the Arabic-digit form
failed too.

The third appearance of one failure: a Chinese way of writing a quantity goes
unrecognised, a gate refuses a correct sentence, and the author learns to copy
the source rather than write. So `tests/test_chinese_quantity_expressions.py`
now holds one corpus run against both readers of these strings, and it earned
its place immediately — the chart reader cannot read `每噸 500 美元` at all,
recorded as a failing-as-asserted gap.

Four shapes it must not join, each with a test: `每` followed by a number rather
than a measure word, two calendar words (`每年 3 月` is a date), no number at
all, and a clause boundary between the two.

### Fixed — the release, and the checks around it

`run_report_quality_benchmark.py --check` re-ran the pipeline, and the pipeline
renders a DOCX, which depends on the machine. The check that existed to prove
the result reproduces was the least reproducible thing in the repository. Both
arms are recorded now and `--check` re-scores fixed documents.

CI installed `.[mcp]` while every install instruction here says
`report-workflow[mcp,render]`, so it measured a configuration nobody ships. It
now installs what the plugin installs.

`scripts/check_version_sync.py` compares the four version strings in the tree
and, with `--pypi`, the tags and published releases. It caught the unpublished
4.30.0 tag on its first real run.

### Known — the fallback renderer drops the Sources section

Without pandoc, the python-docx path keeps References and loses the generated
evidence-trace list, so a reader who installed without the render extra gets a
document whose figures trace to nothing. Asserted as a defect in
`tests/test_evidence_traceability.py` rather than left to be rediscovered.

## 4.30.0 - 2026-08-06

Someone ran a 53,000-character Chinese market report — 39 external sources,
several data tables — through the whole pipeline and read what came out: 2,251
words, one table, no figures, no sources. Every gate passed. The document was
worse than the one they had written by hand.

This release is what that run turned up. The gates were never the problem; the
paths that carry a source's content into the deliverable were missing, and one
gate was actively pushing in the wrong direction.

### Fixed — a claim in Chinese had to copy the source word for word

FE bound each number to the characters following it. Chinese has no spaces, so
"the characters following it" is the rest of the sentence: the claim's
`8,259美元/噸的低點` was compared against the evidence's `8,259美元/噸` and did
not match. One particle was enough to block a true statement, and three correct
claims out of three were refused in the reported run.

The direction of that is the real defect. A gate that passes transcription and
blocks paraphrase rewards copying and punishes the synthesis a report exists to
do — it pointed away from the purpose of the tool it protects.

CJK units now come from a vocabulary, longest match first; ASCII units keep
their word boundary, so `226 edges` is untouched. The unit became optional,
because `2025-06` states two numbers and no unit and a claim citing that date
could never be matched while one was required. An unstated unit is treated as
unknown rather than as a unit named `""`; where both sides state one, the
comparison is exactly as strict as before.

Measured on the adversarial corpus: recall 86.4% → **88.6%**, false positives
still 0. One case moved — `x01`, a documented evasion recorded as *"invented
count evades FE because a trailing number without a unit token is not
extracted"*. Making the unit optional closed it. It is reclassified rather than
deleted, because the corpus is the record that the risk was measured before it
was removed.

A blocked number now says which of the two things went wrong: a value the
evidence does not state, or the right value under a different unit. Those had
one message between them, and an author could not tell whether they had
mis-written a figure or hit a gate that was too strict.

### Fixed — a column's unit is not always written in brackets

FE read a unit only from a halfwidth parenthetical or a bare `%`. Every other
header came back unitless, and because an unstated unit is compared as unknown,
the effect ran both ways: a CSV headed `recovery_rate_pct` blocked *every*
honest statistical claim about it, and a column that stated no unit accepted a
claim written in any unit at all.

Neither shape is exotic. `recovery_rate (%)` is what a person types;
`recovery_rate_pct` is what an export writes. `價格（USD/噸）` uses the brackets
a Chinese keyboard produces — U+FF08, which the halfwidth pattern never saw, so
a Chinese CSV stated no units anywhere in it.

Headers are now read from brackets of either width, square brackets, a percent
sign, or a trailing token that names a unit. Only tokens that *are* units are
accepted: `recovery_rate` still states none, because inventing one for it would
let a claim in any unit match the column.

Compound units are normalised per component, so a column headed `USD/噸` and a
claim written `美元/噸` agree — the same figure in the same unit, spelled by two
people. `USD/t` and `USD/kg` still disagree.

### Added — the sources a source file cites

One file counted as one source. A report citing thirty-nine houses arrived as a
single registry entry named after itself, and nothing anywhere read what it
cited: `publication_reference_list.md`, `publication_references.bib` and
`internal_source_appendix.md` were all zero bytes.

Nothing was broken — the path did not exist. It does now. Markdown links, bare
URLs, and Chinese attributions with no URL at all (`（來源：Fastmarkets，2026）`)
are read out of every parsed source into `cited_sources.json`, each carrying the
file, block and line it came from, deduplicated so a source cited five times is
listed once. They flow into the reference list and the BibTeX file.

An attribution with no link is kept deliberately. It cannot be clicked, but a
named house and a year is what a reader needs in order to go and check, and
dropping it would lose most of what a Chinese business report says about its own
provenance.

A citation whose URL ended in `.pdf` was being deleted by the curation filter as
"a local filename". Published reports are usually served as PDFs; the rule now
ignores anything inside a URL.

`SOURCE_APPENDIX_RENDER` used to return an empty string for two different
situations — a run whose sources genuinely cite nobody, and a run that read
thirty-nine citations and extracted none of them. The second is a defect and now
says so.

### Added — a source's own tables, and the numbers in them

Table rows were split for citation and never put back, so four tables in, zero
tables out. `[TABLE:<id>]` in a draft now rebuilds the grid from the ledger at
render time and prints the file and line span underneath it. The task brief
lists the available tables and says plainly not to retype one: a retyped number
is backed by nothing.

The chart recommender was refusing real data. `~80,000–85,000` and `~8,259` are
how price tables are written, and a column of them was reported as having no
reliable numeric measure — so an ordered time series came back as a table.
Approximation marks, en-dash and hyphen ranges, thousands separators, currency
prefixes, trailing units and `±` tolerances are all read now. A range is carried
as an interval and plotted at its midpoint, and **the caption says so**, because
a midpoint presented as a reading is a quiet fiction.

Magnitude suffixes are refused rather than stripped. Reading `12.4bn` as 12.4 is
not a tolerant parse, it is a wrong number stated with full confidence, and the
cell is reported as unreadable with the reason instead.

### Fixed — a figure that was planned and then dropped said nothing

`figure_plan_audit_report.json` recorded `recommendation_count: 4` and
`figure_count: 1` two lines apart, then `issues: []` and `status: passed`. Three
tables of already-extracted data disappeared without a word.

The check that could have caught it fired only when *every* figure was dropped,
and it was additionally gated on high confidence — which nothing had, because
the numeric parser above had degraded them all. Two defects covering for each
other. Unused recommendations are now reported one by one, with their titles and
their shapes, so the author can see what they are dropping. It stays a warning:
deciding a table is not worth printing is the author's call to make. The brief
now hands over the same titles and shapes up front, and says when the list it
shows has been truncated.

### Added — a benchmark for whether the report is any better

`python scripts/run_report_quality_benchmark.py --check`. Same source, same
prompt, two arms — a live pipeline run and a recorded write-up produced without
the harness — scored by one implementation across eight dimensions. Both arms
and the scorer are in the repository.

The harness wins six. It loses two, and they are reported rather than tuned
away: one of them, `verifiable_number_ratio`, rewards a document for stating
nothing checkable, which is a fact about the metric worth knowing. A test
asserts the losses stay recorded, so removing one requires saying whether it was
fixed or hidden.

## 4.29.1 - 2026-08-04

### Fixed — the stage that can fix it is the stage you are sent to

Driving the pipeline over MCP, a sentence cited a ledger row its claim did not
list. The sensible repair is to add the row to that claim — and
`claim_matrix.json` sits outside the drafts stage's write scope, so the only
move available was to weaken the sentence until it matched the contract. The
document bent to suit the harness.

Authoring failures routed back to themselves unconditionally. The harness
already knows how to rewind: `_invalidate_from` reopens a stage and everything
after it, and that is what a routed failure does everywhere else. This failure
now routes to the stage that owns the file, so the claim stage reopens and its
write scope comes with it.

Deliberately narrow: the routing matches the one message that gate writes, not
a general rule about stages. A broad match would rewind runs that stopped
exactly where they belong, and the guarantee this harness sells — one stage
writable at a time — is worth more than the convenience. No permission was
widened; the author still writes only the stage they are in.

The rejection text changed with it. It used to end by telling the author the
claim stage was closed to them, which was true when it was written and is not
now; it points at `get_controlled_next_action` instead of predicting the answer.

## 4.29.0 - 2026-08-04

### Added — the last manual install step is gone

Installing pandoc was the one thing left that a user had to do by hand, and
skipping it does not fail loudly: the renderer falls back to `python-docx` and
delivers a document with no real Word tables and none of the template's layout.
A first-time reader does not experience that as a missing dependency. They
experience it as a tool that produces mediocre documents.

- **`pip install "report-workflow[render]"` carries pandoc in the wheel.**
  `pypandoc-binary` ships the binary per platform, and `_find_pandoc` now looks
  there after the PATH and the known Windows install locations. A system pandoc
  still wins — it is the one the user chose, and it is usually newer. Kept an
  extra rather than a dependency: those wheels cover win_amd64, macOS
  x86_64/arm64 and manylinux/musllinux, so a core dependency would make
  `pip install report-workflow` fail everywhere else.
- **The plugin asks for both extras.** Its server command is now
  `uvx --from "report-workflow[mcp,render]" report-workflow-mcp`, so installing
  the plugin gets full-fidelity rendering with nothing installed by hand. The
  cost is a larger first run while uvx fetches the binary; it is cached after
  that.

Verified in a clean uv environment built from this commit: with only the
`render` extra, `_bundled_pandoc()` resolves to the binary inside the installed
`pypandoc` package.

## 4.28.2 - 2026-08-03

### Fixed — the MCP server could not start anywhere except this machine

The plugin installed and enabled in 4.28.1. Its server then said:

```text
plugin:report-workflow:report-workflow: uvx --from report-workflow[mcp]
report-workflow-mcp - ✗ Failed to connect
```

`mcp>=1.2` had no upper bound, and **mcp 2.0 removed `mcp.server.fastmcp`** —
the module `build_server` imports. Any clean environment resolved 2.0.0 and the
server exited before serving a single tool. The development machine had 1.28.1
from an older install, so every local check passed; CI passed too, because the
server tests skip themselves when that import fails. Green everywhere, unusable
everywhere else. The extra is now `mcp>=1.2,<2`, and a test that runs whether or
not the extra is present asserts the upper bound — the one check that would have
caught this.

- **The failure said the wrong thing.** `build_server` caught the ImportError
  and reported only "install the optional dependency", which is what someone
  reads immediately after installing it. It now quotes the actual error, so the
  next person sees `No module named 'mcp.server.fastmcp'` rather than being sent
  back to a step they already completed.

Verified in a clean uv environment built from this commit: mcp 1.29.0,
`mcp.server.fastmcp` imports, `build_server()` returns 13 tools.

## 4.28.1 - 2026-08-03

### Fixed — the plugin 4.28.0 shipped did not load

4.28.0 added the Claude Code plugin manifest written against the published
schema. Installing it said otherwise:

```text
Status: × failed to load
Error: Path escapes plugin directory: ./ (skills)
```

`"skills": "./"` was a reading of the documentation, not a tested value, and
Claude Code refuses it. The fix is the layout the default discovery already
expects rather than another guess at the field: the skill moved from
`agent_skill/` to `skills/report-workflow/`, and the manifest points at
`./skills`. Every reference in the repository moved with it — README, AGENTS.md,
the docs, the skill's own reference files, `scripts/render_skill_docs.py`, and
the tests.

`test_version_sync` now pins the skill directory name and the manifest's
`skills` value, because renaming that directory breaks installation and nothing
else, so no other check would notice. The marketplace entry also carries the
description `claude plugin validate` asks for.

Verified by installing it: `claude plugin marketplace add`, `plugin install`,
then `plugin list` reporting `Status: √ enabled`, with the plugin and
marketplace recorded in `~/.claude/settings.json`. The failure above is what the
first attempt actually printed.

## 4.28.0 - 2026-08-03

### Fixed — a job could be published from no directory at all

Found by driving the pipeline the way an installed plugin has to work: an agent
holding only the MCP tools, fresh sources, no checkout of this repository.

- **Relative paths are resolved where their meaning is unambiguous.**
  `output_dir` anchored to the package's own root, so a relative `--output`
  wrote the run inside the installation rather than where the caller stood,
  while source paths were stored exactly as given and re-resolved at PUBLISH
  against whatever directory happened to be current. Run from one place and the
  run is found but not its sources; run from the other and the sources are found
  but not the run. **The job could not be published from anywhere**, and nothing
  warned at prepare: the sources parsed, the ledger was built, and the block
  came after all the authoring was done. For an MCP server this is the default
  case, since the server's working directory is never the user's — for a
  pip-installed user, "relative" meant somewhere inside site-packages. A
  relative `--output` now anchors to the caller's directory, and sources are
  resolved to absolute paths at registration.
- **A rejection describes the mistake you actually made.** One message covered
  two different problems and named only the rarer one: a sentence citing
  evidence its own claims do not list was told its artifacts were stale from an
  older job, and pointed at `remap-evidence`, which cannot help. The two cases
  are now separated, and the misfiled one names the claims the sentence cites,
  the evidence those claims allow, and the fix that fits the current write scope.

### Added — install it the way an agent installs anything

- **The MCP server exposes the pipeline, not just the gate.** Thirteen tools
  instead of three: `check_environment`, `start_report`, `get_next_action`,
  `submit_action`, `query_evidence`, `lint_artifacts`,
  `audit_engineering_report`, `publish_report`, `submit_revision_plan`, and
  `preview_revision_diff`, beside the existing `verify_claims`,
  `list_report_profiles`, and `get_workflow_status`. No new capability — these
  delegate to the same `agent_wrapper` functions the CLI and the skill already
  call. They were simply never registered, so an agent that installed the
  server still had to clone this repository to produce anything.
- **A Claude Code plugin manifest and marketplace entry.**
  `/plugin marketplace add 0Smallcat0/report-workflow` then
  `/plugin install report-workflow@report-workflow` brings the skill and the
  tool server together. The version, the skill directory, and the server command
  are pinned by `test_version_sync`, because a plugin manifest is read at
  install time by something that is not this package and would otherwise rot
  unnoticed.

## 4.27.1 - 2026-08-03

### Fixed — a clean report was marked failed over a tool nobody asks you to install

Found by installing 4.27.0 from PyPI into an empty environment and running the
example, which is the first thing anyone reading the README will do.

- **An optional toolchain's failure is no longer the document's verdict.**
  `VISUAL_RENDER_CHECK` shells out to LibreOffice and Poppler. 4.26.0 already
  excluded their *absence* from the delivery verdict; a **broken** installation
  was not excluded, so a stale `soffice` shim on PATH made the check run, fail,
  and drag a report that passed every gate to `Overall status: failed` —
  in `published/qa/final_qa_summary.md`, the page AGENTS.md tells a reader to
  open first. The same failure text also reached the render-issue list quoted
  from a console in another encoding, so the stated reason was a row of
  replacement characters. The check is still run and still reported verbatim as
  `visual_render_status`; it no longer feeds `render_status`. Anyone who does
  want it enforced still has `strict_visual_render_check`, which hard-blocks
  inside the check itself.

The branch that was fixed and the branch beside it were written at the same
time; only the reported one was changed. That is the third time in this
repository that a defect's neighbour survived its fix.

## 4.27.0 - 2026-08-03

### Fixed — 118 rounds of using the product instead of reading it

The published version throughout this work was 4.23.1. Anyone who installed
from PyPI in that window got a build predating 4.24.0, where **a run carrying a
`.csv`, `.json` or `.docx` source could not be published at all**: reference
curation stripped the local-artifact label and the reference gate then
hard-blocked on a citation it no longer recognised. That fix, and the three
releases of work since, reach an installing reader only now. Cutting this
release is the point of it.

The 118 commits below were all found the same way — by running the product on a
real document until it stopped, then fixing what stopped it. Halfway through,
the framing changed from "I am already inside this workflow, where does it
leak" to "I have just found this repository, where does it stop me", and the
last two dozen entries come from that second question.

### Fixed — the files people actually have

- **Big5/cp950 sources open now.** Every source ever tested was UTF-8 because
  the tester wrote them; Excel on a Traditional Chinese Windows saves CSV as
  Big5 by default. Three separate reading paths were hard-coded to UTF-8 and
  now share one decoder (`utf-8-sig` → `utf-8` → `cp950` → `gb18030`). The
  worst of the three never failed: `parse_code` read with `errors="replace"`,
  so a Big5 file returned `success: True` with a body of U+FFFD, and the
  mojibake was admissible evidence. No `latin-1` catch-all was added — it
  decodes anything, which turns a broken file into silent nonsense.
- **A workbook is more than its first sheet**, and its title cell is not a
  column name. `openpyxl` is also a declared dependency now; it never was, and
  a clean install accepted `.xlsx` as supported and then could not open it.
- **Word and PDF tables survive the trip.** Merged header cells dropped one of
  the two readings beneath them, cells past the last column vanished without a
  word, a table continued onto page two named its columns after a reading, and
  an equation was dropped on the way in and rewritten on the way back. Table
  rows extracted from `.docx`/`.pdf` are citable one row at a time, as CSV rows
  always were.
- **A table pasted out of a spreadsheet is a table.** Tab-separated text glued
  into a note was swallowed by the paragraph above it and registered as one
  qualitative block — six readings, no chart, no statistical claim.
- **Broken attachments are described in your vocabulary, not this build's.** An
  empty `.md` was reported as "agent fallback parser is not implemented in the
  local MVP", a scanned handout was refused as if the file were corrupt, and
  three unreadable attachments were reported one run at a time — three
  round-trips for information the first parse already had.

### Fixed — Chinese was being checked in English

Thirteen rounds of Chinese documents ran through checks whose vocabulary was
Latin-only, so they passed by not applying.

- A number spelled in Chinese escaped the numeric check; a fabricated
  quotation was only scanned in English; the banned-phrase list had no Chinese
  entries; three figure checks and the duplicate-caption check never fired on a
  Chinese report; a Chinese claim citing English evidence got no vocabulary
  check at all.
- **Reference curation skipped Chinese reports entirely** — GB/T style returned
  before the filter ran, so every Chinese bibliography shipped uncurated,
  including the report's own `data.csv`.
- Revising a Chinese report renamed 摘要 to Abstract, and a Chinese heading was
  short enough to be discarded as noise; 備審資料 could not select the profile
  built for 備審資料; a Chinese header matched no term at all, so a trial
  counter was chosen as a chart axis; a Chinese paper could never be classified
  as literature, while the warning kept asking the author to attach the
  literature they had attached.
- CJK typography normalization was rewriting figure file paths — correct for
  prose, destructive for the one thing in the document that is not prose.

### Fixed — statistics with no referent

The derived-statistics layer computes what a grader looks for; each new
inference had to be asked what it would conclude on a different shape of data.

- A column held constant is a controlled variable, not an axis; three steady
  columns were multiplied into a statistic by accident; a curve was fitted
  against a column that never changed, and a measurement was regressed on its
  own row number. A rated/nominal column is now recognised as the reference
  curve it is, in both languages.
- **Evidence that certifies itself is no longer accepted**: a section heading
  could ground the claim that restated it, and a transcript question could
  ground the claim it was asking about. The same file attached twice became
  evidence twice, and padding a thin source set with duplicates cleared the
  source-base bar.
- A table nobody filled in was read as measurements; two of three thermocouples
  were destroyed at ingestion; a file name was cited as if it named the authors;
  a vault's bookkeeping and a note the author had hidden from themselves were
  both printed into the report.

### Fixed — revising your own report

- Revising deleted the figures and left their captions; took the author's name
  off the cover; and put an underscore through every numbered heading.
- A report being revised could not cite the measurements printed in it, and
  revising it destroyed its tables.
- Removing a section that held a figure could only pass by lying about it; a
  revision aimed at the wrong section id lost the sentence in silence;
  renumbering a heading changed which section it was; and adding a missed trial
  discarded every citation below it.

### Fixed — the package you actually send

- The delivery bundle shipped the scaffold beside the document, and the
  delivery summary answered "which file do I send" with a working copy. The
  client-readable note was neither readable nor the answer, and was written in
  the wrong language.
- A clean report came back marked "review" over two optional tools nobody had
  asked for.
- A source that moved before publish was dropped from the bundle in silence, a
  bundle could ship a source that no longer says what the report quotes, and of
  two same-named sources only one was packaged.
- Thirteen `[1]` markers shipped over an empty bibliography; a raw `[FIGURE:]`
  placeholder reached the final document; a figure could disappear from it
  without a word.
- **A delivered report no longer carries the machine that made it.** pandoc
  writes the image's source path into the picture's description, and a run
  directory is named after the prompt, so every report with a chart shipped an
  absolute local path *and* the author's prompt inside the `.docx`, where Word
  shows them in the picture's alt-text pane. The caption was already computed
  and already correct on the neighbouring element; `POST_RENDER_REPAIR` now
  hands it to the one that was holding the path. Found by scanning the sample
  document below before committing it, not by reading the code.
- **Your own template works on a finished report.** `--reference-docx` was
  refused on any report that had already rendered, because the guard demanded
  status `validated` and a delivered report is `completed` — strictly more.
  A course template's cover page also vanished without a word, and the
  template-fidelity report was checking the built-in template rather than the
  author's.

### Fixed — the first hour with the tool

- `prepare --output <dir>` put the run where it was asked and then `status`
  could not find it; `status` itself reported one of the four things the run
  needed; `diff` could not compare two checkpoints, which is what it is for;
  `remap-evidence` rewrote three artifacts and reported touching none;
  `invalidate-cache` told the author to pass the flag they had just passed;
  `diagnose` told a brand-new job its revision had succeeded; and pointing at a
  folder was reported as a permissions problem.
- Task briefs contradicted the gates they describe: an abstract contract that
  was not this run's, a key nothing reads, and a hard rule labelled for a
  profile the run is not.
- An outline with seven empty sections cost seven publish attempts, one per
  round-trip; a blocked stage now says how to get unblocked; pandoc's list of
  dropped elements went to a truncated log line; and two of three
  evidence-policy checks only ever reached stderr, so a run that raised three
  warnings recorded one.
- Tables went out headed by raw column names, a stacked header made a sheet
  unreadable, and a chart that could not draw its own labels said nothing.

### Fixed — claims this repository made about itself

- **CI had been red for eighty-one commits while every round reported green.**
  Python 3.11 could not byte-compile `reference_verify` (a backslash inside an
  f-string expression), `openpyxl` was undeclared, and the `mcp` guard probed a
  module the server does not import. Reporting green from one interpreter on one
  operating system is not reporting green.
- The dependency list the README installs had drifted from the real one; the
  first command a stranger runs after installing did not exist; and the
  credibility page quoted an adversarial run that is not the archived one. The
  archived numbers are now pinned by contract tests, as the test-count badge
  already was — including the count on `docs/EVIDENCE.md`, which had rotted to
  496 against a suite of 783.
- `examples/source_to_report.py` was added: three files and one sentence in, a
  finished DOCX out — the thing the tool is for, which the examples directory
  did not previously demonstrate. The README was cut from 534 lines to 134.

### Added — what a stranger sees before running anything

- **`examples/output/`** holds the document `examples/source_to_report.py`
  produces, committed: the `.docx` itself plus the client-readable QA note that
  says, claim by claim, which source row each sentence rests on. A contract test
  keeps it a real deliverable — headings, a Word table, a chart, no local path —
  so the thing most readers judge the tool by cannot quietly rot.
- **The README leads with the agent path.** Installing the skill and asking for
  the report in your own words comes first; the CLI follows as the scripted
  route. The MCP section now says plainly that it exposes the gates, not the
  whole pipeline, which is what a reader discovers three commands later anyway.
- **The Colab notebook runs the whole path**, not just `verify()`: install,
  three source files, a rendered `.docx` you can download, then the gate on its
  own. It installs from the cloned repository rather than PyPI so the notebook
  always matches the code beside it.

## 4.26.0 - 2026-07-26

### Fixed — the last two untouched profiles, and a total that meant nothing

`custom` and `admissions_project_report` were the only built-in profiles never
run on a real case. Both were dogfooded in Chinese: a three-option evaluation
of lab data-acquisition hardware, and a capstone project report written as
graduate-application material. Six defects, one of them introduced by 4.24.0.

- **A comparison of alternatives is no longer totalled.** The column-total
  derived statistic added in 4.24.0 summed the cost column of an options
  table and registered "採購成本 欄合計為 94,500" as high-grade citable
  evidence — a number with no referent, because you buy one option, not all
  three. That is exactly the confident-but-meaningless figure the gates exist
  to keep out of a document. Tables whose columns name alternatives
  (`方案`/`option`/`alternative`/`scenario`) now produce no total; line-item
  tables still do.
- **An unrecognized unit is still a unit.** `unit_signature` returned a value
  only for a closed vocabulary, so `(kS/s)`, `(bit)` and `(元)` all came back
  empty — indistinguishable from a column carrying no unit. A sampling rate
  and a price therefore read as the same unit and were drawn on one shared
  y-axis. Non-ASCII unit words are kept, and an explicit parenthetical is now
  treated as a signature even when the vocabulary does not know it; a purely
  numeric one (`Revenue (2026)`) still is not.
- **A Chinese abstract is measured in characters, not English words.** The
  policy bounds are English word counts and `count_words` counts each CJK
  character as one unit, so every Chinese abstract was held to roughly half
  its intended length — a 269-字 abstract rejected against a 250-word maximum.
  The conventional pairing is a 250-word English abstract beside a 500-字
  Chinese one, so CJK abstracts scale by two.
- **References sits at the same level as its siblings.** The heading contract
  emitted References at H2 while every other section was H1, so Word nested
  參考文獻 under the last body section in the table of contents instead of
  listing it as a section.
- **An authored References section is no longer dropped in silence.** Prose
  about the sources is correctly removed — References carries citations — but
  the author previously discovered the loss only by reading the rendered file.
  It now warns and says where the commentary belongs.
- **The abstract's claim requirement is documented.** PLAN_LOCK hard-blocks an
  abstract with no `claim_ids`, while the brief tells the author to put no
  `[CITE:]` markers in the abstract; nothing said the outline entry still
  needs the claim ids it summarizes. The brief now says so and the block
  message explains the fix.

496 tests and both benchmark --checks pass.

## 4.25.0 - 2026-07-25

### Fixed — a monthly trend reads as a trend, and 表 1 is reachable

Second untouched profile dogfooded the same way: a Chinese production-line
defect-rate analysis on `business_report`, written to a plant manager from a
monthly CSV, a QA meeting log, and a countermeasure record. Four defects, none
of them visible in the profiles already exercised.

- **A monthly table with one "%" column is no longer stacked.** The
  stacked-bar branch accepted a loose keyword test — `"%"` appearing anywhere
  in the headers — as evidence of part-whole composition, and it runs before
  the time-series branch, so an ordered monthly table could never reach a line
  chart. The rigorous test (rows summing to ~1 or ~100) still wins anywhere;
  the keyword guess now yields to ordered time data.
- **A unitless column is not the same unit as one that has a unit.**
  `mixed_measure_units` counted only detected signatures, so 投產數 / 不良數 /
  不良率(%) reported a single unit ("%") and read as unmixed — counts in the
  thousands and a percentage near 2 on one shared y-axis, drawing the
  defect-rate line flat against the axis. The existing "keep it as a table or
  split the charts" advice now actually fires.
- **Mixed units no longer pre-empt a scatter.** That guard is about sharing
  one y-axis; a scatter puts each measure on its own axis, which is what it is
  for. Surfaced by the fix above, which made an existing fixture mixed.
- **Figures and tables are numbered independently.** The caption printed the
  author's `figure_id`, and ids are unique across the plan, so a report with
  one chart and one table rendered "圖 1." then "表 2." — 表 1 was
  unreachable. `figure_id` remains the identity the manifest and gates match
  on; the caption number is now a per-label sequence.
- **An image path is not publication text.** Figures are written under the run
  directory, whose name is derived from the prompt, so the pre-render scan
  found the prompt inside a markdown image target and hard-blocked with "raw
  prompt fragment leaked into publication text". A CJK prompt hits this every
  time: it has no spaces to trim, so it lands in the directory name whole.
  Link and image targets are excluded from the scan; prompt text in the body
  still blocks.

486 tests and both benchmark --checks pass.

## 4.24.0 - 2026-07-25

### Fixed — a proposal can state its own budget, and cite nothing that isn't there

First end-to-end dogfood of the `proposal` profile: a Chinese undergraduate
capstone proposal built from a department handbook, a prior year's results
summary, and a supplier quote sheet. It is the only built-in profile with no
results-like section and no references section, and every defect below had
survived because nothing had ever been written through it.

- **The budget total is now derived evidence.** A quote sheet is read for a
  number no row states. Evidence build now sums an amount-named column
  (`小計`/`total`/`amount`/…) or a column verified to be the product of two
  others, and registers it as a high-grade entry with
  `derivation.method = "column_total"` — so the proposal rubric's own demand
  ("the ask, the cost and the payoff on the first page") is satisfiable
  without publishing arithmetic no gate can check. Totals need two rows, not
  the three a regression needs.
- **A Markdown table now scores like the same table as a CSV.** Markdown
  sources are ingested paragraph by paragraph, so a table inside one arrived
  typed as prose and missed both the table bonus and the structured-row
  quantitative bonus: 0.5/medium against 0.75/high for identical data. FD
  then forbade measured wording on numbers the source states exactly.
- **A `.csv`, `.json` or `.docx` source no longer makes a run unpublishable.**
  Reference curation blocks four local-file labels; the publication-candidate
  test knew only `[Text file]`, so a dataset reference was carried into the
  publication list and then hard-failed REFERENCE_QA as "not a publication".
  Both now share one pattern.
- **No in-text citation without a reference entry.** Those same local-file
  sources rendered author-year markers over a reference list that curation
  had emptied — a quote sheet cited three times produced three dangling
  markers. Citations for local-file types are now omitted from publication
  text, as internal project sources already were; traceability stays in the
  sidecars.
- **Undated repeats collapse.** The duplicate-citation collapser matched only
  numeric and author-year shapes, so `(手冊 (n.d.))` — nested parentheses, no
  four-digit year — rendered doubled. Every source without a publication date
  was affected.
- **Figures no longer target a section the blueprint does not define.**
  `_section_for_recommendation` fell back to the literal `"results"`;
  `proposal` has no such section, so the brief instructed authors to write
  `sections.results.figure_ids` into an outline that would reject it. It now
  falls back by section type, putting a quote table in `budget_resources`.
- **Bar labels prefer the column that names each row.** The first categorical
  column was used unconditionally, so three different bearings all drew as
  `測試軸承`; the label column is now the categorical column with the most
  distinct values. Boxplot grouping, which needs repeats, is untouched.
- **A blocked sentence says which sentence.** FINAL_QA read only `claim_id`,
  so an FD wording-strength block printed `(?)` and pointed at
  `claim_matrix.json` when the fix lives in `sentence_map.jsonl`. The hint now
  names the target, the checker and the reason, and is a testable function.
- **The brief no longer contradicts the gate.** It told authors to reserve
  `measured` wording for "high-grade or quantitative" evidence; FD accepts
  high-grade only, so following the documented rule earned a hard block.

479 tests and both benchmark --checks pass.

## 4.23.1 - 2026-07-25

### Changed — the README leads with the document, not the gate

The project page still opened with "a deterministic verification layer that
refuses to publish any claim it cannot trace to registered evidence" — the
floor sold as the pitch. Traceability is the price of entry for anything you
put your name on; the reason to use this is the document that comes out.

- New opening: what the tool produces (a submission-ready DOCX aimed at the
  person who grades it, English or Chinese, optionally following your own
  template), with traceability stated plainly as the floor.
- `pip install report-workflow` moved to the top — it was buried 260 lines
  down and still described PyPI as "once tagged", which shipped this morning.
- New **What a graded document reads like**: a real rendered discussion
  section, with the derived slope and R² it cites.
- New **How it aims at "good", not just "not wrong"**: reader rubrics,
  structure discipline with its published sources, derived statistics as
  citable evidence.
- "Who is this for" now leads with people handing in documents; the
  fidelity-gate scope note moved down to where the gate is the subject.
- Package description and keywords match the same framing, so the PyPI
  landing page says what the project is for.

Documentation and packaging metadata only; no code change. 463 tests and
both benchmark --checks pass.

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
    `skills/report-workflow/reference/authoring.md`: translate data identifiers into
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
  `skills/report-workflow/SKILL.md` is now a ~220-line navigation hub (down from ~628) that
  links one-level-deep `skills/report-workflow/reference/` files
  (`setup-and-preflight`, `profiles`, `tools`, `authoring`, `figures`,
  `engineering-lab`, `revision`, `benchmarking`), matching Anthropic's Agent
  Skills 500-line and single-source-of-truth guidance. Removed the duplicated
  `skills/report-workflow/agent_instructions.md`; its content now lives once in the
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
