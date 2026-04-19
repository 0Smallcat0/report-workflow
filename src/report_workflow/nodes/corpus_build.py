"""CORPUS_BUILD node - enumerate uploaded files into corpus_manifest."""
import os
import uuid
from pathlib import Path
from datetime import datetime
from ..state import ReportState
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact

try:
    import filetype
except ImportError:  # pragma: no cover - depends on local environment
    filetype = None

WORKFLOW_RUNS_DIR = Path.home() / ".hermes" / "workflow_runs"


def detect_file_type(file_path: str) -> str:
    """Detect file type from extension and content."""
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext in (
        "csv", "xlsx", "json", "txt", "md",
        "pdf", "docx", "url",
        # Fix #1: code file types routed to code_parser
        "py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h",
        "cs", "go", "rs", "rb", "php", "swift", "kt", "scala",
    ):
        return ext
    
    # Use filetype library for additional detection
    if filetype is None:
        return "unknown"

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

    if not uploaded_files:
        raise QAHardBlockError("No uploaded source files were provided")
    
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
                raise QAHardBlockError(f"Uploaded source not found: {file_path}")
            
            file_size = path.stat().st_size
            file_type = detect_file_type(str(path))
            source_id = str(uuid.uuid4())[:8]
            
            manifest_entry = {
                "source_id": source_id,
                "file_name": path.name,
                "file_path": str(path.resolve()),
                "file_type": file_type,
            }
            corpus_manifest.append(manifest_entry)
            
            artifact_role = artifact_role_map.get(path.name, "source_data")
            
            registry_entry = {
                "source_id": source_id,
                "file_name": path.name,
                "file_path": str(path.resolve()),
                "file_type": file_type,
                "file_size": file_size,
                "uploaded_at": datetime.now().isoformat(),
                "artifact_role": artifact_role,
                "parsed_content": [],
                "parse_attempts": 0,
                "parse_status": None,
                "parse_error": None,
            }
            source_registry.append(registry_entry)
            
        except QAHardBlockError:
            raise
        except Exception as e:
            raise QAHardBlockError(f"Failed to register source {file_path}: {e}") from e

    if not corpus_manifest:
        raise QAHardBlockError("No source files were registered")
    
    state.sources["corpus_manifest"] = corpus_manifest
    state.sources["source_registry"] = source_registry
    state.sources["corpus_manifest_path"] = write_json_artifact(state, "corpus_manifest.json", corpus_manifest)
    state.sources["source_registry_path"] = write_json_artifact(state, "source_registry.json", source_registry)
    return state
