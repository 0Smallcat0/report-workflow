"""Agent wrapper entry points for the controlled report workflow.

Step 1: start_report_task        -> Prepare deterministic artifacts + task briefs
Controlled: get_controlled_next_action / submit_controlled_action
Optional: lint_agent_artifacts   -> Read-only artifact shape and ID lint report
Publish: submit_and_publish_report -> Full validate + render pipeline

The controlled harness is the recommended public surface for staged authoring.
Legacy direct submit helpers remain for compatibility, but skill docs should
route agents through submit_controlled_action.
"""

from pathlib import Path

from report_workflow.run_workflow import (
    prepare_workflow,
    validate_workflow,
    render_workflow,
    validate_step_claim_matrix,
    validate_step_outline,
    validate_step_drafts,
)
from report_workflow.errors import AgentWorkRequired, QAHardBlockError
from report_workflow.state import ReportState, run_dir_for
from report_workflow.runtime_support import load_jsonl
from report_workflow.artifact_contract import remap_evidence_ids
from report_workflow.artifact_lint import lint_agent_artifacts as run_artifact_lint
from report_workflow.automation_harness import (
    get_controlled_next_action as _get_controlled_next_action,
    load_or_create_manifest,
    run_controlled_stage,
)
from report_workflow.engineering_audit import run_engineering_audit as run_engineering_lab_audit
from report_workflow.config import load_config
from report_workflow.preflight import discover_features, check_preflight
from report_workflow.preflight_decisions import (
    evaluate_preflight_start,
    pending_preflight_installs,
    required_preflight_decision_shape,
)

VALID_SOURCE_FILE_ROLES = {"source_data", "base_document"}


def _parse_source_file_string(value: str) -> tuple[str, str]:
    """Parse an optional PATH:ROLE suffix without breaking Windows paths."""
    if value.rsplit(":", 1)[-1] in VALID_SOURCE_FILE_ROLES:
        path, role = value.rsplit(":", 1)
        return path.strip(), role
    return value, "source_data"


def _normalize_source_files(source_files: list[str | dict]) -> tuple[list[str], dict[str, str]]:
    """Normalize legacy and structured agent-skill source file inputs.

    Supported forms:
      - "path/to/source.pdf"
      - "path/to/base.docx:base_document"
      - {"path": "path/to/base.docx", "role": "base_document"}
    """
    normalized_files: list[str] = []
    artifact_role_map: dict[str, str] = {}

    for index, item in enumerate(source_files or []):
        if isinstance(item, str):
            path, role = _parse_source_file_string(item)
        elif isinstance(item, dict):
            path = str(item.get("path") or item.get("file_path") or "").strip()
            role = str(
                item.get("role")
                or item.get("artifact_role")
                or item.get("source_role")
                or "source_data"
            ).strip()
        else:
            raise ValueError(
                f"source_files[{index}] must be a string or object with path/role"
            )

        if not path:
            raise ValueError(f"source_files[{index}] is missing a path")
        if role not in VALID_SOURCE_FILE_ROLES:
            raise ValueError(
                f"source_files[{index}] has invalid role {role!r}; "
                f"expected one of {sorted(VALID_SOURCE_FILE_ROLES)}"
            )

        normalized_files.append(path)
        artifact_role_map[path] = role
        artifact_role_map[str(Path(path).name)] = role
        try:
            artifact_role_map[str(Path(path).expanduser().resolve())] = role
        except OSError:
            pass

    return normalized_files, artifact_role_map


def check_setup() -> dict:
    """Pre-flight environment check; call BEFORE start_report_task.

    Returns:
      - ``pending_installs``: dependencies the agent should install (with user consent).
        The agent MUST ask the user before running any install command.
        After installing, re-run ``check_setup()`` to verify.
      - ``agent_should_ask_user``: optional features to ask the user about.
        Some require additional user input (API keys, notebook URLs).
      - ``message``: human-readable summary of the entire setup state.

    Workflow:
      1. Agent calls check_setup()
      2. If pending_installs is non-empty, show user, ask to install, run commands
      3. Re-run check_setup() to verify installs succeeded
      4. Read agent_should_ask_user, ask user about features, collect inputs
      5. Call start_report_task with the user's chosen flags
    """
    try:
        cfg = load_config()
        preflight = check_preflight()
        discovery = discover_features(
            enable_research=cfg.enable_research,
            enable_notebook_sync=cfg.enable_notebook_sync,
        )

        ask_user = discovery.agent_should_ask_user
        features_dict = discovery.as_dict()

        pending_installs = pending_preflight_installs(preflight, discovery)

        lines = ["Report Workflow setup check"]
        if not preflight.ok:
            lines.append("Missing required Python packages: " + ", ".join(preflight.missing_packages))
        else:
            lines.append("Core Python dependencies are available.")

        installable = [p for p in pending_installs if p["auto_installable"]]
        manual_only = [p for p in pending_installs if not p["auto_installable"]]
        if installable or manual_only:
            lines.append("")
            lines.append("Pending dependencies:")
            for i, inst in enumerate(installable, 1):
                lines.append(f"  {i}. [{inst['severity']}] {inst['name']}")
                lines.append(f"     {inst['description']}")
                lines.append(f"     Command: {inst['command']}")
            for inst in manual_only:
                lines.append(f"  [manual] {inst['name']}: {inst['description']}")
                lines.append(f"     Command: {inst['command']}")
        else:
            lines.append("No dependency installs are pending.")

        lines.append("")
        if ask_user:
            lines.append("Optional feature decisions:")
            for i, item in enumerate(ask_user, 1):
                lines.append(f"  {i}. {item['question']}")
                for inp in item.get("requires_user_input", []):
                    lines.append(f"        - {inp['hint']}")
                    if "example" in inp:
                        lines.append(f"          Example: {inp['example']}")
                for cmd in item.get("setup_commands", []):
                    lines.append(f"     Setup: {cmd}")
                if item.get("ask_every_time"):
                    lines.append("     Ask every time before enabling.")
                lines.append(f"     Action: {item['action']}")
                lines.append("")
        else:
            lines.append("No optional feature decisions are pending.")


        return {
            "status": "ready" if preflight.ok and not manual_only else (
                "needs_install" if pending_installs else "ready"
            ),
            "message": "\n".join(lines),
            "pending_installs": pending_installs,
            "required_preflight_decisions": required_preflight_decision_shape(
                pending_installs, ask_user
            ),
            "feature_discovery": features_dict,
            "config_summary": cfg.as_env_summary(),
            "agent_should_ask_user": ask_user,
            "preflight": preflight.as_dict(),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def start_report_task(
    prompt: str,
    source_files: list[str | dict],
    output_dir: str | None = None,
    report_profile: str | None = None,
    task_intent: str = "new_draft",
    title: str | None = None,
    author_block: str | None = None,
    affiliation_block: str | None = None,
    correspondence: str | None = None,
    keywords: list[str] | None = None,
    template_fields: dict | None = None,
    project_identity: dict | None = None,
    enable_research: bool | None = None,
    enable_notebook_sync: bool | None = None,
    notebooklm_notebook_id: str | None = None,
    notebooklm_storage_path: str | None = None,
    reference_docx: str | None = None,
    preflight_confirmed: bool = False,
    preflight_decisions: dict | None = None,
    allow_degraded_render: bool = False,
) -> dict:
    """Step 1: Start the report generation workflow.

    Creates deterministic artifacts (evidence ledger, blueprint) and
    generates task briefs for the Agent to complete.

    **Required**: Call ``check_setup()`` first to verify dependencies
    and ask the user about optional features. ``preflight_confirmed=True``
    is not sufficient on its own; pass ``preflight_decisions`` with an
    explicit record of the user's install and feature choices.

    Configuration is loaded from multiple sources (highest priority wins):
      1. Function parameters passed here
      2. Environment variables
      3. .env file in project root
      4. workflow_config.yaml in project root
    """
    try:
        normalized_source_files, artifact_role_map = _normalize_source_files(source_files)

        # ---- Load merged configuration ----
        cfg = load_config(
            enable_research=enable_research,
            enable_notebook_sync=enable_notebook_sync,
            notebooklm_notebook_id=notebooklm_notebook_id,
            notebooklm_storage_path=notebooklm_storage_path,
        )

        preflight = check_preflight()
        discovery = discover_features(
            enable_research=cfg.enable_research,
            enable_notebook_sync=cfg.enable_notebook_sync,
        )
        readiness = evaluate_preflight_start(
            preflight=preflight,
            discovery=discovery,
            cfg=cfg,
            preflight_decisions=preflight_decisions,
            preflight_confirmed=preflight_confirmed,
            allow_degraded_render=allow_degraded_render,
        )
        if not readiness["ready"]:
            return {
                "status": "needs_user_decision",
                "message": readiness["message"],
                "pending_installs": readiness.get("pending_installs", []),
                "agent_should_ask_user": readiness.get("agent_should_ask_user", []),
                "decision_issues": readiness.get("decision_issues", []),
                "required_preflight_decisions": readiness.get("required_preflight_decisions", {}),
                "feature_discovery": discovery.as_dict(),
                "config_summary": cfg.as_env_summary(),
                "preflight": preflight.as_dict(),
            }

        state = prepare_workflow(
            prompt,
            normalized_source_files,
            output_dir,
            report_profile=report_profile,
            intent=task_intent,
            artifact_role_map=artifact_role_map,
            front_matter={
                key: value for key, value in {
                    "title": title,
                    "author_block": author_block,
                    "affiliation_block": affiliation_block,
                    "correspondence": correspondence,
                    "keywords": keywords,
                    "template_fields": template_fields,
                }.items()
                if value
            },
            project_identity=project_identity,
            reference_docx=reference_docx,
            enable_research=cfg.enable_research,
            enable_notebook_sync=cfg.enable_notebook_sync,
            notebooklm_notebook_id=cfg.notebooklm_notebook_id,
            notebooklm_storage_path=cfg.notebooklm_storage_path,
        )

        warnings = state.runtime.get("warnings", [])
        controlled_action = None
        if state.status == "awaiting_agent_artifacts":
            _controlled_state, controlled_run_dir, _manifest = load_or_create_manifest(
                state.job_id,
                workspace_root=state.output.get("workspace_root"),
            )
            controlled_action = _get_controlled_next_action(
                state.job_id,
                workspace_root=state.output.get("workspace_root"),
            )

        if state.status == "awaiting_agent_artifacts":
            # Build message with feature status so the agent cannot miss it.
            msg_lines = [
                "Agent work required. Read task briefs at: "
                + str(Path(state.runtime.get("agent_tasks_dir") or (run_dir_for(state) / "agent_tasks"))),
                "",
                "Recommended controlled workflow:",
                "  1. Call get_controlled_next_action to get the current stage and allowed write paths",
                "  2. Write only those allowed paths, then call submit_controlled_action",
                "  3. Repeat until status is completed",
                "",
            ]

            # Embed active features in message
            active = [f for f in discovery.features if f.enabled and f.ready]
            inactive_ready = [f for f in discovery.features if not f.enabled and f.ready]

            if active:
                msg_lines.append("Active optional features: " + ", ".join(f.name for f in active))
            if inactive_ready:
                msg_lines.append(
                    "Optional features available but disabled: "
                    + ", ".join(f.name for f in inactive_ready)
                )

            result = {
                "status": "awaiting_agent_artifacts",
                "job_id": state.job_id,
                "message": "\n".join(msg_lines),
                "controlled_next_action": controlled_action,
                "harness_manifest_path": (
                    controlled_action.get("harness_manifest_path")
                    if isinstance(controlled_action, dict)
                    else str(controlled_run_dir / "harness_manifest.json")
                ),
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



def submit_claim_matrix(job_id: str, workspace_root: str | None = None) -> dict:
    """Step 2: Validate the Agent-authored claim_matrix.json.

    Call this after creating claim_matrix.json in the agent_tasks directory.
    This validates structure and evidence linkage, then checkpoints.
    """
    try:
        state = validate_step_claim_matrix(job_id, workspace_root=workspace_root)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 1/3 complete: claim_matrix.json validated.\n"
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


def submit_outline(job_id: str, workspace_root: str | None = None) -> dict:
    """Step 3: Validate the Agent-authored outline.json.

    Call this after creating outline.json. Requires claim_matrix to be validated first.
    """
    try:
        state = validate_step_outline(job_id, workspace_root=workspace_root)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 2/3 complete: outline.json validated.\n"
                "Next: Create structured_drafts.json or section_drafts/*.md + sentence_map.jsonl, "
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


def submit_drafts(job_id: str, workspace_root: str | None = None) -> dict:
    """Step 4: Validate structured_drafts or canonical draft artifacts.

    Call this after creating structured_drafts.json, or all section draft files
    and sentence_map.jsonl.
    Requires both claim_matrix and outline to be validated first.
    """
    try:
        state = validate_step_drafts(job_id, workspace_root=workspace_root)
        return {
            "status": state.status,
            "job_id": state.job_id,
            "message": (
                "Step 3/3 complete: section drafts validated.\n"
                "All artifacts ready. Call submit_and_publish_report to render."
            ),
        }
    except AgentWorkRequired as e:
        return {
            "status": "validation_failed",
            "job_id": job_id,
            "message": "structured_drafts.json or section drafts/sentence_map are missing.",
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


def lint_agent_artifacts(job_id: str, workspace_root: str | None = None) -> dict:
    """Read-only lint of agent-authored artifacts before full validation."""
    try:
        state = ReportState.resume(job_id, workspace_root=workspace_root)
        report = run_artifact_lint(state)
        return {
            "status": "ok" if report.get("error_count", 0) == 0 else "issues_found",
            "job_id": job_id,
            "report_path": report.get("report_path", ""),
            "issue_count": report.get("issue_count", 0),
            "error_count": report.get("error_count", 0),
            "warning_count": report.get("warning_count", 0),
            "issues": report.get("issues", []),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def run_engineering_audit(job_id: str, workspace_root: str | None = None) -> dict:
    """Read-only engineering lab unit/calculation audit."""
    try:
        state = ReportState.resume(job_id, workspace_root=workspace_root)
        report = run_engineering_lab_audit(state)
        return {
            "status": "ok" if report.get("warning_count", 0) == 0 else "review_recommended",
            "job_id": job_id,
            "report_path": report.get("report_path", ""),
            "measurement_count": report.get("measurement_count", 0),
            "table_evidence_count": report.get("table_evidence_count", 0),
            "calculation_count": report.get("calculation_count", 0),
            "issue_count": report.get("issue_count", 0),
            "warning_count": report.get("warning_count", 0),
            "info_count": report.get("info_count", 0),
            "issues": report.get("issues", []),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_and_publish_report(
    job_id: str,
    workspace_root: str | None = None,
    reference_docx: str | None = None,
) -> dict:
    """Step 5: Run full validation pipeline and render the final DOCX.

    This can be called after all 3 steps, or directly after start_report_task
    if the Agent created all artifacts in one shot (legacy 2-step mode).

    Args:
        reference_docx: optional user-supplied .docx template; the rendered
            document follows its styles, margins, and header/footer.
    """
    try:
        state = validate_workflow(job_id, workspace_root=workspace_root)
        state = render_workflow(
            job_id, workspace_root=workspace_root, reference_docx=reference_docx
        )
        warnings = state.runtime.get("warnings", [])
        result = {
            "status": state.status,
            "job_id": state.job_id,
            "final_docx_path": state.output.get("final_docx_path", ""),
            "published_report_path": state.output.get("published_report_path", ""),
            "workflow_success": bool(state.output.get("workflow_success") and state.status == "completed"),
            "renderer_used": state.output.get("renderer_used", "unknown"),
            "post_render_layout_manifest_path": state.output.get("post_render_layout_manifest_path", ""),
            "final_qa_summary_path": state.output.get("final_qa_summary_path", ""),
            "final_qa_summary_md_path": state.output.get("final_qa_summary_md_path", ""),
            "scholarly_quality_report_path": state.output.get("scholarly_quality_report_path", ""),
            "scholarly_quality_report_md_path": state.output.get("scholarly_quality_report_md_path", ""),
            "figure_visual_quality_report_path": state.output.get("figure_visual_quality_report_path", ""),
            "template_style_map_path": state.output.get("template_style_map_path", ""),
            "template_style_map_md_path": state.output.get("template_style_map_md_path", ""),
            "template_field_fill_report_path": state.output.get("template_field_fill_report_path", ""),
            "template_field_fill_report_md_path": state.output.get("template_field_fill_report_md_path", ""),
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
                "Use get_controlled_next_action, write only the allowed paths, "
                "then call submit_controlled_action."
            ),
            "missing_artifacts": e.missing_artifacts,
        }
    except QAHardBlockError as e:
        run_dir = run_dir_for(job_id, workspace_root=workspace_root)
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
        run_dir = run_dir_for(job_id, workspace_root=workspace_root)
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
    query: str | None = None,
    offset: int = 0,
    limit: int = 20,
    workspace_root: str | None = None,
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
        run_dir = run_dir_for(job_id, workspace_root=workspace_root)
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
        elif query:
            ranked = _rank_evidence_entries(all_entries, query)
            limit = min(limit, 50)
            page = ranked[offset:offset + limit]
            return {
                "status": "ok",
                "job_id": job_id,
                "total_entries": total,
                "query": query,
                "total_matches": len(ranked),
                "offset": offset,
                "limit": limit,
                "returned": len(page),
                "entries": [entry for _score, entry in page],
                "has_more": (offset + limit) < len(ranked),
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
    except FileNotFoundError:
        return {
            "status": "error",
            "message": f"No local workflow run found for job {job_id}",
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def _rank_evidence_entries(entries: list[dict], query: str) -> list[tuple[float, dict]]:
    import re
    import unicodedata

    normalized_query = unicodedata.normalize("NFKC", query or "").casefold()
    terms = set(re.findall(r"[a-z0-9_]{2,}", normalized_query))
    cjk_chars = re.findall(r"[\u3400-\u9fff]", normalized_query)
    cjk_bigrams = {
        "".join(cjk_chars[index:index + 2])
        for index in range(max(0, len(cjk_chars) - 1))
    }

    ranked: list[tuple[float, dict]] = []
    for entry in entries:
        haystack = " ".join(
            str(entry.get(key, ""))
            for key in (
                "evidence_id",
                "content",
                "quote",
                "source_file_name",
                "source_role",
                "evidence_type",
            )
        )
        normalized_haystack = unicodedata.normalize("NFKC", haystack).casefold()
        score = 0.0
        score += sum(1.0 for term in terms if term in normalized_haystack)
        score += sum(1.5 for gram in cjk_bigrams if gram in normalized_haystack)
        if normalized_query and normalized_query in normalized_haystack:
            score += 3.0
        if score > 0:
            ranked.append((score, entry))

    ranked.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("evidence_id", "")),
        )
    )
    return ranked


def remap_agent_artifacts(
    job_id: str,
    previous_job_id: str,
    write: bool = False,
    workspace_root: str | None = None,
) -> dict:
    """Remap evidence IDs in agent artifacts from a previous run to this run."""
    try:
        return remap_evidence_ids(job_id, previous_job_id, write=write, workspace_root=workspace_root)
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def submit_revision_plan(job_id: str, workspace_root: str | None = None) -> dict:
    """Validate a revision_plan.json for revise_existing workflows.

    Pre-validates all changes against the base document, checks for
    conflicts and unresolvable changes, and returns a diff preview.
    Call this before submit_and_publish_report for revision workflows.
    """
    import json

    try:
        run_dir = run_dir_for(job_id, workspace_root=workspace_root)

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
            # This validates the plan, not the job. A revision still needs the
            # same claim matrix, outline, section drafts, and sentence map as a
            # new draft, and promising publication here sent authors into three
            # successive rejections that each revealed one more requirement.
            # The controlled router already knows what is outstanding; point at
            # it rather than restating a list that would drift.
            "message": (
                f"Revision plan validated: {diff_result['valid_changes']}/"
                f"{diff_result['total_changes']} changes are valid. "
                f"Call get_controlled_next_action to see what this job still "
                f"needs before submit_and_publish_report."
            ),
            "diff_report_path": report_path,
            "preview": diff_result["preview"],
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


def preview_revision_diff(job_id: str, workspace_root: str | None = None) -> dict:
    """Preview the diff that revision_plan.json would produce (read-only).

    Does NOT modify state or apply any changes. Use this to inspect
    what the revision would do before committing.
    """
    import json

    try:
        run_dir = run_dir_for(job_id, workspace_root=workspace_root)

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


def get_controlled_next_action(job_id: str, workspace_root: str | None = None) -> dict:
    """Return the next controlled authoring stage and its write scope.

    This is the preferred Skill-facing entry point after ``start_report_task``.
    It gives the agent a single current stage, task brief, read-first files,
    allowed write paths, and any repair context from the previous failed
    attempt.
    """
    try:
        return _get_controlled_next_action(job_id, workspace_root=workspace_root)
    except Exception as e:
        return {"status": "failed", "job_id": job_id, "error": str(e)}


def submit_controlled_action(job_id: str, workspace_root: str | None = None) -> dict:
    """Validate the current controlled stage, enforcing harness write scope."""
    validators = {
        "claim_matrix": submit_claim_matrix,
        "outline": submit_outline,
        "drafts": submit_drafts,
        "revision_plan": submit_revision_plan,
        "artifact_lint": lint_agent_artifacts,
        "publish": submit_and_publish_report,
    }
    try:
        return run_controlled_stage(job_id, validators, workspace_root=workspace_root)
    except Exception as e:
        return {"status": "failed", "job_id": job_id, "error": str(e)}
