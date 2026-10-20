"""Round 3 of the usability work (2026-10-20).

The independent review of PR #1 left a list of what was still in the way of an
author. Each test here was written to fail before its fix. The fixes do not
loosen any factuality check; where a test touches a check it also asserts the
check still blocks the false version of the claim.
"""
from __future__ import annotations

import ast
import importlib.util
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


class GRecordedRunsReproduceFromTheRepoTests(unittest.TestCase):
    """The recorded author scripts loaded files from another session's /tmp.

    `run1_after.py` and three others imported `/tmp/claude-0/rw/tasks/run1.py`
    and the base scripts read sources from `/home/user/...`. Nobody who clones
    the repo could rerun them.
    """

    def test_no_authored_script_names_a_machine_path(self):
        offenders = []
        for py in EVIDENCE.glob("usability_*/**/*.py"):
            text = py.read_text(encoding="utf-8")
            if re.search(r"['\"](/tmp/|/home/|[A-Z]:\\\\)", text):
                offenders.append(str(py.relative_to(REPO)))
        self.assertEqual(offenders, [])

    def test_a_variant_script_loads_its_base_from_beside_it(self):
        path = EVIDENCE / "usability_audit_2026-10-19" / "run1_zh_lab" / "authored" / "run1_after.py"
        spec = importlib.util.spec_from_file_location("run1_after", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for f in mod.START["source_files"]:
            self.assertTrue(Path(f["path"]).is_file(), f["path"])
        self.assertNotIn("results", mod.OUTLINE)


class HTheRepairLogShowsEachStepTests(unittest.TestCase):
    """repair.py logged `{"step": ..., "**": {...}}`, so no status was readable."""

    def _repair(self):
        path = EVIDENCE / "usability_audit_2026-10-19" / "harness" / "repair.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "**":
                self.fail("repair.py writes a literal '**' key")
        spec = importlib.util.spec_from_file_location("repair", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_each_record_carries_status_and_stage_at_top_level(self):
        mod = self._repair()
        rec = mod.entry("submit_action", {"status": "validation_failed", "stage": "drafts", "job_id": "x"})
        self.assertEqual(rec, {"step": "submit_action", "status": "validation_failed", "stage": "drafts"})


if __name__ == "__main__":
    unittest.main()
