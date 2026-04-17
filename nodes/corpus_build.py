"""CORPUS_BUILD node - enumerate uploaded files into corpus_manifest."""
import os
import uuid
from pathlib import Path
from datetime import datetime
import filetype
from ..state import ReportState

WORKFLOW_RUNS_DIR = Path.home() / ".hermes" / "workflow_runs"


def detect_file_type(file_path: str) -> str:
    """Detect file type from extension and content."""
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext in ("csv", "xlsx", "json", "txt", "pdf", "docx", "url"):
        return ext
    
    # Use filetype library for additional detection
    try:
        kind = filetype.guess(file_path)
        if kind:
            return kind.extension
    except Exception:
        pass
    
    return "unknown"


def run_corpus_build(state: ReportState) -> ReportState:
    """T5: CORPUS_BUILD - enumerate uploaded files into corpus_manifest."""
    uploaded_files = state.spec.get("uploaded_files", [])
    artifact_role_map = state.spec.get("artifact_role_map", {})
    
    corpus_manifest = []
    source_registry = []
    
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    for file_path in uploaded_files:
        try:
            path = Path(file_path)
            if not path.exists():
                # Try relative to current dir
                path = Path.cwd() / file_path
            
            if not path.exists():
                continue
            
            file_size = path.stat().st_size
            file_type = detect_file_type(str(path))
            source_id = str(uuid.uuid4())[:8]
            
            manifest_entry = {
                "source_id": source_id,
                "file_name": path.name,
                "file_type": file_type,
            }
            corpus_manifest.append(manifest_entry)
            
            artifact_role = artifact_role_map.get(path.name, "source_data")
            
            registry_entry = {
                "source_id": source_id,
                "file_name": path.name,
                "file_type": file_type,
                "file_size": file_size,
                "uploaded_at": datetime.now().isoformat(),
                "artifact_role": artifact_role,
                "parsed_content": [],
                "parse_attempts": 0,
            }
            source_registry.append(registry_entry)
            
        except Exception as e:
            # Skip with warning, don't fail
            continue
    
    state.sources["corpus_manifest"] = corpus_manifest
    state.sources["source_registry"] = source_registry
    return state
