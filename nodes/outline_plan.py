"""OUTLINE_PLAN node - assign claims to sections using Claude agent."""
import json
import os
import anthropic
from ..state import ReportState

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

OUTLINE_SYSTEM_PROMPT = """You are an expert report outliner.

Given a claim matrix and blueprint, assign claims to sections and determine paragraph structure.

## Output Format
Return a JSON object:
{
  "sections": {
    "section_id": {
      "section_id": "string",
      "goals": "what this section should accomplish",
      "claim_ids": ["claim_id1", "claim_id2"],
      "paragraph_order": ["paragraph description 1", "paragraph description 2"],
      "figure_ids": []
    }
  }
}

## Rules
- Assign each claim to the most relevant section
- Determine logical paragraph order within each section
- figure_ids should be empty in Phase 1 (stub)
- Keep goals concise and actionable"""


def call_claude_outline_plan(state: ReportState) -> dict:
    """Call Claude to create outline from claim matrix."""
    client = anthropic.Anthropic()
    
    claim_matrix = state.plan.get("claim_matrix", {})
    blueprint = state.plan.get("blueprint", {})
    
    user_prompt = f"""## Blueprint
{json.dumps(blueprint, indent=2)}

## Claim Matrix
{json.dumps(claim_matrix, indent=2)}

## Task
Assign claims to sections and create paragraph structure. Output the outline JSON."""

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        system=OUTLINE_SYSTEM_PROMPT,
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
    
    return json.loads(response_text)


def run_outline_plan(state: ReportState) -> ReportState:
    """T9: OUTLINE_PLAN - assign claims to sections."""
    try:
        result = call_claude_outline_plan(state)
        state.plan["outline"] = result
    except Exception:
        # Fallback: empty outline
        state.plan["outline"] = {"sections": {}}
    
    return state
