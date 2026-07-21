"""SUPPLEMENTARY_PACKAGE_BUILD node - build supplementary materials package.

Sits between FINAL_PUBLISH and ARTIFACTS in render phase.

Collects and packages supplementary materials:
  - Claim-evidence matrix
  - Source trace tables
  - Extended audit notes
  - Methods appendix
  - Supplementary references
  - Internal trace map

Output:
  - supplementary_package/ directory
  - supplementary_info.docx (optional single-file option)
"""
import json
import shutil
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR


def _load_jsonl(path: str | None) -> list[dict]:
    """Load JSONL file."""
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_supplementary_package_build(state: ReportState) -> ReportState:
    """T_NEW: SUPPLEMENTARY_PACKAGE_BUILD - build supplementary materials package.

    Position: After FINAL_PUBLISH, before ARTIFACTS.
    """
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    supp_dir = run_dir / "supplementary_package"
    supp_dir.mkdir(parents=True, exist_ok=True)

    files_added = []

    # 1. Claim-Evidence Matrix
    claim_matrix = state.plan.get("claim_matrix", {})
    if claim_matrix:
        cm_path = supp_dir / "claim_evidence_matrix.json"
        with open(cm_path, "w", encoding="utf-8") as f:
            json.dump(claim_matrix, f, indent=2)
        files_added.append({"role": "supplementary_claim_matrix", "path": str(cm_path)})

    # 2. Sentence Map
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path"))
    if sentence_map:
        sm_path = supp_dir / "sentence_map.jsonl"
        with open(sm_path, "w", encoding="utf-8") as f:
            for entry in sentence_map:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        files_added.append({"role": "supplementary_sentence_map", "path": str(sm_path)})

    # 3. Internal Trace Map
    internal_trace_path = state.citations.get("internal_trace_path", "")
    if internal_trace_path and Path(internal_trace_path).exists():
        dest = supp_dir / "internal_trace_map.json"
        shutil.copy(internal_trace_path, dest)
        files_added.append({"role": "supplementary_internal_trace", "path": str(dest)})

    # 4. Supplementary Methods
    supp_methods = state.drafts.get("supplementary_methods", "")
    if supp_methods and Path(supp_methods).exists():
        dest = supp_dir / "supplementary_methods.md"
        shutil.copy(supp_methods, dest)
        files_added.append({"role": "supplementary_methods", "path": str(dest)})

    # 5. Evidence Ledger
    evidence_path = state.sources.get("evidence_ledger_path", "")
    if evidence_path and Path(evidence_path).exists():
        dest = supp_dir / "evidence_ledger.jsonl"
        shutil.copy(evidence_path, dest)
        files_added.append({"role": "supplementary_evidence_ledger", "path": str(dest)})

    # 6. Figure Manifest
    figure_manifest = state.output.get("figure_manifest_path", "")
    if figure_manifest and Path(figure_manifest).exists():
        dest = supp_dir / "figure_manifest.json"
        shutil.copy(figure_manifest, dest)
        files_added.append({"role": "supplementary_figure_manifest", "path": str(dest)})

    # 7. Figure Recommendation and Audit Reports
    figure_recommendations = state.output.get("figure_recommendations_path", "")
    if figure_recommendations and Path(figure_recommendations).exists():
        dest = supp_dir / "figure_recommendations.json"
        shutil.copy(figure_recommendations, dest)
        files_added.append({"role": "supplementary_figure_recommendations", "path": str(dest)})

    figure_plan_audit = state.qa.get("figure_plan_audit_report_path", "")
    if figure_plan_audit and Path(figure_plan_audit).exists():
        dest = supp_dir / "figure_plan_audit_report.json"
        shutil.copy(figure_plan_audit, dest)
        files_added.append({"role": "supplementary_figure_plan_audit", "path": str(dest)})

    # 8. Style Issues Report
    style_issues = state.drafts.get("style_issues_report_path", "")
    if style_issues and Path(style_issues).exists():
        dest = supp_dir / "style_issues_report.json"
        shutil.copy(style_issues, dest)
        files_added.append({"role": "supplementary_style_issues", "path": str(dest)})

    # 9. Guideline Coverage (if academic)
    guideline_coverage = state.governance.get("guideline_coverage_path", "")
    if guideline_coverage and Path(guideline_coverage).exists():
        dest = supp_dir / "guideline_coverage_matrix.json"
        shutil.copy(guideline_coverage, dest)
        files_added.append({"role": "supplementary_guideline_coverage", "path": str(dest)})

    # 10. Section Role Report
    section_role = state.qa.get("section_role_report_path", "")
    if section_role and Path(section_role).exists():
        dest = supp_dir / "section_role_report.json"
        shutil.copy(section_role, dest)
        files_added.append({"role": "supplementary_section_role", "path": str(dest)})

    # Build manifest
    manifest = {
        "job_id": state.job_id,
        "package_type": "supplementary_materials",
        "files": files_added,
        "total_files": len(files_added),
    }

    manifest_path = supp_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Update state
    state.output["supplementary_package_path"] = str(supp_dir)
    state.output["supplementary_package_manifest"] = str(manifest_path)

    return state
