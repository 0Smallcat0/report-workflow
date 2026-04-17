"""ARTIFACTS node - package all workflow outputs into a structured deliverable.

Phase 3: After WAIVER_GOVERNANCE + REVISION_APPLY, collect and package
all artifacts from Phases 1-3 into the output directory:
  ~/.hermes/published/{job_id}/

Deliverable layout:
  {job_id}/
    report.docx              # Final rendered document
    report.md                 # Source markdown
    metadata.json             # Workflow metadata, timing, gate decisions
    qa/
      consistency_report.json
      style_report.json
      guideline_report.json
      waiver_log.json
      edit_manifest.json
    evidence/
      claim_matrix.json
      evidence_ledger.jsonl
      figure_manifest.json
      tables.json
    sources/
      {uploaded files...}
    artifacts.json            # This manifest lists all packaged files
"""
import json
import shutil
from pathlib import Path
from datetime import datetime

from ..state import ReportState, WORKFLOW_RUNS_DIR, PUBLISHED_DIR


def _copy_file(src: str | None, dest_dir: Path, dest_name: str | None = None) -> str | None:
    """Copy file if it exists. Returns packaged path or None."""
    if not src:
        return None
    p = Path(src)
    if not p.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = dest_name or p.name
    dest = dest_dir / name
    shutil.copy2(p, dest)
    return str(dest)


def _load_json(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _collect_paths(subdir: Path, glob_pat: str) -> list[str]:
    try:
        return [str(p) for p in subdir.glob(glob_pat)]
    except Exception:
        return []


def run_artifacts(state: ReportState) -> ReportState:
    """T25: ARTIFACTS - package all outputs into published directory."""
    run_id = state.job_id
    published_dir = PUBLISHED_DIR / run_id
    published_dir.mkdir(parents=True, exist_ok=True)

    qa_dir = published_dir / "qa"
    evidence_dir = published_dir / "evidence"
    sources_dir = published_dir / "sources"

    artifacts_meta: dict = {
        "job_id": run_id,
        "created_at": datetime.now().isoformat(),
        "status": state.status,
        "report_family": state.spec.get("report_family", ""),
        "files": [],
    }

    # --- Core report files ---
    # Final DOCX
    final_docx = state.output.get("final_docx_path")
    docx_copied = _copy_file(final_docx, published_dir, "report.docx")
    if docx_copied:
        artifacts_meta["files"].append({"role": "report_docx", "path": docx_copied})

    # Source markdown
    merged_md = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path")
    md_copied = _copy_file(merged_md, published_dir, "report.md")
    if md_copied:
        artifacts_meta["files"].append({"role": "report_markdown", "path": md_copied})

    # --- QA artifacts ---
    qa_files = {
        "consistency_report.json": state.qa.get("consistency_report_path"),
        "style_report.json": state.qa.get("style_report_path"),
        "guideline_report.json": state.qa.get("guideline_report_path"),
    }
    for fname, fpath in qa_files.items():
        copied = _copy_file(fpath, qa_dir, fname)
        if copied:
            artifacts_meta["files"].append({"role": f"qa_{fname.replace('.json','')}", "path": copied})

    # Waiver / governance artifacts
    gov_files = {
        "waiver_log.json": state.governance.get("waiver_log_path"),
        "edit_manifest.json": state.governance.get("edit_manifest_path"),
    }
    for fname, fpath in gov_files.items():
        copied = _copy_file(fpath, qa_dir, fname)
        if copied:
            artifacts_meta["files"].append({"role": f"governance_{fname.replace('.json','')}", "path": copied})

    # --- Evidence artifacts ---
    evidence_files = {
        "claim_matrix.json": _collect_paths(Path.home() / ".hermes" / "workflow_runs" / run_id, "claim_matrix.json"),
        "evidence_ledger.jsonl": _collect_paths(Path.home() / ".hermes" / "workflow_runs" / run_id, "evidence_ledger.jsonl"),
        "figure_manifest.json": [state.drafts.get("figure_manifest_path")] if state.drafts.get("figure_manifest_path") else [],
        "tables.json": [state.drafts.get("tables_path")] if state.drafts.get("tables_path") else [],
    }
    for fname, fpaths in evidence_files.items():
        for fpath in fpaths:
            copied = _copy_file(fpath, evidence_dir, fname)
            if copied:
                artifacts_meta["files"].append({"role": f"evidence_{fname.replace('.jsonl','').replace('.json','')}", "path": copied})

    # --- Source uploads ---
    uploaded = state.spec.get("uploaded_files", [])
    for src_path in uploaded:
        copied = _copy_file(src_path, sources_dir)
        if copied:
            artifacts_meta["files"].append({"role": "source", "path": copied})

    # --- Metadata JSON ---
    metadata = {
        "job_id": run_id,
        "created_at": datetime.now().isoformat(),
        "status": state.status,
        "report_family": state.spec.get("report_family", ""),
        "report_family_detail": state.spec.get("report_family_detail", ""),
        "delivery_mode": state.spec.get("delivery_mode", "fresh_doc"),
        "audience": state.spec.get("audience", "expert"),
        "citation_style": state.spec.get("citation_style", "apa"),
        "keywords": state.spec.get("keywords", []),
        "selected_guidelines": state.spec.get("selected_guidelines", []),
        # QA gate decisions
        "qa_gate_status": state.qa.get("qa_gate_status", ""),
        "consistency_status": state.qa.get("consistency_status", ""),
        "style_status": state.qa.get("style_status", ""),
        "guideline_status": state.governance.get("guideline_status", ""),
        # Governance summary
        "gate_override": state.governance.get("gate_override", False),
        "patchable_count": state.governance.get("patchable_count", 0),
        "waived_count": state.governance.get("waived_count", 0),
        "revision_applied": state.drafts.get("revision_applied", False),
        "revision_status": state.governance.get("revision_status", ""),
        "unpatchable_count": len(state.governance.get("unpatchable", [])),
        # Artifact inventory
        "file_count": len(artifacts_meta["files"]),
    }
    metadata_path = published_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    artifacts_meta["files"].append({"role": "metadata", "path": str(metadata_path)})

    # --- Main artifacts.json manifest ---
    artifacts_path = published_dir / "artifacts.json"
    with open(artifacts_path, "w") as f:
        json.dump(artifacts_meta, f, indent=2, default=str)

    # Update state
    state.output["published_dir"] = str(published_dir)
    state.output["artifacts_manifest_path"] = str(artifacts_path)
    state.output["metadata_path"] = str(metadata_path)
    state.output["artifact_count"] = len(artifacts_meta["files"])

    return state
