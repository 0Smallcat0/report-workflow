"""VISUAL_RENDER_CHECK - optional DOCX -> PDF/PNG render verification."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR


def _find_executable(name: str, candidates: list[str]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def run_visual_render_check(state: ReportState) -> ReportState:
    """Render DOCX to PDF/PNG when local tools are available."""
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
    report = {
        "job_id": state.job_id,
        "status": "skipped",
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
        subprocess.run(
            [pdftoppm, "-png", "-f", "1", "-l", "3", str(pdf_path), str(visual_dir / "page")],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        png_paths = sorted(str(path) for path in visual_dir.glob("page-*.png"))
        if not png_paths:
            raise QAHardBlockError("VISUAL_RENDER_CHECK: no PNG pages were rendered")
        report.update({
            "status": "passed",
            "pdf_path": str(pdf_path),
            "png_paths": png_paths,
        })
    except subprocess.CalledProcessError as exc:
        report["status"] = "failed"
        report["issues"].append(exc.stderr[:500] if exc.stderr else str(exc))
        if state.flags.get("strict_visual_render_check"):
            raise QAHardBlockError("VISUAL_RENDER_CHECK failed: " + report["issues"][0]) from exc

    state.runtime["visual_render_check_report_path"] = write_json_artifact(
        state, "visual_render_check_report.json", report
    )
    return state
