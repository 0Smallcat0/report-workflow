"""Shared preflight-decision contract for agent and CLI entry points."""
from __future__ import annotations

from typing import Any


INSTALL_DECISIONS = {"install", "installed", "skip", "decline", "accept_degraded"}
FEATURE_DECISIONS = {"enable", "enabled", "disable", "disabled", "skip", "decline"}

#: feature_id in a decision record -> the configuration flag it turns on.
FEATURE_DECISION_FLAGS = {
    "web_research": "enable_research",
    "notebook_sync": "enable_notebook_sync",
}

_ENABLING_DECISIONS = {"enable", "enabled"}
_DISABLING_DECISIONS = {"disable", "disabled", "skip", "decline"}


def feature_flags_from_decisions(
    preflight_decisions: dict | None,
    enable_research: bool | None,
    enable_notebook_sync: bool | None,
) -> tuple[bool | None, bool | None]:
    """Read the user's recorded feature choices as the enable_* flags.

    The record and the flags used to be two independent inputs that had to
    agree, and disagreeing was a hard stop: "feature 'web_research' was
    approved by the user, but the matching enable_* flag was not set". The MCP
    surface exposed no such argument at all, so over MCP an approved feature
    could not be turned on by any means. The recorded decision is now the
    flag. An explicitly passed enable_* still wins, for a caller that means to
    override what was recorded.
    """
    decisions = (preflight_decisions or {}).get("feature_decisions")
    if not isinstance(decisions, dict):
        return enable_research, enable_notebook_sync

    resolved = {"enable_research": enable_research, "enable_notebook_sync": enable_notebook_sync}
    for feature_id, flag in FEATURE_DECISION_FLAGS.items():
        if resolved[flag] is not None:
            continue
        decision = str(decisions.get(feature_id, "")).strip().lower()
        if decision in _ENABLING_DECISIONS:
            resolved[flag] = True
        elif decision in _DISABLING_DECISIONS:
            resolved[flag] = False
    return resolved["enable_research"], resolved["enable_notebook_sync"]


def preflight_item_key(item: dict) -> str:
    return str(
        item.get("feature_id")
        or item.get("tool")
        or item.get("name")
        or item.get("command")
        or "unknown"
    ).strip()


def pending_preflight_installs(preflight, discovery) -> list[dict]:
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


def feature_by_id(discovery, feature_id: str):
    for feature in discovery.features:
        if feature.feature_id == feature_id:
            return feature
    return None


def required_preflight_decision_shape(pending_installs: list[dict], ask_user: list[dict]) -> dict:
    return {
        "confirmed_by_user": True,
        "install_decisions": {
            preflight_item_key(item): "install|installed|skip|decline|accept_degraded"
            for item in pending_installs
        },
        "feature_decisions": {
            str(item.get("feature_id")): "enable|disable|skip|decline"
            for item in ask_user
            if item.get("feature_id")
        },
    }


def validate_preflight_decisions(
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
        return ["missing preflight_decisions; call check_environment and record the user's choices"]
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
        key = preflight_item_key(item)
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
        enabled = bool(
            cfg.enable_research if feature_id == "web_research"
            else cfg.enable_notebook_sync if feature_id == "notebook_sync"
            else False
        )
        if not decision:
            # Silence about an optional connector whose flag is off is not an
            # undecided question — the feature is not going to run. What this
            # gate is for is a feature turning itself on without the user
            # having said so, and it still refuses that, below and here.
            # Demanding the word "skip" for something nobody asked for made
            # the first command of a session fail on a connector that has
            # nothing to do with writing the report.
            if not enabled:
                continue
            issues.append(
                f"feature {feature_id!r} is enabled but the user's decision was "
                "not recorded; call check_environment and record it"
            )
            continue
        if decision not in FEATURE_DECISIONS:
            issues.append(f"invalid feature decision for {feature_id!r}: {decision!r}")
            continue

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


def evaluate_preflight_start(
    *,
    preflight,
    discovery,
    cfg,
    preflight_decisions: dict | None,
    preflight_confirmed: bool,
    allow_degraded_render: bool,
) -> dict[str, Any]:
    """Return one shared readiness decision for report start entry points."""
    pending_installs = pending_preflight_installs(preflight, discovery)
    ask_user = discovery.agent_should_ask_user
    decision_issues = validate_preflight_decisions(
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
            "ready": False,
            "reason": "decision_issues",
            "message": (
                "Call check_environment(), ask the user about every pending install "
                "and optional integration, then start again with selected feature "
                "flags and a complete preflight_decisions record."
            ),
            "pending_installs": pending_installs,
            "agent_should_ask_user": ask_user,
            "decision_issues": decision_issues,
            "required_preflight_decisions": required_preflight_decision_shape(
                pending_installs,
                ask_user,
            ),
        }

    required_installs = [
        item for item in pending_installs if item.get("severity") == "required"
    ]
    if required_installs:
        return {
            "ready": False,
            "reason": "required_dependency_missing",
            "message": (
                "Required dependencies are still missing according to preflight. "
                "Install them and run setup/preflight again before starting."
            ),
            "pending_installs": required_installs,
            "agent_should_ask_user": ask_user,
            "required_preflight_decisions": required_preflight_decision_shape(
                required_installs,
                ask_user,
            ),
        }

    critical_installs = [
        item for item in pending_installs if item.get("severity") == "critical"
    ]
    install_decisions = (
        preflight_decisions.get("install_decisions", {})
        if isinstance(preflight_decisions, dict)
        else {}
    )
    critical_degraded_accepted = all(
        str(install_decisions.get(preflight_item_key(item), "")).strip().lower()
        == "accept_degraded"
        for item in critical_installs
    )
    if critical_installs and (not allow_degraded_render or not critical_degraded_accepted):
        return {
            "ready": False,
            "reason": "critical_render_dependency",
            "message": (
                "Critical render dependencies are missing. Install them before starting, "
                "or explicitly accept lower-quality fallback rendering with "
                "install_decisions set to accept_degraded."
            ),
            "pending_installs": critical_installs,
            "agent_should_ask_user": ask_user,
            "required_preflight_decisions": required_preflight_decision_shape(
                critical_installs,
                ask_user,
            ),
        }

    research_feature = feature_by_id(discovery, "web_research")
    if cfg.enable_research and research_feature and not research_feature.ready:
        return {
            "ready": False,
            "reason": "web_research_not_ready",
            "message": "Web Research was enabled but no research backend/API key is ready.",
            "pending_installs": pending_installs,
            "agent_should_ask_user": ask_user,
            "required_preflight_decisions": required_preflight_decision_shape(
                pending_installs,
                ask_user,
            ),
        }

    notebook_feature = feature_by_id(discovery, "notebook_sync")
    if cfg.enable_notebook_sync:
        if notebook_feature and not notebook_feature.ready:
            return {
                "ready": False,
                "reason": "notebook_sync_not_ready",
                "message": "NotebookLM sync was enabled but notebooklm-py is not installed.",
                "pending_installs": pending_installs,
                "agent_should_ask_user": ask_user,
                "required_preflight_decisions": required_preflight_decision_shape(
                    pending_installs,
                    ask_user,
                ),
            }
        if not cfg.notebooklm_notebook_id:
            return {
                "ready": False,
                "reason": "notebook_id_missing",
                "message": (
                    "NotebookLM sync was enabled but notebooklm_notebook_id was not provided. "
                    "Ask the user for the notebook URL or ID."
                ),
                "pending_installs": pending_installs,
                "agent_should_ask_user": ask_user,
                "required_preflight_decisions": required_preflight_decision_shape(
                    pending_installs,
                    ask_user,
                ),
            }

    return {
        "ready": True,
        "pending_installs": pending_installs,
        "agent_should_ask_user": ask_user,
        "required_preflight_decisions": required_preflight_decision_shape(
            pending_installs,
            ask_user,
        ),
    }
