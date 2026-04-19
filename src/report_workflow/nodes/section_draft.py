"""SECTION_DRAFT node - load agent-produced drafts and sentence map."""
import json
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
from ..runtime_support import PLACEHOLDER_TEXT, run_dir_for
from ..state import ReportState
from .agent_tasks import write_agent_task_briefs
from .section_contract import planned_section_ids


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise QAHardBlockError(f"Malformed sentence_map.jsonl line {line_number}: {exc}") from exc
    except OSError as exc:
        raise QAHardBlockError(f"Could not read sentence_map.jsonl: {exc}") from exc
    return rows


def run_section_draft(state: ReportState) -> ReportState:
    """T10: SECTION_DRAFT - load agent-authored section Markdown and sentence map."""
    run_dir = run_dir_for(state)
    section_drafts_dir = run_dir / "section_drafts"
    sentence_map_path = run_dir / "sentence_map.jsonl"

    missing = []
    if not section_drafts_dir.exists():
        missing.append(str(section_drafts_dir))
    if not sentence_map_path.exists():
        missing.append(str(sentence_map_path))
    if missing:
        write_agent_task_briefs(state)
        state.runtime["required_agent_artifacts"] = missing
        state.update_status("awaiting_agent_artifacts")
        raise AgentWorkRequired("Agent section draft artifacts are required", missing)

    section_order = planned_section_ids(state.plan.get("blueprint") or {}, state.plan.get("outline") or {})
    section_paths = {}
    for section_id in section_order:
        path = section_drafts_dir / f"{section_id}.md"
        if not path.exists():
            missing.append(str(path))
            continue
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise QAHardBlockError(f"Section draft is empty: {section_id}")
        if PLACEHOLDER_TEXT in text:
            raise QAHardBlockError(f"Section draft is placeholder content: {section_id}")
        section_paths[section_id] = str(path)

    if missing:
        write_agent_task_briefs(state)
        state.runtime["required_agent_artifacts"] = missing
        state.update_status("awaiting_agent_artifacts")
        raise AgentWorkRequired("Agent section draft artifacts are incomplete", missing)

    sentence_map_entries = _load_jsonl(sentence_map_path)
    if not sentence_map_entries:
        raise QAHardBlockError("sentence_map.jsonl must contain at least one entry")
    for index, entry in enumerate(sentence_map_entries):
        if not isinstance(entry, dict):
            raise QAHardBlockError(f"sentence_map entry {index} must be an object")
        section_id = entry.get("section_id")
        if not section_id:
            raise QAHardBlockError(f"sentence_map entry {index} missing section_id")
        if section_id not in section_paths:
            raise QAHardBlockError(f"sentence_map entry {index} references unknown section: {section_id}")
        if not isinstance(entry.get("claim_ids", []), list):
            raise QAHardBlockError(f"sentence_map entry {index} claim_ids must be a list")
        if not isinstance(entry.get("evidence_ids", []), list):
            raise QAHardBlockError(f"sentence_map entry {index} evidence_ids must be a list")

    state.drafts["section_drafts"] = section_paths
    state.drafts["sentence_map_path"] = str(sentence_map_path)
    return state
