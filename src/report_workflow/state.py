"""ReportState - the single source of truth for the report workflow."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid

HOME = Path.home()
WORKFLOW_RUNS_DIR = HOME / ".hermes" / "workflow_runs"
PUBLISHED_DIR = HOME / ".hermes" / "published"


class PlanState(BaseModel):
    blueprint: Optional[dict] = None
    claim_matrix: Optional[dict] = None
    outline: Optional[dict] = None


class SourceContentBlock(BaseModel):
    block_id: str
    block_type: str
    content: str
    page_number: Optional[int] = None
    table_data: Optional[list[list[str]]] = None
    # Tracing metadata (populated by parsers)
    source_file_path: Optional[str] = None
    line_start: Optional[int] = None   # 1-based line number in source file
    line_end: Optional[int] = None     # 1-based line number in source file
    content_hash: Optional[str] = None  # SHA-256 first 16 chars for deduplication
    quote: Optional[str] = None        # First 200 chars of content for fast preview


class SourceRegistryEntry(BaseModel):
    source_id: str
    file_name: str
    file_path: str
    file_type: str
    file_size: int
    uploaded_at: str
    artifact_role: str
    parsed_content: list[SourceContentBlock] = Field(default_factory=list)
    parse_attempts: int = 0
    parse_status: Optional[str] = None
    parse_error: Optional[str] = None


class SourcesState(BaseModel):
    corpus_manifest: list[dict] = Field(default_factory=list)
    source_registry: list[SourceRegistryEntry] = Field(default_factory=list)
    evidence_ledger_path: Optional[str] = None


class SectionDraft(BaseModel):
    section_id: str
    content: str
    sentence_map_path: Optional[str] = None


class DraftsState(BaseModel):
    section_drafts: dict[str, str] = Field(default_factory=dict)
    sentence_map_path: Optional[str] = None
    merged_draft_md: Optional[str] = None
    merged_draft_cited_md: Optional[str] = None


class CitationAuditEntry(BaseModel):
    cite_id: str
    evidence_ids: list[str]
    resolved: bool


class CitationsState(BaseModel):
    citation_audit: list[CitationAuditEntry] = Field(default_factory=list)


class FactualityReportEntry(BaseModel):
    claim_id: str
    status: str
    checker: str
    reason: str


class QAState(BaseModel):
    factuality_report_path: Optional[str] = None
    qa_decision: Optional[str] = None
    artifact_completeness_status: Optional[str] = None
    hard_fail_reasons: list[str] = Field(default_factory=list)


class OutputState(BaseModel):
    final_docx_path: Optional[str] = None
    output_dir: Optional[str] = None


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

    @classmethod
    def new(cls, user_prompt: str, uploaded_files: list[str], output_dir: str) -> "ReportState":
        job_id = f"run_{uuid.uuid4().hex[:8]}"
        run_dir = WORKFLOW_RUNS_DIR / job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        runtime = RuntimeState(job_id=job_id, current_node="init")
        spec = {
            "task_intent": "new_draft",
            "report_family": "academic_report",
            "delivery_mode": "fresh_doc",
            "audience": "expert",
            "citation_style": "apa",
            "artifact_role_map": {},
            "report_family_detail": "",
            "keywords": [],
            "report_family_override": None,
            "selected_guidelines": [],
            "user_prompt": user_prompt,
            "uploaded_files": uploaded_files,
        }

        return cls(
            job_id=job_id,
            status="running",
            spec=spec,
            plan={"blueprint": None, "claim_matrix": None, "outline": None},
            sources={"corpus_manifest": [], "source_registry": [], "evidence_ledger_path": None},
            drafts={"section_drafts": {}, "sentence_map_path": None, "merged_draft_md": None, "merged_draft_cited_md": None},
            citations={"citation_audit": []},
            qa={
                "factuality_report_path": None,
                "qa_decision": None,
                "artifact_completeness_status": None,
                "hard_fail_reasons": [],
            },
            output={"final_docx_path": None, "output_dir": output_dir},
            flags={},
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
        run_dir = WORKFLOW_RUNS_DIR / self.job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = run_dir / f"checkpoint_{node_name}.json"

        state_dict = self.model_dump(mode="json")
        state_dict["runtime"]["current_node"] = node_name
        state_dict["updated_at"] = datetime.now().isoformat()

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=2, default=str)

        latest = run_dir / "checkpoint_latest.json"
        with open(latest, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=2, default=str)

    @classmethod
    def resume(cls, job_id: str) -> "ReportState":
        """Load state from last checkpoint."""
        run_dir = WORKFLOW_RUNS_DIR / job_id
        latest = run_dir / "checkpoint_latest.json"
        if not latest.exists():
            raise FileNotFoundError(f"No checkpoint found for job {job_id}")
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def update_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now()
