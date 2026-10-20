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


if __name__ == "__main__":
    unittest.main()
