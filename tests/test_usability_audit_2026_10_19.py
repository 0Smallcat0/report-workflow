"""Defects found by writing three real reports through the pipeline (2026-10-19).

A Chinese physics lab report from a CSV and lab notes, an English business
report from a sales sheet and a memo, and a revision of an existing Chinese
progress report. Each test names what the author ran into, in the author's
words; the step-by-step records are in the description of PR #1.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.automation_harness import get_controlled_next_action, run_controlled_stage
from report_workflow.state import ReportState, run_dir_for


def _validators(**overrides) -> dict:
    base = {
        "claim_matrix": lambda _j, _w=None: {"status": "ok"},
        "outline": lambda _j, _w=None: {"status": "ok"},
        "drafts": lambda _j, _w=None: {"status": "ok"},
        "revision_plan": lambda _j, _w=None: {"status": "ok"},
        "artifact_lint": lambda _j, _w=None: {"status": "ok"},
        "publish": lambda _j, _w=None: {"status": "completed"},
    }
    base.update(overrides)
    return base


class AUnitsColumnIsNotAUnitOfMeasureTests(unittest.TestCase):
    """A sales sheet with a `units` column lost every numeric statistic.

    `units` (units sold: 420, 282, 208…) was read as a unit-of-measure column
    stating many different units, the file was declared mixed-unit, and the
    auto cross tables came out as row counts of a balanced design — 33.33%,
    33.33%, 33.33% — which the outline then made the author place or waive.
    """

    def _dataset(self, rows):
        from report_workflow.derived_evidence import Dataset

        return Dataset({"file_name": "sales.csv"}, rows)

    def test_a_numeric_units_column_keeps_the_measures(self):
        from report_workflow.derived_evidence import _auto_cross_tables, _mixed_unit_column

        rows = [
            {"region": region, "revenue_kusd": str(revenue), "units": str(units)}
            for region, revenue, units in (
                ("North", 142.2, 420), ("North", 91.7, 282), ("South", 119.3, 349),
                ("South", 79.2, 245), ("East", 120.9, 353), ("East", 80.6, 235),
            )
        ]
        dataset = self._dataset(rows)
        self.assertIsNone(_mixed_unit_column(dataset))
        text = _auto_cross_tables(dataset, zh=False)[0][0]
        self.assertIn("mean revenue_kusd", text)

    def test_a_unit_column_of_words_is_still_mixed(self):
        from report_workflow.derived_evidence import _mixed_unit_column

        dataset = self._dataset([
            {"item": "a", "value": "3", "unit": "kg"},
            {"item": "b", "value": "4", "unit": "t"},
        ])
        self.assertEqual(_mixed_unit_column(dataset), "unit")


class BNumbersTheProseWritesTests(unittest.TestCase):
    """Honest sentences FE blocked because of how a number was written."""

    def _findings(self, claim: str, evidence: str):
        from report_workflow.nodes.factuality_check import _content_overlap_findings

        return _content_overlap_findings({"claim_text": claim}, {"content": evidence})

    def test_each_length_five_times_is_not_five_per_classifier(self):
        # 「每個擺長重複 5 次」 was 5 次/個, so the claim 「並重複 5 次取平均」
        # restating it was "a unit the evidence does not state", by FE and FS.
        evidence = "步驟：每個擺長拉開約 10 度後放手，以碼表量測 10 次擺動的總時間，再除以 10 得週期；每個擺長重複 5 次取平均。"
        claim = "每個擺長量測 10 次擺動總時間後除以 10 得週期，並重複 5 次取平均。"
        self.assertEqual(self._findings(claim, evidence), [])

    def test_a_rate_with_a_unit_denominator_is_still_a_rate(self):
        from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

        self.assertEqual(_extract_numbers_with_unit("每噸 500 美元"), [("500", "美元/噸")])
        self.assertEqual(_extract_numbers_with_unit("每人 3 次"), [("3", "次/人")])

    def test_seven_by_twenty_four_in_either_spelling(self):
        evidence = "The support desk is staffed 7x24 and answers within 3 minutes on average."
        claim = "The support desk is staffed 7×24 and answers within 3 minutes on average."
        self.assertEqual(self._findings(claim, evidence), [])
        self.assertEqual(self._findings("實驗室開放時間為 7x24 小時。", "實驗室開放時間為 7×24 小時。"), [])

    def test_a_product_still_states_both_figures(self):
        findings = self._findings("The desk is staffed 7×36.", "The desk is staffed 7x24.")
        self.assertTrue(findings)

    def test_a_function_word_is_not_a_unit(self):
        from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

        self.assertEqual(_extract_numbers_with_unit("24/7 and"), [("24", ""), ("7", "")])
        self.assertEqual(_extract_numbers_with_unit("3 A current"), [("3", "A")])

    def test_the_engineering_audit_reads_both_spellings(self):
        from report_workflow.engineering_audit import _extract_numbers

        self.assertEqual(_extract_numbers("staffed 7x24"), ["7.0", "24.0"])
        self.assertEqual(_extract_numbers("staffed 7×24"), ["7.0", "24.0"])


class CPreflightDoesNotAskEveryTimeTests(unittest.TestCase):
    """SKILL.md's own record, `"install_decisions": {}`, was refused for mmdc."""

    def _issues(self, pending, decisions):
        from report_workflow.config import load_config
        from report_workflow.preflight_decisions import validate_preflight_decisions

        return validate_preflight_decisions(
            decisions, pending, [], cfg=load_config(), allow_degraded_render=False
        )

    def test_an_optional_install_left_out_is_skipped(self):
        pending = [{"name": "mmdc", "severity": "optional"}]
        record = {"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {}}
        self.assertEqual(self._issues(pending, record), [])

    def test_a_critical_install_still_needs_an_answer(self):
        pending = [{"name": "pandoc", "severity": "critical"}]
        record = {"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {}}
        self.assertEqual(self._issues(pending, record), ["missing install decision for 'pandoc'"])


class DResultsModeLivesWhereTheProfileHasItTests(unittest.TestCase):
    """engineering_lab_report has no `results` section; the brief said to use one."""

    def _blueprint(self, profile):
        from report_workflow.nodes import blueprint_plan

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["report_profile"] = profile
        return blueprint_plan.run_blueprint_plan(state).plan["blueprint"]

    def test_the_brief_names_results_discussion_for_a_lab_report(self):
        from report_workflow.nodes.agent_tasks import (
            _results_mode_rule,
            _results_mode_section,
            outline_brief_sections_block,
        )
        from report_workflow.nodes.blueprint_plan import results_section_id

        blueprint = self._blueprint("engineering_lab_report")
        section = results_section_id(blueprint)
        self.assertEqual(section, "results_discussion")
        self.assertIn("sections.results_discussion.results_mode",
                      _results_mode_section("engineering_lab_report", section))
        self.assertIn("sections.results_discussion.results_mode",
                      _results_mode_rule("engineering_lab_report", section))
        self.assertIn('"results_mode"', outline_brief_sections_block(blueprint))

    def test_profiles_with_a_results_section_are_unchanged(self):
        from report_workflow.nodes.blueprint_plan import results_section_id

        self.assertEqual(results_section_id(self._blueprint("academic_paper")), "results")

    def test_qa_gate_reads_results_mode_on_results_discussion(self):
        from report_workflow.nodes.qa_gate import _results_section_reasons

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["report_profile"] = "engineering_lab_report"
        state.plan["blueprint"] = {"sections": {"results_discussion": {}}, "section_order": ["results_discussion"]}
        state.plan["outline"] = {"sections": {"results_discussion": {"results_mode": "architectural_characterization"}}}
        merged = Path(run_dir_for(state)) / "merged.md"
        merged.write_text("# Results\n\nThe new layout improves latency.\n", encoding="utf-8")
        state.drafts["merged_draft_md"] = str(merged)
        self.assertEqual(_results_section_reasons(state), [])


class ERevisionTypesTheBriefDocumentsTests(unittest.TestCase):
    """`retitle` was refused by the pre-check as "Unknown change_type"."""

    SECTIONS = {"期中成果": "期中成果\n截至 6 月底，合計 1,200 具。", "問題與風險": "問題與風險\n訊號不足。"}

    def test_retitle_and_remove_section_pass_the_precheck(self):
        from report_workflow.nodes.base_document_diff import compute_revision_diff

        result = compute_revision_diff(self.SECTIONS, {"changes": [
            {"section_id": "期中成果", "change_type": "retitle", "new_text": "第三季成果"},
            {"section_id": "問題與風險", "change_type": "remove_section"},
        ]})
        self.assertEqual(result["unresolvable"], [])

    def test_retitle_still_needs_a_title_and_a_real_section(self):
        from report_workflow.nodes.base_document_diff import compute_revision_diff

        result = compute_revision_diff(self.SECTIONS, {"changes": [
            {"section_id": "期中成果", "change_type": "retitle", "new_text": ""},
            {"section_id": "附錄", "change_type": "remove_section"},
        ]})
        self.assertEqual(len(result["unresolvable"]), 2)

    def test_a_claim_carried_by_a_revision_change_is_linked(self):
        from report_workflow.nodes.factuality_check import _revision_plan_links

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["task_intent"] = "revise_existing"
        (run_dir_for(state) / "revision_plan.json").write_text(json.dumps({"changes": [{
            "section_id": "期中成果", "change_type": "replace", "original_text": "a", "new_text": "b",
            "claim_ids": ["c4"], "evidence_ids": ["E_D_alerts_total"],
        }]}), encoding="utf-8")
        links = _revision_plan_links(state)
        self.assertEqual(links[0]["claim_ids"], ["c4"])
        self.assertEqual(links[0]["evidence_ids"], ["E_D_alerts_total"])


class FHarnessKeepsWorkAlreadyWrittenTests(unittest.TestCase):
    """A rewind to an earlier stage treated the later drafts as an intrusion."""

    def _state(self, tmpdir):
        state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
        state.checkpoint("TEST")
        return state, state.output["workspace_root"], run_dir_for(state)

    def test_drafts_written_before_a_rewind_are_not_a_scope_violation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state, root, run_dir = self._state(tmpdir)
            (run_dir / "claim_matrix.json").write_text('{"claims":[]}', encoding="utf-8")
            run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            (run_dir / "outline.json").write_text("{}", encoding="utf-8")
            run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            (run_dir / "structured_drafts.json").write_text('{"sections":{}}', encoding="utf-8")
            failing = _validators(drafts=lambda _j, _w=None: {
                "status": "validation_failed",
                "error_details": "sentence 3 cites evidence its own claims do not list",
            })
            result = run_controlled_stage(state.job_id, failing, workspace_root=root)
            self.assertEqual(result["next_stage"], "claim_matrix")
            self.assertTrue(any(p.endswith("structured_drafts.json") for p in result["allowed_repair_paths"]))

            # The author fixes the claim and the sentence together.
            (run_dir / "claim_matrix.json").write_text('{"claims":[{"claim_id":"c1"}]}', encoding="utf-8")
            (run_dir / "structured_drafts.json").write_text('{"sections":{"x":{}}}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "outline")

    def test_editing_after_a_publish_failure_reopens_the_owning_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state, root, run_dir = self._state(tmpdir)
            for name, content in (
                ("claim_matrix.json", '{"claims":[]}'),
                ("outline.json", "{}"),
                ("structured_drafts.json", '{"sections":{}}'),
                (None, None),  # artifact_lint
            ):
                if name:
                    (run_dir / name).write_text(content, encoding="utf-8")
                run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(get_controlled_next_action(state.job_id, workspace_root=root)["stage"], "publish")

            # publish_report said "fix claim_matrix.json"; the author did, first.
            (run_dir / "claim_matrix.json").write_text('{"claims":[{"claim_id":"fixed"}]}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["stage"], "claim_matrix")

    def test_drift_on_a_passed_artifact_mid_run_is_validated_again(self):
        # Refused with a scope violation until 2026-10-20, which left an author
        # who had followed lint's advice nothing to restore; it is now sent
        # back through the stage that owns it (test_usability_review_2026_10_20).
        with tempfile.TemporaryDirectory() as tmpdir:
            state, root, run_dir = self._state(tmpdir)
            (run_dir / "claim_matrix.json").write_text('{"claims":[]}', encoding="utf-8")
            run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            (run_dir / "claim_matrix.json").write_text('{"claims":[{"claim_id":"x"}]}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["stage"], "claim_matrix")
            self.assertEqual(result["status"], "passed")


class GLintSaysWhatSubmitWillSayTests(unittest.TestCase):
    """lint_artifacts passed matrices that submit_action and FA then refused."""

    def _lint(self, claims, profile="engineering_lab_report", manifest_stage=None):
        from report_workflow.artifact_lint import lint_agent_artifacts

        state = ReportState.new("lint", [], tempfile.mkdtemp())
        state.spec["report_profile"] = profile
        run_dir = run_dir_for(state)
        ledger = run_dir / "evidence_ledger.jsonl"
        ledger.write_text(json.dumps({
            "evidence_id": "E1", "content": "本實驗目的是量測單擺週期。",
            "evidence_type": "qualitative", "allowed_claim_types": ["factual", "qualitative"],
        }) + "\n", encoding="utf-8")
        state.sources["evidence_ledger_path"] = str(ledger)
        (run_dir / "claim_matrix.json").write_text(json.dumps({"claims": claims}), encoding="utf-8")
        if manifest_stage:
            (run_dir / "harness_manifest.json").write_text(json.dumps({
                "stage_order": ["claim_matrix", "outline", "drafts", "artifact_lint", "publish"],
                "current_stage": manifest_stage,
            }), encoding="utf-8")
        return [issue["message"] for issue in lint_agent_artifacts(state)["issues"] if issue["severity"] == "error"]

    def _claim(self, **extra):
        claim = {"claim_id": "c1", "claim_text": "本實驗目的是量測單擺週期。", "evidence_ids": ["E1"],
                 "claim_type": "factual", "claim_role": "primary"}
        claim.update(extra)
        return claim

    def test_no_primary_claim_is_an_error(self):
        messages = self._lint([self._claim(claim_role="supporting")], manifest_stage="claim_matrix")
        self.assertTrue(any("primary claim" in m for m in messages))

    def test_a_claim_type_the_evidence_does_not_allow_is_an_error(self):
        messages = self._lint([self._claim(claim_type="statistical")], manifest_stage="claim_matrix")
        self.assertTrue(any("not allowed by its evidence" in m for m in messages))

    def test_an_unverified_claim_is_an_error(self):
        messages = self._lint([self._claim(status="unverified")], manifest_stage="claim_matrix")
        self.assertTrue(any("non-publishable" in m for m in messages))

    def test_drafts_not_yet_due_are_not_reported_missing(self):
        self.assertEqual(self._lint([self._claim()], manifest_stage="claim_matrix"), [])


class HStarterFiguresAreSuggestionsTests(unittest.TestCase):
    """Starter figures the outline did not use blocked the outline, then the render."""

    def test_unplaced_suggestions_are_not_built(self):
        from report_workflow.nodes.figure_build import _drop_unplaced_suggestions

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.plan["outline"] = {"sections": {"findings": {"figure_ids": ["2"]}}}
        figures = [
            {"figure_id": "1", "recommendation_id": "figrec_1"},
            {"figure_id": "2", "recommendation_id": "figrec_2"},
            {"figure_id": "mine"},
        ]
        kept = [figure["figure_id"] for figure in _drop_unplaced_suggestions(state, figures)]
        self.assertEqual(kept, ["2", "mine"])

    def test_an_edited_plan_does_not_demand_the_leftover_suggestions(self):
        from report_workflow.nodes.outline_plan import _validate_figure_plan_against_outline

        state = ReportState.new("x", [], tempfile.mkdtemp())
        plan_dir = run_dir_for(state) / "section_drafts"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "figure_plan.json").write_text(json.dumps({"figures": [
            {"figure_id": "1", "recommendation_id": "figrec_1"},
            {"figure_id": "2", "recommendation_id": "figrec_2", "title": "edited by the author"},
            {"figure_id": "mine"},
        ]}), encoding="utf-8")
        _validate_figure_plan_against_outline(state, {"findings": {"figure_ids": ["mine"]}})

    def test_a_figure_the_author_wrote_and_left_out_still_blocks(self):
        from report_workflow.errors import QAHardBlockError
        from report_workflow.nodes.outline_plan import _validate_figure_plan_against_outline

        state = ReportState.new("x", [], tempfile.mkdtemp())
        plan_dir = run_dir_for(state) / "section_drafts"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "figure_plan.json").write_text(json.dumps({"figures": [{"figure_id": "mine"}]}), encoding="utf-8")
        with self.assertRaises(QAHardBlockError):
            _validate_figure_plan_against_outline(state, {"findings": {"figure_ids": []}})


class IWhatTheDocumentShowsTests(unittest.TestCase):
    def test_the_documented_caption_form_is_not_numbered_twice(self):
        # authoring.md writes [TABLE:id 表 2　基準情境的階段組成]; following it
        # printed 「表 1. 表 1 各擺長的週期平方…」.
        from report_workflow.nodes.source_tables import _LEADING_TABLE_LABEL_RE

        self.assertEqual(_LEADING_TABLE_LABEL_RE.sub("", "表 1 各擺長的週期平方"), "各擺長的週期平方")
        self.assertEqual(_LEADING_TABLE_LABEL_RE.sub("", "Table 2 Revenue by region"), "Revenue by region")
        self.assertEqual(_LEADING_TABLE_LABEL_RE.sub("", "表格說明"), "表格說明")

    def test_a_linux_cjk_font_is_on_the_chart_font_list(self):
        # WenQuanYi was installed and the chart still drew Chinese as boxes.
        import matplotlib

        from report_workflow.nodes.figure_build import _configure_cjk_fonts

        _configure_cjk_fonts(matplotlib)
        fonts = matplotlib.rcParams["font.sans-serif"]
        self.assertIn("WenQuanYi Zen Hei", fonts)
        self.assertLess(fonts.index("WenQuanYi Zen Hei"), fonts.index("DejaVu Sans"))


if __name__ == "__main__":
    unittest.main()
