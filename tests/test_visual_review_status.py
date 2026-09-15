"""A preview of three pages is not a visual check of the document.

Found in the delivery summary of a 25-page Chinese course report, which said
"Visual render check: passed". The check had converted the DOCX to PDF,
rendered pages 1–3 to PNG, and called itself passed because the PNG files
existed: nobody had looked at them, and pages 4–25 were never rendered at all.
The layout defects the reviewer then found — a split short table, a caption
parted from its figure — were on pages the check never produced.

The report now keeps three facts apart: whether conversion succeeded, which
pages were previewed out of how many, and whether a visual review was recorded
for this document. Only a recorded review of every page is "completed".
"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from report_workflow.artifact_packaging.final_qa import visual_render_line
from report_workflow.nodes import visual_render_check as node

PAGES = 25


def _docx(path: Path, body: str = "第一頁") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document><w:body><w:p><w:t>{body}</w:t></w:p></w:body></w:document>")
    return path


def _fake_run(args, **_kwargs):
    """soffice writes the PDF; pdftoppm writes one PNG per requested page."""
    if "--convert-to" in args:
        outdir = Path(args[args.index("--outdir") + 1])
        (outdir / (Path(args[-1]).stem + ".pdf")).write_bytes(b"%PDF")
    else:
        first = int(args[args.index("-f") + 1]) if "-f" in args else 1
        last = int(args[args.index("-l") + 1]) if "-l" in args else PAGES
        prefix = Path(args[-1])
        for page in range(first, last + 1):
            Path(f"{prefix}-{page:02d}.png").write_bytes(b"png")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _check(run_dir: Path, review: dict | None = None, body: str = "第一頁") -> dict:
    docx = _docx(run_dir / "rendered_report.docx", body)
    if review is not None:
        (run_dir / "visual_review.json").write_text(json.dumps(review), encoding="utf-8")
    state = SimpleNamespace(job_id=run_dir.name, output={"final_docx_path": str(docx)}, runtime={}, flags={})
    with mock.patch.object(node, "WORKFLOW_RUNS_DIR", run_dir.parent), \
            mock.patch.object(node, "_find_executable", lambda name, _candidates: name), \
            mock.patch.object(node, "_pdf_page_count", lambda _path: PAGES), \
            mock.patch.object(node.subprocess, "run", _fake_run), \
            mock.patch.object(node, "write_json_artifact", lambda _state, _name, report: report):
        node.run_visual_render_check(state)
    return state.runtime["visual_render_check_report_path"]


class VisualRenderStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "job"
        self.run_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_page_is_previewed_and_nothing_claims_a_review(self):
        report = _check(self.run_dir)
        self.assertEqual(report["conversion_status"], "succeeded")
        self.assertEqual(report["page_count"], PAGES)
        self.assertEqual(report["preview_page_range"], f"1-{PAGES}")
        self.assertEqual(len(report["png_paths"]), PAGES)
        self.assertEqual(report["visual_review_status"], "not_performed")
        self.assertNotEqual(report["status"], "passed")

    def test_a_review_of_every_page_of_this_document_is_completed(self):
        digest = _check(self.run_dir)["document_sha256"]
        report = _check(self.run_dir, {"document_sha256": digest, "reviewed_pages": f"1-{PAGES}", "reviewer": "agent"})
        self.assertEqual(report["visual_review_status"], "completed")

    def test_a_review_of_some_pages_is_partial(self):
        digest = _check(self.run_dir)["document_sha256"]
        report = _check(self.run_dir, {"document_sha256": digest, "reviewed_pages": "1-3"})
        self.assertEqual(report["visual_review_status"], "partial")
        self.assertEqual(report["visual_review"]["reviewed_page_count"], 3)

    def test_a_review_of_another_document_is_stale(self):
        digest = _check(self.run_dir)["document_sha256"]
        report = _check(self.run_dir, {"document_sha256": digest, "reviewed_pages": f"1-{PAGES}"}, body="改過的內容")
        self.assertEqual(report["visual_review_status"], "stale")


class DeliverySummaryLineTests(unittest.TestCase):
    def test_the_summary_names_conversion_range_and_review_separately(self):
        line = visual_render_line({
            "visual_render_status": "preview_rendered",
            "visual_conversion_status": "succeeded",
            "visual_preview_page_range": "1-3",
            "visual_page_count": 25,
            "visual_review_status": "not_performed",
        })
        self.assertEqual(
            line,
            "- Visual render check: PDF conversion succeeded; previewed pages 1-3 of 25; "
            "visual review not performed",
        )

    def test_an_old_report_that_said_passed_is_not_repeated_as_passed(self):
        line = visual_render_line({"visual_render_status": "passed"})
        self.assertNotIn("passed", line)
        self.assertIn("visual review not performed", line)

    def test_skipped_and_failed_read_as_before(self):
        self.assertEqual(
            visual_render_line({"visual_render_status": "skipped", "visual_render_skipped_reason": "LibreOffice missing"}),
            "- Visual render check: skipped (LibreOffice missing)",
        )
        self.assertEqual(visual_render_line({"visual_render_status": "failed"}), "- Visual render check: failed")


if __name__ == "__main__":
    unittest.main()
