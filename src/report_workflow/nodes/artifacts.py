"""ARTIFACTS node - package MVP workflow outputs into a structured deliverable.

Collect and package the validated report, evidence, QA, source, and traceability
artifacts into the output directory:
  ~/.hermes/published/{job_id}/

Deliverable layout:
  {job_id}/
    report.docx              # Final rendered document
    report.md                 # Source markdown
    metadata.json             # Workflow metadata, timing, gate decisions
    qa/
      factuality_report.json
      qa_summary.json
    evidence/
      claim_matrix.json
      evidence_ledger.jsonl
    sources/
      {uploaded files...}
    artifacts.json            # This manifest lists all packaged files
"""
import json
import shutil
from pathlib import Path
from datetime import datetime

from ..state import ReportState, WORKFLOW_RUNS_DIR, PUBLISHED_DIR
from ..runtime_support import write_artifact_lineage


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


def _load_jsonl(path: str | None) -> list[dict]:
    if not path:
        return []
    try:
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    except Exception:
        return []


def _write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _collect_paths(subdir: Path, glob_pat: str) -> list[str]:
    try:
        return [str(p) for p in subdir.glob(glob_pat)]
    except Exception:
        return []


def _build_edit_manifest(state: ReportState, run_dir: Path) -> dict | None:
    """Build edit_manifest.json for revise_existing workflows.

    Records each change with before/after text, claim linkage, evidence linkage,
    and origin timestamp.
    """
    revision_plan_path = run_dir / "revision_plan.json"
    if not revision_plan_path.exists():
        return None

    try:
        with open(revision_plan_path, encoding="utf-8") as f:
            revision_plan = json.load(f)
    except Exception:
        return None

    changes = revision_plan.get("changes", [])
    if not changes:
        return None

    # Load evidence ledger for linkage
    evidence = _load_jsonl(state.sources.get("evidence_ledger_path"))
    evidence_by_id = {e.get("evidence_id"): e for e in evidence}

    # Load claim matrix for linkage
    claim_matrix = state.plan.get("claim_matrix") or {}
    claims_by_id = {c.get("claim_id"): c for c in claim_matrix.get("claims", [])}

    manifest_entries = []
    for idx, change in enumerate(changes):
        claim_ids = change.get("claim_ids", [])
        evidence_ids = change.get("evidence_ids", [])

        entry = {
            "change_index": idx,
            "section_id": change.get("section_id", ""),
            "change_type": change.get("change_type", ""),
            "original_text": change.get("original_text", ""),
            "new_text": change.get("new_text", ""),
            "claim_ids": claim_ids,
            "evidence_ids": evidence_ids,
            "claim_links": [
                {
                    "claim_id": cid,
                    "claim_text": claims_by_id.get(cid, {}).get("claim_text", ""),
                    "claim_type": claims_by_id.get(cid, {}).get("claim_type", ""),
                }
                for cid in claim_ids if cid in claims_by_id
            ],
            "evidence_links": [
                {
                    "evidence_id": eid,
                    "evidence_grade": evidence_by_id.get(eid, {}).get("evidence_grade", ""),
                    "evidence_type": evidence_by_id.get(eid, {}).get("evidence_type", ""),
                    "content_preview": evidence_by_id.get(eid, {}).get("content", "")[:240],
                }
                for eid in evidence_ids if eid in evidence_by_id
            ],
            "origin_timestamp": datetime.now().isoformat(),
        }
        manifest_entries.append(entry)

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
    evidence = _load_jsonl(state.sources.get("evidence_ledger_path"))
    evidence_by_id = {item.get("evidence_id"): item for item in evidence}
    factuality = _load_json(state.qa.get("factuality_report_path"))
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
            "status": factuality_by_claim.get(claim.get("claim_id", ""), {}).get("status", claim.get("status", "")),
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

    coverage_md = "\n".join([
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
    ])
    coverage_path = Path(_write_text(trace_dir / "evidence_coverage_summary.md", coverage_md))

    factuality_md = "\n".join([
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
    ])
    factuality_path = Path(_write_text(trace_dir / "factuality_summary.md", factuality_md))

    qa_note_md = "\n".join([
        "# Client-Readable QA Note",
        "",
        f"- QA decision: {state.qa.get('qa_decision', '')}",
        f"- Artifact completeness: {state.qa.get('artifact_completeness_status', '')}",
        "",
        "## Notes",
        "",
        "This package includes the report, source materials, evidence ledger, claim audit, and QA summaries produced by the workflow.",
        "",
    ])
    qa_note_path = Path(_write_text(trace_dir / "client_readable_qa_note.md", qa_note_md))

    return {
        "claim_to_source_audit": str(claim_audit_path),
        "evidence_coverage_summary": str(coverage_path),
        "factuality_summary": str(factuality_path),
        "client_readable_qa_note": str(qa_note_path),
    }


def run_artifacts(state: ReportState) -> ReportState:
    """T25: ARTIFACTS - package all outputs into published directory."""
    run_id = state.job_id
    published_dir = PUBLISHED_DIR / run_id
    published_dir.mkdir(parents=True, exist_ok=True)

    qa_dir = published_dir / "qa"
    evidence_dir = published_dir / "evidence"
    sources_dir = published_dir / "sources"
    traceability_dir = published_dir / "traceability"
    run_dir = Path.home() / ".hermes" / "workflow_runs" / run_id
    traceability_paths = _build_traceability_artifacts(state, run_dir)

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
        "factuality_report.json": state.qa.get("factuality_report_path"),
        "qa_summary.json": state.qa.get("qa_summary_path"),
    }
    for fname, fpath in qa_files.items():
        copied = _copy_file(fpath, qa_dir, fname)
        if copied:
            artifacts_meta["files"].append({"role": f"qa_{fname.replace('.json','')}", "path": copied})

    # --- Run control artifacts ---
    control_files = {
        "report_spec.json": state.spec.get("report_spec_path"),
        "guideline_selection.json": state.spec.get("guideline_selection_path"),
        "remediation_plan.json": state.governance.get("remediation_plan_path"),
    }
    for fname, fpath in control_files.items():
        copied = _copy_file(fpath, qa_dir, fname)
        if copied:
            artifacts_meta["files"].append({"role": f"control_{fname.replace('.json','')}", "path": copied})

    # --- Evidence artifacts ---
    evidence_files = {
        "claim_matrix.json": _collect_paths(Path.home() / ".hermes" / "workflow_runs" / run_id, "claim_matrix.json"),
        "outline.json": [state.plan.get("outline_path")] if state.plan.get("outline_path") else [],
        "sentence_map.jsonl": [state.drafts.get("sentence_map_path")] if state.drafts.get("sentence_map_path") else [],
        "evidence_ledger.jsonl": _collect_paths(Path.home() / ".hermes" / "workflow_runs" / run_id, "evidence_ledger.jsonl"),
        "evidence_store_manifest.json": [state.sources.get("evidence_store_manifest_path")] if state.sources.get("evidence_store_manifest_path") else [],
        "section_plan_freeze.json": [state.plan.get("section_plan_freeze_path")] if state.plan.get("section_plan_freeze_path") else [],
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

    # --- Traceability artifacts ---
    for role, path in traceability_paths.items():
        copied = _copy_file(path, traceability_dir)
        if copied:
            artifacts_meta["files"].append({"role": f"traceability_{role}", "path": copied})

    # --- F6: edit_manifest.json (revise_existing only) ---
    task_intent = state.spec.get("task_intent", "new_draft")
    if task_intent == "revise_existing":
        edit_manifest = _build_edit_manifest(state, run_dir)
        if edit_manifest:
            edit_manifest_path = run_dir / "edit_manifest.json"
            with open(edit_manifest_path, "w", encoding="utf-8") as f:
                json.dump(edit_manifest, f, indent=2, default=str)
            copied = _copy_file(str(edit_manifest_path), published_dir, "edit_manifest.json")
            if copied:
                artifacts_meta["files"].append({"role": "revision_edit_manifest", "path": copied})

    # --- Metadata JSON ---
    lineage_path = write_artifact_lineage(state, artifacts_meta["files"])
    lineage_copied = _copy_file(lineage_path, published_dir, "artifact_lineage.json")
    if lineage_copied:
        artifacts_meta["files"].append({"role": "artifact_lineage", "path": lineage_copied})

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
        "qa_decision": state.qa.get("qa_decision", ""),
        "qa_gate_status": state.qa.get("qa_decision", ""),
        "artifact_completeness_status": state.qa.get("artifact_completeness_status", ""),
        "hard_fail_reasons": state.qa.get("hard_fail_reasons", []),
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
    state.output["traceability_artifacts"] = traceability_paths
    state.checkpoint("ARTIFACTS")

    return state
