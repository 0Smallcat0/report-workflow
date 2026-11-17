"""soffice.cmd fails on a Chinese path; the check must not depend on it (2026-11-18)."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from report_workflow.nodes import visual_render_check as node


class ResolveSofficeTests(unittest.TestCase):
    def test_a_cmd_shim_resolves_to_the_exe_it_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "LibreOffice" / "program" / "soffice.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            shim = Path(tmp) / "soffice.cmd"
            shim.write_text(
                '@echo off\r\nif /I "%~1"=="--version" (\r\n  "C:\nope\soffice.com" %*\r\n) else (\r\n'
                f'  "{exe}" %*\r\n)\r\n', encoding="utf-8")
            self.assertEqual(Path(node._resolve_soffice_executable(str(shim))), exe)

    def test_a_real_exe_and_unknown_values_are_returned_unchanged(self):
        self.assertEqual(node._resolve_soffice_executable(r"C:\x\soffice.exe"), r"C:\x\soffice.exe")
        self.assertEqual(node._resolve_soffice_executable("definitely-not-a-real-binary"), "definitely-not-a-real-binary")


class ConvertTests(unittest.TestCase):
    def _run(self, run_dir, side_effect):
        docx = run_dir / "解決電力短缺" / "rendered_report.docx"
        docx.parent.mkdir(parents=True)
        docx.write_bytes(b"x")
        state = SimpleNamespace(job_id=run_dir.name, output={"final_docx_path": str(docx)}, runtime={}, flags={})
        with patch.object(node, "WORKFLOW_RUNS_DIR", run_dir.parent), \
                patch.object(node, "_find_executable", lambda *a: r"C:\fake\soffice.cmd"), \
                patch.object(node, "_resolve_soffice_executable", lambda p: r"C:\fake\soffice.exe"), \
                patch.object(node, "write_json_artifact", lambda _s, _n, report: report), \
                patch.object(node.subprocess, "run", side_effect=side_effect):
            node.run_visual_render_check(state)
        return state.runtime["visual_render_check_report_path"]

    def test_non_ascii_paths_are_converted_through_an_ascii_copy(self):
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            if "--convert-to" in cmd:
                self.assertEqual(cmd[0], r"C:\fake\soffice.exe")
                src = Path(cmd[-1])
                out = Path(cmd[cmd.index("--outdir") + 1])
                self.assertTrue(str(src).isascii(), src)
                self.assertTrue(str(out).isascii(), out)
                self.assertTrue(src.exists())
                (out / (src.stem + ".pdf")).write_bytes(b"%PDF-1.4")
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise subprocess.CalledProcessError(1, cmd, stderr="stop here")

        with tempfile.TemporaryDirectory() as workspace:
            run_dir = Path(workspace) / "job"
            run_dir.mkdir()
            report = self._run(run_dir, fake)
            self.assertTrue(calls and "--convert-to" in calls[0])
            # the PDF the ASCII conversion made is brought back next to the document's own name
            self.assertTrue((run_dir / "visual_check" / "rendered_report.pdf").exists())
        self.assertEqual(report["conversion_status"], "succeeded")

    def test_failure_detail_is_not_cut_short(self):
        long_error = "E" * 900

        def fake(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, stderr=long_error)

        with tempfile.TemporaryDirectory() as workspace:
            run_dir = Path(workspace) / "job"
            run_dir.mkdir()
            report = self._run(run_dir, fake)
        self.assertIn(long_error, report["skipped_reason"])
        self.assertIn("exit 1", report["skipped_reason"])


if __name__ == "__main__":
    unittest.main()
