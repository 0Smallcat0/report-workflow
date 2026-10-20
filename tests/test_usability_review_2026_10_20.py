"""Defects found by writing two more reports through the pipeline (2026-10-20).

An independent review of the 2026-10-19 audit: a Chinese proposal to a
district office (a visitor-count CSV, a survey CSV and a budget memo) and an
English academic paper for a statistics course (a 40-row survey and a page
of background notes), each written from `start_report` to `publish_report`
the way SKILL.md describes. Each test names what stopped the author.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import ReportState, run_dir_for


def _all_packages_present(_module_name):
    return object()


def _prepare_survey(tmpdir: str, profile: str = "custom") -> ReportState:
    src = Path(tmpdir) / "survey.csv"
    src.write_text(
        "slot,visitors\n09-12,41\n12-15,51\n15-18,71\n18-20,68\n"
        "09-12,36\n12-15,50\n15-18,73\n18-20,59\n",
        encoding="utf-8",
    )
    with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
        return prepare_workflow(
            "write a short report on library visitors by time slot",
            [str(src)],
            str(Path(tmpdir) / "out"),
            report_profile=profile,
        )


class AFailedRegistrationDoesNotPoisonTheRunTests(unittest.TestCase):
    """A derivation that failed once blocked publish for good.

    The author asked for a ratio before the table it reads (the brief's own
    "order matters" mistake), was told so, and registered the pair again in
    the right order. The stored file kept the ratio at its first position, so
    the second call failed with the same "not computed earlier in this call"
    message although the author's list was now correct. Registering it under
    a new name worked, but the dead entry stayed in derived_evidence.json and
    publish_report then stopped at DERIVED_EVIDENCE over a figure no sentence
    cited, routing the author to the drafts stage, which cannot touch it.
    """

    def _register(self, state, derivations):
        from report_workflow.agent_wrapper import register_derived_evidence

        return register_derived_evidence(
            state.job_id, derivations, workspace_root=state.output["workspace_root"]
        )

    _TABLE = {"id": "by_slot", "source": "survey.csv", "group_by": {"column": "slot"},
              "measures": [{"op": "mean", "column": "visitors", "label": "Mean visitors"}]}
    _RATIO = {"id": "evening_vs_morning", "op": "ratio", "source": "by_slot",
              "column": "Mean visitors", "numerator_group": "18-20", "denominator_group": "09-12"}

    def test_registering_again_in_the_right_order_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir)
            first = self._register(state, [self._RATIO])
            self.assertEqual(first["status"], "blocked")

            second = self._register(state, [self._TABLE, self._RATIO])
            self.assertEqual(second["status"], "ok", second["problems"])
            self.assertIn("E_D_evening_vs_morning", {e["evidence_id"] for e in second["evidence"]})

    def test_a_derivation_that_failed_is_not_kept(self):
        from report_workflow.nodes.derived_evidence import load_requests, run_derived_evidence

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir)
            self._register(state, [self._RATIO])
            ok = self._register(state, [self._TABLE])
            self.assertEqual(ok["status"], "ok", ok["problems"])

            run_dir = run_dir_for(state)
            self.assertEqual([r["id"] for r in load_requests(run_dir)], ["by_slot"])
            # The validate-time recomputation is what used to stop publish.
            run_derived_evidence(ReportState.resume(state.job_id, workspace_root=state.output["workspace_root"]))

    def test_a_failed_re_registration_keeps_the_figure_already_cited(self):
        from report_workflow.nodes.derived_evidence import load_requests

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir)
            self.assertEqual(self._register(state, [self._TABLE])["status"], "ok")
            broken = dict(self._TABLE, measures=[{"op": "mean", "column": "no_such_column"}])
            result = self._register(state, [broken])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("Not registered: by_slot", result["message"])
            self.assertIn("previous version of by_slot is still registered", result["message"])

            run_dir = run_dir_for(state)
            self.assertEqual(load_requests(run_dir), [self._TABLE])
            ledger = (run_dir / "evidence_ledger.jsonl").read_text(encoding="utf-8")
            self.assertIn("E_D_by_slot", ledger)


class BBandLabelsAreReadAsNumbersTests(unittest.TestCase):
    """The tool prints a 7.5 bucket edge as 7.50 and then refused 7.5.

    Buckets [4, 6, 7.5, 9] came back as rows 4–6, 6–7.50 and 7.50–9. A
    comparison naming the band the way the author had just written the edge,
    "7.5-9", was refused as "not a row" — the dash already is forgiven, the
    trailing zero the tool added itself was not.
    """

    def test_a_trailing_zero_the_tool_printed_is_not_a_different_band(self):
        from report_workflow.derived_evidence import _same_label

        self.assertTrue(_same_label("7.50–9", "7.5-9"))
        self.assertTrue(_same_label("6–7.50", "6-7.5"))
        self.assertFalse(_same_label("7.50–9", "7.5-10"))
        self.assertFalse(_same_label("North", "South"))

    def test_registering_against_the_band_as_the_author_wrote_it(self):
        from report_workflow.agent_wrapper import register_derived_evidence

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sleep.csv"
            src.write_text(
                "sleep_hours,score\n4.5,70\n5.5,74\n6.5,80\n7.0,84\n7.8,88\n8.6,90\n",
                encoding="utf-8",
            )
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                state = prepare_workflow("write a paper", [str(src)], str(Path(tmpdir) / "out"), report_profile="custom")
            result = register_derived_evidence(state.job_id, [
                {"id": "bands", "source": "sleep.csv",
                 "group_by": {"column": "sleep_hours", "buckets": [4, 6, 7.5, 9]},
                 "measures": [{"op": "mean", "column": "score", "label": "Mean score"}]},
                {"id": "gap", "op": "ratio", "source": "bands", "column": "Mean score",
                 "numerator_group": "7.5-9", "denominator_group": "4-6", "decimals": 2},
            ], workspace_root=state.output["workspace_root"])
            self.assertEqual(result["status"], "ok", result["problems"])


class CTheClaimStageSaysWhatFAWillSayTests(unittest.TestCase):
    """A claim type the evidence does not allow passed the claim stage.

    The paper's method claim cited the survey's row-count statistic and was
    typed `methodological`. submit_action accepted the claim matrix; the
    author wrote the outline, and only `lint_artifacts` (or, without it, FA at
    publish) said the type was not allowed — after the stage that owns the
    file had closed.
    """

    def _submit(self, claim_type, status="supported"):
        from report_workflow.agent_wrapper import submit_claim_matrix

        tmpdir = tempfile.mkdtemp()
        state = _prepare_survey(tmpdir, profile="proposal")
        run_dir = run_dir_for(state)
        # The intake row count, as the paper's method claim cited it.
        row = next(
            json.loads(line)
            for line in (run_dir / "evidence_ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(line)["content"].startswith("Derived statistics")
        )
        (run_dir / "claim_matrix.json").write_text(json.dumps({"claims": [{
            "claim_id": "c1", "claim_text": "Visitors were counted in four time slots.",
            "claim_type": claim_type, "status": status, "evidence_ids": [row["evidence_id"]],
        }]}), encoding="utf-8")
        return submit_claim_matrix(state.job_id, workspace_root=state.output["workspace_root"]), row

    def test_a_type_the_evidence_does_not_allow_is_refused_at_the_claim_stage(self):
        result, row = self._submit("methodological")
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("c1", result["error_details"])
        self.assertIn("'methodological'", result["error_details"])
        self.assertIn(f"{row['evidence_id']} allows factual, statistical", result["error_details"])

    def test_a_non_publishable_status_is_refused_at_the_claim_stage(self):
        result, _row = self._submit("factual", status="unverified")
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("unverified", result["error_details"])

    def test_an_allowed_type_still_passes(self):
        result, _row = self._submit("statistical")
        self.assertEqual(result["status"], "step_1_complete", result.get("error_details"))


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


class DAPassedArtifactCanStillBeFixedTests(unittest.TestCase):
    """Fixing the claim matrix during the outline stage could not be undone.

    lint_artifacts reported a claim type error after the claim stage had
    passed. The author fixed claim_matrix.json, and the outline stage refused
    with a scope violation: "restore its previous content". The previous
    content was not the author's — CLAIM_PLAN rewrites the file it accepts —
    so there was nothing to restore it from, and putting the author's own
    earlier version back was refused the same way. The run was dead.
    """

    def _state(self, tmpdir):
        state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
        state.checkpoint("TEST")
        return state, state.output["workspace_root"], run_dir_for(state)

    def test_fixing_a_passed_artifact_reopens_its_stage(self):
        from report_workflow.automation_harness import get_controlled_next_action, run_controlled_stage

        with tempfile.TemporaryDirectory() as tmpdir:
            state, root, run_dir = self._state(tmpdir)
            (run_dir / "claim_matrix.json").write_text('{"claims":[]}', encoding="utf-8")
            run_controlled_stage(state.job_id, _validators(), workspace_root=root)

            (run_dir / "claim_matrix.json").write_text('{"claims":[{"claim_id":"fixed"}]}', encoding="utf-8")
            (run_dir / "outline.json").write_text("{}", encoding="utf-8")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["status"], "passed", result.get("error_details"))
            self.assertEqual(result["stage"], "claim_matrix")
            self.assertEqual(result["next_stage"], "outline")
            self.assertIn("claim_matrix.json changed after", result["note"])

            # The outline written meanwhile is kept and validated next.
            self.assertEqual(get_controlled_next_action(state.job_id, workspace_root=root)["stage"], "outline")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "drafts")

    def test_a_later_stage_file_written_early_is_still_refused(self):
        from report_workflow.automation_harness import run_controlled_stage

        with tempfile.TemporaryDirectory() as tmpdir:
            state, root, run_dir = self._state(tmpdir)
            (run_dir / "claim_matrix.json").write_text('{"claims":[]}', encoding="utf-8")
            run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            (run_dir / "structured_drafts.json").write_text('{"sections":{}}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _validators(), workspace_root=root)
            self.assertEqual(result["status"], "scope_violation")
            self.assertEqual(result["stage"], "outline")

    def test_a_violation_names_each_path_once(self):
        from report_workflow.automation_harness import _scope_violation_message

        message = _scope_violation_message("outline", [
            {"relative_path": "structured_drafts.json", "reason": "changed outside current stage write scope"},
            {"relative_path": "structured_drafts.json", "reason": "changed after stage 'drafts' passed"},
        ])
        self.assertEqual(message.count("structured_drafts.json"), 1)


class EHeadingNumbersDoNotSkipTests(unittest.TestCase):
    """A proposal without the optional timeline went 5. → 7.

    The proposal used seven of the blueprint's sections and left out the
    optional 時程規劃. The delivered document numbered 範疇與交付項目 as 5 and
    預算與資源 as 7: numbers were assigned from the blueprint's list, not from
    the sections the document has.
    """

    BLUEPRINT = {
        "section_order": ["executive_summary", "scope", "timeline", "budget", "references"],
        "sections": {
            "executive_summary": {"title": "Executive Summary", "required": True},
            "scope": {"title": "Scope", "required": True},
            "timeline": {"title": "Timeline", "required": False},
            "budget": {"title": "Budget", "required": False},
            "references": {"title": "References", "required": False},
        },
    }

    def test_an_omitted_optional_section_takes_no_number(self):
        from report_workflow.nodes.heading_contract_check import normalize_heading_contract

        markdown = "# Executive Summary\n\nA.\n\n# Scope\n\nB.\n\n# Budget\n\nC.\n"
        normalized, issues = normalize_heading_contract(markdown, self.BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 1. Executive Summary", normalized)
        self.assertIn("# 2. Scope", normalized)
        self.assertIn("# 3. Budget", normalized)

    def test_every_section_present_keeps_the_blueprint_numbers(self):
        from report_workflow.nodes.heading_contract_check import normalize_heading_contract

        markdown = "# Executive Summary\n\nA.\n\n# Scope\n\nB.\n\n# Timeline\n\nT.\n\n# Budget\n\nC.\n"
        normalized, _ = normalize_heading_contract(markdown, self.BLUEPRINT)
        self.assertIn("# 3. Timeline", normalized)
        self.assertIn("# 4. Budget", normalized)


class FTheDraftBriefShowsThePreferredPathTests(unittest.TestCase):
    """The drafts brief never mentioned structured_drafts.json.

    SKILL.md calls it "the preferred low-drift new-draft input", and the
    drafts stage allows writing it, but 03_section_draft.md — the file
    get_next_action says to read — documented only hand-written Markdown
    plus a hand-built sentence_map.jsonl. An author following the brief took
    the longer, error-prone path.
    """

    def test_the_brief_shows_structured_drafts_with_this_runs_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir, profile="proposal")
            brief = (run_dir_for(state) / "agent_tasks" / "03_section_draft.md").read_text(encoding="utf-8")
            self.assertIn("structured_drafts.json", brief)
            self.assertIn('"executive_summary": {"paragraphs"', brief)
            self.assertIn("problem_statement", brief)
            self.assertLess(brief.index("structured_drafts.json"), brief.index("Each sentence map line"))


class GTheDecisionTemplateAsksOnlyWhatIsRequiredTests(unittest.TestCase):
    """check_environment's template still listed every optional item.

    The 10-19 fix made start_report accept an empty answer for optional
    installs, but check_environment kept returning
    `required_preflight_decisions` with mmdc, notebook_sync and web_research
    in it, and setup-and-preflight.md says "always start from" that template.
    An agent following it asked the user three optional questions first.
    """

    PENDING = [
        {"name": "mmdc", "severity": "optional"},
        {"name": "pandoc", "severity": "critical"},
    ]
    ASK = [{"feature_id": "web_research"}, {"feature_id": "notebook_sync"}]

    def test_optional_items_are_not_in_the_required_template(self):
        from report_workflow.preflight_decisions import required_preflight_decision_shape

        shape = required_preflight_decision_shape(self.PENDING, self.ASK)
        self.assertEqual(list(shape["install_decisions"]), ["pandoc"])
        self.assertEqual(shape["feature_decisions"], {})

    def test_a_feature_switched_on_still_needs_its_decision(self):
        from report_workflow.preflight_decisions import required_preflight_decision_shape

        shape = required_preflight_decision_shape(self.PENDING, self.ASK, {"web_research"})
        self.assertEqual(list(shape["feature_decisions"]), ["web_research"])

    def test_check_environment_separates_the_optional_ones(self):
        from report_workflow.agent_wrapper import check_environment

        result = check_environment()
        required = result["required_preflight_decisions"]
        optional = result["optional_preflight_decisions"]
        self.assertFalse(set(required["install_decisions"]) & set(optional["install_decisions"]))
        self.assertFalse(set(required["feature_decisions"]) & set(optional["feature_decisions"]))


class HAStarterChartDoesNotAddUpUnlikeThingsTests(unittest.TestCase):
    """The first chart offered for visitors by time slot was a stacked bar.

    It stacked the row count, the share of rows, the mean and the median on
    top of one another, and drew the 合計 (total) row as a fifth time slot.
    The 佔比 column's "%" sent the table down the composition branch. The
    numbers were real; the picture said 9 + 25% + 40.78 + 41 was a quantity.
    """

    def _recommend(self, headers, rows, total_label="合計"):
        from report_workflow.nodes.figure_recommend import recommend_figures_from_evidence

        state = ReportState.new("x", [], tempfile.mkdtemp())
        entry = {
            "evidence_id": "E_slot", "source_file_name": "visits.csv",
            "content": "衍生統計:時段 分組交叉表。" + " ".join("|".join(r) for r in [headers, *rows]),
            "table_grid": {"headers": headers, "rows": rows + [[total_label] + ["0"] * (len(headers) - 1)]},
        }
        recs = recommend_figures_from_evidence(state, [entry])
        self.assertTrue(recs)
        return recs[0]

    def test_counts_shares_and_the_total_row_are_not_plotted(self):
        rec = self._recommend(
            ["時段", "筆數", "佔比", "平均每日入館人次 平均", "平均每日入館人次 中位數"],
            [["09-12", "9", "25.00%", "40.78", "41.00"], ["12-15", "9", "25.00%", "51.44", "50.00"],
             ["15-18", "9", "25.00%", "69.44", "68.00"], ["18-20", "9", "25.00%", "64.00", "66.00"]],
        )
        self.assertNotEqual(rec["recommended_figure_type"], "stacked_bar")
        data = rec["figure_plan"]["data"]
        self.assertNotIn("合計", data.get("labels", []))
        names = [series["name"] for series in data.get("series", [])]
        self.assertNotIn("筆數", names)
        self.assertNotIn("佔比", names)

    def test_a_real_composition_is_still_stacked(self):
        rec = self._recommend(
            ["region", "online %", "store %"],
            [["North", "60", "40"], ["South", "45", "55"], ["East", "70", "30"]],
            total_label="All",
        )
        self.assertEqual(rec["recommended_figure_type"], "stacked_bar")
        self.assertNotIn("All", rec["figure_plan"]["data"]["labels"])


class IAReportWithoutATitleSaysSoTests(unittest.TestCase):
    """The proposal shipped with no title, and nothing said so.

    SKILL.md's start_report example has no `title`, so the proposal was
    started without one. Its blueprint has no cover section to carry one, the
    delivered DOCX opened on the table of contents, and final_qa_summary
    reported pass. The run directory was named after the whole prompt.
    """

    def _start(self, tmpdir, **extra):
        from report_workflow.agent_wrapper import start_report_task

        src = Path(tmpdir) / "notes.md"
        src.write_text("The library is open 09:00 to 20:00, Tuesday to Sunday.", encoding="utf-8")
        with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present), \
             patch("report_workflow.preflight._find_executable", return_value="/usr/bin/tool"):
            return start_report_task(
                "propose longer opening hours", [str(src)], output_dir=str(Path(tmpdir) / "out"),
                report_profile="proposal", preflight_confirmed=True,
                preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {}},
                **extra,
            )

    def test_no_title_is_named_when_the_run_starts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._start(tmpdir)
            self.assertEqual(result["status"], "awaiting_agent_artifacts")
            self.assertTrue(any("title" in warning for warning in result.get("warnings", [])), result.get("warnings"))
            self.assertIn("title", result["message"])

    def test_a_title_given_raises_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._start(tmpdir, title="延長社區圖書館開放時間提案")
            self.assertFalse(any("no title" in warning for warning in result.get("warnings", [])))


class JTheThesisIsAskedForWhereItIsWrittenTests(unittest.TestCase):
    """The paper's outline passed; publish then wanted a thesis_statement.

    The outline brief's only hard rule about framing is "fill paper_spine",
    and the author did — problem, gap, objective, contribution. Nothing reads
    paper_spine. PAPER_SCOPE_FREEZE, at publish, wanted `thesis_statement`
    in the introduction, which no brief mentions, and the outline stage had
    already passed.
    """

    def test_the_spines_contribution_is_the_thesis(self):
        from report_workflow.nodes.paper_scope_freeze import _require_thesis

        outline = {
            "paper_spine": {"contribution": "Students sleeping 7.5-9 h scored 13.28 points higher."},
            "sections": {"introduction": {"claim_ids": ["c1"]}},
        }
        thesis, where = _require_thesis(outline, "academic_paper")
        self.assertIn("13.28", thesis)
        self.assertEqual(where, "paper_spine.contribution")

    def test_a_missing_thesis_stops_the_outline_stage(self):
        from report_workflow.errors import QAHardBlockError
        from report_workflow.nodes.outline_plan import _require_outline_thesis

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["report_profile"] = "academic_paper"
        with self.assertRaises(QAHardBlockError) as caught:
            _require_outline_thesis(state, {"sections": {"introduction": {"claim_ids": ["c1"]}}})
        self.assertIn("thesis_statement", str(caught.exception))
        self.assertIn("paper_spine.contribution", str(caught.exception))

        state.spec["report_profile"] = "proposal"
        _require_outline_thesis(state, {"sections": {}})

    def test_the_outline_brief_names_the_thesis_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir, profile="academic_paper")
            brief = (run_dir_for(state) / "agent_tasks" / "02_outline_plan.md").read_text(encoding="utf-8")
            self.assertIn("thesis_statement", brief)


class KFrontMatterIsAskedForAtTheStartTests(unittest.TestCase):
    """The course paper stopped at publish for a missing correspondence line.

    academic_paper refuses to render without author, affiliation and a
    corresponding-author contact. Those were start_report arguments only:
    nothing an author could write mid-run supplied them, so the cure was a
    new run. The run said nothing about it at start, passed every stage, and
    stopped at METADATA_GATE.
    """

    def _start(self, tmpdir, **extra):
        from report_workflow.agent_wrapper import start_report_task

        src = Path(tmpdir) / "notes.md"
        src.write_text("Forty students reported their sleep before the midterm.", encoding="utf-8")
        with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present), \
             patch("report_workflow.preflight._find_executable", return_value="/usr/bin/tool"):
            return start_report_task(
                "write a paper on sleep and grades", [str(src)], output_dir=str(Path(tmpdir) / "out"),
                report_profile="academic_paper", preflight_confirmed=True,
                preflight_decisions={"confirmed_by_user": True, "install_decisions": {}, "feature_decisions": {}},
                title="Sleep and midterm scores", **extra,
            )

    def test_the_missing_fields_are_named_when_the_run_starts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._start(tmpdir, author_block="Lin Chen", affiliation_block="Dept. of Statistics")
            warnings = " ".join(result.get("warnings", []))
            self.assertIn("correspondence", warnings)
            self.assertNotIn("author_block", warnings)
            self.assertIn("correspondence", result["message"])

    def test_the_publish_stop_says_where_the_field_comes_from(self):
        from report_workflow.errors import QAHardBlockError
        from report_workflow.nodes.front_matter_build import run_front_matter_build

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._start(tmpdir, author_block="Lin Chen", affiliation_block="Dept. of Statistics")
            state = ReportState.resume(result["job_id"], workspace_root=result["workspace_root"])
            with self.assertRaises(QAHardBlockError) as caught:
                run_front_matter_build(state)
            message = str(caught.exception)
            self.assertIn("outline.json", message)
            self.assertIn('"front_matter"', message)

    def test_front_matter_in_the_outline_fills_what_start_report_left_empty(self):
        from report_workflow.nodes.front_matter_build import run_front_matter_build

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._start(tmpdir, author_block="Lin Chen", affiliation_block="Dept. of Statistics")
            state = ReportState.resume(result["job_id"], workspace_root=result["workspace_root"])
            state.plan["outline"] = {"sections": {}, "front_matter": {
                "correspondence": "lin.chen@example.edu", "author_block": "Someone Else",
                "keywords": ["sleep", "exam performance", "undergraduates"],
            }}
            state = run_front_matter_build(state)
            front = state.plan["front_matter"]
            self.assertEqual(front["correspondence"], "lin.chen@example.edu")
            # What start_report was given still wins.
            self.assertEqual(front["author_block"], "Lin Chen")


class LTheAbstractTheBriefShowsIsTheOneThatPassesTests(unittest.TestCase):
    """The abstract written exactly as the brief shows was refused at publish.

    03_section_draft.md shows `**Background:** ...` and says to use those
    headings "exactly". ABSTRACT_CHECK accepted only `## Background:` lines,
    reported "Found: none", and the failure was routed as one no author file
    could fix (`blocked_non_author_repair`, no write paths).
    """

    ABSTRACT = (
        "# Abstract\n\n"
        "**Background:** Students are told sleep matters.\n\n"
        "**Objective:** We asked whether sleep and scores move together.\n\n"
        "**Methods:** Forty students reported sleep.\n\n"
        "**Principal Findings:** Longer sleepers scored 13.28 points higher.\n\n"
        "**Significance:** Sleep belongs in study advice.\n"
    )

    def test_the_bold_labels_the_brief_shows_are_the_structure(self):
        from report_workflow.nodes.abstract_check import _check_structure

        self.assertEqual(_check_structure(self.ABSTRACT), [])

    def test_the_heading_form_still_passes_and_a_missing_part_still_fails(self):
        from report_workflow.nodes.abstract_check import _check_structure

        headings = self.ABSTRACT.replace("**Background:**", "## Background:\n")
        self.assertEqual(_check_structure(headings), [])
        missing = self.ABSTRACT.replace("**Significance:** Sleep belongs in study advice.\n", "")
        self.assertTrue(_check_structure(missing))

    def test_an_abstract_failure_is_routed_to_the_drafts(self):
        from report_workflow.automation_harness import _stage_from_artifact_text

        order = ["claim_matrix", "outline", "drafts", "artifact_lint", "publish"]
        self.assertEqual(_stage_from_artifact_text(
            "METADATA_GATE/ABSTRACT_CHECK: ABSTRACT_CHECK failed: 1 issue(s)", order), "drafts")
        self.assertEqual(_stage_from_artifact_text(
            "PLAN_LOCK/PAPER_SCOPE_FREEZE: Academic report requires a thesis statement", order), "outline")


class MFigureReferencesUseTheNumberTheReaderSeesTests(unittest.TestCase):
    """The paper's only chart had id 2, was printed as Figure 1, and the gate wanted "Figure 2".

    The starter plan took id 1, so the author's scatter plot was id 2. The
    renderer numbers figures by where they are placed — it printed
    "Figure 1." under the chart — but FIGURE_QUALITY required the prose to
    say "Figure 2", a cross-reference to a figure the document does not
    have. It also required a caption line in the draft, although the
    renderer writes the caption from the plan's title. And the stop read
    "FIGURE_QUALITY: 1 hard issue(s): [None]".
    """

    TEXT = "# Results\n\n[FIGURE:2]\n\nScores rise with sleep, as Figure 1 shows.\n"

    def test_the_printed_number_is_the_reference(self):
        from report_workflow.nodes.figure_quality import _check_figure_contract

        issues = _check_figure_contract(self.TEXT, ["2"], hard_contract=True, titled_ids={"2"})
        hard = [j for i in issues for j in i.get("issues", [i]) if j.get("severity") == "hard"]
        self.assertEqual(hard, [])

    def test_a_missing_reference_names_the_number_to_write(self):
        from report_workflow.nodes.figure_quality import _check_figure_contract

        text = "# Results\n\n[FIGURE:2]\n\nScores rise with sleep.\n"
        issues = _check_figure_contract(text, ["2"], hard_contract=True, titled_ids={"2"})
        details = " ".join(j["detail"] for i in issues for j in i.get("issues", []))
        self.assertIn("Figure 1", details)
        self.assertNotIn("missing_caption", json.dumps(issues))

    def test_an_untitled_figure_still_needs_a_caption(self):
        from report_workflow.nodes.figure_quality import _check_figure_contract

        issues = _check_figure_contract(self.TEXT, ["2"], hard_contract=True, titled_ids=set())
        self.assertIn("missing_caption", json.dumps(issues))

    def test_the_stop_message_says_what_is_wrong(self):
        from report_workflow.nodes.figure_quality import _hard_issue_details

        details = _hard_issue_details([{"figure_id": "2", "issues": [
            {"type": "missing_prose_reference", "severity": "hard", "detail": "Figure '2' is not mentioned"},
        ]}])
        self.assertNotIn("None", details)
        self.assertIn("Figure '2' is not mentioned", details)


class NASentenceMayOpenWithASpelledNumberTests(unittest.TestCase):
    """APA spells out a number that opens a sentence; FS read it as missing.

    The paper's claim says "40 first- and second-year undergraduates", the
    evidence says 40, and the methods sentence opens "Forty first- and
    second-year undergraduates…" because a sentence does not start with a
    numeral. FS blocked the claim: "asserts 40first, which the drafted
    sentences do not state".
    """

    def test_a_sentence_initial_number_word_states_the_number(self):
        from report_workflow.nodes.factuality_check import _spell_out_sentence_numbers

        self.assertEqual(
            _spell_out_sentence_numbers("Forty first-year students replied. Twenty-five did not."),
            "40 first-year students replied. 25 did not.",
        )

    def test_number_words_inside_a_sentence_are_left_alone(self):
        from report_workflow.nodes.factuality_check import _spell_out_sentence_numbers

        text = "Only one of them replied, and one reason was time."
        self.assertEqual(_spell_out_sentence_numbers(text), text)
        self.assertEqual(_spell_out_sentence_numbers("Once upon a time."), "Once upon a time.")

    def test_fs_accepts_the_spelled_number_and_still_blocks_a_wrong_one(self):
        from report_workflow.nodes.factuality_check import run_factuality_check_fs

        claim = {"claims": [{"claim_id": "c3", "claim_text": "40 first- and second-year undergraduates replied.",
                             "evidence_ids": ["E1"]}]}
        right = "Forty first- and second-year undergraduates replied [CITE:E1]."
        wrong = "Fifty first- and second-year undergraduates replied [CITE:E1]."
        ok = run_factuality_check_fs(right, claim, sentence_map=[{"sentence_id": "s1", "claim_ids": ["c3"]}])
        bad = run_factuality_check_fs(wrong, claim, sentence_map=[{"sentence_id": "s1", "claim_ids": ["c3"]}])
        self.assertEqual(ok[0]["status"], "verified", ok)
        self.assertEqual(bad[0]["status"], "blocked", bad)


class OKeywordsAreNeverAnotherProjectsTests(unittest.TestCase):
    """The sleep paper was delivered with the keywords of a compiler project.

    No keywords were passed, and every academic_paper new draft without them
    received a fixed list — "deterministic compilation, StrategyIR,
    domain-specific intermediate representation, abstract syntax tree
    compilation…" — printed on the title page of a statistics course paper.
    """

    def _front(self, outline=None):
        from report_workflow.nodes.front_matter_build import _build_front_matter

        state = ReportState.new("write a paper on sleep and midterm scores", [], tempfile.mkdtemp())
        state.spec["report_profile"] = "academic_paper"
        state.spec["task_intent"] = "new_draft"
        state.plan["outline"] = outline or {"sections": {}}
        state.plan["blueprint"] = {}
        return _build_front_matter(state)

    def test_no_keywords_given_means_none_invented(self):
        keywords = self._front()["keywords"]
        self.assertNotIn("StrategyIR", keywords)
        self.assertEqual(keywords, [])

    def test_keywords_in_the_outline_are_used(self):
        front = self._front({"sections": {}, "front_matter": {"keywords": ["sleep", "exam performance", "undergraduates"]}})
        self.assertEqual(front["keywords"], ["sleep", "exam performance", "undergraduates"])


class PAnUnregisteredFigureIsNotAnotherRunsTests(unittest.TestCase):
    """A claim citing a derivation that never registered was told to remap.

    gap_high_low failed to register (the band label), and the claim citing
    E_D_gap_high_low was refused with "These artifacts likely came from
    another run. Use remap-evidence" — a run that does not exist, and a tool
    that cannot help.
    """

    def test_a_missing_derived_id_is_called_unregistered(self):
        from report_workflow.agent_wrapper import submit_claim_matrix

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_survey(tmpdir, profile="proposal")
            (run_dir_for(state) / "claim_matrix.json").write_text(json.dumps({"claims": [{
                "claim_id": "c1", "claim_text": "Evening visits are 1.57 times morning visits.",
                "claim_type": "statistical", "evidence_ids": ["E_D_evening_ratio"],
            }]}), encoding="utf-8")
            result = submit_claim_matrix(state.job_id, workspace_root=state.output["workspace_root"])
            self.assertEqual(result["status"], "validation_failed")
            self.assertIn("E_D_evening_ratio", result["error_details"])
            self.assertIn("register_derived_evidence", result["error_details"])
            self.assertNotIn("another run", result["error_details"])


if __name__ == "__main__":
    unittest.main()
