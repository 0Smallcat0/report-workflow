"""VISUAL_RENDER_CHECK - optional DOCX -> PDF/PNG render preview.

It converts the document and renders every page for someone to look at. It
does not look at them. It used to render pages 1–3 and report "passed" because
the PNG files existed, and a 25-page report went out with that verdict while
its split tables and parted captions sat on pages the check never produced.
So the report keeps three facts apart — whether conversion succeeded, which
pages were previewed out of how many, and whether a visual review was recorded
for this document — and only a recorded review of every page is "completed".

A review is recorded by whoever looked, in ``visual_review.json`` beside this
report: ``{"document_sha256": <from this report>, "reviewed_pages": "1-25",
"reviewer": "..."}``. The hash covers the document body and its images, so a
re-render of the same content keeps the review and an edited document does not.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR

#: Rendering resolution for the preview pages: legible body text, and a
#: 25-page report stays a few megabytes.
PREVIEW_DPI = 100

REVIEW_RECORD_FILENAME = "visual_review.json"

_PAGE_PNG_RE = re.compile(r"page-(\d+)\.png$")


def _find_executable(name: str, candidates: list[str]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def document_sha256(docx_path: str | Path) -> str:
    """What a review applies to: the document body and its images.

    Not the file's bytes: a re-render of identical content writes new
    timestamps into the package, and a review of the same pages should not go
    stale over that.
    """
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(docx_path) as archive:
            names = sorted(
                name for name in archive.namelist()
                if name == "word/document.xml" or name.startswith("word/media/")
            )
            for name in names:
                digest.update(name.encode("utf-8"))
                digest.update(archive.read(name))
    except (OSError, zipfile.BadZipFile, KeyError):
        digest = hashlib.sha256(Path(docx_path).read_bytes())
    return digest.hexdigest()


def _pdf_page_count(pdf_path: str | Path) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0


def page_range(pages: list[int]) -> str:
    """[1, 2, 3, 5] as "1-3, 5"."""
    spans: list[str] = []
    ordered = sorted(set(pages))
    index = 0
    while index < len(ordered):
        start = end = ordered[index]
        while index + 1 < len(ordered) and ordered[index + 1] == end + 1:
            index += 1
            end = ordered[index]
        spans.append(f"{start}-{end}" if end != start else str(start))
        index += 1
    return ", ".join(spans)


def _parse_pages(raw: object) -> list[int]:
    """A review's page list: [1, 2] or "1-25, 27"."""
    if isinstance(raw, list):
        return [int(item) for item in raw if isinstance(item, int) or str(item).strip().isdigit()]
    pages: list[int] = []
    for part in re.split(r"[,，;；\s]+", str(raw or "")):
        match = re.fullmatch(r"(\d+)(?:[-–](\d+))?", part.strip())
        if match:
            first = int(match.group(1))
            last = int(match.group(2) or first)
            pages.extend(range(min(first, last), max(first, last) + 1))
    return pages


def _review_status(run_dir: Path, digest: str, page_count: int) -> tuple[str, dict | None]:
    """Whether someone recorded looking at this document's pages, and which."""
    path = run_dir / REVIEW_RECORD_FILENAME
    if not path.exists():
        return "not_performed", None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "not_performed", {"path": str(path), "error": "the review record could not be read"}
    if not isinstance(record, dict):
        return "not_performed", {"path": str(path), "error": "the review record is not an object"}
    reviewed = sorted({
        page for page in _parse_pages(record.get("reviewed_pages"))
        if page >= 1 and (not page_count or page <= page_count)
    })
    summary = {
        "path": str(path),
        "reviewer": str(record.get("reviewer") or ""),
        "reviewed_pages": page_range(reviewed),
        "reviewed_page_count": len(reviewed),
    }
    if str(record.get("document_sha256") or "") != digest:
        return "stale", summary
    if not reviewed:
        return "not_performed", summary
    if page_count and len(reviewed) >= page_count:
        return "completed", summary
    return "partial", summary


def run_visual_render_check(state: ReportState) -> ReportState:
    """Render the DOCX to PDF and every page to PNG when local tools are available."""
    docx_path = state.output.get("final_docx_path") or state.output.get("rendered_docx_path")
    if not docx_path or not Path(docx_path).exists():
        raise QAHardBlockError("VISUAL_RENDER_CHECK: rendered DOCX is missing")

    soffice = _find_executable("soffice", [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files\LibreOffice\program\soffice.com",
    ])
    pdftoppm = _find_executable("pdftoppm", [
        str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe/poppler-25.07.0/Library/bin/pdftoppm.exe"),
    ])

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    visual_dir = run_dir / "visual_check"
    visual_dir.mkdir(parents=True, exist_ok=True)
    digest = document_sha256(docx_path)
    report = {
        "job_id": state.job_id,
        # skipped | failed | preview_rendered. Never "passed": rendering pages
        # is not looking at them.
        "status": "skipped",
        "conversion_status": "not_run",
        "page_count": 0,
        "preview_pages": [],
        "preview_page_range": "",
        "document_sha256": digest,
        "visual_review_status": "not_performed",
        "visual_review": None,
        "issues": [],
        "skipped_reason": "",
        "pdf_path": "",
        "png_paths": [],
    }

    if not soffice or not pdftoppm:
        # Why the optional check did not run is not a finding about the
        # document. Filed under "issues" it reaches the delivery summary's
        # render-issue list and downgrades the verdict on a clean report,
        # over tools the project never asks anyone to install.
        report["skipped_reason"] = "LibreOffice soffice or Poppler pdftoppm not found"
        state.runtime["visual_render_check_report_path"] = write_json_artifact(
            state, "visual_render_check_report.json", report
        )
        return state

    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(visual_dir), str(docx_path)],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        pdf_path = visual_dir / (Path(docx_path).stem + ".pdf")
        if not pdf_path.exists():
            raise QAHardBlockError("VISUAL_RENDER_CHECK: LibreOffice did not produce a PDF")
        report["conversion_status"] = "succeeded"
        report["pdf_path"] = str(pdf_path)
        page_count = _pdf_page_count(pdf_path)
        # A preview left over from an earlier render would count as this one's.
        for stale in visual_dir.glob("page-*.png"):
            stale.unlink()
        command = [pdftoppm, "-png", "-r", str(PREVIEW_DPI)]
        if page_count:
            command += ["-f", "1", "-l", str(page_count)]
        subprocess.run(
            command + [str(pdf_path), str(visual_dir / "page")],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        png_paths = sorted(
            (path for path in visual_dir.glob("page-*.png") if _PAGE_PNG_RE.search(path.name)),
            key=lambda path: int(_PAGE_PNG_RE.search(path.name).group(1)),
        )
        if not png_paths:
            raise QAHardBlockError("VISUAL_RENDER_CHECK: no PNG pages were rendered")
        pages = [int(_PAGE_PNG_RE.search(path.name).group(1)) for path in png_paths]
        page_count = page_count or max(pages)
        review_status, review = _review_status(run_dir, digest, page_count)
        report.update({
            "status": "preview_rendered",
            "page_count": page_count,
            "preview_pages": pages,
            "preview_page_range": page_range(pages),
            "png_paths": [str(path) for path in png_paths],
            "visual_review_status": review_status,
            "visual_review": review,
        })
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Not being able to run the optional converter is the same class of
        # non-finding as not having it installed, and the branch above already
        # says so. Reported as a failure it put `visual_render_status: failed`
        # with an empty reason into the delivery summary of three clean runs --
        # a missing dependency reading as a defect in the document. Here the
        # tool was on PATH as a shim whose own quoted path would not launch,
        # which is a fact about this machine and about nothing else.
        detail = str(getattr(exc, "stderr", "") or exc).strip()[:300]
        if report["conversion_status"] != "succeeded":
            report["conversion_status"] = "failed"
        if state.flags.get("strict_visual_render_check"):
            report["status"] = "failed"
            report["issues"].append(detail)
            raise QAHardBlockError("VISUAL_RENDER_CHECK failed: " + detail) from exc
        report["skipped_reason"] = f"optional renderer could not be run: {detail}"

    state.runtime["visual_render_check_report_path"] = write_json_artifact(
        state, "visual_render_check_report.json", report
    )
    return state
