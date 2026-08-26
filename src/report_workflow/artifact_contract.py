"""Artifact contracts and evidence remapping helpers.

This module is the single home for run-local artifact provenance checks and
cross-run evidence ID remapping. Keep this logic centralized so workflow nodes
stay small and agent-facing failures remain consistent.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .errors import QAHardBlockError
from .state import ReportState, WORKFLOW_RUNS_DIR, run_dir_for


CONTRACT_KEY = "_contract"
BASE_INTEGRITY_FILENAME = "base_document_integrity.json"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _stable_json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return _hash_bytes(encoded)


def compute_sections_hash(sections: dict[str, str]) -> str:
    return _stable_json_hash(sections)


def compute_evidence_ledger_hash(path_or_state: str | Path | ReportState | None) -> str:
    path: Path | None
    if isinstance(path_or_state, ReportState):
        raw = path_or_state.sources.get("evidence_ledger_path")
        path = Path(raw) if raw else None
    elif path_or_state:
        path = Path(path_or_state)
    else:
        path = None
    if not path or not path.exists():
        return ""
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return _hash_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def compute_source_registry_hash(path_or_state: str | Path | ReportState | None) -> str:
    if isinstance(path_or_state, ReportState):
        registry = path_or_state.sources.get("source_registry", [])
        if registry:
            return _stable_json_hash(registry)
        raw = path_or_state.sources.get("source_registry_path")
        path = Path(raw) if raw else None
    elif path_or_state:
        path = Path(path_or_state)
    else:
        path = None
    if not path or not path.exists():
        return ""
    try:
        return _stable_json_hash(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return _hash_bytes(path.read_bytes())


def make_artifact_contract(state: ReportState) -> dict:
    return {
        "job_id": state.job_id,
        "evidence_ledger_hash": compute_evidence_ledger_hash(state),
        "source_registry_hash": compute_source_registry_hash(state),
    }


def write_base_document_integrity(state: ReportState, sections: dict[str, str], source_entry: dict) -> str:
    """Record what the base document was, so a later change can be noticed.

    Size and modification time were recorded here and compared by nobody, under
    a name that promised otherwise. They also cannot do the job: fixing what
    looks like a typo — 79.3 to 89.3 — changes neither, and making that edit
    between prepare and the revision being applied is an ordinary thing to do.
    The revision was then applied against a snapshot of a file that no longer
    said what the snapshot said.

    So the content is hashed, and that is what gets compared. Modification time
    stays recorded and stays uncompared on purpose: opening a file and saving it
    changes the time without changing a character, and refusing a sound run for
    that would be worse than the gap being closed here.
    """
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    source_path = Path(source_entry.get("file_path", ""))
    stat = source_path.stat() if source_path.exists() else None
    payload = {
        "job_id": state.job_id,
        "source_file_path": str(source_path),
        "source_file_name": source_entry.get("file_name", ""),
        "source_file_size": stat.st_size if stat else None,
        "source_mtime_ns": stat.st_mtime_ns if stat else None,
        "source_content_hash": _hash_bytes(source_path.read_bytes()) if stat else "",
        "sections_hash": compute_sections_hash(sections),
    }
    path = run_dir / BASE_INTEGRITY_FILENAME
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    state.sources["base_document_integrity_path"] = str(path)
    state.sources["base_document_sections_hash"] = payload["sections_hash"]
    return str(path)


def validate_base_document_integrity(state: ReportState, sections: dict[str, str]) -> None:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    raw_path = state.sources.get("base_document_integrity_path") or str(run_dir / BASE_INTEGRITY_FILENAME)
    path = Path(raw_path)
    if not path.exists():
        return
    integrity = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = integrity.get("sections_hash", "")
    actual_hash = compute_sections_hash(sections)
    if expected_hash and actual_hash != expected_hash:
        raise QAHardBlockError(
            "base_document_sections.json differs from the immutable parse snapshot "
            f"(expected sections_hash={expected_hash}, actual={actual_hash}). "
            "Do not edit base_document_sections.json or checkpoint state directly; "
            "use revision_plan.json and rerun prepare if the base document changed."
        )

    # The message above tells the author what to do when the base document
    # changed. Until now nothing could tell that it had.
    expected_source = integrity.get("source_content_hash", "")
    if not expected_source:
        return
    source_path = Path(integrity.get("source_file_path", ""))
    if not source_path.exists():
        raise QAHardBlockError(
            f"the base document is no longer at {source_path}. The revision would be "
            "applied to a parse of a file that is not there to check it against; "
            "restore the file or rerun prepare against its new location."
        )
    if _hash_bytes(source_path.read_bytes()) != expected_source:
        raise QAHardBlockError(
            f"the base document {integrity.get('source_file_name') or source_path.name} "
            "changed on disk after it was parsed, so this revision would be applied to "
            "text the file no longer contains. Rerun prepare to parse it as it is now."
        )


def load_artifact_contract(path: str | Path) -> dict:
    artifact = Path(path)
    if not artifact.exists():
        return {}
    if artifact.suffix.lower() == ".jsonl":
        for line in artifact.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return {}
            return payload.get(CONTRACT_KEY, {}) if isinstance(payload, dict) else {}
        return {}
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload.get(CONTRACT_KEY, {}) if isinstance(payload, dict) else {}


def write_artifact_contract(path: str | Path, contract: dict) -> None:
    artifact = Path(path)
    if artifact.suffix.lower() == ".jsonl":
        lines = [line for line in artifact.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            try:
                first = json.loads(lines[0])
            except json.JSONDecodeError:
                first = {}
            if isinstance(first, dict) and CONTRACT_KEY in first:
                lines = lines[1:]
        artifact.write_text(
            json.dumps({CONTRACT_KEY: contract}, ensure_ascii=False, default=str)
            + "\n" + "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )
        return

    payload = json.loads(artifact.read_text(encoding="utf-8")) if artifact.exists() else {}
    if not isinstance(payload, dict):
        payload = {}
    payload[CONTRACT_KEY] = contract
    # ensure_ascii matches how the author's artifacts are written everywhere
    # else; stamping a contract onto a Chinese claim_matrix used to hand back
    # escaped text where the author had written prose. These files are compared
    # field by field, not by file hash, so the encoding disturbs no check.
    artifact.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _artifact_evidence_ids(path: str | Path) -> set[str]:
    """Every evidence id an authored artifact leans on."""
    artifact = Path(path)
    ids: set[str] = set()
    if not artifact.exists():
        return ids

    def harvest(payload: Any) -> None:
        if isinstance(payload, dict):
            for key in ("evidence_ids", "citation_ids", "source_evidence_ids"):
                value = payload.get(key)
                if isinstance(value, list):
                    ids.update(str(item) for item in value)
            unused = payload.get("unused_derived_evidence")
            if isinstance(unused, dict):
                ids.update(str(key) for key in unused)
            for value in payload.values():
                harvest(value)
        elif isinstance(payload, list):
            for item in payload:
                harvest(item)

    if artifact.suffix.lower() == ".jsonl":
        for line in artifact.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                harvest(json.loads(line))
            except json.JSONDecodeError:
                continue
        return ids
    try:
        harvest(json.loads(artifact.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        pass
    return ids


def _ledger_evidence_ids(state: ReportState) -> set[str]:
    raw = state.sources.get("evidence_ledger_path")
    if not raw or not Path(raw).exists():
        return set()
    ids: set[str] = set()
    for line in Path(raw).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("evidence_id"):
            ids.add(str(payload["evidence_id"]))
    return ids


def validate_artifact_contract(state: ReportState, path: str | Path, *, allow_missing: bool = True) -> None:
    contract = load_artifact_contract(path)
    if not contract:
        if allow_missing:
            return
        raise QAHardBlockError(
            f"{Path(path).name} is missing _contract. Recreate it for job {state.job_id} "
            "or run remap-evidence from the previous job."
        )
    expected = make_artifact_contract(state)
    mismatches = [
        key for key in ("job_id", "evidence_ledger_hash", "source_registry_hash")
        if contract.get(key) != expected.get(key)
    ]
    if mismatches:
        details = ", ".join(f"{key}: artifact={contract.get(key)!r}, current={expected.get(key)!r}" for key in mismatches)
        # Two different situations used to get the same prescription, and for
        # one of them it was the wrong prescription. When the job id matches,
        # the artifact is this run's own and the ledger moved underneath it —
        # which is what registering a derived statistic does. There is no "old
        # job" to remap from, and an author following that advice looks for one.
        if contract.get("job_id") == expected.get("job_id"):
            # The ledger is append-only within a run, and the pipeline itself
            # appends to it — the grouped table built during outline planning
            # is enough to move the hash. An artifact stamped before such an
            # append is not stale; it is only stale if something it cites is
            # gone. So check that instead of the hash, and re-stamp when every
            # id it leans on still resolves.
            #
            # Without this a run can deadlock with no way out: publish refuses
            # on the hash, routing the failure hands back an empty repair
            # scope, and the prescribed cure (call register_derived_evidence
            # again) has no derivation to re-register when the author never
            # registered one — the pipeline made the row.
            if mismatches == ["evidence_ledger_hash"]:
                cited = _artifact_evidence_ids(path)
                missing = cited - _ledger_evidence_ids(state)
                if not missing:
                    write_artifact_contract(path, expected)
                    return
                raise QAHardBlockError(
                    f"{Path(path).name} cites evidence that is no longer in this "
                    f"run's ledger ({', '.join(sorted(missing))}). The ledger "
                    "changed under the artifact and took those rows with it; "
                    "rebuild the artifact from the current ledger."
                )
            raise QAHardBlockError(
                f"{Path(path).name} was stamped against an earlier state of this "
                f"run's evidence ledger ({details}). The ledger changed after the "
                "artifact was accepted — registering a derived statistic does "
                "this, because it appends rows. Call register_derived_evidence "
                "again with the same derivations: it re-stamps the accepted "
                "artifacts against the current ledger. Do not run remap-evidence; "
                "there is no previous job here."
            )
        raise QAHardBlockError(
            f"{Path(path).name} appears to belong to another workflow run or stale evidence ledger ({details}). "
            "Run report-workflow remap-evidence --from-job <old> --to-job "
            f"{state.job_id} --write, or rebuild the artifacts from this run's evidence ledger."
        )


def load_jsonl_without_contract(path: str | Path | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if line_number == 1 and isinstance(payload, dict) and CONTRACT_KEY in payload:
                continue
            rows.append(payload)
    return rows


def validate_evidence_ledger_provenance(path: str | Path | None) -> None:
    entries = load_jsonl_without_contract(path)
    if not entries:
        return
    issues: list[str] = []
    for index, item in enumerate(entries):
        role = str(item.get("source_role", "primary_source"))
        if role in {"derived_summary", "agent_supplied"}:
            continue
        if role == "base_document":
            issues.append(
                f"entry {index} ({item.get('evidence_id', '<missing>')}) uses forbidden source_role=base_document; "
                "base document text may support revision diffing but cannot be promoted to publishable evidence"
            )
            continue
        required = ("evidence_id", "source_id", "source_file_name", "content")
        missing = [key for key in required if not item.get(key)]
        has_trace = bool(item.get("content_hash") or item.get("source_span") or item.get("line_start") is not None)
        if missing or not has_trace:
            issues.append(
                f"entry {index} ({item.get('evidence_id', '<missing>')}) lacks parser provenance "
                f"for source_role={role}: missing={missing}, has_trace={has_trace}"
            )
    if issues:
        raise QAHardBlockError(
            "evidence_ledger.jsonl contains hand-authored or unverifiable evidence entries. "
            "Evidence used for publishable claims must come from source parsing/remap. "
            + "; ".join(issues[:5])
        )


def find_repo_hygiene_issues(root: str | Path | None = None) -> list[str]:
    root_path = Path(root or PROJECT_ROOT)
    patterns = [
        "fix_*.py",
        "strip_figures*.py",
        "check_sentence_map.py",
        "create_artifacts.py",
        "run_start.py",
        "submit_all.py",
    ]
    issues: list[str] = []
    for pattern in patterns:
        for path in root_path.glob(pattern):
            if path.is_file():
                issues.append(str(path))
    return sorted(set(issues))


def stable_evidence_id(entry: dict, block: dict) -> str:
    source_id = str(entry.get("source_id") or Path(entry.get("file_name", "source")).stem)
    line_start = block.get("line_start")
    line_end = block.get("line_end")
    content_hash = str(block.get("content_hash") or "")
    if line_start is not None and line_end is not None and content_hash:
        seed = f"{source_id}:{line_start}:{line_end}:{content_hash}"
        # Every row of one table shares that table's line span, so the span
        # cannot tell the rows apart — the row's own hash does, and two
        # byte-identical rows do not even have that. A table listing the same
        # reading twice filed both under one id, and the gate that resolves a
        # cited id took whichever row came first: the second row's
        # allowed_claim_types were never consulted, so a legitimate claim was
        # refused naming an id the author had no way to disambiguate.
        # Appending the occurrence only past the first leaves existing ids
        # unchanged.
        occurrence = block.get("content_occurrence")
        if occurrence is not None and occurrence > 1:
            seed += f":n{occurrence}"
    else:
        # block_id is positional — block_0, block_1 — so inserting a missed
        # trial in the middle of a CSV renumbered every row below it and
        # changed their ids, discarding the author's citations to rows whose
        # text had not moved a character. When the caller supplies how many
        # identical rows came before this one, that is used instead: it tells
        # the two copies of a repeated row apart without tying either to a
        # line number.
        occurrence = block.get("content_occurrence")
        position = f"n{occurrence}" if occurrence is not None else block.get("block_id", "")
        seed = f"{source_id}:{position}:{content_hash}:{block.get('content', '')[:200]}"
    return "E_" + re.sub(r"[^A-Za-z0-9]+", "_", source_id).strip("_")[:12] + "_" + _hash_bytes(seed.encode("utf-8"))[:10]


def _evidence_signature(item: dict) -> tuple:
    content_hash = item.get("content_hash") or ""
    if content_hash:
        return (
            item.get("source_file_name", ""),
            item.get("line_start"),
            item.get("line_end"),
            content_hash,
        )
    quote = item.get("quote") or item.get("content", "")[:200]
    return (
        item.get("source_file_name", ""),
        item.get("line_start"),
        item.get("line_end"),
        _hash_bytes(str(quote).encode("utf-8")),
    )


def _ledger_by_signature(job_id: str, *, workspace_root: str | Path | None = None) -> dict[tuple, dict]:
    ledger = run_dir_for(job_id, workspace_root=workspace_root) / "evidence_ledger.jsonl"
    return {_evidence_signature(item): item for item in load_jsonl_without_contract(ledger)}


def _replace_ids(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [mapping.get(item, item) if isinstance(item, str) else _replace_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _replace_ids(val, mapping) for key, val in value.items()}
    return value


def _rewrite_citations(text: str, mapping: dict[str, str]) -> str:
    def repl(match: re.Match) -> str:
        old_id = match.group(1).strip()
        return f"[CITE:{mapping.get(old_id, old_id)}]"
    return re.sub(r"\[CITE:([^\]]+)\]", repl, text)


def remap_evidence_ids(
    job_id: str,
    previous_job_id: str,
    *,
    write: bool = False,
    workspace_root: str | Path | None = None,
    previous_workspace_root: str | Path | None = None,
) -> dict:
    run_dir = run_dir_for(job_id, workspace_root=workspace_root)
    previous_by_sig = _ledger_by_signature(previous_job_id, workspace_root=previous_workspace_root)
    current_by_sig = _ledger_by_signature(job_id, workspace_root=workspace_root)
    mapping: dict[str, str] = {}
    unmapped: list[str] = []

    for signature, old_item in previous_by_sig.items():
        old_id = old_item.get("evidence_id")
        new_item = current_by_sig.get(signature)
        if old_id and new_item and new_item.get("evidence_id"):
            mapping[str(old_id)] = str(new_item["evidence_id"])

    touched_files: list[str] = []
    unresolved_ids: set[str] = set()

    def collect_ids(payload: Any) -> set[str]:
        ids: set[str] = set()
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in {"evidence_ids", "citation_ids"} and isinstance(value, list):
                    ids.update(str(item) for item in value if isinstance(item, str))
                else:
                    ids.update(collect_ids(value))
        elif isinstance(payload, list):
            for item in payload:
                ids.update(collect_ids(item))
        return ids

    json_paths = [run_dir / "claim_matrix.json", run_dir / "outline.json", run_dir / "revision_plan.json"]
    for path in json_paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        used = collect_ids(payload)
        unresolved_ids.update(eid for eid in used if eid not in mapping and eid not in {item.get("evidence_id") for item in current_by_sig.values()})
        updated = _replace_ids(payload, mapping)
        if updated != payload:
            touched_files.append(str(path))
            if write:
                path.write_text(json.dumps(updated, indent=2, default=str), encoding="utf-8")

    sm_path = run_dir / "sentence_map.jsonl"
    if sm_path.exists():
        rows = load_jsonl_without_contract(sm_path)
        updated_rows = [_replace_ids(row, mapping) for row in rows]
        if updated_rows != rows:
            touched_files.append(str(sm_path))
            if write:
                sm_path.write_text("\n".join(json.dumps(row, default=str) for row in updated_rows) + "\n", encoding="utf-8")

    section_dir = run_dir / "section_drafts"
    if section_dir.exists():
        for md_path in sorted(section_dir.glob("*.md")):
            original = md_path.read_text(encoding="utf-8")
            updated = _rewrite_citations(original, mapping)
            if updated != original:
                touched_files.append(str(md_path))
                if write:
                    md_path.write_text(updated, encoding="utf-8")

    if write:
        contract = {
            "job_id": job_id,
            "evidence_ledger_hash": compute_evidence_ledger_hash(run_dir / "evidence_ledger.jsonl"),
            "source_registry_hash": compute_source_registry_hash(run_dir / "source_registry.json"),
        }
        for path in (run_dir / "claim_matrix.json", run_dir / "outline.json", run_dir / "sentence_map.jsonl"):
            if path.exists():
                # Stamping is a write, and it was invisible: touched_files is
                # only appended by the id-rewriting branches above, which do
                # nothing when the ids map one-to-one — the ordinary case since
                # source ids became content-derived. So the usual run rewrote
                # three of the author's artifacts and reported touching none.
                before = path.read_text(encoding="utf-8")
                write_artifact_contract(path, contract)
                if path.read_text(encoding="utf-8") != before:
                    touched_files.append(str(path))

    unmapped = sorted(unresolved_ids)
    return {
        "status": "ok" if not unmapped else "partial",
        "job_id": job_id,
        "previous_job_id": previous_job_id,
        "write": write,
        "mapped_count": len(mapping),
        "mapping": mapping,
        "unmapped_ids": unmapped,
        "files_touched": sorted(set(touched_files)),
    }
