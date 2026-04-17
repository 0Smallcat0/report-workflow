"""SECTION_DRAFT node - write prose using Claude writer agent."""
import json
import logging
import os
import anthropic
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..prompts.writer_prompt import get_writer_system_prompt, get_writer_user_prompt

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
logger = logging.getLogger(__name__)


def call_claude_writer(state: ReportState) -> dict:
    """Call Claude writer to draft sections."""
    client = anthropic.Anthropic()
    
    # Load evidence ledger
    evidence_ledger_path = state.sources.get("evidence_ledger_path")
    evidence_ledger = []
    if evidence_ledger_path:
        try:
            with open(evidence_ledger_path) as f:
                for line in f:
                    evidence_ledger.append(json.loads(line))
        except Exception:
            pass
    
    user_prompt = get_writer_user_prompt(
        state.plan.get("outline", {}),
        state.plan.get("claim_matrix", {}),
        evidence_ledger
    )
    
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=get_writer_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    response_text = response.content[0].text.strip()
    
    # Extract JSON
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.exception(
            "Claude writer returned malformed JSON; response preview=%r",
            response_text[:500],
        )
        raise ValueError("Claude writer returned malformed JSON") from e


def run_section_draft(state: ReportState) -> ReportState:
    """T10: SECTION_DRAFT - write prose for each section."""
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    section_drafts_dir = run_dir / "section_drafts"
    section_drafts_dir.mkdir(parents=True, exist_ok=True)
    
    sentence_map_entries = []
    
    try:
        result = call_claude_writer(state)
        sections = result.get("sections", {})
        
        for section_id, section_data in sections.items():
            content = section_data.get("content", "")
            
            # Write section markdown
            section_path = section_drafts_dir / f"{section_id}.md"
            with open(section_path, "w") as f:
                f.write(content)
            
            # Build sentence map entries
            sentences = section_data.get("sentences", [])
            for sent in sentences:
                entry = {
                    "sentence_id": f"sent_{len(sentence_map_entries)}",
                    "section_id": section_id,
                    "claim_ids": sent.get("claim_ids", []),
                    "evidence_ids": sent.get("evidence_ids", []),
                    "citation_ids": sent.get("citation_ids", []),
                    "wording_strength": sent.get("wording_strength", "strong"),
                    "revision_origin": "initial_draft"
                }
                sentence_map_entries.append(entry)
        
        state.drafts["section_drafts"] = {
            section_id: str(section_drafts_dir / f"{section_id}.md")
            for section_id in sections.keys()
        }
        
    except Exception as exc:
        logger.exception("SECTION_DRAFT failed; writing placeholder section drafts")
        state.runtime["error"] = f"SECTION_DRAFT failed: {type(exc).__name__}: {exc}"

        # Fallback: create minimal section if agent fails
        blueprint = state.plan.get("blueprint", {})
        section_order = blueprint.get("section_order", [])
        
        for section_id in section_order:
            content = f"# {section_id.title()}\n\nThis section is under development."
            section_path = section_drafts_dir / f"{section_id}.md"
            with open(section_path, "w") as f:
                f.write(content)
            
            state.drafts["section_drafts"][section_id] = str(section_path)
    
    # Write sentence map
    sentence_map_path = run_dir / "sentence_map.jsonl"
    with open(sentence_map_path, "w") as f:
        for entry in sentence_map_entries:
            f.write(json.dumps(entry) + "\n")
    
    state.drafts["sentence_map_path"] = str(sentence_map_path)
    
    return state
