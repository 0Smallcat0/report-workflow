"""Controlled outer harness for agent-authored report artifacts.

The harness does not generate prose and does not change the core workflow DAG.
It records a per-run manifest, constrains which author-owned artifacts may
change at each stage, and routes validation failures back to the smallest
authoring stage that can repair them.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from .state import ReportState, run_dir_for


MANIFEST_FILENAME = "harness_manifest.json"
MANIFEST_VERSION = 1


STAGE_DEFS: dict[str, dict[str, Any]] = {
    "claim_matrix": {
        "validation_tool": "submit_action",
        "allowed_write_paths": ["claim_matrix.json"],
        "task_brief": "agent_tasks/01_claim_plan.md",
        "read_first_paths": [
            "agent_tasks/01_claim_plan.md",
            "report_spec.json",
            "blueprint.json",
            "evidence_ledger.jsonl",
        ],
    },
    "outline": {
        "validation_tool": "submit_action",
        "allowed_write_paths": ["outline.json"],
        "task_brief": "agent_tasks/02_outline_plan.md",
        "read_first_paths": [
            "agent_tasks/02_outline_plan.md",
            "blueprint.json",
            "claim_matrix.json",
            "figure_recommendations.json",
        ],
    },
    "drafts": {
        "validation_tool": "submit_action",
        "allowed_write_paths": [
            "structured_drafts.json",
            "section_drafts/*.md",
            "section_drafts/figure_plan.json",
            "sentence_map.jsonl",
        ],
        "task_brief": "agent_tasks/03_section_draft.md",
        "read_first_paths": [
            "agent_tasks/03_section_draft.md",
            "blueprint.json",
            "claim_matrix.json",
            "outline.json",
            "evidence_ledger.jsonl",
            "figure_recommendations.json",
        ],
    },
    "revision_plan": {
        "validation_tool": "submit_action",
        "allowed_write_paths": ["revision_plan.json"],
        "task_brief": "agent_tasks/04_revision_plan.md",
        "read_first_paths": [
            "agent_tasks/04_revision_plan.md",
            "base_document_sections.json",
            "claim_matrix.json",
            "outline.json",
        ],
    },
    "artifact_lint": {
        "validation_tool": "lint_agent_artifacts",
        "allowed_write_paths": [],
        "task_brief": "",
        "read_first_paths": [
            "claim_matrix.json",
            "outline.json",
            "structured_drafts.json",
            "section_drafts",
            "sentence_map.jsonl",
            "revision_plan.json",
        ],
    },
    "publish": {
        "validation_tool": "publish_report",
        "allowed_write_paths": [],
        "task_brief": "",
        "read_first_paths": [
            "qa_summary.json",
            "artifact_lint_report.json",
            "factuality_report.json",
            "final_qa_summary.json",
        ],
    },
}


AUTHOR_OWNED_PATTERNS = [
    "claim_matrix.json",
    "outline.json",
    "structured_drafts.json",
    "section_drafts/*.md",
    "section_drafts/figure_plan.json",
    "sentence_map.jsonl",
    "revision_plan.json",
]


TARGET_NODE_TO_STAGE = {
    "AGENT_ARTIFACTS": "claim_matrix",
    "CLAIM_PLAN": "claim_matrix",
    "OUTLINE_PLAN": "outline",
    "SECTION_DRAFT": "drafts",
    "CONTENT_ASSEMBLY": "drafts",
    "MERGE_DRAFT": "drafts",
    "CITATION_BIND": "drafts",
    "EVIDENCE_AND_CLAIMS": "drafts",
    "FIGURE_PLAN_AUDIT": "drafts",
    "FIGURE_BUILD": "drafts",
    "FIGURE_QUALITY": "drafts",
    "REVISION_APPLY": "revision_plan",
}

REPAIRLESS_STATUS = "blocked_non_author_repair"


def _now() -> str:
    return datetime.now().isoformat()


def _rel(path: Path, run_dir: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _matches(rel_path: str, patterns: list[str]) -> bool:
    lowered = rel_path.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in patterns)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_author_owned(run_dir: Path) -> dict[str, str | None]:
    """Return hashes for all author-owned files known to the harness."""
    snapshot: dict[str, str | None] = {}
    for pattern in AUTHOR_OWNED_PATTERNS:
        if _has_glob(pattern):
            for path in sorted(run_dir.glob(pattern)):
                if path.is_file():
                    snapshot[_rel(path, run_dir)] = _hash_file(path)
            continue
        path = run_dir / pattern
        snapshot[pattern] = _hash_file(path) if path.exists() and path.is_file() else None
    return dict(sorted(snapshot.items()))


def _is_trusted_preexisting_artifact(state: ReportState, run_dir: Path, rel_path: str) -> bool:
    """Return true for deterministic workflow artifacts created before authoring.

    The harness normally treats future-stage author-owned files as absent on a
    new manifest so agents cannot preload later artifacts before their stage.
    The starter figure plan is different: it is generated by the deterministic
    prepare pipeline from figure recommendations, then optionally edited during
    the drafts stage.  Baseline only that exact generated file; preserved or
    manually preexisting plans still count as out-of-scope author changes.
    """
    if rel_path != "section_drafts/figure_plan.json":
        return False

    expected = state.output.get("auto_figure_plan_path")
    if not expected:
        return False

    path = run_dir / rel_path
    try:
        same_path = path.resolve() == Path(expected).expanduser().resolve()
    except OSError:
        return False
    if not same_path or not path.exists() or not path.is_file():
        return False

    info = state.runtime.get("auto_figure_plan", {})
    if not isinstance(info, dict) or info.get("status") != "generated":
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("generated_by") == "report_workflow.nodes.agent_tasks.auto_figure_plan"
    )


def _initial_observed_hashes(state: ReportState, run_dir: Path, first_stage: str) -> dict[str, str | None]:
    """Create a strict baseline for a newly controlled run.

    Current-stage files may already exist and are treated as the first stage's
    work. Future-stage files are intentionally baselined as absent so first
    submission reports them as out-of-scope instead of silently adopting them.
    """
    snapshot = _snapshot_author_owned(run_dir)
    allowed = STAGE_DEFS[first_stage]["allowed_write_paths"]
    observed: dict[str, str | None] = {}
    for rel_path, digest in snapshot.items():
        if (
            digest is not None
            and not _matches(rel_path, allowed)
            and not _is_trusted_preexisting_artifact(state, run_dir, rel_path)
        ):
            observed[rel_path] = None
        else:
            observed[rel_path] = digest
    return dict(sorted(observed.items()))


def _changed_paths(before: dict[str, str | None], after: dict[str, str | None]) -> list[str]:
    keys = sorted(set(before) | set(after))
    return [key for key in keys if before.get(key) != after.get(key)]


def stage_order_for_state(state: ReportState) -> list[str]:
    order = ["claim_matrix", "outline", "drafts"]
    if state.spec.get("task_intent") == "revise_existing":
        order.append("revision_plan")
    order.extend(["artifact_lint", "publish"])
    return order


def manifest_path_for(run_dir: Path) -> Path:
    return run_dir / MANIFEST_FILENAME


def _stage_manifest(stage: str) -> dict[str, Any]:
    definition = STAGE_DEFS[stage]
    return {
        "status": "pending",
        "attempts": 0,
        "validation_tool": definition["validation_tool"],
        "allowed_write_paths": list(definition["allowed_write_paths"]),
        "task_brief_path": "",
        "read_first_paths": [],
        "evidence_paths": [],
        "last_error": None,
        "passed_hashes": {},
    }


def _absolute_existing_or_planned(run_dir: Path, rel_path: str) -> str:
    return str(run_dir / rel_path) if rel_path else ""


def _hydrate_stage_paths(manifest: dict[str, Any], run_dir: Path) -> None:
    for stage in manifest.get("stage_order", []):
        definition = STAGE_DEFS[stage]
        entry = manifest["stages"].setdefault(stage, _stage_manifest(stage))
        entry["validation_tool"] = definition["validation_tool"]
        entry["allowed_write_paths"] = list(definition["allowed_write_paths"])
        entry["task_brief_path"] = _absolute_existing_or_planned(run_dir, definition["task_brief"])
        entry["read_first_paths"] = [
            _absolute_existing_or_planned(run_dir, rel_path)
            for rel_path in definition["read_first_paths"]
        ]


def _new_manifest(state: ReportState, run_dir: Path) -> dict[str, Any]:
    order = stage_order_for_state(state)
    first_stage = order[0]
    manifest = {
        "version": MANIFEST_VERSION,
        "job_id": state.job_id,
        "created_at": _now(),
        "updated_at": _now(),
        "current_stage": first_stage,
        "stage_order": order,
        "stages": {stage: _stage_manifest(stage) for stage in order},
        "observed_hashes": _initial_observed_hashes(state, run_dir, first_stage),
        "author_owned_patterns": list(AUTHOR_OWNED_PATTERNS),
    }
    _hydrate_stage_paths(manifest, run_dir)
    return manifest


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = _now()
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_or_create_manifest(job_id: str, workspace_root: str | None = None) -> tuple[ReportState, Path, dict[str, Any]]:
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    run_dir = run_dir_for(state)
    path = manifest_path_for(run_dir)
    manifest = _load_manifest(path) or _new_manifest(state, run_dir)

    expected_order = stage_order_for_state(state)
    if manifest.get("stage_order") != expected_order:
        old_stages = manifest.get("stages", {})
        manifest["stage_order"] = expected_order
        manifest["stages"] = {
            stage: old_stages.get(stage, _stage_manifest(stage))
            for stage in expected_order
        }
        if manifest.get("current_stage") not in expected_order and manifest.get("current_stage") != "completed":
            manifest["current_stage"] = expected_order[0]

    _hydrate_stage_paths(manifest, run_dir)
    _save_manifest(path, manifest)
    return state, run_dir, manifest


def _stage_response(manifest: dict[str, Any], run_dir: Path, stage: str) -> dict[str, Any]:
    entry = manifest["stages"][stage]
    repair_context = (
        entry.get("last_error")
        if entry.get("status") in {"failed", "scope_violation", REPAIRLESS_STATUS}
        else None
    )
    return {
        "status": entry.get("status", "pending"),
        "job_id": manifest.get("job_id"),
        "stage": stage,
        "task_brief_path": entry.get("task_brief_path", ""),
        "allowed_write_paths": [
            str(run_dir / rel_path) for rel_path in entry.get("allowed_write_paths", [])
        ],
        "read_first_paths": entry.get("read_first_paths", []),
        "validation_tool": entry.get("validation_tool", ""),
        "repair_context": repair_context,
        "harness_manifest_path": str(manifest_path_for(run_dir)),
    }


def get_controlled_next_action(job_id: str, workspace_root: str | None = None) -> dict[str, Any]:
    _state, run_dir, manifest = load_or_create_manifest(job_id, workspace_root=workspace_root)
    current = manifest.get("current_stage")
    if current == "completed":
        return {
            "status": "completed",
            "job_id": job_id,
            "stage": "completed",
            "task_brief_path": "",
            "allowed_write_paths": [],
            "read_first_paths": [],
            "validation_tool": "",
            "repair_context": None,
            "harness_manifest_path": str(manifest_path_for(run_dir)),
        }
    return _stage_response(manifest, run_dir, str(current))


def _scope_violations(manifest: dict[str, Any], run_dir: Path, stage: str) -> list[dict[str, str]]:
    observed = manifest.get("observed_hashes", {})
    current = _snapshot_author_owned(run_dir)
    changed = _changed_paths(observed, current)
    allowed = manifest["stages"][stage].get("allowed_write_paths", [])
    violations: list[dict[str, str]] = []
    for rel_path in changed:
        if not _matches(rel_path, allowed):
            violations.append({
                "path": str(run_dir / rel_path),
                "relative_path": rel_path,
                "reason": "changed outside current stage write scope",
            })

    for passed_stage, entry in manifest.get("stages", {}).items():
        if entry.get("status") != "passed":
            continue
        for rel_path, expected_hash in entry.get("passed_hashes", {}).items():
            if current.get(rel_path) != expected_hash and not _matches(rel_path, allowed):
                violations.append({
                    "path": str(run_dir / rel_path),
                    "relative_path": rel_path,
                    "reason": f"changed after stage {passed_stage!r} passed",
                })

    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for violation in violations:
        deduped[(violation["relative_path"], violation["reason"])] = violation
    return list(deduped.values())


def _extract_evidence_paths(result: dict[str, Any], run_dir: Path) -> list[str]:
    paths = [str(manifest_path_for(run_dir))]
    for key, value in result.items():
        if not isinstance(value, str):
            continue
        if key.endswith("_path") or key.endswith("_report") or "path" in key:
            paths.append(value)
    for rel_path in (
        "artifact_lint_report.json",
        "remediation_plan.json",
        "qa_summary.json",
        "factuality_report.json",
        "final_qa_summary.json",
    ):
        path = run_dir / rel_path
        if path.exists():
            paths.append(str(path))
    return sorted(dict.fromkeys(path for path in paths if path))


def _result_passed(stage: str, result: dict[str, Any]) -> bool:
    status = str(result.get("status", "")).lower()
    if stage == "artifact_lint":
        return status == "ok"
    if stage == "publish":
        return status == "completed"
    return status in {"ok", "step_1_complete", "step_2_complete", "step_3_complete"}


def _result_error(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", "validation_failed"),
        "message": result.get("message", ""),
        "error_details": result.get("error_details") or result.get("error", ""),
        "missing_artifacts": result.get("missing_artifacts", []),
        "issues": result.get("issues", []),
    }


def _stage_from_artifact_text(text: str, order: list[str]) -> str | None:
    lowered = text.lower()
    candidates = [
        ("claim_matrix", "claim_matrix"),
        ("outline", "outline"),
        ("structured_drafts", "drafts"),
        ("section_drafts", "drafts"),
        ("sentence_map", "drafts"),
        ("figure_plan", "drafts"),
        ("revision_plan", "revision_plan"),
        ("factuality", "claim_matrix"),
        ("citation", "drafts"),
        ("figure", "drafts"),
    ]
    for needle, stage in candidates:
        if needle in lowered and stage in order:
            return stage
    return None


def _stage_from_artifact_lint(result: dict[str, Any], order: list[str]) -> str | None:
    for issue in result.get("issues", []) or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("severity") not in {None, "error", "hard"}:
            continue
        text = " ".join(str(issue.get(key, "")) for key in ("artifact", "path", "json_path", "message"))
        stage = _stage_from_artifact_text(text, order)
        if stage:
            return stage
    return None


def _stage_from_remediation(run_dir: Path, order: list[str]) -> str | None:
    path = run_dir / "remediation_plan.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    target_nodes = payload.get("target_nodes", [])
    stages = [
        TARGET_NODE_TO_STAGE.get(str(node))
        for node in target_nodes
        if TARGET_NODE_TO_STAGE.get(str(node)) in order
    ]
    if not stages:
        for route in payload.get("routes", []) or []:
            stage = TARGET_NODE_TO_STAGE.get(str(route.get("target_node", "")))
            if stage in order:
                stages.append(stage)
    if not stages:
        return None
    return min(stages, key=order.index)


#: Failures raised while authoring one stage whose only correct fix belongs to
#: an earlier one. Without this the harness kept the author where the error was
#: raised, and the write scope there excludes the file that has to change --
#: putting the sensible fix out of reach and bending the prose to suit the
#: contract instead. Matched on the message the raising gate writes, and
#: deliberately narrow: a broad match would rewind runs that stopped exactly
#: where they belong.
_FAILURE_OWNED_EARLIER = (
    ("cites evidence its own claims do not list", "claim_matrix"),
)


def _stage_owning_the_fix(result: dict[str, Any], order: list[str]) -> str | None:
    text = json.dumps(_result_error(result), ensure_ascii=False, default=str)
    for needle, owner in _FAILURE_OWNED_EARLIER:
        if needle in text and owner in order:
            return owner
    return None


def _route_failure_stage(stage: str, result: dict[str, Any], run_dir: Path, order: list[str]) -> str | None:
    if stage in {"claim_matrix", "outline", "drafts", "revision_plan"}:
        owner = _stage_owning_the_fix(result, order)
        if owner and order.index(owner) < order.index(stage):
            return owner
        return stage
    if stage == "artifact_lint":
        routed = _stage_from_artifact_lint(result, order)
        if routed:
            return routed
    routed = _stage_from_remediation(run_dir, order)
    if routed:
        return routed
    text = json.dumps(_result_error(result), ensure_ascii=False, default=str)
    return _stage_from_artifact_text(text, order)


def _invalidate_from(manifest: dict[str, Any], target_stage: str, error: dict[str, Any]) -> None:
    order = manifest["stage_order"]
    start = order.index(target_stage)
    for stage in order[start:]:
        entry = manifest["stages"][stage]
        entry["status"] = "pending"
        entry["passed_hashes"] = {}
        if stage != target_stage:
            entry["last_error"] = None
            entry["evidence_paths"] = []
    target = manifest["stages"][target_stage]
    target["status"] = "failed"
    target["last_error"] = error
    manifest["current_stage"] = target_stage


def _scope_violation_message(stage: str, violations: list[dict[str, str]]) -> str:
    """Say what went wrong and how to get out of it.

    Naming the offending paths is not enough to act on, and the recovery is not
    uniform: a file the author created clears by deleting it, while one that
    already existed clears only by restoring its previous content. That second
    case is easy to hit without realising, because an author directory can hold
    a file the pipeline generated — `section_drafts/figure_plan.json` — so
    clearing out "everything I wrote" takes that with it and keeps the stage
    blocked on a file the author never meant to touch.
    """
    named = ", ".join(
        violation.get("relative_path") or violation.get("path", "")
        for violation in violations[:5]
    )
    if len(violations) > 5:
        named += f", and {len(violations) - 5} more"
    return (
        "Author-owned artifacts changed outside the current stage write scope: "
        f"{named}. "
        f"Put each path listed in `violations` back as it stood when the {stage} "
        "stage began — delete it if you created it, restore its previous content "
        "if it already existed — then submit again. Note that some files under an "
        "author directory are generated by the pipeline, such as "
        "`section_drafts/figure_plan.json`; deleting one of those is itself a "
        "change and will keep the stage blocked. Only the paths in "
        "`allowed_repair_paths` may differ at this stage; write the later "
        "artifacts once the stage that owns them is current."
    )


def _record_scope_violation(
    manifest: dict[str, Any],
    run_dir: Path,
    stage: str,
    violations: list[dict[str, str]],
) -> dict[str, Any]:
    entry = manifest["stages"][stage]
    entry["status"] = "scope_violation"
    entry["last_error"] = {
        "message": _scope_violation_message(stage, violations),
        "violations": violations,
    }
    _save_manifest(manifest_path_for(run_dir), manifest)
    return {
        "status": "scope_violation",
        "job_id": manifest["job_id"],
        "stage": stage,
        "next_stage": stage,
        "violations": violations,
        "error_details": entry["last_error"]["message"],
        "allowed_repair_paths": [
            str(run_dir / rel_path)
            for rel_path in entry.get("allowed_write_paths", [])
        ],
        "evidence_paths": [str(manifest_path_for(run_dir))],
    }


def _record_pass(
    manifest: dict[str, Any],
    run_dir: Path,
    stage: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot_author_owned(run_dir)
    entry = manifest["stages"][stage]
    entry["status"] = "passed"
    entry["last_error"] = None
    entry["evidence_paths"] = _extract_evidence_paths(result, run_dir)
    entry["passed_hashes"] = {
        rel_path: digest
        for rel_path, digest in snapshot.items()
        if digest is not None and _matches(rel_path, entry.get("allowed_write_paths", []))
    }
    manifest["observed_hashes"] = snapshot

    order = manifest["stage_order"]
    index = order.index(stage)
    if stage == "publish":
        manifest["current_stage"] = "completed"
        entry["status"] = "completed"
        status = "completed"
        next_stage = "completed"
    else:
        next_stage = order[index + 1]
        manifest["current_stage"] = next_stage
        status = "ready_to_publish" if stage == "artifact_lint" else "passed"

    _save_manifest(manifest_path_for(run_dir), manifest)
    return {
        "status": status,
        "job_id": manifest["job_id"],
        "stage": stage,
        "next_stage": next_stage,
        "evidence_paths": entry["evidence_paths"],
        "error_details": "",
        "allowed_repair_paths": [],
        "validation_result": result,
        "harness_manifest_path": str(manifest_path_for(run_dir)),
    }


def _record_failure(
    manifest: dict[str, Any],
    run_dir: Path,
    stage: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    order = manifest["stage_order"]
    routed_stage = _route_failure_stage(stage, result, run_dir, order)
    error = _result_error(result)
    error["source_stage"] = stage
    error["routed_stage"] = routed_stage
    error["evidence_paths"] = _extract_evidence_paths(result, run_dir)
    if routed_stage is None:
        entry = manifest["stages"][stage]
        entry["status"] = REPAIRLESS_STATUS
        entry["last_error"] = error
        entry["evidence_paths"] = error["evidence_paths"]
        manifest["current_stage"] = stage
        _save_manifest(manifest_path_for(run_dir), manifest)
        return {
            "status": REPAIRLESS_STATUS,
            "job_id": manifest["job_id"],
            "stage": stage,
            "next_stage": stage,
            "evidence_paths": error["evidence_paths"],
            "error_details": error.get("error_details") or error.get("message", ""),
            "allowed_repair_paths": [],
            "repair_context": entry.get("last_error"),
            "validation_result": result,
            "harness_manifest_path": str(manifest_path_for(run_dir)),
        }

    _invalidate_from(manifest, routed_stage, error)
    _save_manifest(manifest_path_for(run_dir), manifest)

    target = manifest["stages"][routed_stage]
    return {
        "status": "validation_failed",
        "job_id": manifest["job_id"],
        "stage": stage,
        "next_stage": routed_stage,
        "evidence_paths": error["evidence_paths"],
        "error_details": error.get("error_details") or error.get("message", ""),
        "allowed_repair_paths": [
            str(run_dir / rel_path)
            for rel_path in target.get("allowed_write_paths", [])
        ],
        "repair_context": target.get("last_error"),
        "validation_result": result,
        "harness_manifest_path": str(manifest_path_for(run_dir)),
    }


ValidatorMap = dict[str, Callable[[str, str | None], dict[str, Any]]]


def run_controlled_stage(
    job_id: str,
    validators: ValidatorMap,
    workspace_root: str | None = None,
) -> dict[str, Any]:
    _state, run_dir, manifest = load_or_create_manifest(job_id, workspace_root=workspace_root)
    stage = str(manifest.get("current_stage"))
    if stage == "completed":
        return get_controlled_next_action(job_id, workspace_root=workspace_root)
    if stage not in validators:
        return {
            "status": "failed",
            "job_id": job_id,
            "stage": stage,
            "next_stage": stage,
            "evidence_paths": [str(manifest_path_for(run_dir))],
            "error_details": f"No validator configured for controlled stage {stage!r}",
            "allowed_repair_paths": [],
        }

    violations = _scope_violations(manifest, run_dir, stage)
    if violations:
        return _record_scope_violation(manifest, run_dir, stage, violations)

    entry = manifest["stages"][stage]
    entry["attempts"] = int(entry.get("attempts", 0) or 0) + 1
    entry["status"] = "running"
    _save_manifest(manifest_path_for(run_dir), manifest)

    result = validators[stage](job_id, workspace_root)
    if _result_passed(stage, result):
        return _record_pass(manifest, run_dir, stage, result)
    return _record_failure(manifest, run_dir, stage, result)
