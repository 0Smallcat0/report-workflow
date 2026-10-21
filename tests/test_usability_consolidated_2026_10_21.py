"""Defects found writing three reports through the consolidated usability work.

Each was met by an author following the brief from start_report to
publish_report; the run record is in
benchmarks/evidence/usability_consolidated_2026-10-21/README.md.
"""
from __future__ import annotations

import tempfile
import unittest

from report_workflow.state import ReportState


class OutlineShapeShowsOnlyWhatIsReadTests(unittest.TestCase):
    def _blueprint(self, profile):
        from report_workflow.nodes import blueprint_plan

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["report_profile"] = profile
        return blueprint_plan.run_blueprint_plan(state).plan["blueprint"]

    def test_a_memo_outline_shape_has_no_results_mode(self):
        # The quant memo brief showed results_mode in the JSON shape and then
        # said "results_mode is not read for quant_research_memo; leave it out".
        from report_workflow.nodes.agent_tasks import outline_brief_sections_block

        block = outline_brief_sections_block(self._blueprint("quant_research_memo"), "quant_research_memo")
        self.assertNotIn("results_mode", block)
        lab = outline_brief_sections_block(self._blueprint("engineering_lab_report"), "engineering_lab_report")
        self.assertIn('"results_mode"', lab)



class TableHeadersReadAsWordsTests(unittest.TestCase):
    def test_a_placed_table_prints_its_headers_without_underscores(self):
        # The quant memo's two tables printed 「年化報酬_pct 平均」 in every header.
        from report_workflow.nodes.source_tables import render_source_table

        table = {
            "table_id": "E1",
            "headers": ["組合", "年化報酬_pct 平均", "review_count"],
            "rows": [["低波動", "8.53", "3"]],
            "source_file_name": "bt.csv",
            "computed": True,
        }
        rendered = render_source_table(table, number=1, caption="x", language="zh")
        self.assertIn("| 組合 | 年化報酬 (%) 平均 | review count |", rendered)
        self.assertNotIn("_pct", rendered)


_ROW = {
    "evidence_id": "E1",
    "content": '{"回看月數": "12", "樣本": "樣本內", "組合": "低波動", "年化報酬_pct": "10.6", '
               '"年化波動_pct": "10.8", "最大回撤_pct": "-16.9", "夏普值": "0.81"}',
    "granularity": "row",
    "block_type": "table_row",
    "evidence_type": "quantitative",
}


def _fe(text, evidence):
    from report_workflow.nodes.factuality_check import _check_content_overlap

    return _check_content_overlap({"claim_id": "c1", "claim_text": text, "claim_type": "statistical"}, evidence)


class BacktestVocabularyTests(unittest.TestCase):
    def test_a_lookback_written_out_names_its_column(self):
        self.assertEqual(_fe("樣本內回看 12 個月時，低波動組合夏普值 0.81。", _ROW), [])

    def test_the_figure_still_has_to_be_in_the_column_the_claim_names(self):
        # 12 is the lookback, not a Sharpe ratio; 10.8 is volatility, not return.
        self.assertTrue(_fe("低波動組合夏普值 12。", _ROW))
        self.assertTrue(_fe("低波動組合年化報酬 10.8%。", _ROW))

    def test_a_claim_reporting_the_question_may_cite_it(self):
        question = {
            "evidence_id": "E2",
            "content": "在台股大型股中，過去波動較低的股票，是否在扣除交易成本後仍有較好的風險調整後報酬？",
            "granularity": "paragraph",
            "evidence_type": "methodological",
        }
        self.assertEqual(_fe("研究問題是過去波動較低的股票在扣除交易成本後，是否有較好的風險調整後報酬。", question), [])
        self.assertTrue(_fe("過去波動較低的股票在扣除交易成本後有較好的風險調整後報酬。", question))

    def test_month_end_is_a_time_not_a_denominator(self):
        from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

        self.assertEqual(_extract_numbers_with_unit("每月底依過去 6 個月的報酬排序"), [("6", "個月")])


_LAB_ROW = {
    "evidence_id": "E3",
    "content": '{"砝碼質量_g": "250", "第一次伸長_cm": "10.2", "第二次伸長_cm": "9.9", '
               '"第三次伸長_cm": "10.2", "平均伸長_cm": "10.1"}',
    "granularity": "row",
    "block_type": "table_row",
    "evidence_type": "quantitative",
}


class LabSheetVocabularyTests(unittest.TestCase):
    def test_a_setting_written_with_its_unit_is_read_from_its_column(self):
        # 「負重 250 g」 names 砝碼質量_g by its unit, not by its header.
        self.assertEqual(_fe("負重 250 g 時，平均伸長量為 10.1 cm。", _LAB_ROW), [])

    def test_a_named_column_still_owns_figures_in_its_unit(self):
        # 9.9 cm is the second trial, not the mean the claim names.
        self.assertTrue(_fe("負重 250 g 時，平均伸長量為 9.9 cm。", _LAB_ROW))

    def test_the_readings_of_a_row_do_not_name_the_third_trial(self):
        # 「三次讀數」 is "the three readings"; it does not name 第三次伸長_cm.
        self.assertEqual(_fe("250 g 的伸長讀數為 10.2、9.9、10.2 cm。", _LAB_ROW), [])

    def test_a_numeral_pointing_into_the_table_is_not_a_count(self):
        from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

        self.assertEqual(_extract_numbers_with_unit("前四組相同，最後兩組略降"), [])
        self.assertEqual(_extract_numbers_with_unit("實驗分三組"), [("3", "組")])


if __name__ == "__main__":
    unittest.main()
