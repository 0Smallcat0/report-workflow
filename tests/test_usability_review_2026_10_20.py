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


if __name__ == "__main__":
    unittest.main()
