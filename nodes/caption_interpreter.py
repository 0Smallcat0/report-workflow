"""CAPTION_INTERPRETER - Agent node: generates figure captions using Claude."""
import json
import os
import anthropic
from pathlib import Path


ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


CAPTION_SYSTEM_PROMPT = """You are a scientific figure caption writer. Your task is to write clear, concise, 
and informative captions for scientific figures based on the provided figure contract information.

Guidelines for writing captions:
1. Start with a brief title that describes what the figure shows
2. Describe the key finding or relationship illustrated
3. Include methodological context (e.g., "Data from X studies", "Comparison of Y groups")
4. Keep it concise but informative (typically 2-4 sentences)
5. Use past tense for completed studies, present tense for ongoing displays
6. Do NOT interpret beyond what the data shows

IMPORTANT: Only write the caption text. Do not decide chart types or suggest modifications.
The chart type has already been determined by the system."""

CAPTION_USER_PROMPT = """Write a caption for a figure with the following contract:

Chart Type: {chart_type}
Claim ID: {claim_id}
Evidence Grade: {evidence_grade}
Required Data Fields: {required_fields}

Additional Context:
{context}

Write only the caption text, no additional explanation."""


def caption_interpreter(figure_contracts: list[dict], claim_matrix: dict = None) -> list[dict]:
    """Generate draft captions for each figure using Claude.
    
    This is the only AGENT node in T21. It calls Claude to write captions
    from the figure contract - it does NOT decide chart type.
    
    Args:
        figure_contracts: List of figure contract dicts
        claim_matrix: Optional claim matrix for context
    
    Returns:
        List of dicts with figure_number, caption, and contract
    """
    client = anthropic.Anthropic()
    
    captions = []
    
    for idx, contract in enumerate(figure_contracts):
        chart_type = contract.get("chart_type", "")
        claim_id = contract.get("claim_id", "")
        evidence_grade = contract.get("evidence_grade", "unknown")
        required_fields = contract.get("required_fields", [])
        
        # Build context from claim matrix if available
        context = f"Claim ID: {claim_id}\n"
        if claim_matrix:
            claim = claim_matrix.get(claim_id, {})
            claim_type = claim.get("claim_type", "")
            description = claim.get("description", "")
            context += f"Claim Type: {claim_type}\n"
            context += f"Description: {description}\n"
        
        user_prompt = CAPTION_USER_PROMPT.format(
            chart_type=chart_type,
            claim_id=claim_id,
            evidence_grade=evidence_grade,
            required_fields=", ".join(required_fields),
            context=context
        )
        
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=512,
                system=CAPTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            caption_text = response.content[0].text.strip()
            
            captions.append({
                "figure_number": idx + 1,
                "caption": caption_text,
                "contract": contract
            })
            
        except Exception as e:
            # Fallback caption if agent fails
            captions.append({
                "figure_number": idx + 1,
                "caption": f"Figure {idx + 1}: {chart_type.replace('_', ' ').title()}",
                "contract": contract,
                "error": str(e)
            })
    
    return captions
