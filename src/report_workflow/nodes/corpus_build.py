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


def _source_id_for(path: Path, taken: set[str], siblings: list[Path] | None = None) -> str:
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

    Two files sharing a name are separated by the shortest tail of their paths
    that tells them apart — 2024/月報.csv against 2025/月報.csv — which is a
    fact about the files.

    They used to be separated by a counter in attachment order, on the stated
    assumption that attachment order is itself stable across reruns. It is not:
    re-typing the command, a shell expanding a glob differently, or dropping the
    files in another order is enough. Listing the same two exports the other way
    round swapped their ids, so the prefix that meant one file's evidence in the
    morning meant the other file's in the afternoon.
    """
    seed = _distinguishing_seed(path, siblings)
    candidate = _hash_bytes(seed.encode("utf-8"))[:8]
    collision = 1
    while candidate in taken:
        candidate = _hash_bytes(f"{seed}:{collision}".encode("utf-8"))[:8]
        collision += 1
    return candidate


def _distinguishing_seed(path: Path, siblings: list[Path] | None) -> str:
    """The shortest trailing path segments unique among this run's sources.

    A file whose name nobody shares seeds on that name alone, so moving the
    folder it lives in changes nothing — the property that lets an author
    reorganise their files and keep every citation already made.
    """
    if not siblings:
        return path.name
    same_name = [item for item in siblings if item.name == path.name]
    if len(same_name) <= 1:
        return path.name
    parts = path.resolve().parts
    for depth in range(2, len(parts) + 1):
        tail = "/".join(parts[-depth:])
        matches = sum(
            1 for item in same_name
            if "/".join(item.resolve().parts[-depth:]) == tail
        )
        if matches == 1:
            return tail
    return str(path.resolve())


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

    # Every source this run has, resolved up front, so a file's id is decided
    # by which files it shares its name with — not by how far down the list it
    # happens to sit. Missing files are skipped here and still raise below.
    all_sources: list[Path] = []
    for candidate_path in uploaded_files:
        candidate = Path(candidate_path)
        if not candidate.exists():
            candidate = PROJECT_ROOT / candidate_path
        if candidate.exists():
            all_sources.append(candidate)

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
            source_id = _source_id_for(path, taken_source_ids, all_sources)
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
