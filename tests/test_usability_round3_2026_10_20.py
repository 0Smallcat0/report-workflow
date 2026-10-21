"""Round 3 of the usability work (2026-10-20).

The independent review of PR #1 left a list of what was still in the way of an
author. Each test here was written to fail before its fix. The fixes do not
loosen any factuality check; where a test touches a check it also asserts the
check still blocks the false version of the claim.
"""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import ReportState

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "benchmarks" / "evidence"


def _all_packages_present(_module_name):
    return object()


def _prepare(tmpdir: str, files: dict, prompt: str, profile: str = "custom") -> ReportState:
    paths = []
    for name, text in files.items():
        p = Path(tmpdir) / name
        p.write_text(text, encoding="utf-8")
        paths.append(str(p))
    with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
        return prepare_workflow(prompt, paths, str(Path(tmpdir) / "out"), report_profile=profile)


_SURVEY = {
    "survey.csv": "slot,visitors\n09-12,41\n12-15,51\n15-18,71\n18-20,68\n"
                  "09-12,36\n12-15,50\n15-18,73\n18-20,59\n",
}


def _register(state, derivations):
    from report_workflow.agent_wrapper import register_derived_evidence

    return register_derived_evidence(
        state.job_id, derivations, workspace_root=state.output["workspace_root"]
    )


def _ledger(state) -> list[dict]:
    path = Path(state.sources["evidence_ledger_path"])
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AComparisonsReadTheTablesIntakeBuiltTests(unittest.TestCase):
    """`ratio` and `formula` could not name a table intake had already built.

    The brief lists the auto cross tabulations as "already built", but a ratio
    of two of its rows failed with "not a derivation computed earlier in this
    call", so the author registered an identical table by hand and then had to
    waive the original one in the outline.
    """

    def _auto_table(self, state) -> str:
        tables = [row for row in _ledger(state) if row.get("table_grid") and row.get("origin") == "auto"]
        self.assertEqual(len(tables), 1)
        return tables[0]["evidence_id"]

    def test_a_ratio_reads_two_rows_of_an_auto_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
            table_id = self._auto_table(state)
            result = _register(state, [{
                "id": "evening_vs_morning", "op": "ratio", "source": table_id,
                "column": "mean visitors", "numerator_group": "18-20",
                "denominator_group": "09-12", "decimals": 2,
            }])
            self.assertEqual(result["status"], "ok", result.get("problems"))
            content = result["evidence"][0]["content"]
            self.assertIn("1.65", content)  # 63.5 / 38.5

    def test_a_formula_reads_a_cell_of_an_auto_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
            table_id = self._auto_table(state)
            result = _register(state, [{
                "id": "evening_gap", "op": "formula", "expr": "late - early", "decimals": 1,
                "inputs": {
                    "late": {"table": table_id, "column": "mean visitors", "row": "18-20"},
                    "early": {"table": table_id, "column": "mean visitors", "row": "09-12"},
                },
            }])
            self.assertEqual(result["status"], "ok", result.get("problems"))
            self.assertIn("25", result["evidence"][0]["content"])

    def test_a_wrong_expect_against_an_auto_table_still_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
            table_id = self._auto_table(state)
            result = _register(state, [{
                "id": "evening_vs_morning", "op": "ratio", "source": table_id,
                "column": "mean visitors", "numerator_group": "18-20",
                "denominator_group": "09-12", "decimals": 2, "expect": 2.0,
            }])
            self.assertEqual(result["status"], "blocked")

    def test_an_unknown_source_lists_the_built_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
            table_id = self._auto_table(state)
            result = _register(state, [{
                "id": "x", "op": "ratio", "source": "by_slot", "column": "mean visitors",
                "numerator_group": "18-20", "denominator_group": "09-12",
            }])
            self.assertEqual(result["status"], "blocked")
            self.assertIn(table_id, json.dumps(result["problems"]))


class BAnEmptyOverflowBandIsNotARowTests(unittest.TestCase):
    """Buckets [5, 6, 7, 8, 9] over sleep hours that top out at 8.5 printed a
    `9+ | 0 | — | — | —` row in the delivered table. The last edge the author
    gave is where they chose to stop; an open band above it with nothing in it
    is not a finding.
    """

    _ROWS = "hours,score\n5.5,61\n6.2,66\n6.8,70\n7.1,72\n7.6,75\n8.0,79\n8.5,80\n"

    def _table(self, csv: str, buckets: list) -> dict:
        from report_workflow.derived_evidence import Dataset, compute_group_table

        lines = csv.strip().splitlines()
        header = lines[0].split(",")
        rows = [dict(zip(header, line.split(","))) for line in lines[1:]]
        frame = Dataset({"file_name": "sleep.csv", "source_id": "s1", "file_type": "csv"}, rows)
        return compute_group_table(frame, {
            "group_by": {"column": "hours", "buckets": buckets},
            "measures": [{"op": "count"}, {"op": "mean", "column": "score"}],
        })

    def test_an_empty_open_band_above_the_last_edge_is_dropped(self):
        table = self._table(self._ROWS, [5, 6, 7, 8, 9])
        labels = [row[0] for row in table["rows"]]
        self.assertNotIn("9+", labels)
        self.assertEqual(labels[-1], "All")
        self.assertEqual(table["derivation"]["groups"], 4)

    def test_an_open_band_holding_rows_is_kept(self):
        table = self._table(self._ROWS + "9.5,82\n", [5, 6, 7, 8, 9])
        self.assertIn("9+", [row[0] for row in table["rows"]])

    def test_an_empty_band_between_edges_is_kept(self):
        table = self._table(self._ROWS, [5, 6, 7, 8, 8.2, 9])
        self.assertIn("8–8.20", [row[0] for row in table["rows"]])

    def test_band_members_follow_the_rows(self):
        csv = "stars,n\n1,1\n2,1\n3,1\n4,1\n"
        table = self._table(csv.replace("stars", "hours").replace(",n", ",score"), [1, 3, 5])
        members = table["derivation"]["band_members"]
        self.assertEqual(len(members), len(table["rows"]) - 1)


class CStarterChartsSpeakTheReadersLanguageTests(unittest.TestCase):
    """Starter chart titles were raw column names, and every chart a proposal
    was offered was filed under budget_resources.

    `mean weekday_visitors and 1 other measure by time_slot` and
    `annual_cost_twd by item after sort desc` reached the caption; a table of
    visitor counts, which is the case for the proposal, was offered to the
    budget section beside the cost table.
    """

    _FILES = {
        "visits.csv": "time_slot,weekday_visitors,wait_minutes\nmorning,41,3\nafternoon,51,4\n"
                      "evening,71,6\nmorning,36,2\nafternoon,50,5\nevening,73,7\n",
        "cost.csv": "item,annual_cost_twd\nstaff,480000\nutilities,60000\nsecurity,90000\n",
    }

    def _recommendations(self, tmpdir: str, profile: str = "proposal") -> list[dict]:
        _prepare(tmpdir, self._FILES, "Write a proposal to extend library opening hours", profile)
        found = list(Path(tmpdir, "out").rglob("figure_recommendations.json"))
        self.assertEqual(len(found), 1)
        return json.loads(found[0].read_text(encoding="utf-8"))["recommendations"]

    def test_titles_carry_no_raw_column_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            titles = [rec["figure_plan"]["title"] for rec in self._recommendations(tmpdir)]
        self.assertTrue(titles)
        for title in titles:
            self.assertNotIn("_", title)
            self.assertNotIn("sort desc", title)
        self.assertIn("Annual cost (TWD) by item", titles)

    def test_a_proposal_files_demand_data_under_the_problem_and_costs_under_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recs = self._recommendations(tmpdir)
        by_source = {}
        for rec in recs:
            by_source.setdefault(rec["source_file_name"], set()).add(rec["section_id"])
        self.assertEqual(by_source["cost.csv"], {"budget_resources"})
        self.assertEqual(by_source["visits.csv"], {"problem_statement"})

    def test_a_profile_with_a_results_section_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recs = self._recommendations(tmpdir, "academic_paper")
        self.assertEqual({rec["section_id"] for rec in recs}, {"results"})

    def test_humanized_names(self):
        from report_workflow.nodes.figure_recommend import _reader_label

        self.assertEqual(_reader_label("週期_s"), "週期 (s)")
        self.assertEqual(_reader_label("溫度_C"), "溫度 (°C)")
        self.assertEqual(_reader_label("mean median_processing_minutes"), "mean median processing minutes")
        self.assertEqual(_reader_label("annual_cost_twd"), "annual cost (TWD)")
        self.assertEqual(_reader_label("Revenue (USD)"), "Revenue (USD)")


class DReusingAnEarlierRunTests(unittest.TestCase):
    """remap_agent_artifacts could neither find nor bring over an earlier run.

    The brief says "if you reuse artifacts from an older job, run
    remap_agent_artifacts". The agent tool had no way to say where the older
    run lives, so a run under a non-default workspace was "not found" once the
    process that made it had exited; and when it was found, only files already
    sitting in the new run were rewritten -- nothing was copied, so the
    author's claim matrix stayed behind in the old directory.
    """

    def _two_runs(self, tmpdir: str):
        from report_workflow.state import run_dir_for

        old = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
        old_dir = run_dir_for(old)
        ids = [row["evidence_id"] for row in _ledger(old)][:2]
        (old_dir / "claim_matrix.json").write_text(json.dumps({
            "_contract": {"job_id": old.job_id},
            "claims": [{"claim_id": "c1", "claim_text": "x", "evidence_ids": ids}],
        }), encoding="utf-8")
        (old_dir / "outline.json").write_text(json.dumps({"sections": {}}), encoding="utf-8")
        new = _prepare(tmpdir, _SURVEY, "write a short report on library visitors by time slot")
        return old, new, ids

    def _forget_where_runs_live(self):
        from report_workflow import state as state_module

        state_module._JOB_RUN_HINTS.clear()

    def test_the_earlier_run_is_found_in_the_same_workspace(self):
        from report_workflow.agent_wrapper import remap_agent_artifacts

        with tempfile.TemporaryDirectory() as tmpdir:
            old, new, _ids = self._two_runs(tmpdir)
            self._forget_where_runs_live()
            result = remap_agent_artifacts(new.job_id, old.job_id, write=False,
                                           workspace_root=new.output["workspace_root"])
            self.assertNotEqual(result.get("status"), "failed", result)

    def test_the_earlier_run_may_live_in_another_workspace(self):
        from report_workflow.agent_wrapper import remap_agent_artifacts

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            old = _prepare(first, _SURVEY, "write a short report on library visitors by time slot")
            new = _prepare(second, _SURVEY, "write a short report on library visitors by time slot")
            self._forget_where_runs_live()
            result = remap_agent_artifacts(new.job_id, old.job_id, write=False,
                                           workspace_root=new.output["workspace_root"],
                                           previous_workspace_root=old.output["workspace_root"])
            self.assertNotEqual(result.get("status"), "failed", result)

    def test_the_authors_files_are_copied_and_stamped_for_this_run(self):
        from report_workflow.agent_wrapper import remap_agent_artifacts
        from report_workflow.state import run_dir_for

        with tempfile.TemporaryDirectory() as tmpdir:
            old, new, ids = self._two_runs(tmpdir)
            result = remap_agent_artifacts(new.job_id, old.job_id, write=True,
                                           workspace_root=new.output["workspace_root"])
            self.assertEqual(result["status"], "ok", result)
            copied = json.loads((run_dir_for(new) / "claim_matrix.json").read_text(encoding="utf-8"))
            self.assertEqual(copied["_contract"]["job_id"], new.job_id)
            self.assertEqual(copied["claims"][0]["evidence_ids"], [result["mapping"].get(i, i) for i in ids])
            self.assertIn("claim_matrix.json", result["files_copied"])

    def test_a_controlled_run_receives_each_file_when_its_stage_opens(self):
        from report_workflow.agent_wrapper import remap_agent_artifacts
        from report_workflow.automation_harness import get_controlled_next_action
        from report_workflow.state import run_dir_for

        with tempfile.TemporaryDirectory() as tmpdir:
            old, new, _ids = self._two_runs(tmpdir)
            root = new.output["workspace_root"]
            self.assertEqual(get_controlled_next_action(new.job_id, workspace_root=root)["stage"], "claim_matrix")
            result = remap_agent_artifacts(new.job_id, old.job_id, write=True, workspace_root=root)
            self.assertIn("claim_matrix.json", result["files_copied"])
            self.assertFalse((run_dir_for(new) / "outline.json").exists())
            self.assertEqual(result["files_deferred"].get("outline.json"), "outline")


_NOTES = (
    "Survey method: 40 undergraduates self-reported sleep. The survey ran from 3 to 14 March 2026.\n\n"
    "Walker (2017, Why We Sleep) argues that sleep after learning consolidates memory.\n\n"
    "Okano et al. (2019, npj Science of Learning) found that sleep explained about 25% of the "
    "variance in grades of 88 MIT students.\n"
)


def _notes_registry(text: str = _NOTES) -> list[dict]:
    blocks = [
        {"block_id": f"b{i}", "block_type": "paragraph", "content": para}
        for i, para in enumerate(p for p in text.split("\n\n") if p.strip())
    ]
    return [{"source_id": "notes", "file_name": "background_notes.md", "file_type": "md",
             "parsed_content": blocks}]


class EReferencesTheAuthorCanSeeTests(unittest.TestCase):
    """A paper that wrote "Okano et al. (2019)" in its discussion published
    with no reference list.

    The notes named both works by author and year, and nothing read that
    shape, so neither reached the References. The two lines the author wrote
    under References were removed for not looking like publications (no DOI,
    no "journal" or "press"), and the only trace was a log line nobody sees.
    """

    def test_an_author_year_mention_in_the_notes_is_a_cited_source(self):
        from report_workflow.nodes.cited_sources import extract_cited_sources, format_reference_entry

        cited = extract_cited_sources(_notes_registry())
        entries = [format_reference_entry(c) for c in cited]
        self.assertEqual(len(cited), 2, entries)
        self.assertEqual(entries[0], "Walker. (2017). *Why We Sleep*.")
        self.assertEqual(entries[1], "Okano et al. (2019). *npj Science of Learning*.")

    def test_a_month_or_a_table_with_a_year_is_not_an_author(self):
        from report_workflow.nodes.cited_sources import extract_cited_sources

        cited = extract_cited_sources(_notes_registry(
            "Data from March (2026) and Table (2025) and In (2024) were pooled.\n"
        ))
        self.assertEqual(cited, [])

    def test_a_reference_line_the_sources_state_is_kept(self):
        from report_workflow.nodes.docx_render import _filter_body_reference_lines
        from report_workflow.nodes.cited_sources import reference_line_is_stated

        stated = lambda line: reference_line_is_stated(line, _notes_registry())
        kept = _filter_body_reference_lines([
            "- Walker, M. (2017). Why We Sleep. Scribner.",
            "- Okano, K., et al. (2019). Sleep quality and academic performance. npj Science of Learning, 4, 16.",
            "- Smith, J. (2021). A study nobody supplied. Sleep Review.",
            "- Walker, M. (2018). The wrong year. Scribner.",
        ], strict=True, stated=stated)
        self.assertEqual(len(kept), 2, kept)
        self.assertTrue(kept[0].startswith("- Walker, M. (2017)"))
        self.assertTrue(kept[1].startswith("- Okano"))

    def test_removed_lines_are_named_where_the_author_looks(self):
        from report_workflow.nodes.docx_render import _split_body_references

        removed: list[str] = []
        md = "# Body\n\nText.\n\n## References\n\n- Smith, J. (2021). A study nobody supplied.\n"
        body, refs = _split_body_references(md, strict_refs=True, stated=lambda _l: False, removed=removed)
        self.assertEqual(refs, "")
        self.assertEqual(removed, ["Smith, J. (2021). A study nobody supplied."])

    def test_the_delivery_summary_lists_author_notices(self):
        from report_workflow.artifact_packaging.final_qa import _build_final_qa_summary_md

        summary = _minimal_summary()
        summary["author_notices"] = ["References: removed 1 line no supplied file states: Smith (2021)"]
        md = _build_final_qa_summary_md(summary)
        self.assertIn("## For the author", md)
        self.assertIn("Smith (2021)", md)


def _minimal_summary() -> dict:
    return {
        "overall_status": "pass", "report_profile": "academic_paper",
        "gate_summary": {"qa_decision": "pass", "hard_fail_reasons": []},
        "factuality": {"status": "pass", "verified_count": 1, "blocked_count": 0,
                       "checkers_run": ["FE"], "verified_means": "x"},
        "artifact_lint": {"status": "pass", "error_count": 0, "warning_count": 0},
        "engineering_audit": {"status": "n/a", "warning_count": 0, "table_evidence_count": 0},
        "template_style": {"status": "n/a", "warning_count": 0, "reference_docx_applied": False},
        "template_field_fill": {"status": "n/a", "filled_count": 0, "warning_count": 0},
        "figure_visual_quality": {"status": "pass", "issue_count": 0, "figure_count": 0},
        "render": {"status": "pass", "paragraph_count": 1, "table_count": 0, "inline_shape_count": 0,
                   "issues": [], "visual_review": {}},
        "report": {"renderer_used": "pandoc", "published_report_path": "r.docx", "final_docx_path": ""},
        "source_artifacts": {},
    }


_SLEEP = {
    "sleep.csv": "student,hours,score\n"
                 "s1,5.0,62\ns2,5.5,70\ns3,6.0,66\ns4,6.5,75\ns5,7.0,73\n"
                 "s6,7.5,82\ns7,8.0,80\ns8,8.5,88\ns9,,90\ns10,6.2,n/a\n",
}


class FCorrelationAndASimpleFitAreRegistrableTests(unittest.TestCase):
    """There was no way to cite a correlation, a slope or an R².

    A paper on sleep and grades could only state group means; "r = 0.93"
    typed into prose is the unbacked number FE exists to block, and no op
    computed it. `pearson_r` and `linear_fit` are computed from the rows like
    every other derivation, and the evidence text states every figure a
    sentence may quote.
    """

    # The eight rows with both values, computed independently.
    _N = 8

    @staticmethod
    def _reference():
        xs = [5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5]
        ys = [62, 70, 66, 75, 73, 82, 80, 88]
        mx, my = sum(xs) / 8, sum(ys) / 8
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx
        r = sxy / (sxx * syy) ** 0.5
        return r, slope, my - slope * mx

    def test_pearson_r_is_computed_from_rows_with_both_values(self):
        r, _slope, _intercept = self._reference()
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SLEEP, "write a short paper on sleep and scores")
            result = _register(state, [{"id": "sleep_r", "op": "pearson_r", "source": "sleep.csv",
                                        "x": "hours", "y": "score", "decimals": 2}])
            self.assertEqual(result["status"], "ok", result.get("problems"))
            content = result["evidence"][0]["content"]
            self.assertIn(f"{r:.2f}", content)
            self.assertIn("n = 8", content)

    def test_linear_fit_states_slope_intercept_r2_and_n(self):
        r, slope, intercept = self._reference()
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SLEEP, "write a short paper on sleep and scores")
            result = _register(state, [{"id": "sleep_fit", "op": "linear_fit", "source": "sleep.csv",
                                        "x": "hours", "y": "score", "decimals": 2}])
            self.assertEqual(result["status"], "ok", result.get("problems"))
            content = result["evidence"][0]["content"]
            for figure in (f"{slope:.2f}", f"{intercept:.2f}", f"{r * r:.2f}", "n = 8"):
                self.assertIn(figure, content)

    def test_expect_is_checked_against_the_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SLEEP, "write a short paper on sleep and scores")
            result = _register(state, [{"id": "sleep_r", "op": "pearson_r", "source": "sleep.csv",
                                        "x": "hours", "y": "score", "decimals": 2, "expect": 0.5}])
            self.assertEqual(result["status"], "blocked")

    def test_a_column_that_is_not_numeric_or_too_few_pairs_is_refused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SLEEP, "write a short paper on sleep and scores")
            bad = _register(state, [{"id": "a", "op": "pearson_r", "source": "sleep.csv",
                                     "x": "student", "y": "score"}])
            self.assertEqual(bad["status"], "blocked")
            few = _register(state, [{"id": "b", "op": "linear_fit", "source": "sleep.csv",
                                     "x": "hours", "y": "score", "rows": "hours>=8"}])
            self.assertEqual(few["status"], "blocked")
            self.assertIn("3", json.dumps(few["problems"]))

    def test_fe_accepts_the_stated_r_and_blocks_a_different_one(self):
        from report_workflow.nodes.factuality_check import _check_content_overlap

        def fe(text, evidence):
            return _check_content_overlap({"claim_id": "c1", "claim_text": text, "claim_type": "statistical"}, evidence[0])

        r, _slope, _intercept = self._reference()
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, _SLEEP, "write a short paper on sleep and scores")
            result = _register(state, [{"id": "sleep_r", "op": "pearson_r", "source": "sleep.csv",
                                        "x": "hours", "y": "score", "decimals": 2}])
            evidence = [row for row in _ledger(state) if row["evidence_id"] == "E_D_sleep_r"]
            self.assertEqual(len(evidence), 1)
            good = fe(f"Sleep and score were strongly correlated (r = {r:.2f}, n = 8).", evidence)
            wrong = fe("Sleep and score were strongly correlated (r = 0.71, n = 8).", evidence)
            self.assertFalse(good, good)
            self.assertTrue(wrong)


class IAnAbstractLengthSaysWhatItCountsTests(unittest.TestCase):
    """The brief said "300-500 characters"; the author's abstract was 312
    characters long and the gate answered "287 characters". It counts Chinese
    characters and Latin words and skips punctuation, which neither the brief
    nor the message said, so the author lengthened it by guesswork.
    """

    _TEXT = "本研究量測教室二氧化碳濃度，並記錄專注度。" * 13

    def test_the_message_names_what_is_counted(self):
        from report_workflow.nodes.abstract_check import _word_count_check

        errors = _word_count_check(self._TEXT, "admissions_project_report")
        self.assertEqual(len(errors), 1)
        self.assertIn("punctuation", errors[0])
        self.assertIn(str(len(self._TEXT)), errors[0])

    def test_the_rule_is_unchanged(self):
        from report_workflow.nodes.abstract_check import _word_count_check

        self.assertTrue(_word_count_check(self._TEXT, "admissions_project_report"))
        self.assertFalse(_word_count_check(self._TEXT * 2, "admissions_project_report"))

    def test_the_brief_says_punctuation_is_not_counted(self):
        from report_workflow.nodes.agent_tasks import _abstract_section

        text = _abstract_section("admissions_project_report", {"sections": {"abstract": {}}}, "zh")
        self.assertIn("punctuation", text)


class JTheAdmissionsBriefIsAboutTheAuthorsProjectTests(unittest.TestCase):
    """The drafts brief told a high-school CO2 project to use "deterministic
    compilation / StrategyIR / AST / orthogonal quality gates as the spine"
    and to treat "LLM components" as supporting modules: one earlier
    project's outline, given to every admissions report.
    """

    def test_no_other_projects_spine_in_the_brief(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _prepare(tmpdir, _SURVEY, "write a project report on library visitors", "admissions_project_report")
            brief = next(Path(tmpdir, "out").rglob("03_section_draft.md")).read_text(encoding="utf-8")
        self.assertIn("project-monograph tone", brief)
        for leaked in ("StrategyIR", "orthogonal quality gates", "LLM components"):
            self.assertNotIn(leaked, brief)


class GRecordedRunsReproduceFromTheRepoTests(unittest.TestCase):
    """Recorded author scripts once loaded files from another session's /tmp.

    Scripts that import `/tmp/...` or read sources from `/home/user/...` cannot
    be rerun by anyone who clones the repo, and leak the recording machine.
    """

    def test_no_authored_script_names_a_machine_path(self):
        offenders = []
        for py in EVIDENCE.glob("usability_*/**/*.py"):
            text = py.read_text(encoding="utf-8")
            if re.search(r"['\"](/tmp/|/home/|[A-Z]:\\\\)", text):
                offenders.append(str(py.relative_to(REPO)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
