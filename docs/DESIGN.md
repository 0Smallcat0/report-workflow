# Design: Evidence-Bounded Report Generation

*A deterministic verification layer that lets an LLM draft a report but refuses
to publish any claim it cannot trace to registered evidence.*

This document explains **why** the system is built the way it is and **what its
verification layer measurably does and does not catch**. The development-facing
contract (stage lists, artifact schema, full gate list) lives in
[AGENTS.md](../AGENTS.md); operating instructions live in
[`agent_skill/SKILL.md`](../agent_skill/SKILL.md).

## 1. Problem

LLMs write fluent prose and, at some rate, invent numbers, misquote sources,
and cite studies that do not exist. In a chat reply that is a nuisance; in a
lab report, a financial memo, or a regulatory document it is disqualifying.

Two common mitigations are insufficient:

- **Retrieval + citation formatting.** Attaching a citation ID to a sentence
  proves the citation *exists*, not that the sentence *says what the source
  says*. On this project's adversarial corpus, that level of checking catches
  10.5% of hallucinations (see §4).
- **LLM-as-judge.** Asking a second model "is this grounded?" produces a
  probabilistic opinion: the verdict can change between runs, cannot be
  audited mechanically, and inherits the failure mode it is supposed to
  detect. This project deliberately avoids it — the checker contains no model
  at all, so a verdict is a pure function of (claim, evidence) and is
  reproducible byte-for-byte (§5).

The design bet: **separate drafting from publishing.** The model proposes; a
deterministic pipeline holds the publish decision and can prove, after the
fact, why every published sentence was allowed to ship.

## 2. Threat model: how a draft lies

The unit of verification is a **claim** — a checkable statement extracted from
the draft, typed (`factual`, `statistical`, `qualitative`, `methodological`,
`contextual`) and linked to entries in an **evidence ledger** built
deterministically from the user's sources. The adversarial corpus (§4)
enumerates the attack families; each maps to the gate designed to stop it:

| Attack family | Example | Gate |
| --- | --- | --- |
| Fabricated citation | cites `ev_external_audit`, which does not exist | FA |
| Missing evidence | confident claim with no evidence mapped | FA |
| Dangling claim | in the claim matrix but never anchored in the draft | FA |
| Status laundering | claim internally marked `disputed`/`unverified` is pushed anyway | FA |
| Type mismatch | `statistical` claim resting on qualitative prose | FA/FB |
| Invented statistic | evidence says 3.5%, claim says 0.2% | FE |
| Precision inflation | evidence says 3.5%, claim says 3.53% — a decimal the source never asserted | FE |
| Unit mismatch | 7.8 *minutes* becomes 7.8 *hours* | FE |
| Fabricated quote | quotation marks around words the source never said (4+ chars) | FE |
| Off-topic citation | real evidence ID laundering an unrelated claim | FE |
| CJK fabrication | Chinese claim not grounded in Chinese evidence | FE |
| Cross-language mismatch | English claim citing Chinese evidence it shares no vocabulary with | FE |
| Wording-grade violation | "measured" certainty on low-grade evidence | FD |

The gate stack, in pipeline order
([`src/report_workflow/nodes/factuality_check.py`](../src/report_workflow/nodes/factuality_check.py)):

- **FA — linkage.** Every claim must have a publishable status, map to
  evidence IDs that exist, appear in the sentence map, and carry a claim type
  the cited evidence is allowed to support.
- **FB — statistical backing.** A `statistical` claim must cite at least one
  piece of quantitative evidence. (FA's per-evidence type check subsumes FB on
  most inputs; FB stays as a belt-and-suspenders re-check.)
- **FE — deep-audit content overlap.** Compares claim *content* against
  evidence *content*: numbers with units must appear in the cited evidence
  within a 1% tolerance — and may not state more decimal places than the
  evidence itself provides; quoted phrases (4+ chars) must appear verbatim;
  key terms must reach coverage thresholds (40% English terms, 25% CJK
  bigrams). A non-CJK claim citing CJK-heavy evidence falls back to the
  English term check instead of passing unexamined, so cross-language
  citations must share vocabulary (bilingual evidence rows qualify) or block.
- **FD — provenance-weighted wording.** Sentence wording strength
  (`measured` / `hedged` / `weak`) must be permitted by the weakest evidence
  grade backing it: high-grade evidence permits measured assertions;
  low-grade evidence permits hedged wording only.

Beyond the factuality stack, profile policies and QA gates (front matter,
section contracts, citation audits, figure contracts, placeholder and
fake-metadata scans) also hard-block; `render` runs only after the validated
checkpoint records `qa_decision=pass`. See AGENTS.md for the full list.

## 3. Architecture rationale

```
sources ──> [prepare: deterministic]  evidence ledger + task briefs
                     │
                     v
            [author: external LLM agent]  claim matrix + drafts + sentence map
                     │
                     v
            [validate + render: deterministic]  gates ──> publish | hard block
```

- **The package never calls an LLM.** Parsing, the evidence ledger, artifact
  contracts, gates, rendering, and traceability packaging are all
  deterministic Python. The external agent (Claude Code, Codex, any harness)
  owns judgment and drafting. This split is what makes the verdict auditable:
  there is no prompt whose phrasing changes the outcome.
- **Artifacts, not conversations, are the interface.** The agent hands over
  `claim_matrix.json`, drafts, and `sentence_map.jsonl`; the pipeline replies
  with machine-readable reports (`factuality_report.json`, `qa_summary.json`).
  Every publish decision is reconstructable from files on disk.
- **Fail closed.** Anything unverifiable is blocked, not warned about. The
  cost of that choice is measured as the false-positive rate in §4 (0% on the
  corpus's honest controls, by construction of the authoring guidance: claims
  must reuse the evidence's own numbers and vocabulary).
- **Same gates, three surfaces.** CLI (`report-workflow validate`), agent
  skill, and MCP server (`report-workflow-mcp`, [docs/mcp.md](mcp.md)) all
  call the same checker functions, so measured behavior transfers.

## 4. Measured behavior (adversarial benchmark)

Happy-path evidence: the seven-profile benchmark renders a full report for
every built-in profile from one controlled source, 42 claims verified, QA
`pass` everywhere (`python scripts/run_report_benchmarks.py --check`).

Adversarial evidence
([`benchmarks/evidence/adversarial_2026-07-14/summary.md`](../benchmarks/evidence/adversarial_2026-07-14/summary.md),
reproducible via `python scripts/run_adversarial_benchmark.py --check`):
58 hand-audited cases — 20 honest controls, 38 hallucinated claims across the
13 attack families above plus 4 documented evasion variants.

| Checker | Recall | False-positive rate | Precision |
| --- | --- | --- | --- |
| `no_gate` (publish everything) | 0.0% | 0.0% | — |
| `citation_presence` (shallow RAG-style check) | 10.5% | 0.0% | 100% |
| **full gate stack (FA/FB/FE/FD)** | **89.5%** (34/38) | **0.0%** (0/20) | **100%** |

Every one of the 13 targeted attack families is caught at 100%. The missing
10.5% is not noise — it is four *documented evasions*, each kept in the corpus
deliberately (§6). The 2026-07-14 hardening closed three former evasions
(precision fudging, short fabricated quotes, cross-language laundering) and
promoted them to attack families; the corpus records which rule closed each.
The corpus doubles as a regression suite: every case's expected verdict is
asserted in CI, so a gate regression fails the build.

Out-of-domain evidence
([`benchmarks/evidence/halueval_qa_2026-07-15/summary.md`](../benchmarks/evidence/halueval_qa_2026-07-15/summary.md),
reproducible via `python scripts/run_external_benchmark.py --check`): the
zero-schema `verify()` adapter over the public HaluEval QA dataset — 10,000
pairs nobody here authored — yields a 0.06% false-positive rate (6/10,000,
each inspected and characterized), 99.7% precision per block verdict, 23.2%
overall recall, and 66.7% recall on the numeric subset. HaluEval's
hallucinations are open-domain entity swaps, the class §6 places outside
lexical checking, so the transferable claim is the fail-closed discipline
rather than the recall: out of domain, the gates almost never cry wolf, and
what they block is almost certainly fabricated.

## 5. Determinism as a feature

The checkers are pure functions: no model, no network, no randomness, no
global state. The benchmark exploits that:

- five consecutive runs must produce identical verdicts (sha256 over all
  verdicts), and
- CI re-runs the whole corpus from source on Linux and compares against the
  archive generated on Windows — the verdict hash is a cross-platform
  reproducibility check, not just a stability check.

Practical consequences: verdicts can be cached, diffed, and litigated
("*which* gate blocked this claim, for *what* reason"); a blocked claim is
re-testable after editing the draft; and the verification layer adds no token
cost and no privacy exposure at check time.

## 6. Limitations (measured, not hypothetical)

The evasion rows in the adversarial corpus define the current boundary of
lexical/structural checking. Each is a real, reproducible miss:

| Evasion | Why it slips |
| --- | --- |
| Bare number without unit ("increased to 99.") | FE's numeric extractor requires a number+unit pair |
| Negation flip ("results generalized" vs "should **not** be generalized") | term overlap cannot see polarity |
| Hedged reinterpretation | invented interpretation reusing enough source vocabulary |
| Value misattribution (real 9.0% assigned to the wrong condition) | needs relational semantics, not term matching |

Three evasions documented in earlier revisions of this corpus were closed by
the 2026-07-14 gate hardening and now live as regular attack families:
precision fudging (a claim may no longer state more decimal places than the
evidence asserts), short fabricated quotes (the quote scanner floor dropped
from 10 to 4 characters), and cross-language citation laundering (a non-CJK
claim citing CJK-heavy evidence now runs the English term check instead of
passing unexamined).

The cross-language closure has a deliberate cost: under deep audit, an honest
claim *translated* from its evidence shares no vocabulary with it and is
blocked — deterministic lexical checking cannot verify translation, and the
fail-closed rule wins. The supported pattern is same-language or bilingual
evidence rows (their embedded English terms satisfy the check); a translation
gate would need the semantic layer discussed below.

Structural limitations worth stating plainly:

- **The gates check grounding, not truth.** If the source itself is wrong,
  a faithfully grounded report reproduces the error. Garbage in, verified
  garbage out.
- **Claims are the unit of trust.** The agent chooses what to claim; a
  draft that asserts things *outside* any claim would be caught by the
  citation-placeholder and sentence-map gates, but adversarial phrasing
  inside a single anchored sentence is bounded by FE's lexical checks.
- **Conjunction claims are conservative.** FE checks a claim's numbers
  against *each* cited evidence row, so a claim aggregating two sources
  should be split into two claims — a strictness quirk, documented rather
  than hidden.
- **Thresholds are tunable, not learned.** The 40%/25% coverage thresholds
  and 1% numeric tolerance were set by inspection; the corpus exists so any
  retuning shows its effect immediately.

The honest framing: deterministic gates raise the floor — the classes of
hallucination that empirically dominate careless drafting (fabricated
citations, invented statistics, wrong units, fabricated quotes) go from
"ships silently" to "cannot ship." They do not solve semantic entailment.
Closing the negation/misattribution gap would require an NLI-style semantic
checker, which would reintroduce a probabilistic component; the design keeps
that trade-off explicit instead of blending the two.

### What this does not detect, by decision

**Disagreement between sources.** If two attached files state different
values for the same quantity, nothing notices. A mechanical rule — same
column, same key, different value — is easy to write and wrong most of the
time: two CSVs whose `Voltage` columns differ are usually two experiments,
not a contradiction. Firing on those would trade the measured 0% false-block
rate for warnings an author learns to dismiss, which is worse than silence.
Detecting real disagreement needs to know what each file *is*, and that is
the semantic layer this design refuses. Both values reach the draft, both are
cited, and the author decides.

**Censored measurements as chart data.** A column written `<0.01` — below the
detection limit, standard in lab data — profiles as categorical rather than
as a measure, so it is tabulated and never plotted. Counting censored cells
toward a column's numeric ratio would let a chart draw the half of a column
that happens to be plain numbers without saying so, which is a worse failure
than not drawing it. Claims citing such a cell are still checked: a bound is
rejected as a stand-in for a reading (§2).

**A plan reported as an accomplishment.** Minutes record what a meeting
decided to do next, and the words of a plan and of an accomplishment differ
by tense alone: "the team will introduce auto-fill in Q3" and "auto-fill has
been introduced" share every content word, every name and every number.
Every check here passes the second citing the first. Catching it means
reading modality — distinguishing *will*, *is due to*, *plans to* from *has*
— across two languages and in sentences that often carry both at once
("A shipped, B is scheduled"). A keyword list would fire on deadlines
("complete by 10 July" contains *complete*) and miss anything phrased
around it, which buys a worse thing than the gap: confidence that is not
earned. The case is kept in the adversarial corpus as a documented evasion,
uncaught, so the recall figure states the cost rather than hiding it.

**A Chinese claim on English evidence with nothing in common.** A report
written in Chinese citing the English literature is the ordinary case here,
and across scripts the only vocabulary both sides spell the same way is the
technical kind a Chinese sentence keeps in Latin — NTU, CRM, R², an author's
name. Where the claim carries such a term it is checked against the
evidence, and a term the source never mentions is caught. Where it carries
none — no Latin term, no digit, and no Chinese numeral, since those are read
too — there is nothing to compare: comparing would mean translating, which
is the semantic layer this design refuses. Reporting every such claim would
block the honest case — a Chinese sentence summarising an English source in
Chinese words — far more often than it caught a false one, and the measured
0% false-block rate is worth more than the coverage. Kept in the adversarial
corpus as a documented evasion.

**A PDF table drawn with whitespace instead of lines.** A ruled table in a
PDF is read row by row and reaches the ledger exactly as the same table
would from a CSV — citable per row, with the fit derived. A table laid out
by alignment alone, with no ruling, is read as the prose it typographically
is: one block of page text. Widening detection to whitespace columns would
find those tables and would also carve ordinary paragraphs into rows that
were never in the document. Inventing structure is a worse failure here than
missing it, because a row that never existed can be cited, and prose that
was merely mis-shelved cannot lie about a measurement.

**A Chinese figure or table that carries no caption line.** When a revision
deletes a figure or table reference, the plan must say so explicitly and
state what replaces it. English finds those references in prose, because
"Figure" is a rare word and a bare mention is reliable. 圖 and 表 are ordinary
morphemes — 發表 2 篇, 試圖 3 次, 代表 3 家 — and matching them the same way
put false positives on 5 of 9 ordinary report sentences for 表 and 3 of 9 for
圖. The Chinese side therefore anchors on a caption line, which is document
structure rather than vocabulary. A figure referenced only in running prose,
with its caption living in a text box or omitted, is not tracked and its
removal is not challenged. That is a miss; the alternative was hard-blocking
honest sentences, and this design rates a false block as the worse failure.

### Formatting boundary

The renderer targets a clean, submission-ready *manuscript*: title page
first, a localized table-of-contents field after the front matter, a
page-number footer, styled tables, embedded figures with captions,
hanging-indent references, and TeX math rendered to native equations.

It deliberately does **not** implement venue-specific layout: journal house
styles and two-column layouts (IEEE/ACM), LaTeX output, or per-institution
thesis rules (mandated fonts, margin regimes, roman-to-arabic page-number
switches that require multi-section documents). Citation output is APA 7th
for publications plus GB/T 7714 labels for data sources; other styles are
not implemented. Submitting to a venue still means pouring the content into
that venue's template — the contract here is that the content survives the
pour: headings, citations, numbers, and figures arrive real and traceable.

### Equations read in, not round-tripped

A Word equation in an attached source is read as the text an engineer would
write in prose — `Re=ρVD/μ`, `2F/(ρU^2A)`, `sqrt(2gh)` — so the formula reaches
the evidence ledger saying what its author wrote. Reading only the runs, as
every reader here did, dropped it: an inline formula left the sentence still
promising a definition it no longer carried, and one set on its own line
produced no block at all. Collecting the raw text nodes instead, as the
revision reader did, was worse — ρVD over μ came back as `ρVDμ`, a different
formula written into the author's own report as if they had typed it.

What is **not** promised is a round trip. An equation read out of a base
document comes back as that readable text, not as a native Word equation; only
math the draft itself writes in TeX renders to OMML. Accents and matrices are
carried in a flattened notation. The contract is that the formula survives and
means what it meant, not that its typesetting does.

## 7. Generalization

Report generation is one instance of **evidence-bounded generation**: wherever
a claim must trace to a source — a financial memo where every number cites a
filing, a regulatory submission, an admissions document grounded in a real
project — the trustworthy part is not the fluent draft but the layer that can
prove each statement and refuse the ones it cannot. The pattern (deterministic
evidence registry → model proposes typed claims → deterministic verifier holds
the publish decision → auditable QA pack) transfers unchanged; only the source
parsers and rendering targets are domain-specific.
