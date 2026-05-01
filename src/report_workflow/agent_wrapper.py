"""Agent wrapper entry points for the 4-step report workflow.

Step 1: start_report_task        -> Prepare deterministic artifacts + task briefs
Step 2: submit_claim_matrix      -> Validate claim_matrix.json (agent produces this)
Step 3: submit_outline           -> Validate outline.json (agent produces this)
Step 4: submit_drafts            -> Validate section_drafts/*.md + sentence_map.jsonl
Step 5: submit_and_publish_report -> Full validate + render pipeline

The 4-step split (Steps 2-4) allows the agent to work on each artifact
independently, checkpointing after each step. This prevents context window
exhaustion that occurs when the agent must produce all artifacts in a single
conversation turn.

Legacy 2-step workflow (start + submit_and_publish) still works; the agent
simply skips Steps 2-4 and goes directly from Step 1 to Step 5.
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
from report_workflow.state import run_dir_for
from report_workflow.runtime_support import load_jsonl
from report_workflow.artifact_contract import remap_evidence_ids
from report_workflow.config import load_config, save_feature_flag
from report_workflow.preflight import discover_features, check_preflight


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

        # ---- Build pending_installs list ----
        # These are things the agent can install with user's permission
        pending_installs = []

        # Core packages
        if not preflight.ok:
            pending_installs.append({
                "name": "Python package dependencies",
                "description": "Install required Python packages for report_workflow",
                "command": "pip install -r requirements.txt",
                "severity": "required",  # Cannot proceed without this
                "auto_installable": True,
            })

        # External tools from preflight
        seen_commands = set()
        for tw in preflight.external_tool_warnings:
            pending_installs.append({
                "name": tw["tool"],
                "description": tw["description"],
                "command": tw["install_command"],
                "severity": tw["severity"],  # "critical" or "optional"
                "auto_installable": tw["tool"] != "pandoc",  # pandoc needs system install
            })
            seen_commands.add(tw["install_command"])

        # Optional packages from feature discovery (skip already-added tools)
        for f in discovery.features:
            if not f.ready and f.install_commands:
                for cmd in f.install_commands:
                    if cmd in seen_commands:
                        continue  # Already added from preflight
                    if cmd.startswith("pip ") or cmd.startswith("npm "):
                        pending_installs.append({
                            "name": f.name,
                            "description": f.description,
                            "command": cmd,
                            "severity": "optional",
                            "auto_installable": True,
                            "feature_id": f.feature_id,
                        })
                        seen_commands.add(cmd)

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
            "required_preflight_decisions": _required_preflight_decision_shape(
                pending_installs, ask_user
            ),
            "feature_discovery": features_dict,
            "config_summary": cfg.as_env_summary(),
            "agent_should_ask_user": ask_user,
            "preflight": preflight.as_dict(),
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}


def _pending_preflight_installs(preflight, discovery) -> list[dict]:
    pending_installs = []
    if not preflight.ok:
        pending_installs.append({
            "name": "python_packages",
            "description": "Required Python packages are missing: "
            + ", ".join(preflight.missing_packages),
            "command": "pip install -r requirements.txt",
            "severity": "required",
            "auto_installable": True,
        })

    seen_commands = set()
    for warning in preflight.external_tool_warnings:
        pending_installs.append({
            "name": warning["tool"],
            "description": warning["description"],
            "command": warning["install_command"],
            "severity": warning["severity"],
            "auto_installable": warning["tool"] != "pandoc",
        })
        seen_commands.add(warning["install_command"])

    for feature in discovery.features:
        if feature.ready or not feature.install_commands:
            continue
        for command in feature.install_commands:
            if command in seen_commands:
                continue
            if command.startswith(("pip ", "npm ")):
                pending_installs.append({
                    "name": feature.name,
                    "description": feature.description,
                    "command": command,
                    "severity": "optional",
                    "auto_installable": True,
                    "feature_id": feature.feature_id,
                })
                seen_commands.add(command)

    return pending_installs


def _feature_by_id(discovery, feature_id: str):
    for feature in discovery.features:
        if feature.feature_id == feature_id:
            return feature
    return None


INSTALL_DECISIONS = {"install", "installed", "skip", "decline", "accept_degraded"}
FEATURE_DECISIONS = {"enable", "enabled", "disable", "disabled", "skip", "decline"}


def _preflight_item_key(item: dict) -> str:
    return str(
        item.get("feature_id")
        or item.get("tool")
        or item.get("name")
        or item.get("command")
        or "unknown"
    ).strip()


def _required_preflight_decision_shape(pending_installs: list[dict], ask_user: list[dict]) -> dict:
    return {
        "confirmed_by_user": True,
        "install_decisions": {
            _preflight_item_key(item): "install|installed|skip|decline|accept_degraded"
            for item in pending_installs
        },
        "feature_decisions": {
            str(item.get("feature_id")): "enable|disable|skip|decline"
            for item in ask_user
            if item.get("feature_id")
        },
    }


def _validate_preflight_decisions(
    decisions: dict | None,
    pending_installs: list[dict],
    ask_user: list[dict],
    *,
    cfg,
    allow_degraded_render: bool,
) -> list[str]:
    """Require a structured user-confirmation record before workflow start."""
    issues: list[str] = []
    if not isinstance(decisions, dict):
        return ["missing preflight_decisions; call check_setup and record the user's choices"]
    if decisions.get("confirmed_by_user") is not True:
        issues.append("preflight_decisions.confirmed_by_user must be true")

    install_decisions = decisions.get("install_decisions") or {}
    feature_decisions = decisions.get("feature_decisions") or {}
    if not isinstance(install_decisions, dict):
        issues.append("preflight_decisions.install_decisions must be an object")
        install_decisions = {}
    if not isinstance(feature_decisions, dict):
        issues.append("preflight_decisions.feature_decisions must be an object")
        feature_decisions = {}

    for item in pending_installs:
        key = _preflight_item_key(item)
        decision = str(install_decisions.get(key, "")).strip().lower()
        if not decision:
            issues.append(f"missing install decision for {key!r}")
            continue
        if decision not in INSTALL_DECISIONS:
            issues.append(f"invalid install decision for {key!r}: {decision!r}")
            continue
        if item.get("severity") == "critical" and decision in {"skip", "decline"}:
            issues.append(
                f"critical dependency {key!r} cannot be skipped; use 'install' or "
                "'accept_degraded' with allow_degraded_render=True"
            )
        if (
            item.get("severity") == "critical"
            and decision == "accept_degraded"
            and not allow_degraded_render
        ):
            issues.append(
                f"critical dependency {key!r} accepted degraded rendering, but "
                "allow_degraded_render=True was not provided"
            )
        if item.get("severity") == "required" and decision not in {"install", "installed"}:
            issues.append(f"required dependency {key!r} must be installed before starting")

    for item in ask_user:
        feature_id = str(item.get("feature_id") or "").strip()
        if not feature_id:
            continue
        decision = str(feature_decisions.get(feature_id, "")).strip().lower()
        if not decision:
            issues.append(f"missing feature decision for {feature_id!r}")
            continue
        if decision not in FEATURE_DECISIONS:
            issues.append(f"invalid feature decision for {feature_id!r}: {decision!r}")
            continue

        enabled = bool(
            cfg.enable_research if feature_id == "web_research"
            else cfg.enable_notebook_sync if feature_id == "notebook_sync"
            else False
        )
        if decision in {"enable", "enabled"} and not enabled:
            issues.append(
                f"feature {feature_id!r} was approved by the user, but the matching "
                "enable_* flag was not set"
            )
        if decision in {"disable", "disabled", "skip", "decline"} and enabled:
            issues.append(
                f"feature {feature_id!r} was declined by the user, but the matching "
                "enable_* flag is true"
            )

    return issues


def start_report_task(
    prompt: str,
    source_files: list[str],
    output_dir: str | None = None,
    report_profile: str | None = None,
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
        pending_installs = _pending_preflight_installs(preflight, discovery)
        ask_user = discovery.agent_should_ask_user

        decision_issues = _validate_preflight_decisions(
            preflight_decisions,
            pending_installs,
            ask_user,
            cfg=cfg,
            allow_degraded_render=allow_degraded_render,
        )
        if not preflight_confirmed:
            decision_issues.insert(0, "preflight_confirmed must be true after user confirmation")
        if decision_issues:
            return {
                "status": "needs_user_decision",
                "message": (
                    "Call check_setup(), ask the user about every pending install "
                    "and optional integration, then call start_report_task again "
                    "with preflight_confirmed=True, selected feature flags, and "
                    "a complete preflight_decisions record."
                ),
                "pending_installs": pending_installs,
                "agent_should_ask_user": ask_user,
                "decision_issues": decision_issues,
                "required_preflight_decisions": _required_preflight_decision_shape(
                    pending_installs, ask_user
                ),
                "feature_discovery": discovery.as_dict(),
                "config_summary": cfg.as_env_summary(),
                "preflight": preflight.as_dict(),
            }

        critical_installs = [
            item for item in pending_installs if item.get("severity") == "critical"
        ]
        if critical_installs and not allow_degraded_render:
            return {
                "status": "needs_user_decision",
                "message": (
                    "Critical render dependencies are missing. Install them before starting, "
                    "or explicitly set allow_degraded_render=True after the user accepts the "
                    "lower-quality fallback."
                ),
                "pending_installs": critical_installs,
                "feature_discovery": discovery.as_dict(),
                "config_summary": cfg.as_env_summary(),
                "preflight": preflight.as_dict(),
            }

        research_feature = _feature_by_id(discovery, "web_research")
        if cfg.enable_research and research_feature and not research_feature.ready:
            return {
                "status": "needs_user_decision",
                "message": "Web Research was enabled but no research backend/API key is ready.",
                "agent_should_ask_user": ask_user,
                "feature_discovery": discovery.as_dict(),
                "config_summary": cfg.as_env_summary(),
            }

        notebook_feature = _feature_by_id(discovery, "notebook_sync")
        if cfg.enable_notebook_sync:
            if notebook_feature and not notebook_feature.ready:
                return {
                    "status": "needs_user_decision",
                    "message": "NotebookLM sync was enabled but notebooklm-py is not installed.",
                    "agent_should_ask_user": ask_user,
                    "feature_discovery": discovery.as_dict(),
                    "config_summary": cfg.as_env_summary(),
                }
            if not cfg.notebooklm_notebook_id:
                return {
                    "status": "needs_user_decision",
                    "message": (
                        "NotebookLM sync was enabled but notebooklm_notebook_id was not provided. "
                        "Ask the user for the notebook URL or ID."
                    ),
                    "agent_should_ask_user": ask_user,
                    "feature_discovery": discovery.as_dict(),
                    "config_summary": cfg.as_env_summary(),
                }

        state = prepare_workflow(
            prompt,
            source_files,
            output_dir,
            report_profile=report_profile,
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

        warnings = state.runtime.get("warnings", [])

        if state.status == "awaiting_agent_artifacts":
            # Build message with feature status so the agent cannot miss it.
            msg_lines = [
                "Agent work required. Read task briefs at: "
                + str(Path(state.runtime.get("agent_tasks_dir") or (run_dir_for(state) / "agent_tasks"))),
                "",
                "Submit artifacts step-by-step:",
                "  1. Create claim_matrix.json, then call submit_claim_matrix",
                "  2. Create outline.json, then call submit_outline",
                "  3. Create section_drafts/*.md + sentence_map.jsonl, then call submit_drafts",
                "  4. Call submit_and_publish_report to render the final DOCX",
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


def submit_drafts(job_id: str, workspace_root: str | None = None) -> dict:
    """Step 4: Validate section_drafts/*.md and sentence_map.jsonl.

    Call this after creating all section draft files and sentence_map.jsonl.
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


def submit_and_publish_report(job_id: str, workspace_root: str | None = None) -> dict:
    """Step 5: Run full validation pipeline and render the final DOCX.

    This can be called after all 3 steps, or directly after start_report_task
    if the Agent created all artifacts in one shot (legacy 2-step mode).
    """
    try:
        state = validate_workflow(job_id, workspace_root=workspace_root)
        state = render_workflow(job_id, workspace_root=workspace_root)
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
                "  submit_claim_matrix -> submit_outline -> submit_drafts -> submit_and_publish_report"
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
