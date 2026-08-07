"""What an outline has to account for, and what it no longer has to.

Two rules survive because they change the delivered document: a cross tabulation
the pipeline built is placed or waived by name, and a counter-evidence section
carries more than one claim. Three did not: a minimum waiver-reason length, a
no-duplicate-reasons rule, and two id-mapping exercises (`undermines`,
`answers`) that never reached the page. They policed rule-following, not reports.
""" 
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from report_workflow.errors import QAHardBlockError  # noqa: E402
from report_workflow.nodes.outline_plan import (  # noqa: E402
    _validate_counter_evidence,
    _validate_derived_table_coverage,
)
from report_workflow.prompt_questions import extract_questions  # noqa: E402
from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR  # noqa: E402

DRONE_PROMPT = (
    "根據 Amazon US 無人機類商品資料撰寫一份市場研究報告，涵蓋品類結構、價格帶分布、"
    "品牌集中度、買家痛點四個面向，結論必須能支撐「這個市場值不值得進入、"
    "從哪個切點進入」的判斷。"
)
RECYCLING_PROMPT = "分析電池、塑膠、紡織、紙張四個品類的回收經濟性，比較單位成本與價格驅動因子"

BLUEPRINT = {
    "section_order": ["findings", "limitations", "recommendations"],
    "sections": {
        "findings": {"section_id": "findings", "required": True},
        "limitations": {"section_id": "limitations", "required": True, "counter_evidence": True},
        "recommendations": {
            "section_id": "recommendations",
            "required": True,
            "must_answer_prompt_questions": True,
        },
    },
}


def _state(prompt: str = DRONE_PROMPT, tables: int = 1) -> ReportState:
    """A state carrying a ledger with `tables` built cross tabulations."""
    state = ReportState.new(prompt, [], None)
    state.spec["user_prompt"] = prompt
    state.plan["blueprint"] = json.loads(json.dumps(BLUEPRINT))
    state.plan["claim_matrix"] = {
        "claims": [
            {"claim_id": "c1", "evidence_ids": []},
            {"claim_id": "c_lim_1", "evidence_ids": []},
            {"claim_id": "c_lim_2", "evidence_ids": []},
        ]
    }
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = run_dir / "evidence_ledger.jsonl"
    with open(ledger, "w", encoding="utf-8") as handle:
        for index in range(tables):
            handle.write(json.dumps({
                "evidence_id": f"E_auto_{index}",
                "origin": "auto",
                "table_grid": [["a"], ["1"]],
                "source_file_name": "products.csv",
                "derivation": {"origin": "auto", "group_by": f"col{index}"},
            }, ensure_ascii=False) + "\n")
        handle.write(json.dumps({
            "evidence_id": "E_scalar",
            "origin": "auto",
            "derivation": {"origin": "auto"},
        }, ensure_ascii=False) + "\n")
    state.sources["evidence_ledger_path"] = str(ledger)
    return state


def _sections(**overrides) -> dict:
    sections = {
        "findings": {"section_id": "findings", "claim_ids": ["c1"]},
        "limitations": {
            "section_id": "limitations",
            "claim_ids": ["c_lim_1", "c_lim_2"],
            "undermines": ["c1"],
        },
        "recommendations": {
            "section_id": "recommendations",
            "claim_ids": ["c1"],
            "answers": [
                {"question_index": 0, "claim_ids": ["c1"]},
                {"question_index": 1, "claim_ids": ["c1"]},
            ],
        },
    }
    for section_id, patch in overrides.items():
        sections[section_id] = patch
    return sections


class QuestionExtractionTests(unittest.TestCase):
    def test_a_market_brief_asks_two_questions_without_a_question_mark(self):
        found = extract_questions(DRONE_PROMPT)
        self.assertEqual(len(found), 2)
        self.assertIn("值不值得進入", found[0])
        self.assertIn("哪個切點", found[1])

    def test_a_statement_asking_for_work_asks_nothing(self):
        # The requirement must stay off for the common brief, or authors learn
        # to satisfy it rather than to answer anything.
        self.assertEqual(extract_questions(RECYCLING_PROMPT), [])

    def test_no_prompt_is_not_an_error(self):
        self.assertEqual(extract_questions(""), [])
        self.assertEqual(extract_questions(None), [])


class BuiltTableCoverageTests(unittest.TestCase):
    def test_an_unplaced_table_names_itself_in_the_refusal(self):
        state = _state()
        with self.assertRaises(QAHardBlockError) as ctx:
            _validate_derived_table_coverage(state, {"sections": _sections()})
        message = str(ctx.exception)
        self.assertIn("E_auto_0", message)
        self.assertIn("unused_derived_evidence", message)
        self.assertIn("products.csv grouped by col0", message)

    def test_a_claim_citing_the_table_places_it(self):
        state = _state()
        state.plan["claim_matrix"]["claims"][0]["evidence_ids"] = ["E_auto_0"]
        _validate_derived_table_coverage(state, {"sections": _sections()})
        coverage = json.loads(
            (WORKFLOW_RUNS_DIR / state.job_id / "derived_table_coverage.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(coverage["placed"], ["E_auto_0"])
        self.assertEqual(coverage["waived"], {})

    def test_a_figure_drawing_on_the_table_places_it(self):
        state = _state()
        plan_dir = WORKFLOW_RUNS_DIR / state.job_id / "section_drafts"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "figure_plan.json").write_text(
            json.dumps({"figures": [{"figure_id": "f1", "source_evidence_ids": ["E_auto_0"]}]}),
            encoding="utf-8",
        )
        _validate_derived_table_coverage(state, {"sections": _sections()})

    def test_a_waiver_with_a_reason_is_accepted_and_recorded(self):
        state = _state()
        outline = {
            "sections": _sections(),
            "unused_derived_evidence": {
                "E_auto_0": "the model axis repeats the brand table at a finer cut"
            },
        }
        _validate_derived_table_coverage(state, outline)
        coverage = json.loads(
            (WORKFLOW_RUNS_DIR / state.job_id / "derived_table_coverage.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(list(coverage["waived"]), ["E_auto_0"])

    def test_a_waiver_with_no_reason_at_all_is_refused(self):
        # A minimum length and a no-duplicates rule used to police this. Both
        # measured rule-following rather than the report, and both are gone; what
        # is left is that dropping a table is a decision someone made in words.
        state = _state()
        outline = {"sections": _sections(), "unused_derived_evidence": {"E_auto_0": "  "}}
        with self.assertRaises(QAHardBlockError) as ctx:
            _validate_derived_table_coverage(state, outline)
        self.assertIn("no reason at all", str(ctx.exception))

    def test_a_short_reason_is_accepted(self):
        state = _state()
        outline = {"sections": _sections(), "unused_derived_evidence": {"E_auto_0": "重複"}}
        _validate_derived_table_coverage(state, outline)

    def test_waiving_an_id_that_is_not_a_built_table_is_refused(self):
        state = _state()
        outline = {
            "sections": _sections(),
            "unused_derived_evidence": {
                "E_auto_0": "the model axis repeats the brand table at a finer cut",
                "E_scalar": "a single number, not a table, and not needed here",
            },
        }
        with self.assertRaises(QAHardBlockError) as ctx:
            _validate_derived_table_coverage(state, outline)
        self.assertIn("not built tables", str(ctx.exception))

    def test_a_ledger_with_no_tables_requires_nothing(self):
        state = _state(tables=0)
        _validate_derived_table_coverage(state, {"sections": _sections()})


class CounterEvidenceSectionTests(unittest.TestCase):
    def test_a_single_claim_is_a_disclaimer(self):
        sections = _sections(limitations={
            "section_id": "limitations", "claim_ids": ["c_lim_1"], "undermines": ["c1"],
        })
        with self.assertRaises(QAHardBlockError) as ctx:
            _validate_counter_evidence(_state(), sections)
        self.assertIn("at least 2 are required", str(ctx.exception))

    def test_a_section_naming_what_it_qualifies_is_accepted(self):
        _validate_counter_evidence(_state(), _sections())


class JoinCitationMeasurementTests(unittest.TestCase):
    """The measurement that reported nine join-backed conclusions as zero.

    A joined derivation does not carry a `join` marker on its evidence record;
    it surfaces as `E_D_<request id>`. Looking for the marker found nothing, and
    the conclusion drawn was that the feature was unused.
    """

    def test_a_claim_citing_a_joined_derivation_is_counted(self):
        from measure_report_body_density import measure_run

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "derived_evidence.json").write_text(json.dumps({
                "derivations": [
                    {"id": "review_by_price_band", "join": {"on": "asin", "how": "inner"}},
                    {"id": "brand_cr10"},
                ]
            }), encoding="utf-8")
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [
                    {"claim_id": "c1", "evidence_ids": ["E_D_review_by_price_band"]},
                    {"claim_id": "c2", "evidence_ids": ["E_D_brand_cr10"]},
                ]
            }), encoding="utf-8")

            result = measure_run(run_dir)
            self.assertEqual(result["join_derivations"], 1)
            self.assertEqual(result["claims_citing_a_join"], 1)
            self.assertEqual(result["hand_registered_derivations"], 2)


if __name__ == "__main__":
    unittest.main()
