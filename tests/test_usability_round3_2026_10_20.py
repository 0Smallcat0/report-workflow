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
