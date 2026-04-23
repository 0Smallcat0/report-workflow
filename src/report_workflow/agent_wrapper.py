"""Agent wrapper — entry points for the 4-step report workflow.

Step 1: start_report_task        → Prepare deterministic artifacts + task briefs
Step 2: submit_claim_matrix      → Validate claim_matrix.json (Agent produces this)
Step 3: submit_outline           → Validate outline.json (Agent produces this)
Step 4: submit_drafts            → Validate section_drafts/*.md + sentence_map.jsonl
Step 5: submit_and_publish_report→ Full validate + render pipeline

The 4-step split (Steps 2-4) allows the Agent to work on each artifact
independently, checkpointing after each step. This prevents context window
exhaustion that occurs when the Agent must produce all artifacts in a single
conversation turn.

Legacy 2-step workflow (start + submit_and_publish) still works — the Agent
simply skips Steps 2-4 and goes directly from Step 1 to Step 5.
"""

from report_workflow.run_workflow import (
    prepare_workflow,
    validate_workflow,
    render_workflow,
    validate_step_claim_matrix,
    validate_step_outline,
    validate_step_drafts,
)
from report_workflow.errors import AgentWorkRequired, QAHardBlockError
from report_workflow.state import WORKFLOW_RUNS_DIR
from report_workflow.runtime_support import load_jsonl
from report_workflow.artifact_contract import remap_evidence_ids
from report_workflow.config import load_config, save_feature_flag
from report_workflow.preflight import discover_features, check_preflight


def check_setup() -> dict:
    """Pre-flight environment check — call BEFORE start_report_task.

    Returns the current configuration state, feature discovery results,
    and any missing dependencies. Does NOT start a workflow run or parse
    any source files.

    The agent MUST call this first, read the ``agent_should_ask_user``
    list, and present each option to the user. Only after the user has
    made their choices should the agent call ``start_report_task`` with
    the appropriate flags.
    """
    try:
        cfg = load_config()
        preflight = check_preflight()
        discovery = discover_features(
            enable_research=cfg.enable_research,
            enable_notebook_sync=cfg.enable_notebook_sync,
        )

        ask_user = discovery.agent_should_ask_user
        features = discovery.as_dict()

        # Build a human-readable setup message
        lines = ["📋 Report Workflow — 環境檢查結果\n"]

        # Prerequisites
        if not preflight.ok:
            lines.append("❌ 缺少必要套件: " + ", ".join(preflight.missing_packages))
            lines.append("   修復: pip install -r requirements.txt\n")
        else:
            lines.append("✅ 所有必要套件已安裝")

        # External tools
        for tw in preflight.external_tool_warnings:
            sev = "⚠️" if tw["severity"] == "critical" else "ℹ️"
            lines.append(f"{sev} {tw['tool']} 未安裝 — {tw['description']}")
            lines.append(f"   安裝指令: {tw['install_command']}")
        if not preflight.external_tool_warnings:
            lines.append("✅ 外部工具已就緒 (pandoc, mmdc)")

        lines.append("")

        # Feature discovery — what to ask the user
        if ask_user:
            lines.append("━━━ 以下功能需要您向使用者確認 ━━━\n")
            for i, item in enumerate(ask_user, 1):
                lines.append(f"  {i}. {item.get('question', item.get('question_en', ''))}")
                if "setup_commands" in item:
                    for cmd in item["setup_commands"]:
                        lines.append(f"     安裝: {cmd}")
                lines.append(f"     動作: {item['action']}")
                lines.append("")
            lines.append(
                "👉 請向使用者詢問以上功能是否要啟用，"
                "然後在 start_report_task 中帶入對應參數。"
            )
        else:
            lines.append("✅ 無需額外確認，可直接呼叫 start_report_task")

        return {
            "status": "ready" if preflight.ok else "missing_dependencies",
            "message": "\n".join(lines),
            "feature_discovery": features,
            "config_summary": cfg.as_env_summary(),
            "agent_should_ask_user": ask_user,
            "preflight": preflight.as_dict(),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def start_report_task(
    prompt: str,
    source_files: list[str],
    output_dir: str,
    report_family: str | None = None,
    report_family_detail: str | None = None,
    title: str | None = None,
    author_block: str | None = None,
    affiliation_block: str | None = None,
    correspondence: str | None = None,
    keywords: list[str] | None = None,
    project_identity: dict | None = None,
    enable_research: bool | None = None,
    enable_notebook_sync: bool | None = None,
    notebooklm_notebook_id: str | None = None,
    notebooklm_storage_path: str | None = None,
) -> dict:
    """Step 1: Start the report generation workflow.

    Creates deterministic artifacts (evidence ledger, blueprint) and
    generates task briefs for the Agent to complete.

    **Recommended**: Call ``check_setup()`` first to verify dependencies
    and ask the user about optional features. Then call this function
    with the user's chosen flags.

    Configuration is loaded from multiple sources (highest priority wins):
      1. Function parameters passed here
      2. Environment variables
      3. .env file in project root
      4. workflow_config.yaml in project root
    """
    try:
        # ---- Load merged configuration ----
        cfg = load_config(
            enable_research=enable_research,
            enable_notebook_sync=enable_notebook_sync,
            notebooklm_notebook_id=notebooklm_notebook_id,
            notebooklm_storage_path=notebooklm_storage_path,
        )

        state = prepare_workflow(
            prompt,
            source_files,
            output_dir,
            report_family=report_family,
            report_family_detail=report_family_detail,
            front_matter={
                key: value for key, value in {
                    "title": title,
                    "author_block": author_block,
                    "affiliation_block": affiliation_block,
                    "correspondence": correspondence,
                    "keywords": keywords,
                }.items()
                if value
            },
            project_identity=project_identity,
        )

        # Apply resolved config to state flags
        if cfg.enable_research:
            state.flags["enable_research"] = True
        if cfg.enable_notebook_sync:
            state.flags["enable_notebook_sync"] = True
        if cfg.notebooklm_notebook_id:
            state.spec["notebooklm_notebook_id"] = cfg.notebooklm_notebook_id
        if cfg.notebooklm_storage_path:
            state.spec["notebooklm_storage_path"] = cfg.notebooklm_storage_path

        # ---- Feature discovery (for info, not blocking) ----
        discovery = discover_features(
            enable_research=cfg.enable_research,
            enable_notebook_sync=cfg.enable_notebook_sync,
        )

        warnings = state.runtime.get("warnings", [])

        if state.status == "awaiting_agent_artifacts":
            # Build message — embed feature status directly so agent can't miss it
            msg_lines = [
                f"Agent work required. Read task briefs at: "
                f"~/.hermes/workflow_runs/{state.job_id}/agent_tasks/",
                "",
                "Submit artifacts step-by-step:",
                "  1. Create claim_matrix.json → call submit_claim_matrix",
                "  2. Create outline.json → call submit_outline",
                "  3. Create section_drafts/*.md + sentence_map.jsonl → call submit_drafts",
                "  4. Call submit_and_publish_report to render the final DOCX",
                "",
            ]

            # Embed active features in message
            active = [f for f in discovery.features if f.enabled and f.ready]
            inactive_ready = [f for f in discovery.features if not f.enabled and f.ready]

            if active:
                msg_lines.append("已啟用功能: " + ", ".join(f.name for f in active))
            if inactive_ready:
                msg_lines.append(
                    "⚠️ 可用但未啟用的功能: " + ", ".join(f.name for f in inactive_ready)
                    + "\n   建議先呼叫 check_setup() 確認使用者是否要啟用。"
                )

            result = {
                "status": "awaiting_agent_artifacts",
                "job_id": state.job_id,
                "message": "\n".join(msg_lines),
                "feature_discovery": discovery.as_dict(),
                "config_summary": cfg.as_env_summary(),
            }
            if warnings:
                result["warnings"] = warnings
            return result

        result = {
            "status": state.status,
            "job_id": state.job_id,
            "message": "Workflow completed successfully.",
            "feature_discovery": discovery.as_dict(),
            "config_summary": cfg.as_env_summary(),
        }
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        return {"status": "failed", "error": str(e)}



def submit_claim_matrix(job_id: str) -> dict:
    """Step 2: Validate the Agent-authored claim_matrix.json.

    Call this after creating claim_matrix.json in the agent_tasks directory.
    This validates structure and evidence linkage, then checkpoints.
    """
    try:
        state = validate_step_claim_matrix(job_id)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 1/3 complete — claim_matrix.json validated.\n"
                "Next: Create outline.json and call submit_outline."
            ),
        }
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "claim_matrix.json is missing or incomplete.",
            "missing_artifacts": e.missing_artifacts,
        }
    except QAHardBlockError as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "claim_matrix.json validation failed. Revise and resubmit.",
            "error_details": str(e),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_outline(job_id: str) -> dict:
    """Step 3: Validate the Agent-authored outline.json.

    Call this after creating outline.json. Requires claim_matrix to be validated first.
    """
    try:
        state = validate_step_outline(job_id)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 2/3 complete — outline.json validated.\n"
                "Next: Create section_drafts/*.md + sentence_map.jsonl, "
                "then call submit_drafts."
            ),
        }
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "outline.json is missing or incomplete.",
            "missing_artifacts": e.missing_artifacts,
        }
    except QAHardBlockError as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "outline.json validation failed. Revise and resubmit.",
            "error_details": str(e),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_drafts(job_id: str) -> dict:
    """Step 4: Validate section_drafts/*.md and sentence_map.jsonl.

    Call this after creating all section draft files and sentence_map.jsonl.
    Requires both claim_matrix and outline to be validated first.
    """
    try:
        state = validate_step_drafts(job_id)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 3/3 complete — section drafts validated.\n"
                "All artifacts ready. Call submit_and_publish_report to render."
            ),
        }
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "Section drafts or sentence_map are missing.",
            "missing_artifacts": e.missing_artifacts,
        }
    except QAHardBlockError as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "Section draft validation failed. Revise and resubmit.",
            "error_details": str(e),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_and_publish_report(job_id: str) -> dict:
    """Step 5: Run full validation pipeline and render the final DOCX.

    This can be called after all 3 steps, or directly after start_report_task
    if the Agent created all artifacts in one shot (legacy 2-step mode).
    """
    try:
        state = validate_workflow(job_id)
        state = render_workflow(job_id)
        warnings = state.runtime.get("warnings", [])
        result = {
            "status": state.status,
            "job_id": state.job_id,
            "final_docx_path": state.output.get("final_docx_path", ""),
            "published_report_path": state.output.get("published_report_path", ""),
            "workflow_success": bool(state.output.get("workflow_success") and state.status == "completed"),
            "renderer_used": state.output.get("renderer_used", "unknown"),
            "message": "Report validation passed and DOCX successfully rendered!",
        }
        if warnings:
            result["warnings"] = warnings
        return result
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": (
                "Missing agent artifacts. You must create all required files before submitting.\n"
                "Consider using the step-by-step workflow:\n"
                "  submit_claim_matrix → submit_outline → submit_drafts → submit_and_publish_report"
            ),
            "missing_artifacts": e.missing_artifacts,
        }
    except QAHardBlockError as e:
        run_dir = WORKFLOW_RUNS_DIR / job_id
        rendered_docx = run_dir / "rendered_report.docx"
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "QA Gates Failed. Revise your artifacts and submit again.",
            "error_details": str(e),
            "rendered_but_not_publishable": rendered_docx.exists(),
            "not_final_deliverable": rendered_docx.exists(),
            "rendered_docx_path": str(rendered_docx) if rendered_docx.exists() else "",
        }
    except Exception as e:
        run_dir = WORKFLOW_RUNS_DIR / job_id
        rendered_docx = run_dir / "rendered_report.docx"
        return {
            "status": "failed",
            "error": str(e),
            "rendered_but_not_publishable": rendered_docx.exists(),
            "not_final_deliverable": rendered_docx.exists(),
            "rendered_docx_path": str(rendered_docx) if rendered_docx.exists() else "",
        }


def query_evidence(
    job_id: str,
    evidence_ids: list[str] | None = None,
    offset: int = 0,
    limit: int = 20,
) -> dict:
    """Query evidence entries from the evidence ledger.

    Allows the Agent to look up specific evidence entries by ID or browse
    the ledger in pages, without loading the entire JSONL file.

    Args:
        job_id: The job ID from start_report_task.
        evidence_ids: Optional list of specific evidence_id values to retrieve.
            If provided, offset/limit are ignored.
        offset: Starting index for paginated browsing (default 0).
        limit: Maximum entries to return (default 20, max 50).
    """
    try:
        run_dir = WORKFLOW_RUNS_DIR / job_id
        ledger_path = run_dir / "evidence_ledger.jsonl"

        if not ledger_path.exists():
            return {
                "status": "error",
                "message": f"Evidence ledger not found at {ledger_path}",
            }

        all_entries = load_jsonl(str(ledger_path))
        total = len(all_entries)

        if evidence_ids:
            # Filter by specific IDs
            id_set = set(evidence_ids)
            entries = [e for e in all_entries if e.get("evidence_id") in id_set]
            found_ids = {e.get("evidence_id") for e in entries}
            missing = id_set - found_ids
            return {
                "status": "ok",
                "job_id": job_id,
                "total_entries": total,
                "returned": len(entries),
                "entries": entries,
                "missing_ids": list(missing) if missing else [],
            }
        else:
            # Paginated browsing
            limit = min(limit, 50)
            page = all_entries[offset:offset + limit]
            return {
                "status": "ok",
                "job_id": job_id,
                "total_entries": total,
                "offset": offset,
                "limit": limit,
                "returned": len(page),
                "entries": page,
                "has_more": (offset + limit) < total,
            }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def remap_agent_artifacts(
    job_id: str,
    previous_job_id: str,
    write: bool = False,
) -> dict:
    """Remap evidence IDs in agent artifacts from a previous run to this run."""
    try:
        return remap_evidence_ids(job_id, previous_job_id, write=write)
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_revision_plan(job_id: str) -> dict:
    """Validate a revision_plan.json for revise_existing workflows.

    Pre-validates all changes against the base document, checks for
    conflicts and unresolvable changes, and returns a diff preview.
    Call this before submit_and_publish_report for revision workflows.
    """
    import json

    try:
        run_dir = WORKFLOW_RUNS_DIR / job_id

        # Load base_document_sections
        sections_path = run_dir / "base_document_sections.json"
        if not sections_path.exists():
            return {
                "status": "error",
                "message": (
                    "base_document_sections.json not found. "
                    "This tool is only for revise_existing workflows."
                ),
            }

        with open(sections_path, encoding="utf-8") as f:
            base_sections = json.load(f)

        # Load revision_plan
        plan_path = run_dir / "revision_plan.json"
        if not plan_path.exists():
            return {
                "status": "error",
                "message": (
                    "revision_plan.json not found. "
                    "Create it first (see 04_revision_plan.md brief)."
                ),
            }

        with open(plan_path, encoding="utf-8") as f:
            revision_plan = json.load(f)

        # Run diff validation
        from report_workflow.nodes.base_document_diff import (
            compute_revision_diff,
            write_diff_report,
        )

        diff_result = compute_revision_diff(base_sections, revision_plan)

        # Write report
        report_path = write_diff_report(job_id, diff_result)

        # Determine status
        has_errors = (
            len(diff_result["unresolvable"]) > 0
            or len(diff_result["conflicts"]) > 0
        )

        if has_errors:
            return {
                "status": "validation_failed",
                "job_id": job_id,
                "message": (
                    f"Revision plan has issues: "
                    f"{len(diff_result['unresolvable'])} unresolvable change(s), "
                    f"{len(diff_result['conflicts'])} conflict(s). "
                    f"Fix revision_plan.json and call again."
                ),
                "diff_report_path": report_path,
                "total_changes": diff_result["total_changes"],
                "valid_changes": diff_result["valid_changes"],
                "unresolvable": diff_result["unresolvable"],
                "conflicts": diff_result["conflicts"],
            }

        return {
            "status": "ok",
            "job_id": job_id,
            "message": (
                f"Revision plan validated: {diff_result['valid_changes']}/"
                f"{diff_result['total_changes']} changes are valid. "
                f"You can now call submit_and_publish_report."
            ),
            "diff_report_path": report_path,
            "preview": diff_result["preview"],
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


def preview_revision_diff(job_id: str) -> dict:
    """Preview the diff that revision_plan.json would produce (read-only).

    Does NOT modify state or apply any changes. Use this to inspect
    what the revision would do before committing.
    """
    import json

    try:
        run_dir = WORKFLOW_RUNS_DIR / job_id

        sections_path = run_dir / "base_document_sections.json"
        plan_path = run_dir / "revision_plan.json"

        if not sections_path.exists():
            return {"status": "error", "message": "base_document_sections.json not found."}
        if not plan_path.exists():
            return {"status": "error", "message": "revision_plan.json not found."}

        with open(sections_path, encoding="utf-8") as f:
            base_sections = json.load(f)
        with open(plan_path, encoding="utf-8") as f:
            revision_plan = json.load(f)

        from report_workflow.nodes.base_document_diff import compute_revision_diff

        diff_result = compute_revision_diff(base_sections, revision_plan)

        return {
            "status": "ok",
            "job_id": job_id,
            "total_changes": diff_result["total_changes"],
            "valid_changes": diff_result["valid_changes"],
            "unresolvable": diff_result["unresolvable"],
            "conflicts": diff_result["conflicts"],
            "preview": diff_result["preview"],
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}
