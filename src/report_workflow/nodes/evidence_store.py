"""EVIDENCE_STORE - build a lightweight evidence index manifest."""
import json
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR


def run_evidence_store(state: ReportState) -> ReportState:
    """Build a queryable manifest over evidence_ledger.jsonl."""
    evidence_path = state.sources.get("evidence_ledger_path")
    if not evidence_path or not Path(evidence_path).exists():
        raise QAHardBlockError("Cannot build evidence store without evidence ledger")

    evidence = []
    with open(evidence_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                evidence.append(json.loads(line))

    if not evidence:
        raise QAHardBlockError("Cannot build evidence store from empty evidence ledger")

    by_source: dict[str, list[str]] = {}
    by_type: dict[str, list[str]] = {}
    by_grade: dict[str, list[str]] = {}
    all_topic_tags: set[str] = set()
    for item in evidence:
        evidence_id = item.get("evidence_id", "")
        by_source.setdefault(item.get("source_id", ""), []).append(evidence_id)
        by_type.setdefault(item.get("evidence_type", "unknown"), []).append(evidence_id)
        by_grade.setdefault(item.get("evidence_grade", "unknown"), []).append(evidence_id)
        for tag in item.get("topic_tags", []):
            all_topic_tags.add(tag)

    manifest = {
        "job_id": state.job_id,
        "evidence_ledger_path": evidence_path,
        "evidence_count": len(evidence),
        "by_source": by_source,
        "by_type": by_type,
        "by_grade": by_grade,
        "topic_tags": sorted(all_topic_tags),
    }

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "evidence_store_manifest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    state.sources["evidence_store_manifest_path"] = str(path)
    return state
