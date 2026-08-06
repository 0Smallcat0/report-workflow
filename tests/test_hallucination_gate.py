"""Does the gate stop a claim the source does not make?

Every other end-to-end case in this repo feeds a finished report back in as
its own evidence. That is circular: it confirms the draft agrees with the
document it was written from, which is not the question. Here the source is
first-party data nobody has written prose about — a measurement CSV and a
regulator's notice — and the claims are written against it deliberately,
some true to the data and some not.

The gates are lexical by design (see AGENTS.md, "No semantic layer"), so what
is measured here is the reach of that: fabricated magnitudes, invented
entities, borrowed precision, and quoted text nobody wrote are all catchable
without entailment. Cases the lexical checker cannot reach belong in the
adversarial corpus, which records them as measured misses.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.mcp_server import verify_claims_payload
from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import ReportState


#: First-party data: a plant's own throughput log. No prose, no conclusions,
#: nothing for a draft to paraphrase — the only way to make a claim about it
#: is to read the numbers.
THROUGHPUT_CSV = """batch_id,feedstock,input (tonnes),recovered (tonnes),recovery_rate (%),downtime (hours)
B-101,occ,120.0,81.6,68.0,2.5
B-102,occ,118.0,79.2,67.1,3.0
B-103,mixed,96.0,39.4,41.0,5.5
B-104,mixed,101.0,41.8,41.4,4.0
B-105,white,64.0,49.3,77.0,1.5
B-106,white,66.0,50.4,76.4,1.0
"""

#: A second first-party source in prose form, so a claim can be written
#: against a document that states some things and not others.
NOTICE_TEXT = """Regulatory notice 2026-14

The mixed-paper gate fee is set at 138 currency units per tonne with effect
from 2026-04-01. Operators processing more than 50,000 tonnes per year must
file quarterly throughput returns. No change is made to the occ gate fee.
"""


def _all_packages_present(name: str, *args, **kwargs):
    return object()


def _prepare(tmpdir: str) -> ReportState:
    csv_path = Path(tmpdir) / "throughput_log.csv"
    csv_path.write_text(THROUGHPUT_CSV, encoding="utf-8")
    notice_path = Path(tmpdir) / "notice_2026_14.txt"
    notice_path.write_text(NOTICE_TEXT, encoding="utf-8")
    with patch(
        "report_workflow.preflight.importlib.util.find_spec",
        side_effect=_all_packages_present,
    ):
        return prepare_workflow(
            "report on recovery performance",
            [str(csv_path), str(notice_path)],
            str(Path(tmpdir) / "out"),
            report_profile="business_report",
        )


def _ledger(state: ReportState) -> list[dict]:
    path = Path(state.sources["evidence_ledger_path"])
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _find(rows: list[dict], needle: str) -> dict:
    for row in rows:
        if needle in row.get("content", ""):
            return row
    raise AssertionError(f"no evidence row contains {needle!r}")


def _verdict(rows: list[dict], claim: dict) -> dict:
    result = verify_claims_payload([claim], rows, deep_audit=True)
    return result["claim_results"][0]


class FabricatedClaimTests(unittest.TestCase):
    """Claims written against data that does not contain them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state = _prepare(self._tmp.name)
        self.rows = _ledger(self.state)

    def test_a_true_reading_of_the_data_is_publishable(self):
        """The control. Without it, a gate that blocks everything would pass."""
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_true",
            "claim_text": "The white feedstock batch recovered 49.3 tonnes at a 77.0 % recovery rate.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "verified", verdict.get("reason"))

    def test_a_number_absent_from_the_row_is_blocked(self):
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_invented_number",
            "claim_text": "Recovery reached 94.8 % on the white feedstock batch.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("94.8", verdict["reason"])

    def test_precision_the_source_never_stated_is_blocked(self):
        """77.0 in the log does not license 77.04 in the report."""
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_borrowed_precision",
            "claim_text": "Recovery reached 77.04 % on the white feedstock batch.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_a_quotation_nobody_wrote_is_blocked(self):
        row = _find(self.rows, "gate fee")
        verdict = _verdict(self.rows, {
            "claim_id": "c_invented_quote",
            "claim_text": 'The notice states that operators "may apply for a fee waiver".',
            "claim_type": "factual",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_a_claim_citing_evidence_that_does_not_exist_is_blocked(self):
        verdict = _verdict(self.rows, {
            "claim_id": "c_ghost_evidence",
            "claim_text": "Independent audits confirm a 91 percent recovery rate across all feedstocks.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_audit_report_001"],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("E_audit_report_001", verdict["reason"])

    def test_a_claim_with_no_evidence_at_all_is_blocked(self):
        verdict = _verdict(self.rows, {
            "claim_id": "c_unsourced",
            "claim_text": "Recovery performance is the best in the region.",
            "claim_type": "factual",
            "status": "supported",
            "evidence_ids": [],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_a_statistical_claim_on_a_prose_row_is_blocked(self):
        """The notice states a fee; it supports no statistic about compliance."""
        row = _find(self.rows, "quarterly throughput returns")
        verdict = _verdict(self.rows, {
            "claim_id": "c_wrong_type",
            "claim_text": "Filing compliance reached 88 % in the first quarter.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_the_blocked_reason_names_the_row_that_answered(self):
        """An id alone is not repairable when several rows answer to it."""
        row = _find(self.rows, "quarterly throughput returns")
        verdict = _verdict(self.rows, {
            "claim_id": "c_wrong_type",
            "claim_text": "Filing compliance reached 88 % in the first quarter.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        reason = verdict["reason"]
        if "is not allowed by evidence" in reason:
            self.assertIn(row["block_id"], reason)
            self.assertIn("allows:", reason)


class FabricatedEntityTests(unittest.TestCase):
    """Where the lexical checker reaches, and where it stops."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.rows = _ledger(_prepare(self._tmp.name))

    def test_a_batch_that_was_never_run_is_blocked(self):
        """B-207 is in no row, and its numbers are in no row either."""
        row = _find(self.rows, "B-101")
        verdict = _verdict(self.rows, {
            "claim_id": "c_ghost_batch",
            "claim_text": "Batch B-207 recovered 88.9 tonnes of occ feedstock.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_an_attribute_swap_with_correct_numbers_is_a_measured_miss(self):
        """Right figures, wrong subject: the checker passes this, and it should not.

        The white batch's numbers are attributed to the mixed batch. Every
        number is in the cited row and every term overlaps, so a lexical
        checker has nothing to fire on — deciding that "mixed" contradicts
        "white" is entailment, which this project deliberately does not do
        (AGENTS.md, "No semantic layer"). Asserted as verified on purpose: if
        a future checker catches it, this test fails and someone gets to
        delete it, which is the only honest way to record a known miss.
        """
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_attribute_swap",
            "claim_text": "The mixed feedstock batch recovered 49.3 tonnes at a 77.0 % recovery rate.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "verified")


class WholeSetTests(unittest.TestCase):
    """The publishable flag is the one an author actually reads."""

    def test_one_fabricated_claim_makes_the_set_unpublishable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)
            rows = _ledger(state)
            true_row = _find(rows, "B-105")
            claims = [
                {
                    "claim_id": "c_true",
                    "claim_text": "The white feedstock batch recovered 49.3 tonnes at a 77.0 % recovery rate.",
                    "claim_type": "statistical",
                    "status": "supported",
                    "evidence_ids": [true_row["evidence_id"]],
                },
                {
                    "claim_id": "c_false",
                    "claim_text": "Recovery reached 94.8 % on the white feedstock batch.",
                    "claim_type": "statistical",
                    "status": "supported",
                    "evidence_ids": [true_row["evidence_id"]],
                },
            ]
            result = verify_claims_payload(claims, rows, deep_audit=True)
            self.assertFalse(result["publishable"])
            self.assertEqual(result["verified_count"], 1)
            self.assertGreaterEqual(result["blocked_count"], 1)


#: Chinese evidence written the way a market report writes it: numbers with
#: measure words, particles between the number and the next clause, and a
#: currency-per-unit price.
CHINESE_EVIDENCE = [
    {
        "evidence_id": "E_pet",
        "source_id": "S1",
        "source_role": "internal_project_source",
        "source_file_name": "recycling.md",
        "file_type": "md",
        "evidence_type": "quantitative",
        "evidence_grade": "high",
        "allowed_claim_types": ["factual", "statistical"],
        "block_id": "md_3",
        "content": (
            "美國原生 PET 樹脂價格在 3月的原生料報價已低於 2019 年水準，"
            "再生料價差收斂至 25%，業者在 15 個月內關閉了 7 座回收廠。"
        ),
    },
    {
        "evidence_id": "E_li",
        "source_id": "S1",
        "source_role": "internal_project_source",
        "source_file_name": "recycling.md",
        "file_type": "md",
        "evidence_type": "quantitative",
        "evidence_grade": "high",
        "allowed_claim_types": ["factual", "statistical"],
        "block_id": "md_7",
        "content": "碳酸鋰價格於 2025-06 觸及 8,259 美元/噸 的週期低點，隨後回升。",
    },
]


#: The same log with the headers an export actually writes. "recovery_rate (%)"
#: is what a person types; "recovery_rate_pct" is what a tool emits, and the
#: gate used to read a unit only from a halfwidth bracket or a bare "%", so
#: this file stated no units at all.
SNAKE_CASE_CSV = """batch_id,feedstock,input_tonnes,recovered_tonnes,recovery_rate_pct,downtime_hours
B-101,occ,120.0,81.6,68.0,2.5
B-105,white,64.0,49.3,77.0,1.5
B-106,white,66.0,50.4,76.4,1.0
"""


class HeaderUnitTests(unittest.TestCase):
    """A column's unit is not always written in halfwidth brackets.

    Read only from "(...)" or a bare "%", every other header came back
    unitless — and an unstated unit is compared as unknown, so a claim in any
    unit matched such a column. The two failures were opposite and both real:
    an honest claim naming the right unit could not be matched to a column
    that stated one differently, and a claim in the wrong unit sailed past a
    column that had stated none.
    """

    def _units(self, header: str) -> str:
        from report_workflow.nodes.factuality_check import _unit_from_header

        return _unit_from_header(header)

    def test_a_snake_case_suffix_states_a_unit(self):
        self.assertEqual(self._units("recovery_rate_pct"), "pct")
        self.assertEqual(self._units("input_tonnes"), "tonnes")
        self.assertEqual(self._units("downtime_hours"), "hours")

    def test_a_fullwidth_bracket_states_a_unit(self):
        """The brackets a Chinese keyboard produces are not U+0028."""
        self.assertEqual(self._units("價格（USD/噸）"), "USD/噸")
        self.assertEqual(self._units("Voltage [V]"), "V")

    def test_a_header_naming_no_unit_stays_unitless(self):
        """Inventing one would let a claim in any unit match the column."""
        self.assertEqual(self._units("recovery_rate"), "")
        self.assertEqual(self._units("batch_id"), "")
        self.assertEqual(self._units("notes"), "")

    def test_the_same_unit_spelled_two_ways_agrees(self):
        from report_workflow.nodes.factuality_check import _units_match

        self.assertTrue(_units_match("USD/噸", "美元/噸"))
        self.assertTrue(_units_match("pct", "%"))
        self.assertTrue(_units_match("tonnes", "噸"))

    def test_different_units_still_disagree(self):
        from report_workflow.nodes.factuality_check import _units_match

        self.assertFalse(_units_match("USD/t", "USD/kg"))
        self.assertFalse(_units_match("kg", "噸"))


class SnakeCaseHeaderClaimTests(unittest.TestCase):
    """Every honest statistical claim about this CSV used to be blocked."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        csv_path = Path(self._tmp.name) / "throughput_log.csv"
        csv_path.write_text(SNAKE_CASE_CSV, encoding="utf-8")
        with patch(
            "report_workflow.preflight.importlib.util.find_spec",
            side_effect=_all_packages_present,
        ):
            state = prepare_workflow(
                "report on recovery performance",
                [str(csv_path)],
                str(Path(self._tmp.name) / "out"),
                report_profile="business_report",
            )
        self.rows = _ledger(state)

    def test_a_true_reading_of_a_snake_case_column_is_publishable(self):
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_true",
            "claim_text": "The white feedstock batch recovered 49.3 tonnes at a 77.0 percent recovery rate.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "verified", verdict.get("reason"))

    def test_a_fabricated_figure_is_still_blocked(self):
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_false",
            "claim_text": "The white feedstock batch reached a 94.8 percent recovery rate.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")

    def test_the_right_number_in_the_wrong_unit_is_blocked(self):
        """The column now states a unit, so this can finally be caught."""
        row = _find(self.rows, "B-105")
        verdict = _verdict(self.rows, {
            "claim_id": "c_wrong_unit",
            "claim_text": "The white feedstock batch recovered 49.3 kg of fibre.",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": [row["evidence_id"]],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("unit", verdict["reason"])


class ChineseParaphraseTests(unittest.TestCase):
    """FE blocked every true Chinese claim that did not copy the source.

    The extractor bound a number to the characters following it, which in a
    language without spaces is the rest of the sentence: the claim's
    "8,259美元/噸的低點" was compared against the evidence's "8,259美元/噸"
    and did not match. One particle was enough. The gate therefore rewarded
    transcription and punished the synthesis a report exists to do — the
    incentive pointed away from the product's purpose, which is worse than
    any single wrong verdict.
    """

    def _verdict(self, claim: dict) -> dict:
        return verify_claims_payload(
            [claim], CHINESE_EVIDENCE, deep_audit=True
        )["claim_results"][0]

    def test_a_number_is_read_apart_from_the_prose_after_it(self):
        from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

        self.assertEqual(_extract_numbers_with_unit("3月的原生 PET"), [("3", "月")])
        self.assertEqual(
            _extract_numbers_with_unit("15 個月內關閉了 7 座回收廠"),
            [("15", "個月"), ("7", "座")],
        )
        self.assertEqual(
            _extract_numbers_with_unit("8,259 美元/噸 的低點"), [("8,259", "美元/噸")]
        )

    def test_a_paraphrase_of_the_evidence_is_publishable(self):
        verdict = self._verdict({
            "claim_id": "t1",
            "claim_text": "美國原生 PET 報價已低於 2019 年水準，業者在 15 個月內關閉了 7 座回收廠。",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_pet"],
        })
        self.assertEqual(verdict["status"], "verified", verdict.get("reason"))

    def test_a_price_restated_in_another_word_order_is_publishable(self):
        """The evidence writes 觸及…的週期低點; the claim writes 跌至…的低點."""
        verdict = self._verdict({
            "claim_id": "t2",
            "claim_text": "碳酸鋰在 2025 年 6 月跌至 8,259 美元/噸 的低點。",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_li"],
        })
        self.assertEqual(verdict["status"], "verified", verdict.get("reason"))

    def test_changing_the_count_still_blocks(self):
        verdict = self._verdict({
            "claim_id": "f1",
            "claim_text": "業者在 15 個月內關閉了 23 座回收廠。",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_pet"],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("23", verdict["reason"])

    def test_changing_the_price_still_blocks(self):
        verdict = self._verdict({
            "claim_id": "f2",
            "claim_text": "碳酸鋰在 2025 年 6 月跌至 3,100 美元/噸 的低點。",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_li"],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("3,100", verdict["reason"])

    def test_a_price_in_the_wrong_unit_is_named_as_a_unit_conflict(self):
        """Right value, wrong unit is the author's other possible mistake."""
        verdict = self._verdict({
            "claim_id": "f5",
            "claim_text": "碳酸鋰的低點為 8,259 美元/公斤。",
            "claim_type": "statistical",
            "status": "supported",
            "evidence_ids": ["E_li"],
        })
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("states a unit the evidence does not", verdict["reason"])


class DraftStatesItsClaimTests(unittest.TestCase):
    """A number vanished between the claim and the page, and everything passed.

    A claim asserting "需約 US$500/噸的產品售價才達 10% IRR，capex 約
    US$1,000/噸年產能" was drafted as "需約 US/噸的產品售價才達 10% 內部報酬率，
    每噸年產能的資本支出約 US,000" — a shell had expanded `$500` and `$1` as
    variables. FA checks the links, FE checks the claim against its evidence,
    and nothing checked the leg the reader actually reads. It shipped.

    What makes it worse than a wrong number is that the sentence stays fluent.
    "每噸年產能約 US,000 的資本門檻" reads like finished prose; "US$9,999" would
    have been caught by whoever proofread it.
    """

    EVIDENCE_ID = "E_plastics_capex"

    def _matrix(self, claim_text: str) -> dict:
        return {
            "claims": [{
                "claim_id": "c9",
                "claim_text": claim_text,
                "claim_type": "statistical",
                "status": "supported",
                "evidence_ids": [self.EVIDENCE_ID],
            }]
        }

    def _verdicts(self, claim_text: str, draft: str) -> list[dict]:
        from report_workflow.nodes.factuality_check import run_factuality_check_fs

        return run_factuality_check_fs(draft, self._matrix(claim_text))

    def test_a_figure_the_draft_never_states_is_blocked(self):
        results = self._verdicts(
            "塑膠機械回收需約 US$500/噸的產品售價才達 10% IRR。",
            f"機械回收需約 US/噸的產品售價才達 10% 內部報酬率 [CITE:{self.EVIDENCE_ID}]。",
        )
        self.assertEqual(results[0]["status"], "blocked")
        self.assertEqual(results[0]["checker"], "FS")
        self.assertIn("500", results[0]["reason"])

    def test_a_draft_restating_every_figure_passes(self):
        results = self._verdicts(
            "塑膠機械回收需約 US$500/噸的產品售價才達 10% IRR，capex 約 US$1,000/噸年產能。",
            f"機械回收需約 US$500/噸的售價才達 10% 內部報酬率，"
            f"資本支出約 US$1,000/噸年產能 [CITE:{self.EVIDENCE_ID}]。",
        )
        self.assertEqual(results[0]["status"], "verified", results[0]["reason"])

    def test_several_sentences_may_share_the_work(self):
        """One claim is often written as two or three sentences."""
        results = self._verdicts(
            "回收率 72%，噸成本 210 美元，投資回收期 5 年。",
            f"機械回收的產出率為 72% [CITE:{self.EVIDENCE_ID}]。\n\n"
            f"其噸成本為 210 美元 [CITE:{self.EVIDENCE_ID}]。\n\n"
            f"投資回收期約 5 年 [CITE:{self.EVIDENCE_ID}]。",
        )
        self.assertEqual(results[0]["status"], "verified", results[0]["reason"])

    def test_a_figure_stated_in_chinese_words_counts(self):
        """500 written as 五百 is a restatement, not an omission."""
        results = self._verdicts(
            "產品售價需達 500 美元。",
            f"產品售價需達五百美元 [CITE:{self.EVIDENCE_ID}]。",
        )
        self.assertEqual(results[0]["status"], "verified", results[0]["reason"])

    def test_a_figure_shown_in_a_bound_table_counts_as_stated(self):
        """Making the prose repeat a table it sits beside writes it out twice."""
        from report_workflow.nodes.factuality_check import run_factuality_check_fs
        from report_workflow.run_workflow import prepare_workflow
        from report_workflow.state import WORKFLOW_RUNS_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "costs.md"
            source.write_text(
                "# 回收成本分析\n\n"
                "機械回收的噸成本與產出率隨製程而異，本節整理三種主流路線的單位成本，"
                "並比較其投資回收期與適用料源。\n",
                encoding="utf-8",
            )
            with patch(
                "report_workflow.preflight.importlib.util.find_spec",
                side_effect=_all_packages_present,
            ):
                state = prepare_workflow(
                    "analyse costs",
                    [str(source)],
                    str(Path(tmpdir) / "out"),
                    report_profile="business_report",
                )
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            section_dir = run_dir / "section_drafts"
            section_dir.mkdir(parents=True, exist_ok=True)
            (section_dir / "figure_plan.json").write_text(
                json.dumps({
                    "figures": [{
                        "figure_id": "1",
                        "section_id": "findings",
                        "data": {"columns": ["製程", "噸成本"], "rows": [["機械回收", "210"]]},
                    }]
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            outline = {"sections": {"findings": {"claim_ids": ["c9"]}}}
            results = run_factuality_check_fs(
                f"回收率為 72%，投資回收期約 5 年 [CITE:{self.EVIDENCE_ID}]。",
                self._matrix("回收率 72%，噸成本 210 美元，投資回收期 5 年。"),
                state,
                outline,
            )
            self.assertEqual(results[0]["status"], "verified", results[0]["reason"])

    def test_a_claim_no_sentence_cites_is_left_to_fa(self):
        """Reporting it here too would block one mistake twice."""
        results = self._verdicts(
            "產品售價需達 US$500/噸。", "一段沒有引用任何證據的文字。"
        )
        self.assertEqual(results, [])

    def test_a_claim_asserting_no_figures_is_not_examined(self):
        results = self._verdicts(
            "機械回收的瓶頸在於分選而非處理。",
            f"分選是主要瓶頸 [CITE:{self.EVIDENCE_ID}]。",
        )
        self.assertEqual(results, [])


class MangledAmountLintTests(unittest.TestCase):
    """The cheap half: a currency marker whose amount is gone.

    Independent of any claim binding, so it also guards prose that no claim
    covers — which is where the claim-level check cannot reach.
    """

    def _lint(self, text: str):
        from report_workflow.nodes.factuality_check import find_mangled_amounts

        return find_mangled_amounts(text)

    def test_the_shapes_a_lost_substitution_leaves_behind(self):
        for text in (
            "每噸年產能約 US,000 的資本門檻",
            "機械回收需約 US/噸的產品售價",
            "成本約 /噸",
            "$ 的成本佔比偏高",
        ):
            with self.subTest(text=text):
                self.assertTrue(self._lint(text), f"{text!r} was not flagged")

    def test_ordinary_writing_is_not_flagged(self):
        """A lint with false positives gets switched off, so it must have none."""
        for text in (
            "US$1,000/噸年產能",
            "約 500 噸",
            "成本佔 20%",
            "價格為 8,259 美元/噸",
            "US$2,500–10,000 的區間",
            "價格（USD/噸）",
            "TWD/kg 的單價",
            "毛利率 41%",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._lint(text), [], f"{text!r} was wrongly flagged")


if __name__ == "__main__":
    unittest.main()
