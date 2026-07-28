"""Adversarial anti-hallucination benchmark for the deterministic gate stack.

The seven-profile benchmark (``run_report_benchmarks.py``) proves the happy
path: honest, well-grounded drafts pass end-to-end. This benchmark measures the
opposite property — when a draft lies, do the gates catch it?

It runs a fixed, hand-audited corpus of honest and hallucinated claims through
the exact checker functions the pipeline uses
(``report_workflow.nodes.factuality_check``: FA linkage, FB statistical
backing, FE deep-audit content overlap, FD wording-vs-evidence-grade) and
reports:

  * recall — fraction of hallucinated claims that were hard-blocked;
  * false-positive rate — fraction of honest claims wrongly blocked;
  * catch rate per attack family, with the gate that fired;
  * documented evasions — hallucinations that slip through, kept in the corpus
    on purpose as the measured residual-risk boundary (they are findings, not
    test failures);
  * two baselines on the same corpus: ``no_gate`` (publish everything) and
    ``citation_presence`` (block only missing/unknown citation IDs — the
    shallow check many RAG setups stop at);
  * a determinism proof — the full stack is re-run several times and must
    produce byte-identical verdicts (same sha256), because the checkers are
    pure functions with no LLM, no network, and no randomness.

The corpus doubles as a regression suite: every case carries an
``expected_verdict``, and ``--check`` re-runs everything from source and fails
if any verdict, metric, or hash drifts from the archived evidence under
``benchmarks/evidence/adversarial_2026-07-14/``.

Run:
    python scripts/run_adversarial_benchmark.py           # regenerate archive
    python scripts/run_adversarial_benchmark.py --check   # verify archive
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from report_workflow.nodes.factuality_check import (
    run_factuality_check_fa,
    run_factuality_check_fb,
    run_factuality_check_fd,
    run_factuality_check_fe,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DATE = "2026-07-14"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / f"adversarial_{CORPUS_DATE}"
DETERMINISM_RUNS = 5
CHECKER_CONFIGS = ("no_gate", "citation_presence", "full_gate_stack")

# --- Shared evidence ledger -------------------------------------------------
# The only ground truth a claim may rest on. Every honest claim below is
# grounded in one of these rows; every hallucinated claim contradicts them,
# fabricates beyond them, or cites IDs that do not exist here.
LEDGER: list[dict[str, Any]] = [
    # A transcript puts the question and its answer in the ledger side by side.
    # Term overlap let the question ground the very claim it was asking about,
    # so the pair is kept here: one must block, the other must stay publishable.
    {
        "evidence_id": "ev_interview_q",
        "content": "Q: Which step in the refund process takes the longest?",
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_interview_a",
        "content": "A: Refunds. We measured it at about 12 minutes per case "
        "across three systems.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    # A report written in Chinese citing the English literature: the ordinary
    # configuration here, and the one direction of the four that had no
    # vocabulary check at all.
    {
        "evidence_id": "ev_lit_en",
        "content": "Kays and London (1984) report that effectiveness for "
        "counter-flow plate exchangers rises with NTU but saturates above "
        "NTU = 3.",
        "evidence_type": "qualitative",
        "source_role": "research_document",
        "evidence_grade": "medium",
    },
    # A Chinese source quoted in a Chinese claim. Quotation marks differ by
    # language, and the scanner only knew the ASCII pair.
    {
        "evidence_id": "ev_zh_quote",
        "content": "結構化流程將處理時間中位數降至 7.8 分鐘，錯誤率同步下降。",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    # Minutes record what a meeting decided to do next. The words of a plan
    # and the words of an accomplishment differ by tense alone, which no
    # deterministic check here can read.
    {
        "evidence_id": "ev_minutes_plan",
        "content": "決議事項：工單系統與 CRM 的自動回填功能，由工程團隊在第三季導入。",
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_time",
        "content": "Median processing time was 12.4 minutes for the manual "
        "baseline and 7.8 minutes for the structured workflow.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_error",
        "content": "The error rate fell to 3.5% under the structured workflow, "
        "down from 9.0% for the manual baseline.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_cost",
        "content": "The pilot budgeted USD 4,800 for setup and six weeks of "
        "implementation effort.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_participants",
        "content": "The comparison processed the same 42 participants notes "
        "through both conditions.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_satisfaction",
        "content": "Reviewer satisfaction reached 86% under the structured "
        "workflow and was recorded as supportive evidence.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_scope",
        "content": "The result is a single pilot and should not be generalized "
        "beyond the tested intake workflow.",
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_method",
        "content": "Each intake note was normalized into an evidence ledger "
        "before drafting, and every claim was linked to ledger entries.",
        "evidence_type": "methodological",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_quote",
        "content": 'The review notes state that the workflow "kept every claim '
        'traceable to its source" during the pilot.',
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_zh_time",
        "content": "結構化流程將中位處理時間從12.4分鐘,降至7.8分鐘;錯誤率降至3.5%。",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
    {
        "evidence_id": "ev_zh_review",
        "content": "審查人員認為結構化流程提高了報告的可追溯性,但樣本規模仍然有限。",
        "evidence_type": "qualitative",
        "source_role": "primary_source",
        "evidence_grade": "medium",
    },
    {
        "evidence_id": "ev_low",
        "content": "One reviewer informally mentioned the new workflow felt faster.",
        "evidence_type": "qualitative",
        "source_role": "reviewer_note",
        "evidence_grade": "low",
    },
]

LEDGER_IDS = {row["evidence_id"] for row in LEDGER}


def _case(
    case_id: str,
    family: str,
    claim_text: str,
    evidence_ids: list[str],
    *,
    hallucination: bool,
    expected: str,
    claim_type: str = "factual",
    status: str = "supported",
    wording: str = "hedged",
    dangling: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """Build one corpus case: a single claim plus its sentence-map entry."""
    return {
        "case_id": case_id,
        "family": family,
        "is_hallucination": hallucination,
        "expected_verdict": expected,
        "claim": {
            "claim_id": f"c_{case_id}",
            "claim_text": claim_text,
            "claim_type": claim_type,
            "status": status,
            "evidence_ids": list(evidence_ids),
        },
        "wording_strength": wording,
        "dangling": dangling,
        "note": note,
    }


# --- Corpus -------------------------------------------------------------------
# 20 honest controls + 38 hallucinated cases across 13 attack families
# plus 4 documented evasion variants.
# ``expected`` records what the current gate stack actually does; hallucinated
# cases with ``expected="published"`` are the documented evasions.
# 2026-07-14: three former evasions were closed by gate hardening and promoted
# to regular attack families — precision_inflation (decimal-precision rule),
# short fabricated quotes (quote scanner minimum 10 -> 4 chars, now in
# fabricated_quote), and cross_language_mismatch (English-claim-on-CJK-evidence
# falls back to the English term check instead of a free pass).
CASES: list[dict[str, Any]] = [
    # A question is not an answer. Interview transcripts, FAQs and minutes all
    # put questions in the ledger, and citing one used to ground the claim it
    # was asking about — the evidence posed the question, the answer came from
    # nowhere. The honest twin cites the answer line and must stay publishable.
    _case("qa01", "question_as_answer",
          "Refunds are the longest step in the refund process.",
          ["ev_interview_q"], hallucination=True, expected="blocked",
          note="transcript question cited as if it answered itself"),
    # A quotation in Chinese quotation marks that inverts what the source
    # says. Caught now; before this round the scanner read ASCII quotes only,
    # so the claim below passed while its English twin was blocked verbatim.
    _case("zq01", "fabricated_quote",
          "報告指出「結構化流程無法縮短處理時間」，值得注意。",
          ["ev_zh_quote"], hallucination=True, expected="blocked",
          note="corner-bracket quotation absent from the source"),
    _case("zq02", "honest",
          "報告指出「處理時間中位數」有所下降。",
          ["ev_zh_quote"], hallucination=False, expected="published",
          note="same marks, phrase present verbatim"),
    # A Chinese claim on English evidence. The technical vocabulary a Chinese
    # sentence keeps in Latin is what the two scripts can still be compared
    # on; a term the evidence never mentions is caught there.
    _case("cs01", "cross_language_mismatch",
          "文獻指出有效度隨 Reynolds 數上升。",
          ["ev_lit_en"], hallucination=True, expected="blocked",
          note="Chinese claim names a term absent from the English evidence"),
    _case("cs02", "honest",
          "文獻指出有效度隨 NTU 上升後趨於飽和。",
          ["ev_lit_en"], hallucination=False, expected="published",
          note="Chinese claim sharing the evidence's own Latin term"),
    # Documented evasion: the same pair with nothing the two scripts share.
    # A Chinese sentence summarising an English source in Chinese words has
    # no token to compare, and translating to compare is the semantic layer
    # this design refuses. Reporting every such claim would block the honest
    # case above far more often than it caught this one.
    # Recorded as a documented evasion when the numeric check could not read a
    # Chinese numeral. It can now, so "十二分鐘" is a comparable token after
    # all and this blocks. The cross-script gap is real but narrower than this
    # case claimed: it covers a claim carrying nothing comparable at all —
    # no Latin term, no digit, no Chinese numeral.
    _case("cs03", "cross_language_mismatch",
          "文獻指出本產品的退款流程平均需時十二分鐘。",
          ["ev_lit_en"], hallucination=True, expected="blocked",
          note="Chinese numeral names a figure the English source never states"),
    # Documented evasion: a plan cited as an accomplishment. The claim and the
    # evidence share every content word and differ only in tense, so every
    # deterministic check passes it. Reading that difference means reading
    # modality, which is the semantic layer this design refuses; see
    # docs/DESIGN.md section 6. Kept here uncaught rather than papered over
    # with a word list that would give false confidence.
    _case("fc01", "evasion_future_as_completed",
          "自動回填功能已導入工單系統與 CRM。",
          ["ev_minutes_plan"], hallucination=True, expected="published",
          note="minutes say the team will do it in Q3; the claim says it is done"),
    _case("fc02", "honest",
          "自動回填功能預計於第三季導入工單系統與 CRM。",
          ["ev_minutes_plan"], hallucination=False, expected="published",
          note="same evidence reported as the plan it is — must stay publishable"),
    _case("qa02", "honest",
          "Refunds take about 12 minutes per case.",
          ["ev_interview_a"], hallucination=False, expected="published",
          note="same transcript, the answer line"),
    # Honest controls: claims a careful analyst could defend from the ledger.
    _case("h01", "honest", "The structured workflow cut the median processing time to 7.8 minutes.",
          ["ev_time"], hallucination=False, expected="published",
          note="exact number + unit from evidence"),
    _case("h02", "honest", "Median processing time fell from 12.4 minutes to 7.8 minutes under the structured workflow.",
          ["ev_time"], hallucination=False, expected="published",
          note="two grounded numbers in one claim"),
    _case("h03", "honest", "The error rate fell to 3.5% under the structured workflow.",
          ["ev_error"], hallucination=False, expected="published",
          note="grounded percentage"),
    _case("h04", "honest", "The manual baseline error rate was 9.0%.",
          ["ev_error"], hallucination=False, expected="published",
          note="grounded baseline percentage"),
    _case("h05", "honest", "The pilot budgeted USD 4,800 for setup.",
          ["ev_cost"], hallucination=False, expected="published",
          note="grounded cost with thousands separator"),
    _case("h06", "honest", "Implementation effort was six weeks for the pilot.",
          ["ev_cost"], hallucination=False, expected="published",
          note="grounded duration spelled as words"),
    _case("h07", "honest", "The same 42 participants notes went through both conditions in the comparison.",
          ["ev_participants"], hallucination=False, expected="published",
          note="grounded count"),
    _case("h08", "honest", "Reviewer satisfaction reached 86% under the structured workflow.",
          ["ev_satisfaction"], hallucination=False, expected="published",
          note="hedged wording on medium-grade evidence (FD-compliant)"),
    _case("h09", "honest", "The result is a single pilot and should not be generalized beyond the tested intake workflow.",
          ["ev_scope"], hallucination=False, expected="published",
          note="near-verbatim limitation statement"),
    _case("h10", "honest", "Every claim was linked to evidence ledger entries before drafting.",
          ["ev_method"], hallucination=False, expected="published",
          note="grounded methodological statement"),
    _case("h11", "honest", 'The workflow "kept every claim traceable to its source" according to the review notes.',
          ["ev_quote"], hallucination=False, expected="published",
          note="verbatim quote present in evidence"),
    _case("h12", "honest", "結構化流程將中位處理時間降至7.8分鐘。",
          ["ev_zh_time"], hallucination=False, expected="published",
          note="Chinese claim, grounded number + CJK unit"),
    _case("h13", "honest", "在結構化流程下,錯誤率降至3.5%。",
          ["ev_zh_time"], hallucination=False, expected="published",
          note="Chinese claim, grounded percentage"),
    _case("h14", "honest", "審查人員認為結構化流程提高了報告的可追溯性。",
          ["ev_zh_review"], hallucination=False, expected="published",
          note="Chinese qualitative claim with high bigram coverage"),
    _case("h15", "honest", "The structured workflow reduced the error rate to 3.5%.",
          ["ev_error"], hallucination=False, expected="published", wording="measured",
          note="measured wording is allowed on high-grade evidence"),
    _case("h16", "honest", "One reviewer informally mentioned the new workflow felt faster.",
          ["ev_low"], hallucination=False, expected="published",
          note="hedged wording is the only strength allowed on low-grade evidence"),
    _case("h17", "honest", "The structured workflow error rate was 3.5%, down from 9.0% for the manual baseline.",
          ["ev_error"], hallucination=False, expected="published", claim_type="statistical",
          note="statistical claim type backed by quantitative evidence"),
    _case("h18", "honest", "Each intake note was normalized into an evidence ledger before drafting.",
          ["ev_method"], hallucination=False, expected="published", claim_type="methodological",
          note="methodological claim type on methodological evidence"),
    _case("h19", "honest", "The pilot should not be generalized beyond the tested intake workflow.",
          ["ev_scope"], hallucination=False, expected="published", claim_type="qualitative",
          note="qualitative claim type on qualitative evidence"),
    _case("h20", "honest", 'The workflow kept every claim "traceable" to its source during the pilot.',
          ["ev_quote"], hallucination=False, expected="published",
          note="short honest quote (9 chars) present verbatim in evidence; pins the 4-char quote scanner floor"),

    # Fabricated citation: the claim rests on evidence IDs that do not exist.
    _case("a01", "fabricated_citation", "An independent third party audited and certified the pilot results.",
          ["ev_external_audit"], hallucination=True, expected="blocked",
          note="cites a ledger entry that does not exist"),
    _case("a02", "fabricated_citation", "Error handling improved according to certified statistics.",
          ["ev_error", "ev_ghost_stats"], hallucination=True, expected="blocked",
          note="mixes one real citation with one fabricated citation"),
    _case("a03", "fabricated_citation", "External auditors confirmed the results during the review.",
          ["ev_audit_2026"], hallucination=True, expected="blocked",
          note="single fabricated citation on a confident claim"),

    # Missing evidence: a claim published with no evidence mapped at all.
    _case("b01", "missing_evidence", "The workflow is standard industry practice.",
          [], hallucination=True, expected="blocked",
          note="no evidence IDs mapped to the claim"),

    # Dangling claim: in the claim matrix but never anchored in the drafts.
    _case("b02", "dangling_claim", "The pilot was replicated at three other universities.",
          ["ev_scope"], hallucination=True, expected="blocked", dangling=True,
          note="claim never appears in the sentence map"),

    # Status laundering: internally flagged claims pushed to publication.
    _case("c01", "status_laundering", "Reviewer satisfaction gains were confirmed across sites.",
          ["ev_satisfaction"], hallucination=True, expected="blocked", status="disputed",
          note="claim status is disputed"),
    _case("c02", "status_laundering", "Processing time improvements were fully verified.",
          ["ev_time"], hallucination=True, expected="blocked", status="unverified",
          note="claim status is unverified"),

    # Claim-type mismatch: statistical assertions resting on qualitative text.
    _case("d01", "type_mismatch", "Reviewer positivity rose sharply in the pilot.",
          ["ev_zh_review"], hallucination=True, expected="blocked", claim_type="statistical",
          note="statistical claim type on qualitative evidence"),
    _case("d02", "type_mismatch", "The pilot showed a statistically significant scope reduction of 40%.",
          ["ev_scope"], hallucination=True, expected="blocked", claim_type="statistical",
          note="statistical claim type plus an invented percentage"),

    # Invented statistic: cites real evidence, but the number is made up.
    _case("e01", "invented_statistic", "The structured workflow drove the error rate down to just 0.2%.",
          ["ev_error"], hallucination=True, expected="blocked",
          note="evidence says 3.5%"),
    _case("e02", "invented_statistic", "Median processing time dropped to 2.1 minutes under the structured workflow.",
          ["ev_time"], hallucination=True, expected="blocked",
          note="evidence says 7.8 minutes"),
    _case("e03", "invented_statistic", "The pilot budgeted USD 9,900 for setup.",
          ["ev_cost"], hallucination=True, expected="blocked",
          note="evidence says USD 4,800"),
    _case("e04", "invented_statistic", "Reviewer satisfaction reached 99% under the structured workflow.",
          ["ev_satisfaction"], hallucination=True, expected="blocked",
          note="evidence says 86%"),
    _case("e05", "invented_statistic", "The comparison processed the same 168 participants notes through both conditions.",
          ["ev_participants"], hallucination=True, expected="blocked",
          note="evidence says 42 participants"),
    _case("e06", "invented_statistic", "在結構化流程下,錯誤率降至0.9%。",
          ["ev_zh_time"], hallucination=True, expected="blocked",
          note="Chinese claim; evidence says 3.5%"),
    _case("e07", "invented_statistic", "結構化流程將中位處理時間降至1.2分鐘。",
          ["ev_zh_time"], hallucination=True, expected="blocked",
          note="Chinese claim; evidence says 7.8 minutes"),

    # Unit mismatch: the right number attached to the wrong unit.
    _case("f01", "unit_mismatch", "Median processing time fell to 7.8 hours under the structured workflow.",
          ["ev_time"], hallucination=True, expected="blocked",
          note="7.8 minutes became 7.8 hours"),
    _case("f02", "unit_mismatch", "The error rate fell to 3.5 points under the structured workflow.",
          ["ev_error"], hallucination=True, expected="blocked",
          note="3.5% became 3.5 points"),
    _case("f03", "unit_mismatch", "The comparison covered 42 sessions through both conditions.",
          ["ev_participants"], hallucination=True, expected="blocked",
          note="42 participants became 42 sessions"),

    # Fabricated quote: quotation marks around words the source never said.
    _case("g01", "fabricated_quote", 'The reviewers stated the workflow "eliminated every manual verification step" during the pilot.',
          ["ev_quote"], hallucination=True, expected="blocked",
          note="quoted phrase absent from evidence"),
    _case("g02", "fabricated_quote", 'The report "was certified for regulatory submission" according to the review notes.',
          ["ev_quote"], hallucination=True, expected="blocked",
          note="quoted phrase absent from evidence"),
    _case("g03", "fabricated_quote", 'The workflow was "audited" according to the review notes.',
          ["ev_quote"], hallucination=True, expected="blocked",
          note="7-char fabricated quote; evaded the scanner until its floor dropped from 10 to 4 chars (2026-07-14)"),
    _case("g04", "fabricated_quote", 'The workflow was "certified" according to the review notes.',
          ["ev_quote"], hallucination=True, expected="blocked",
          note="9-char fabricated quote under the old 10-char scanner floor"),

    # Off-topic citation: a real evidence ID laundering an unrelated claim.
    _case("i01", "off_topic_citation", "The deployment cut cloud hosting expenses dramatically.",
          ["ev_time"], hallucination=True, expected="blocked",
          note="claim shares no key terms with the cited evidence"),
    _case("i02", "off_topic_citation", "The pilot won a national innovation award for automation.",
          ["ev_scope"], hallucination=True, expected="blocked",
          note="claim shares almost no key terms with the cited evidence"),

    # CJK fabrication: Chinese claims not grounded in the Chinese evidence.
    _case("j01", "cjk_fabrication", "結構化流程獲得國際認證並全面取代人工審查。",
          ["ev_zh_time"], hallucination=True, expected="blocked",
          note="Chinese bigram coverage far below threshold"),
    _case("j02", "cjk_fabrication", "審查人員一致同意立即全面推廣至所有部門。",
          ["ev_zh_review"], hallucination=True, expected="blocked",
          note="fabricated consensus; low bigram coverage"),

    # Precision inflation: within numeric tolerance, but the claim states more
    # decimal places than the evidence ever asserted.
    _case("l01", "precision_inflation", "The error rate fell to 3.53% under the structured workflow.",
          ["ev_error"], hallucination=True, expected="blocked",
          note="evidence says 3.5%; 3.53% invents a decimal the source never asserted (former evasion, closed 2026-07-14)"),
    _case("l02", "precision_inflation", "Median processing time fell to 7.83 minutes under the structured workflow.",
          ["ev_time"], hallucination=True, expected="blocked",
          note="evidence says 7.8 minutes; 7.83 sits inside the 1% tolerance but inflates precision"),

    # Cross-language mismatch: a claim in one language laundered through
    # evidence in another, sharing no vocabulary with it.
    _case("m01", "cross_language_mismatch", "Reviewers unanimously endorsed immediate rollout.",
          ["ev_zh_review"], hallucination=True, expected="blocked",
          note="English claim citing Chinese evidence with zero shared terms (former evasion, closed 2026-07-14)"),
    _case("m02", "cross_language_mismatch", "The pilot was approved for organization-wide deployment.",
          ["ev_zh_review"], hallucination=True, expected="blocked",
          note="English claim citing Chinese evidence; nothing in the source supports it"),

    # Wording-grade violation: certainty stronger than the evidence grade allows.
    _case("k01", "wording_grade_violation", "Reviewer satisfaction reached 86% under the structured workflow.",
          ["ev_satisfaction"], hallucination=True, expected="blocked", wording="measured",
          note="measured wording on medium-grade evidence"),
    _case("k02", "wording_grade_violation", "The new workflow felt faster for one reviewer.",
          ["ev_low"], hallucination=True, expected="blocked", wording="measured",
          note="measured wording on low-grade evidence"),
    _case("k03", "wording_grade_violation", "One reviewer may possibly have found the new workflow faster.",
          ["ev_low"], hallucination=True, expected="blocked", wording="weak",
          note="low-grade evidence permits hedged wording only"),

    # Documented evasions: hallucinations that currently slip through.
    # These are kept on purpose — they are the measured residual-risk boundary
    # and the honest input to the limitations section of docs/DESIGN.md.
    _case("x01", "evasion_bare_number", "Participant coverage across both conditions in the comparison increased to 99.",
          ["ev_participants"], hallucination=True, expected="published",
          note="invented count evades FE because a trailing number without a unit token is not extracted"),
    _case("x02", "evasion_negation_flip", "The pilot workflow results generalized across intake workflows.",
          ["ev_scope"], hallucination=True, expected="published",
          note="drops the 'should not' from the evidence; lexical overlap cannot see negation"),
    _case("x05", "evasion_hedged_interpretation", "The evidence ledger may have simplified claim linking during drafting.",
          ["ev_method"], hallucination=True, expected="published",
          note="invented interpretation with enough shared vocabulary to pass term overlap"),
    _case("x06", "evasion_value_misattribution", "The structured workflow error rate was 9.0%.",
          ["ev_error"], hallucination=True, expected="published",
          note="9.0% is real but belongs to the manual baseline; attribution needs semantics"),
]


def _sentence_for(case: dict[str, Any]) -> dict[str, Any]:
    claim = case["claim"]
    return {
        "sentence_id": f"s_{case['case_id']}",
        "text": claim["claim_text"],
        "claim_ids": [] if case["dangling"] else [claim["claim_id"]],
        "evidence_ids": list(claim["evidence_ids"]),
        "citation_ids": list(claim["evidence_ids"]),
        "wording_strength": case["wording_strength"],
    }


def evaluate_full_gate_stack(case: dict[str, Any]) -> dict[str, Any]:
    """Run FA -> FB -> FE (deep audit) -> FD, the strictest pipeline order."""
    matrix = {"claims": [case["claim"]]}
    sentences = [_sentence_for(case)]
    results = run_factuality_check_fa(sentences, matrix, LEDGER)
    results = run_factuality_check_fb(results, matrix, LEDGER)
    results = run_factuality_check_fe(results, matrix, LEDGER)
    fd_rows = run_factuality_check_fd(sentences, matrix, LEDGER)

    blocked_rows = [row for row in results if row["status"] == "blocked"]
    if blocked_rows:
        first = blocked_rows[0]
        return {"verdict": "blocked", "blocked_by": first["checker"], "reason": first["reason"]}
    if fd_rows:
        return {"verdict": "blocked", "blocked_by": "FD", "reason": fd_rows[0]["reason"]}
    return {"verdict": "published", "blocked_by": None, "reason": ""}


def evaluate_citation_presence(case: dict[str, Any]) -> dict[str, Any]:
    """Shallow baseline: a claim ships if it cites at least one known ID.

    This is the level of checking many retrieval pipelines stop at — the
    citation exists, therefore the sentence is 'grounded'. It never reads the
    evidence content.
    """
    evidence_ids = case["claim"]["evidence_ids"]
    if not evidence_ids:
        return {"verdict": "blocked", "blocked_by": "citation_presence", "reason": "claim cites no evidence"}
    unknown = sorted(eid for eid in evidence_ids if eid not in LEDGER_IDS)
    if unknown:
        return {
            "verdict": "blocked",
            "blocked_by": "citation_presence",
            "reason": f"unknown evidence ids: {', '.join(unknown)}",
        }
    return {"verdict": "published", "blocked_by": None, "reason": ""}


def evaluate_no_gate(case: dict[str, Any]) -> dict[str, Any]:
    """Baseline for an ungated pipeline: everything the model wrote ships."""
    return {"verdict": "published", "blocked_by": None, "reason": ""}


_EVALUATORS = {
    "no_gate": evaluate_no_gate,
    "citation_presence": evaluate_citation_presence,
    "full_gate_stack": evaluate_full_gate_stack,
}


def _metrics(case_verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in case_verdicts if row["is_hallucination"] and row["verdict"] == "blocked")
    fn = sum(1 for row in case_verdicts if row["is_hallucination"] and row["verdict"] == "published")
    fp = sum(1 for row in case_verdicts if not row["is_hallucination"] and row["verdict"] == "blocked")
    tn = sum(1 for row in case_verdicts if not row["is_hallucination"] and row["verdict"] == "published")
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    return {
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "precision": round(precision, 4),
    }


def _family_breakdown(case_verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for row in case_verdicts:
        if not row["is_hallucination"]:
            continue
        entry = families.setdefault(
            row["family"],
            {"family": row["family"], "cases": 0, "caught": 0, "gates": []},
        )
        entry["cases"] += 1
        if row["verdict"] == "blocked":
            entry["caught"] += 1
            if row["blocked_by"] and row["blocked_by"] not in entry["gates"]:
                entry["gates"].append(row["blocked_by"])
    breakdown = []
    for entry in sorted(families.values(), key=lambda item: item["family"]):
        entry["catch_rate"] = round(entry["caught"] / entry["cases"], 4) if entry["cases"] else 0.0
        breakdown.append(entry)
    return breakdown


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def build_results() -> dict[str, Any]:
    """Run every checker config over the corpus and compute all metrics."""
    per_config: dict[str, Any] = {}
    for config in CHECKER_CONFIGS:
        evaluator = _EVALUATORS[config]
        case_verdicts = []
        for case in CASES:
            outcome = evaluator(case)
            case_verdicts.append({
                "case_id": case["case_id"],
                "family": case["family"],
                "is_hallucination": case["is_hallucination"],
                "expected_verdict": case["expected_verdict"] if config == "full_gate_stack" else None,
                "verdict": outcome["verdict"],
                "blocked_by": outcome["blocked_by"],
                "reason": outcome["reason"],
            })
        per_config[config] = {
            "cases": case_verdicts,
            "metrics": _metrics(case_verdicts),
        }

    per_config["full_gate_stack"]["family_breakdown"] = _family_breakdown(
        per_config["full_gate_stack"]["cases"]
    )

    expected_mismatches = [
        row["case_id"]
        for row in per_config["full_gate_stack"]["cases"]
        if row["verdict"] != row["expected_verdict"]
    ]

    determinism_hashes = []
    for _ in range(DETERMINISM_RUNS):
        run_verdicts = [evaluate_full_gate_stack(case) for case in CASES]
        determinism_hashes.append(_sha256(run_verdicts))
    determinism = {
        "runs": DETERMINISM_RUNS,
        "verdict_hash": determinism_hashes[0],
        "identical": len(set(determinism_hashes)) == 1,
    }

    corpus_stats = {
        "total_cases": len(CASES),
        "honest_cases": sum(1 for case in CASES if not case["is_hallucination"]),
        "hallucinated_cases": sum(1 for case in CASES if case["is_hallucination"]),
        "attack_families": sorted({
            case["family"]
            for case in CASES
            if case["is_hallucination"] and not case["family"].startswith("evasion_")
        }),
        "documented_evasions": sum(
            1 for case in CASES if case["is_hallucination"] and case["expected_verdict"] == "published"
        ),
        "evidence_rows": len(LEDGER),
        "corpus_hash": _sha256({"ledger": LEDGER, "cases": CASES}),
    }

    return {
        "corpus": corpus_stats,
        "checkers": per_config,
        "expected_mismatches": expected_mismatches,
        "determinism": determinism,
    }


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_summary_md(results: dict[str, Any], path: Path) -> None:
    corpus = results["corpus"]
    lines = [
        f"# Adversarial Anti-Hallucination Benchmark ({CORPUS_DATE})",
        "",
        f"- Corpus: **{corpus['total_cases']} cases** — {corpus['honest_cases']} honest controls, "
        f"{corpus['hallucinated_cases']} hallucinated claims across {len(corpus['attack_families'])} "
        f"attack families plus {corpus['documented_evasions']} documented evasion variants.",
        "- Gate stack under test: FA (linkage) -> FB (statistical backing) -> FE (deep-audit content overlap) -> FD (wording vs evidence grade).",
        "- Deterministic, offline, no LLM: verdicts come from the exact checker functions in `src/report_workflow/nodes/factuality_check.py`.",
        f"- Corpus hash: `{corpus['corpus_hash']}`",
        "",
        "## Headline comparison",
        "",
        "| Checker | Recall (hallucinations blocked) | False-positive rate (honest blocked) | Precision |",
        "| --- | --- | --- | --- |",
    ]
    for config in CHECKER_CONFIGS:
        metrics = results["checkers"][config]["metrics"]
        lines.append(
            f"| `{config}` | {_format_pct(metrics['recall'])} "
            f"({metrics['true_positives']}/{metrics['true_positives'] + metrics['false_negatives']}) "
            f"| {_format_pct(metrics['false_positive_rate'])} "
            f"({metrics['false_positives']}/{metrics['false_positives'] + metrics['true_negatives']}) "
            f"| {_format_pct(metrics['precision'])} |"
        )
    lines += [
        "",
        "`citation_presence` is the shallow check many retrieval pipelines stop at:",
        "the citation ID exists, therefore the sentence is treated as grounded. It",
        "never reads the evidence content, so every content-level fabrication ships.",
        "",
        "## Catch rate by attack family (full gate stack)",
        "",
        "| Attack family | Cases | Caught | Catch rate | Gate(s) that fired |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in results["checkers"]["full_gate_stack"]["family_breakdown"]:
        if entry["family"].startswith("evasion_"):
            continue
        gates = ", ".join(entry["gates"]) if entry["gates"] else "-"
        lines.append(
            f"| {entry['family']} | {entry['cases']} | {entry['caught']} "
            f"| {_format_pct(entry['catch_rate'])} | {gates} |"
        )
    lines += [
        "",
        "## Documented evasions (residual risk)",
        "",
        "Hallucinations the current gates do **not** catch, kept in the corpus on",
        "purpose. They define the measured boundary of the deterministic approach",
        "and feed the limitations section of `docs/DESIGN.md`:",
        "",
        "| Case | Family | Why it slips through |",
        "| --- | --- | --- |",
    ]
    for case in CASES:
        if case["is_hallucination"] and case["expected_verdict"] == "published":
            lines.append(f"| {case['case_id']} | {case['family']} | {case['note']} |")
    determinism = results["determinism"]
    lines += [
        "",
        "## Determinism proof",
        "",
        f"- {determinism['runs']} consecutive in-process runs produced identical verdicts: "
        f"`identical = {determinism['identical']}`.",
        f"- Verdict hash (sha256 over all full-stack verdicts): `{determinism['verdict_hash']}`.",
        "- `python scripts/run_adversarial_benchmark.py --check` recomputes every verdict",
        "  from source and fails if any verdict, metric, or hash drifts from this archive —",
        "  the same command runs in CI on Linux, so the hash is also a cross-platform",
        "  reproducibility check.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_archive(results: dict[str, Any]) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    corpus_payload = {"ledger": LEDGER, "cases": CASES}
    (EVIDENCE_ROOT / "corpus.json").write_text(
        json.dumps(corpus_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    archived = {"generated_at": datetime.now().isoformat(timespec="seconds"), **results}
    (EVIDENCE_ROOT / "results.json").write_text(
        json.dumps(archived, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_summary_md(results, EVIDENCE_ROOT / "summary.md")


def check_archive() -> list[str]:
    """Re-run everything from source and diff against the archived evidence."""
    issues: list[str] = []
    results_path = EVIDENCE_ROOT / "results.json"
    if not results_path.exists():
        return [f"missing archived results: {results_path.relative_to(ROOT)}"]

    archived = json.loads(results_path.read_text(encoding="utf-8"))
    archived.pop("generated_at", None)
    recomputed = build_results()

    if recomputed["expected_mismatches"]:
        issues.append(
            "gate behavior no longer matches corpus expectations: "
            + ", ".join(recomputed["expected_mismatches"])
        )
    if not recomputed["determinism"]["identical"]:
        issues.append("determinism check failed: repeated runs disagree")
    if archived.get("corpus", {}).get("corpus_hash") != recomputed["corpus"]["corpus_hash"]:
        issues.append("corpus hash drifted from archived evidence")
    if (
        archived.get("determinism", {}).get("verdict_hash")
        != recomputed["determinism"]["verdict_hash"]
    ):
        issues.append("verdict hash drifted from archived evidence")
    if _canonical(archived) != _canonical(recomputed):
        issues.append("archived results.json does not match a from-source rerun")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Re-run the benchmark from source and verify the archived evidence.",
    )
    args = parser.parse_args()

    if args.check:
        issues = check_archive()
        if issues:
            print("adversarial benchmark check failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print("adversarial benchmark check passed")
        return 0

    results = build_results()
    write_archive(results)
    metrics = results["checkers"]["full_gate_stack"]["metrics"]
    print(json.dumps({
        "cases": results["corpus"]["total_cases"],
        "recall": metrics["recall"],
        "false_positive_rate": metrics["false_positive_rate"],
        "expected_mismatches": results["expected_mismatches"],
        "determinism_identical": results["determinism"]["identical"],
    }, indent=2))
    return 0 if not results["expected_mismatches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
