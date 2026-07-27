"""CORPUS_BUILD node - enumerate uploaded files into corpus_manifest."""
from pathlib import Path
from datetime import datetime
from ..state import ReportState, run_dir_for
from ..config import PROJECT_ROOT
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..artifact_contract import _hash_bytes

try:
    import filetype
except ImportError:  # pragma: no cover - depends on local environment
    filetype = None

VALID_ARTIFACT_ROLES = {"source_data", "base_document"}

def detect_file_type(file_path: str) -> str:
    """Detect file type from extension and content."""
    ext = Path(file_path).suffix.lower().lstrip(".")
    if ext in (
        "csv", "xlsx", "json", "toml", "txt", "md",
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


def _source_id_for(path: Path, taken: set[str]) -> str:
    """A source id that depends on the file, not on when it was read.

    This used to be a fresh uuid4 per run, and it seeds every evidence id —
    both the ``E_<source_id>_…`` prefix and the hash after it. So running the
    same unchanged CSV twice produced two ledgers with no id in common, and
    a claim_matrix written against the first run cited nothing that existed
    in the second. Resuming work the next day, or re-preparing after fixing
    one source, threw away every citation the author had already made.

    Seeded from the file's name, deliberately not its contents. Seeding on
    contents would rotate this prefix on any edit, and with it every id in
    the file — so fixing one typo in one source would still throw away the
    citations for every untouched row. The per-block content hash already
    changes exactly the ids whose text changed; the prefix should not.

    Two different files sharing a name are separated by a counter, in
    attachment order, which is itself stable across reruns.
    """
    seed = path.name
    candidate = _hash_bytes(seed.encode("utf-8"))[:8]
    collision = 1
    while candidate in taken:
        candidate = _hash_bytes(f"{seed}:{collision}".encode("utf-8"))[:8]
        collision += 1
    return candidate


def run_corpus_build(state: ReportState) -> ReportState:
    """T5: CORPUS_BUILD - enumerate uploaded files into corpus_manifest."""
    uploaded_files = state.spec.get("uploaded_files", [])
    artifact_role_map = state.spec.get("artifact_role_map", {})

    if not uploaded_files:
        raise QAHardBlockError("No uploaded source files were provided")
    
    corpus_manifest = []
    source_registry = []
    taken_source_ids: set[str] = set()

    run_dir = run_dir_for(state)
    run_dir.mkdir(parents=True, exist_ok=True)
    
    for file_path in uploaded_files:
        try:
            path = Path(file_path)
            if not path.exists():
                # Try relative to project root for stable repo-local behavior.
                path = PROJECT_ROOT / file_path
            
            if not path.exists():
                raise QAHardBlockError(f"Uploaded source not found: {file_path}")
            
            file_size = path.stat().st_size
            file_type = detect_file_type(str(path))
            source_id = _source_id_for(path, taken_source_ids)
            taken_source_ids.add(source_id)
            
            manifest_entry = {
                "source_id": source_id,
                "file_name": path.name,
                "file_path": str(path.resolve()),
                "file_type": file_type,
            }
            corpus_manifest.append(manifest_entry)
            
            artifact_role = (
                artifact_role_map.get(str(path.resolve()))
                or artifact_role_map.get(str(path))
                or artifact_role_map.get(str(file_path))
                or artifact_role_map.get(path.name)
                or "source_data"
            )
            if artifact_role not in VALID_ARTIFACT_ROLES:
                raise QAHardBlockError(
                    f"Invalid artifact role {artifact_role!r} for source {path.name}; "
                    f"expected one of {sorted(VALID_ARTIFACT_ROLES)}"
                )
            
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
