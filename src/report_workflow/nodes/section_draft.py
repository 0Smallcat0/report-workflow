"""SECTION_DRAFT node - load agent-produced drafts and sentence map."""
import json
import re
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
from ..runtime_support import PLACEHOLDER_TEXT, run_dir_for
from ..state import ReportState
from ..artifact_contract import load_jsonl_without_contract, make_artifact_contract, validate_artifact_contract, write_artifact_contract
from .agent_tasks import write_agent_task_briefs
from .section_contract import planned_section_ids, section_requires_claims


STRUCTURED_DRAFTS_FILENAME = "structured_drafts.json"


def _load_jsonl(path: Path) -> list[dict]:
    try:
        rows = load_jsonl_without_contract(path)
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed sentence_map.jsonl: {exc}") from exc
    except OSError as exc:
        raise QAHardBlockError(f"Could not read sentence_map.jsonl: {exc}") from exc
    return rows


def _load_structured_drafts(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed {STRUCTURED_DRAFTS_FILENAME}: {exc}") from exc
    except OSError as exc:
        raise QAHardBlockError(f"Could not read {STRUCTURED_DRAFTS_FILENAME}: {exc}") from exc
    if not isinstance(payload, dict):
        raise QAHardBlockError(f"{STRUCTURED_DRAFTS_FILENAME} must be a JSON object")
    return payload


def _structured_sections(payload: dict) -> dict[str, dict]:
    raw_sections = payload.get("sections")
    if isinstance(raw_sections, dict):
        sections: dict[str, dict] = {}
        for section_id, section in raw_sections.items():
            if not isinstance(section, dict):
                raise QAHardBlockError(
                    f"{STRUCTURED_DRAFTS_FILENAME} section {section_id!r} must be an object"
                )
            sections[str(section_id)] = section
        return sections

    if isinstance(raw_sections, list):
        sections = {}
        for index, section in enumerate(raw_sections):
            if not isinstance(section, dict):
                raise QAHardBlockError(
                    f"{STRUCTURED_DRAFTS_FILENAME} sections[{index}] must be an object"
                )
            section_id = str(section.get("section_id") or "").strip()
            if not section_id:
                raise QAHardBlockError(
                    f"{STRUCTURED_DRAFTS_FILENAME} sections[{index}] missing section_id"
                )
            sections[section_id] = section
        return sections

    raise QAHardBlockError(f"{STRUCTURED_DRAFTS_FILENAME} must contain a sections object or list")


def _section_heading(section_id: str, section: dict) -> str:
    title = str(section.get("title") or section_id.replace("_", " ").title()).strip()
    return title or section_id.replace("_", " ").title()


def _as_list(value, field_name: str, section_id: str, sentence_index: int) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise QAHardBlockError(
            f"{STRUCTURED_DRAFTS_FILENAME} {section_id}.sentences[{sentence_index}].{field_name} must be a list"
        )
    return value


def _split_citation_ids(raw: str) -> list[str]:
    """Split one [CITE:...] payload into individual citation ids.

    Older structured-draft compilation emitted [CITE:id1,id2].  Downstream
    citation binders treat citations as individual evidence IDs, so normalize
    comma/semicolon-delimited payloads everywhere we compare or generate them.
    """
    return [part.strip() for part in re.split(r"[,;]", raw or "") if part.strip()]


def _sentence_text_with_citations(text: str, evidence_ids: list[str]) -> tuple[str, list[str]]:
    citation_ids = [str(eid).strip() for eid in evidence_ids if str(eid).strip()]
    if not citation_ids:
        return text.strip(), []

    existing = {
        cite_id
        for raw_marker in re.findall(r"\[CITE:([^\]]+)\]", text)
        for cite_id in _split_citation_ids(raw_marker)
    }
    missing = [eid for eid in citation_ids if eid not in existing]
    if not missing:
        return text.strip(), citation_ids

    cite_marker = " ".join(f"[CITE:{eid}]" for eid in missing)
    stripped = text.strip()
    if stripped.endswith((".", "!", "?", "\u3002", "\uff01", "\uff1f")):
        return stripped[:-1].rstrip() + f" {cite_marker}" + stripped[-1], citation_ids
    return f"{stripped} {cite_marker}", citation_ids


def _compile_structured_drafts(state: ReportState, section_order: list[str]) -> None:
    """Compile structured_drafts.json into canonical section drafts and sentence_map."""
    run_dir = run_dir_for(state)
    structured_path = run_dir / STRUCTURED_DRAFTS_FILENAME
    if not structured_path.exists():
        return

    payload = _load_structured_drafts(structured_path)
    validate_artifact_contract(state, structured_path, allow_missing=True)
    sections = _structured_sections(payload)
    blueprint = state.plan.get("blueprint") or {}
    section_drafts_dir = run_dir / "section_drafts"
    section_drafts_dir.mkdir(exist_ok=True)

    sentence_rows: list[dict] = []
    missing_sections = [section_id for section_id in section_order if section_id not in sections]
    if missing_sections:
        raise QAHardBlockError(
            f"{STRUCTURED_DRAFTS_FILENAME} missing planned sections: {missing_sections}"
        )

    for section_id in section_order:
        section = sections[section_id]
        raw_sentences = section.get("sentences")
        if not isinstance(raw_sentences, list):
            raise QAHardBlockError(
                f"{STRUCTURED_DRAFTS_FILENAME} section {section_id!r} must contain a sentences list"
            )
        if not raw_sentences and section_requires_claims(blueprint, section_id):
            raise QAHardBlockError(
                f"{STRUCTURED_DRAFTS_FILENAME} section {section_id!r} has no sentences"
            )

        lines = [f"# {_section_heading(section_id, section)}", ""]
        for sentence_index, sentence in enumerate(raw_sentences):
            if not isinstance(sentence, dict):
                raise QAHardBlockError(
                    f"{STRUCTURED_DRAFTS_FILENAME} {section_id}.sentences[{sentence_index}] must be an object"
                )
            raw_text = str(sentence.get("text") or "").strip()
            if not raw_text:
                raise QAHardBlockError(
                    f"{STRUCTURED_DRAFTS_FILENAME} {section_id}.sentences[{sentence_index}] missing text"
                )

            claim_ids = [str(item) for item in _as_list(sentence.get("claim_ids"), "claim_ids", section_id, sentence_index)]
            evidence_ids = [str(item) for item in _as_list(sentence.get("evidence_ids"), "evidence_ids", section_id, sentence_index)]
            citation_ids = [str(item) for item in _as_list(sentence.get("citation_ids"), "citation_ids", section_id, sentence_index)]
            text, auto_citations = _sentence_text_with_citations(raw_text, citation_ids or evidence_ids)
            citation_ids = citation_ids or auto_citations
            lines.append(text)
            lines.append("")

            if claim_ids or evidence_ids or citation_ids:
                sentence_rows.append({
                    "sentence_id": sentence.get("sentence_id") or f"{section_id}_{sentence_index + 1}",
                    "section_id": section_id,
                    "claim_ids": claim_ids,
                    "evidence_ids": evidence_ids,
                    "citation_ids": citation_ids,
                    "wording_strength": sentence.get("wording_strength", "hedged"),
                    "draft_origin": "structured_draft",
                })

        draft_path = section_drafts_dir / f"{section_id}.md"
        draft_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if not sentence_rows:
        raise QAHardBlockError(f"{STRUCTURED_DRAFTS_FILENAME} produced an empty sentence_map")

    sentence_map_path = run_dir / "sentence_map.jsonl"
    sentence_map_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in sentence_rows) + "\n",
        encoding="utf-8",
    )
    contract = make_artifact_contract(state)
    write_artifact_contract(sentence_map_path, contract)
    write_artifact_contract(structured_path, contract)
    state.runtime["structured_drafts_compiled_path"] = str(structured_path)


def run_section_draft(state: ReportState) -> ReportState:
    """T10: SECTION_DRAFT - load agent-authored section Markdown and sentence map."""
    run_dir = run_dir_for(state)
    section_drafts_dir = run_dir / "section_drafts"
    sentence_map_path = run_dir / "sentence_map.jsonl"
    section_order = planned_section_ids(state.plan.get("blueprint") or {}, state.plan.get("outline") or {})

    structured_path = run_dir / STRUCTURED_DRAFTS_FILENAME
    canonical_missing = (
        not section_drafts_dir.exists()
        or not sentence_map_path.exists()
        or any(not (section_drafts_dir / f"{section_id}.md").exists() for section_id in section_order)
    )
    # Re-authoring: when structured_drafts.json is newer than the compiled
    # sentence map, the agent has rewritten it since the last compile; the
    # stale compiled drafts must not stay canonical (previously an edited
    # structured_drafts silently had no effect and even
    # `invalidate-cache --drafts` could not help).
    structured_stale_recompile = (
        structured_path.exists()
        and sentence_map_path.exists()
        and structured_path.stat().st_mtime > sentence_map_path.stat().st_mtime
    )
    if (canonical_missing or structured_stale_recompile) and structured_path.exists():
        _compile_structured_drafts(state, section_order)

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

    revise_mode = state.spec.get("task_intent") == "revise_existing"
    section_paths = {}
    for section_id in section_order:
        path = section_drafts_dir / f"{section_id}.md"
        if not path.exists():
            if revise_mode:
                # In revise_existing the authoring surface is
                # revision_plan.json and section drafts are never merged;
                # requiring a draft file per outline section contradicted the
                # revision contract. Register the section id so sentence-map
                # entries can still anchor to it.
                section_paths[section_id] = ""
                continue
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
    validate_artifact_contract(state, sentence_map_path, allow_missing=True)
    if not sentence_map_entries:
        raise QAHardBlockError("sentence_map.jsonl must contain at least one entry")
    known_claims = {
        claim.get("claim_id")
        for claim in state.plan.get("claim_matrix", {}).get("claims", [])
        if claim.get("claim_id")
    }
    known_evidence = {
        eid
        for claim in state.plan.get("claim_matrix", {}).get("claims", [])
        for eid in claim.get("evidence_ids", [])
    }
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
        unknown_claims = sorted(cid for cid in entry.get("claim_ids", []) if cid not in known_claims)
        if unknown_claims:
            raise QAHardBlockError(f"sentence_map entry {index} references unknown claims: {', '.join(unknown_claims)}")
        unknown_evidence = sorted(eid for eid in entry.get("evidence_ids", []) if known_evidence and eid not in known_evidence)
        if unknown_evidence:
            raise QAHardBlockError(
                f"sentence_map entry {index} references evidence IDs outside claim_matrix/current run: "
                + ", ".join(unknown_evidence)
                + f". Run `report-workflow remap-evidence --from-job <old> --to-job {state.job_id} --write` "
                "or rebuild sentence_map.jsonl from this run."
            )

    state.drafts["section_drafts"] = section_paths
    state.drafts["sentence_map_path"] = str(sentence_map_path)
    write_artifact_contract(sentence_map_path, make_artifact_contract(state))
    return state
