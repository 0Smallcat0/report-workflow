"""CLAIM_PLAN node - map evidence to claims using Claude agent."""
import json
import os
import anthropic
from ..state import ReportState
from ..prompts.analyst_prompt import get_analyst_system_prompt, get_analyst_user_prompt

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


def call_claude_claim_plan(state: ReportState) -> dict:
    """Call Claude to map evidence to claims."""
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
    
    user_prompt = get_analyst_user_prompt(
        state.plan.get("blueprint", {}),
        evidence_ledger
    )
    
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        system=get_analyst_system_prompt(),
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


def run_claim_plan(state: ReportState) -> ReportState:
    """T8: CLAIM_PLAN - map evidence to claims using analyst agent."""
    try:
        result = call_claude_claim_plan(state)
        claims = result.get("claims", [])
        state.plan["claim_matrix"] = {"claims": claims}
    except Exception as e:
        # Fallback: create minimal claim matrix
        state.plan["claim_matrix"] = {"claims": []}
    
    return state
