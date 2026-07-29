"""ARTIFACTS node - package workflow outputs into a structured deliverable.

Collects the rendered report, evidence, QA, source, and traceability artifacts
under:
  output/<slug>--<job_id>/published/
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from ..artifact_packaging.common import (
    load_json,
    load_jsonl,
    qa_role_for_filename,
    write_text,
)
from ..artifact_packaging.final_qa import build_final_qa_summary
from ..artifact_packaging.template_reports import (
    build_template_field_fill_report,
    build_template_style_map,
)
from ..runtime_support import write_artifact_lineage
from ..state import ReportState, published_dir_for, run_dir_for


def _copy_file(src: str | None, dest_dir: Path, dest_name: str | None = None) -> str | None:
    """Copy file if it exists. Returns packaged path or None."""
    if not src:
        return None
    p = Path(src)
    if not p.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (dest_name or p.name)
    shutil.copy2(p, dest)
    return str(dest)


def _unique_source_names(paths: list[str]) -> dict[str, str]:
    """Destination names that keep two same-named sources apart.

    2024/月報.csv and 2025/月報.csv both landed on published/sources/月報.csv, so
    the bundle shipped whichever was copied last. A reader checking the report's
    2024 claim opened the surviving file and read 2025's numbers — the
    traceability package contradicting the report it exists to substantiate,
    with every gate green, because no gate compares the bundle against the
    registry.
    """
    by_name: dict[str, list[str]] = {}
    for path in paths:
        by_name.setdefault(Path(path).name, []).append(path)
    names: dict[str, str] = {}
    for name, group in by_name.items():
        if len(group) == 1:
            names[group[0]] = name
            continue
        for path in group:
            parent = Path(path).parent.name
            names[path] = f"{parent}_{name}" if parent else name
        if len({names[path] for path in group}) != len(group):
            for index, path in enumerate(group, start=1):
                stem, suffix = Path(path).stem, Path(path).suffix
                names[path] = f"{stem}_{index}{suffix}"
    return names


def _collect_paths(subdir: Path, glob_pat: str) -> list[str]:
    try:
        return [str(p) for p in subdir.glob(glob_pat)]
    except Exception:
        return []


def _build_edit_manifest(state: ReportState, run_dir: Path) -> dict | None:
    """Build edit_manifest.json for revise_existing workflows."""
    revision_plan_path = run_dir / "revision_plan.json"
    if not revision_plan_path.exists():
        return None

    revision_plan = load_json(str(revision_plan_path))
    changes = revision_plan.get("changes", [])
    if not changes:
        return None

    evidence = load_jsonl(state.sources.get("evidence_ledger_path"))
    evidence_by_id = {item.get("evidence_id"): item for item in evidence}
    claim_matrix = state.plan.get("claim_matrix") or {}
    claims_by_id = {item.get("claim_id"): item for item in claim_matrix.get("claims", [])}

    manifest_entries = []
    for idx, change in enumerate(changes):
        claim_ids = change.get("claim_ids", [])
        evidence_ids = change.get("evidence_ids", [])
        manifest_entries.append({
            "change_index": idx,
            "section_id": change.get("section_id", ""),
            "change_type": change.get("change_type", ""),
            "original_text": change.get("original_text", ""),
            "new_text": change.get("new_text", ""),
            "claim_ids": claim_ids,
            "evidence_ids": evidence_ids,
            "claim_links": [
                {
                    "claim_id": claim_id,
                    "claim_text": claims_by_id.get(claim_id, {}).get("claim_text", ""),
                    "claim_type": claims_by_id.get(claim_id, {}).get("claim_type", ""),
                }
                for claim_id in claim_ids if claim_id in claims_by_id
            ],
            "evidence_links": [
                {
                    "evidence_id": evidence_id,
                    "evidence_grade": evidence_by_id.get(evidence_id, {}).get("evidence_grade", ""),
                    "evidence_type": evidence_by_id.get(evidence_id, {}).get("evidence_type", ""),
                    "content_preview": evidence_by_id.get(evidence_id, {}).get("content", "")[:240],
                }
                for evidence_id in evidence_ids if evidence_id in evidence_by_id
            ],
            "origin_timestamp": datetime.now().isoformat(),
        })

    return {
        "job_id": state.job_id,
        "intent": "revise_existing",
        "total_changes": len(manifest_entries),
        "changes": manifest_entries,
    }


def _build_traceability_artifacts(state: ReportState, run_dir: Path) -> dict[str, str]:
    trace_dir = run_dir / "traceability"
    trace_dir.mkdir(parents=True, exist_ok=True)

    claim_matrix = state.plan.get("claim_matrix") or {}
    claims = claim_matrix.get("claims", [])
    evidence = load_jsonl(state.sources.get("evidence_ledger_path"))
    evidence_by_id = {item.get("evidence_id"): item for item in evidence}
    factuality = load_json(state.qa.get("factuality_report_path"))
    factuality_by_claim = {
        item.get("claim_id"): item for item in factuality.get("claims", [])
    }

    audit_items = []
    claims_with_evidence = 0
    for claim in claims:
        evidence_ids = claim.get("evidence_ids", [])
        if evidence_ids:
            claims_with_evidence += 1
        audit_items.append({
            "claim_id": claim.get("claim_id", ""),
            "claim_text": claim.get("claim_text", ""),
            "claim_type": claim.get("claim_type", ""),
            "status": factuality_by_claim.get(
                claim.get("claim_id", ""), {}
            ).get("status", claim.get("status", "")),
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "source_id": evidence_by_id.get(evidence_id, {}).get("source_id", ""),
                    "source_file_name": evidence_by_id.get(evidence_id, {}).get("source_file_name", ""),
                    "evidence_grade": evidence_by_id.get(evidence_id, {}).get("evidence_grade", ""),
                    "evidence_type": evidence_by_id.get(evidence_id, {}).get("evidence_type", ""),
                    "content_preview": evidence_by_id.get(evidence_id, {}).get("content", "")[:240],
                }
                for evidence_id in evidence_ids
            ],
        })

    claim_audit_path = trace_dir / "claim_to_source_audit.json"
    with open(claim_audit_path, "w", encoding="utf-8") as f:
        json.dump({"claims": audit_items}, f, indent=2, default=str)

    grade_counts: dict[str, int] = {}
    for item in evidence:
        grade = item.get("evidence_grade", "unknown")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    coverage_path = Path(write_text(trace_dir / "evidence_coverage_summary.md", "\n".join([
        "# Evidence Coverage Summary",
        "",
        f"- Claims total: {len(claims)}",
        f"- Claims with evidence: {claims_with_evidence}",
        f"- Claims without evidence: {len(claims) - claims_with_evidence}",
        f"- Evidence units total: {len(evidence)}",
        "",
        "## Evidence By Grade",
        "",
        *[f"- {grade}: {count}" for grade, count in sorted(grade_counts.items())],
        "",
    ])))

    factuality_path = Path(write_text(trace_dir / "factuality_summary.md", "\n".join([
        "# Factuality Summary",
        "",
        f"- Verified claims: {factuality.get('verified_count', 0)}",
        f"- Blocked claims: {factuality.get('blocked_count', 0)}",
        "",
        "## Claim Results",
        "",
        *[
            f"- {item.get('claim_id', '')}: {item.get('status', '')} ({item.get('checker', '')})"
            for item in factuality.get("claims", [])
        ],
        "",
    ])))

    qa_note_path = Path(write_text(trace_dir / "client_readable_qa_note.md", "\n".join([
        "# Client-Readable QA Note",
        "",
        f"- QA decision: {state.qa.get('qa_decision', '')}",
        f"- Artifact completeness: {state.qa.get('artifact_completeness_status', '')}",
        "",
        "## Notes",
        "",
        "This package includes the report, source materials, evidence ledger, claim audit, and QA summaries produced by the workflow.",
        "",
    ])))

    return {
        "claim_to_source_audit": str(claim_audit_path),
        "evidence_coverage_summary": str(coverage_path),
        "factuality_summary": str(factuality_path),
        "client_readable_qa_note": str(qa_note_path),
    }


def _copy_named_files(files: dict[str, str | None], dest_dir: Path, role_prefix: str, artifacts_meta: dict) -> None:
    for fname, fpath in files.items():
        copied = _copy_file(fpath, dest_dir, fname)
        if copied:
            stem = fname.replace(".jsonl", "").replace(".json", "")
            artifacts_meta["files"].append({"role": f"{role_prefix}_{stem}", "path": copied})


def run_artifacts(state: ReportState) -> ReportState:
    """T25: ARTIFACTS - package all outputs into published directory."""
    run_id = state.job_id
    published_dir = published_dir_for(state)
    published_dir.mkdir(parents=True, exist_ok=True)

    qa_dir = published_dir / "qa"
    evidence_dir = published_dir / "evidence"
    sources_dir = published_dir / "sources"
    traceability_dir = published_dir / "traceability"
    run_dir = run_dir_for(state)

    traceability_paths = _build_traceability_artifacts(state, run_dir)
    template_style_paths = build_template_style_map(state, run_dir)
    template_field_paths = build_template_field_fill_report(state, run_dir)
    final_qa_paths = build_final_qa_summary(state, run_dir)

    artifacts_meta: dict = {
        "job_id": run_id,
        "created_at": datetime.now().isoformat(),
        "status": state.status,
        "report_profile": state.spec.get("report_profile", ""),
        "files": [],
    }

    docx_copied = _copy_file(state.output.get("final_docx_path"), published_dir, "report.docx")
    if docx_copied:
        artifacts_meta["files"].append({"role": "report_docx", "path": docx_copied})

    merged_md = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path")
    md_copied = _copy_file(merged_md, published_dir, "report.md")
    if md_copied:
        artifacts_meta["files"].append({"role": "report_markdown", "path": md_copied})

    layout_manifest_path = (
        state.runtime.get("post_render_layout_manifest_path")
        or state.output.get("post_render_layout_manifest_path")
    )
    qa_files = {
        "final_qa_summary.json": final_qa_paths.get("json"),
        "final_qa_summary.md": final_qa_paths.get("markdown"),
        "template_style_map.json": template_style_paths.get("json"),
        "template_style_map.md": template_style_paths.get("markdown"),
        "template_field_fill_report.json": template_field_paths.get("json"),
        "template_field_fill_report.md": template_field_paths.get("markdown"),
        "factuality_report.json": state.qa.get("factuality_report_path"),
        "qa_summary.json": state.qa.get("qa_summary_path"),
        "engineering_audit_report.json": state.qa.get("engineering_audit_report_path"),
        "scholarly_quality_report.json": state.qa.get("scholarly_quality_report_path"),
        "scholarly_quality_report.md": state.qa.get("scholarly_quality_report_md_path"),
        "figure_recommendations.json": state.output.get("figure_recommendations_path"),
        "figure_plan_audit_report.json": state.qa.get("figure_plan_audit_report_path"),
        "figure_visual_quality_report.json": state.qa.get("figure_visual_quality_report_path"),
        "post_render_repair_report.json": state.runtime.get("post_render_repair_report_path"),
        "post_render_validate_report.json": state.runtime.get("post_render_validate_report_path"),
        "post_render_layout_manifest.json": layout_manifest_path,
        "visual_render_check_report.json": state.runtime.get("visual_render_check_report_path"),
    }
    for fname, fpath in qa_files.items():
        copied = _copy_file(fpath, qa_dir, fname)
        if copied:
            artifacts_meta["files"].append({"role": qa_role_for_filename(fname), "path": copied})

    control_files = {
        "report_spec.json": state.spec.get("report_spec_path"),
        "guideline_selection.json": state.spec.get("guideline_selection_path"),
        "remediation_plan.json": state.governance.get("remediation_plan_path"),
    }
    _copy_named_files(control_files, qa_dir, "control", artifacts_meta)

    evidence_files = {
        "claim_matrix.json": _collect_paths(run_dir, "claim_matrix.json"),
        "outline.json": [state.plan.get("outline_path")] if state.plan.get("outline_path") else [],
        "sentence_map.jsonl": [state.drafts.get("sentence_map_path")] if state.drafts.get("sentence_map_path") else [],
        "evidence_ledger.jsonl": _collect_paths(run_dir, "evidence_ledger.jsonl"),
        "evidence_store_manifest.json": [state.sources.get("evidence_store_manifest_path")] if state.sources.get("evidence_store_manifest_path") else [],
        "section_plan_freeze.json": [state.plan.get("section_plan_freeze_path")] if state.plan.get("section_plan_freeze_path") else [],
    }
    for fname, fpaths in evidence_files.items():
        for fpath in fpaths:
            copied = _copy_file(fpath, evidence_dir, fname)
            if copied:
                stem = fname.replace(".jsonl", "").replace(".json", "")
                artifacts_meta["files"].append({"role": f"evidence_{stem}", "path": copied})

    uploaded = [str(p) for p in state.spec.get("uploaded_files", []) if p]
    source_names = _unique_source_names(uploaded)
    for src_path in uploaded:
        copied = _copy_file(src_path, sources_dir, source_names.get(src_path))
        if copied:
            artifacts_meta["files"].append({"role": "source", "path": copied})

    for role, path in traceability_paths.items():
        copied = _copy_file(path, traceability_dir)
        if copied:
            artifacts_meta["files"].append({"role": f"traceability_{role}", "path": copied})

    if state.spec.get("task_intent", "new_draft") == "revise_existing":
        edit_manifest = _build_edit_manifest(state, run_dir)
        if edit_manifest:
            edit_manifest_path = run_dir / "edit_manifest.json"
            with open(edit_manifest_path, "w", encoding="utf-8") as f:
                json.dump(edit_manifest, f, indent=2, default=str)
            copied = _copy_file(str(edit_manifest_path), published_dir, "edit_manifest.json")
            if copied:
                artifacts_meta["files"].append({"role": "revision_edit_manifest", "path": copied})

    lineage_path = write_artifact_lineage(state, artifacts_meta["files"])
    lineage_copied = _copy_file(lineage_path, published_dir, "artifact_lineage.json")
    if lineage_copied:
        artifacts_meta["files"].append({"role": "artifact_lineage", "path": lineage_copied})

    metadata = {
        "job_id": run_id,
        "created_at": datetime.now().isoformat(),
        "status": state.status,
        "report_profile": state.spec.get("report_profile", ""),
        "delivery_mode": state.spec.get("delivery_mode", "fresh_doc"),
        "audience": state.spec.get("audience", "expert"),
        "citation_style": state.spec.get("citation_style", "apa"),
        "keywords": state.spec.get("keywords", []),
        "selected_guidelines": state.spec.get("selected_guidelines", []),
        "qa_decision": state.qa.get("qa_decision", ""),
        "qa_gate_status": state.qa.get("qa_decision", ""),
        "artifact_completeness_status": state.qa.get("artifact_completeness_status", ""),
        "hard_fail_reasons": state.qa.get("hard_fail_reasons", []),
        "workflow_success": bool(state.output.get("workflow_success") and state.status == "completed"),
        "published_report_path": state.output.get("published_report_path", ""),
        "final_qa_summary_path": state.qa.get("final_qa_summary_path", ""),
        "template_style_map_path": state.output.get("template_style_map_path", ""),
        "template_field_fill_report_path": state.output.get("template_field_fill_report_path", ""),
        "file_count": len(artifacts_meta["files"]),
    }
    metadata_path = published_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)
    artifacts_meta["files"].append({"role": "metadata", "path": str(metadata_path)})

    artifacts_path = published_dir / "artifacts.json"
    with open(artifacts_path, "w", encoding="utf-8") as f:
        json.dump(artifacts_meta, f, indent=2, default=str)

    state.output["published_dir"] = str(published_dir)
    state.output["artifacts_manifest_path"] = str(artifacts_path)
    state.output["metadata_path"] = str(metadata_path)
    state.output["artifact_count"] = len(artifacts_meta["files"])
    state.output["traceability_artifacts"] = traceability_paths
    state.checkpoint("ARTIFACTS")

    return state
