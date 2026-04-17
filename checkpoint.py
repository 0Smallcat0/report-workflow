"""Checkpoint and resume utilities for ReportState."""
import json
from pathlib import Path
from .state import ReportState, WORKFLOW_RUNS_DIR


def checkpoint(state: ReportState, node_name: str) -> None:
    """Write state checkpoint (delegates to ReportState.checkpoint)."""
    state.checkpoint(node_name)


def resume(job_id: str) -> ReportState:
    """Resume from last checkpoint."""
    return ReportState.resume(job_id)


def get_checkpoint_path(job_id: str, node_name: str) -> Path:
    """Get path to a specific checkpoint."""
    return WORKFLOW_RUNS_DIR / job_id / f"checkpoint_{node_name}.json"


def get_latest_checkpoint_path(job_id: str) -> Path:
    """Get path to the latest checkpoint."""
    return WORKFLOW_RUNS_DIR / job_id / "checkpoint_latest.json"


def list_checkpoints(job_id: str) -> list[str]:
    """List all checkpoint node names for a job."""
    run_dir = WORKFLOW_RUNS_DIR / job_id
    if not run_dir.exists():
        return []
    return sorted([
        p.name.replace("checkpoint_", "").replace(".json", "")
        for p in run_dir.glob("checkpoint_*.json")
        if p.name != "checkpoint_latest.json"
    ])
