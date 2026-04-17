"""INTAKE node - classify user intent using Claude agent."""
import json
import os
from pathlib import Path
from typing import Optional
import anthropic

from ..state import ReportState
from ..prompts.intake_prompt import get_intake_system_prompt, get_intake_user_prompt

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


def call_claude_intake(state: ReportState) -> dict:
    """Call Claude to classify intake."""
    client = anthropic.Anthropic()
    
    user_prompt = get_intake_user_prompt(
        state.spec.get("user_prompt", ""),
        state.spec.get("uploaded_files", [])
    )
    
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=get_intake_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    response_text = response.content[0].text.strip()
    # Extract JSON from response
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    
    return json.loads(response_text)


def run_intake(state: ReportState) -> ReportState:
    """T2: INTAKE - classify user intent and populate report_spec."""
    try:
        result = call_claude_intake(state)
        
        # Update spec with classified fields
        state.spec["task_intent"] = result.get("task_intent", "new_draft")
        state.spec["report_family"] = result.get("report_family", "academic_report")
        state.spec["delivery_mode"] = result.get("delivery_mode", "fresh_doc")
        state.spec["audience"] = result.get("audience", "expert")
        state.spec["citation_style"] = result.get("citation_style", "apa")
        state.spec["artifact_role_map"] = result.get("artifact_role_map", {})
        state.spec["report_family_detail"] = result.get("report_family_detail", "")
        state.spec["keywords"] = result.get("keywords", [])
        
        state.update_status("running")
    except Exception as e:
        # Fallback: use defaults
        state.spec["task_intent"] = "new_draft"
        state.spec["report_family"] = "academic_report"
        state.spec["delivery_mode"] = "fresh_doc"
        state.spec["audience"] = "expert"
        state.spec["citation_style"] = "apa"
        state.spec["artifact_role_map"] = {}
        state.spec["keywords"] = []
    
    return state
