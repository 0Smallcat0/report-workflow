"""Runtime support helpers for job events and artifact lineage."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import ReportState, WORKFLOW_RUNS_DIR

# Shared constants
PLACEHOLDER_TEXT = "This section is under development"


def load_jsonl(path: Optional[str]) -> list[dict]:
    """Load JSONL file, returning empty list if path is None or file doesn't exist."""
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_dir_for(state: ReportState) -> Path:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json_artifact(state: ReportState, filename: str, payload: object) -> str:
    """Write a stable JSON artifact into the workflow run directory."""
    path = run_dir_for(state) / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return str(path)


def append_job_event(
    state: ReportState,
    node_name: str,
    event: str,
    status: str,
    details: dict | None = None,
) -> str:
    """Append one runtime event to job_events.jsonl."""
    run_dir = run_dir_for(state)
    path = run_dir / "job_events.jsonl"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "job_id": state.job_id,
        "node": node_name,
        "event": event,
        "status": status,
        "details": details or {},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")
    state.runtime["job_events_path"] = str(path)
    return str(path)


def write_artifact_lineage(state: ReportState, files: list[dict]) -> str:
    """Write an artifact lineage manifest derived from packaged files."""
    run_dir = run_dir_for(state)
    path = run_dir / "artifact_lineage.json"
    lineage = {
        "job_id": state.job_id,
        "created_at": datetime.now().isoformat(),
        "files": [
            {
                "role": item.get("role", ""),
                "path": item.get("path", ""),
                "produced_by": _producer_for_role(item.get("role", "")),
            }
            for item in files
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(lineage, f, indent=2, default=str)
    state.runtime["artifact_lineage_path"] = str(path)
    return str(path)


def _producer_for_role(role: str) -> str:
    if role.startswith("traceability_"):
        return "TRACEABILITY_ARTIFACTS"
    if role.startswith("qa_"):
        return "QUALITY_GATES"
    if role.startswith("control_"):
        return "WORKFLOW_CONTROL"
    if role.startswith("evidence_"):
        return "EVIDENCE_STORE"
    if role == "report_docx":
        return "FINAL_PUBLISH"
    if role == "report_markdown":
        return "MERGE_DRAFT"
    if role == "source":
        return "CORPUS_BUILD"
    if role == "metadata":
        return "TRACEABILITY_ARTIFACTS"
    return "UNKNOWN"
