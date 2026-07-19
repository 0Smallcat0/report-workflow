"""ReportState and workspace path resolution for the report workflow."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .config import PROJECT_ROOT


DEFAULT_OUTPUT_DIRNAME = "output"
MAX_RUN_SLUG_LENGTH = 80
WINDOWS_FORBIDDEN_CHARS = '<>:"/\\|?*'
_JOB_RUN_HINTS: dict[str, Path] = {}


def default_workspace_root() -> Path:
    """Return the repo-local default workspace root."""
    return (PROJECT_ROOT / DEFAULT_OUTPUT_DIRNAME).resolve()


def resolve_workspace_root(workspace_root: str | Path | None = None) -> Path:
    """Resolve a workspace root override or fall back to repo-local output/."""
    if workspace_root:
        path = Path(workspace_root).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()
    return default_workspace_root()


def register_job_run(job_id: str, run_dir: str | Path) -> Path:
    """Record an in-process hint for resolving a job_id to a run directory."""
    path = Path(run_dir).resolve()
    _JOB_RUN_HINTS[str(job_id)] = path
    return path


def clear_job_run_hints() -> None:
    """Clear process-local job lookup hints.

    Useful in tests to verify that run discovery does not depend on shared sidecars.
    """
    _JOB_RUN_HINTS.clear()


def _clean_slug_text(value: str) -> str:
    cleaned = re.sub(rf"[{re.escape(WINDOWS_FORBIDDEN_CHARS)}\x00-\x1f]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned[:MAX_RUN_SLUG_LENGTH].strip()


def derive_run_slug(user_prompt: str, front_matter: dict[str, Any] | None = None) -> str:
    title = ""
    if front_matter:
        title = str(front_matter.get("title") or "").strip()
    candidate = title or str(user_prompt or "").strip() or "report"
    slug = _clean_slug_text(candidate)
    return slug or "report"


def build_run_dir_name(user_prompt: str, job_id: str, front_matter: dict[str, Any] | None = None) -> str:
    slug = derive_run_slug(user_prompt, front_matter)
    return f"{slug}--{job_id}"


def locate_run_dir(job_id: str, workspace_root: str | Path | None = None) -> Path:
    """Resolve the on-disk run directory for a job_id."""
    hinted_path = _JOB_RUN_HINTS.get(str(job_id))
    if hinted_path and hinted_path.exists():
        return hinted_path.resolve()

    roots: list[Path] = []
    if workspace_root:
        roots.append(resolve_workspace_root(workspace_root))
    default_root = default_workspace_root()
    if default_root not in roots:
        roots.append(default_root)

    for root in roots:
        if (root / "checkpoint_latest.json").exists() and job_id in root.name:
            register_job_run(job_id, root)
            return root.resolve()
        exact = root / str(job_id)
        if exact.exists():
            register_job_run(job_id, exact)
            return exact.resolve()
        matches = sorted(root.glob(f"*--{job_id}"))
        if matches:
            register_job_run(job_id, matches[0])
            return matches[0].resolve()

    raise FileNotFoundError(
        f"No local workflow run found for job {job_id}. "
        f"Expected under {', '.join(str(root) for root in roots)}."
    )


class _RunDirectoryResolver:
    """Compatibility shim for legacy `WORKFLOW_RUNS_DIR / job_id` call sites."""

    def __truediv__(self, job_id: str | Path) -> Path:
        return locate_run_dir(str(job_id))

    def __str__(self) -> str:
        return str(default_workspace_root())

    def __fspath__(self) -> str:
        return str(default_workspace_root())


class _PublishedDirectoryResolver:
    """Compatibility shim for legacy `PUBLISHED_DIR / job_id` call sites."""

    def __truediv__(self, job_id: str | Path) -> Path:
        return locate_run_dir(str(job_id)) / "published"

    def __str__(self) -> str:
        return str(default_workspace_root() / "published")

    def __fspath__(self) -> str:
        return str(default_workspace_root() / "published")


WORKFLOW_RUNS_DIR = _RunDirectoryResolver()
PUBLISHED_DIR = _PublishedDirectoryResolver()


class SourceContentBlock(BaseModel):
    block_id: str
    block_type: str
    content: str
    page_number: Optional[int] = None
    table_data: Optional[list[list[str]]] = None
    source_file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    content_hash: Optional[str] = None
    quote: Optional[str] = None


class CitationAuditEntry(BaseModel):
    cite_id: str
    evidence_ids: list[str]
    resolved: bool


class CitationsState(BaseModel):
    citation_audit: list[CitationAuditEntry] = Field(default_factory=list)


class RuntimeState(BaseModel):
    job_id: str
    current_node: Optional[str] = None
    error: Optional[str] = None


class ReportState(BaseModel):
    job_id: str
    version: str = "1.0"
    status: str = "running"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    spec: dict = Field(default_factory=dict)
    plan: dict = Field(default_factory=dict)
    sources: dict = Field(default_factory=dict)
    drafts: dict = Field(default_factory=dict)
    citations: dict = Field(default_factory=lambda: CitationsState().model_dump())
    qa: dict = Field(default_factory=dict)
    governance: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    runtime: dict = Field(default_factory=dict)
    flags: dict = Field(default_factory=dict)
    knowledge_sync: dict = Field(default_factory=lambda: {
        "status": "not_started",
        "buffer": [],
        "imported_sources": [],
        "sync_notes": [],
    })
    research: dict = Field(default_factory=lambda: {
        "routing_mode": "conditional_web_fallback",
        "status": "not_started",
        "tasks": [],
        "results_path": None,
    })

    @classmethod
    def new(
        cls,
        user_prompt: str,
        uploaded_files: list[str],
        output_dir: str | None = None,
        front_matter: dict[str, Any] | None = None,
    ) -> "ReportState":
        job_id = f"run_{uuid.uuid4().hex[:8]}"
        workspace_root = resolve_workspace_root(output_dir)
        run_dir = workspace_root / build_run_dir_name(user_prompt, job_id, front_matter)
        run_dir.mkdir(parents=True, exist_ok=True)
        published_dir = run_dir / "published"
        register_job_run(job_id, run_dir)

        runtime = RuntimeState(job_id=job_id, current_node="init")
        spec = {
            "task_intent": "new_draft",
            "report_profile": "academic_paper",
            "delivery_mode": "fresh_doc",
            "audience": "expert",
            "citation_style": "apa",
            "artifact_role_map": {},
            "keywords": [],
            "report_profile_override": None,
            "selected_guidelines": [],
            "user_prompt": user_prompt,
            "uploaded_files": uploaded_files,
        }
        if front_matter:
            spec["front_matter"] = front_matter

        return cls(
            job_id=job_id,
            status="running",
            spec=spec,
            plan={"blueprint": None, "claim_matrix": None, "outline": None},
            sources={"corpus_manifest": [], "source_registry": [], "evidence_ledger_path": None},
            drafts={
                "section_drafts": {},
                "sentence_map_path": None,
                "merged_draft_md": None,
                "merged_draft_cited_md": None,
            },
            citations={"citation_audit": []},
            qa={
                "factuality_report_path": None,
                "qa_decision": None,
                "artifact_completeness_status": None,
                "hard_fail_reasons": [],
            },
            output={
                "final_docx_path": None,
                "output_dir": str(run_dir),
                "workspace_root": str(workspace_root),
                "run_dir": str(run_dir),
                "published_dir": str(published_dir),
                "published_report_path": None,
            },
            flags={},
            knowledge_sync={
                "status": "not_started",
                "buffer": [],
                "imported_sources": [],
                "sync_notes": [],
            },
            research={
                "routing_mode": "conditional_web_fallback",
                "status": "not_started",
                "tasks": [],
                "results_path": None,
            },
            runtime={
                **runtime.model_dump(),
                "preflight": None,
                "warnings": [],
                "agent_tasks_dir": None,
                "required_agent_artifacts": [],
            },
        )

    def checkpoint(self, node_name: str) -> None:
        """Write current state to checkpoint file."""
        run_dir = run_dir_for(self)
        checkpoint_path = run_dir / f"checkpoint_{node_name}.json"

        state_dict = self.model_dump(mode="json")
        state_dict["runtime"]["current_node"] = node_name
        state_dict["updated_at"] = datetime.now().isoformat()

        checkpoint_path.write_text(
            json.dumps(state_dict, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        latest = run_dir / "checkpoint_latest.json"
        latest.write_text(
            json.dumps(state_dict, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    @classmethod
    def resume(cls, job_id: str, workspace_root: str | Path | None = None) -> "ReportState":
        """Load state from the last checkpoint for a local workspace run."""
        run_dir = locate_run_dir(job_id, workspace_root=workspace_root)
        latest = run_dir / "checkpoint_latest.json"
        if not latest.exists():
            raise FileNotFoundError(f"No local checkpoint found for job {job_id}")
        data = json.loads(latest.read_text(encoding="utf-8"))
        state = cls(**data)
        _sync_state_paths(state, run_dir)
        register_job_run(job_id, run_dir)
        return state

    def update_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now()


def _sync_state_paths(state: ReportState, run_dir: Path) -> None:
    run_dir = run_dir.resolve()
    published_dir = run_dir / "published"
    state.output.setdefault("workspace_root", str(run_dir.parent))
    state.output["run_dir"] = str(run_dir)
    state.output["output_dir"] = str(run_dir)
    state.output.setdefault("published_dir", str(published_dir))


def run_dir_for(job: ReportState | str, workspace_root: str | Path | None = None) -> Path:
    if isinstance(job, ReportState):
        raw = job.output.get("run_dir")
        if raw:
            path = Path(raw).expanduser().resolve()
        else:
            path = locate_run_dir(job.job_id, workspace_root=workspace_root or job.output.get("workspace_root"))
        path.mkdir(parents=True, exist_ok=True)
        _sync_state_paths(job, path)
        register_job_run(job.job_id, path)
        return path

    path = locate_run_dir(str(job), workspace_root=workspace_root)
    register_job_run(str(job), path)
    return path


def published_dir_for(job: ReportState | str, workspace_root: str | Path | None = None) -> Path:
    if isinstance(job, ReportState):
        raw = job.output.get("published_dir")
        if raw:
            path = Path(raw).expanduser().resolve()
        else:
            path = run_dir_for(job, workspace_root=workspace_root) / "published"
        job.output["published_dir"] = str(path)
        return path
    return run_dir_for(str(job), workspace_root=workspace_root) / "published"
