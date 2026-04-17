"""GAP_ANALYSIS - Agent node: analyzes claim matrix to find evidence gaps."""
import json
import os
import anthropic
from pathlib import Path


ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


GAP_ANALYSIS_PROMPT = """You are a research gap analyzer. Your task is to analyze claims from a report 
and identify gaps in the evidence that could be filled by additional research.

For each claim, determine:
1. Is there supporting evidence present?
2. What type of gap exists (corroborating, opposing, statistical support)?
3. What kind of additional evidence would strengthen the claim?

Output a JSON array of gap analysis objects with the following structure:
{{
  "claim_id": "claim_1",
  "gap_type": "corroborating_evidence|opposing_evidence|statistical_support",
  "gap_description": "Brief description of the gap",
  "suggested_search_terms": ["term1", "term2", "term3"],
  "priority": "high|medium|low"
}}

Return ONLY the JSON array, no additional text."""


def gap_analysis(claim_matrix_path: str) -> list[dict]:
    """Analyze claim matrix to find evidence gaps.
    
    This is an AGENT node that uses Claude to analyze the claim matrix
    and identify where additional research might be needed.
    
    Args:
        claim_matrix_path: Path to claim_matrix.json
    
    Returns:
        List of gap analysis dicts per claim
    """
    client = anthropic.Anthropic()
    
    # Load claim matrix
    claim_matrix = {}
    if claim_matrix_path and Path(claim_matrix_path).exists():
        try:
            with open(claim_matrix_path) as f:
                data = json.load(f)
                for claim in data.get("claims", []):
                    claim_matrix[claim["claim_id"]] = claim
        except Exception:
            pass
    
    if not claim_matrix:
        return []
    
    # Build summary for the agent
    claims_summary = []
    for claim_id, claim in claim_matrix.items():
        claims_summary.append({
            "claim_id": claim_id,
            "claim_type": claim.get("claim_type", ""),
            "description": claim.get("description", ""),
            "evidence_grade": claim.get("evidence_grade", "unknown"),
            "evidence_count": len(claim.get("evidence_ids", [])),
            "status": claim.get("status", "unknown")
        })
    
    user_prompt = f"""Analyze the following claims and identify evidence gaps:

{json.dumps(claims_summary, indent=2)}

For each claim, determine the gap type:
- corroborating_evidence: Need more studies supporting the same conclusion
- opposing_evidence: Need studies with different/contradicting findings
- statistical_support: Need better statistical evidence (larger sample, better tests)

Return ONLY the JSON array."""
    
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=GAP_ANALYSIS_PROMPT,
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
        
        gap_analysis = json.loads(response_text)
        return gap_analysis
        
    except Exception as e:
        # Fallback: generate simple gap analysis without agent
        return _fallback_gap_analysis(claim_matrix)


def _fallback_gap_analysis(claim_matrix: dict) -> list[dict]:
    """Fallback gap analysis when agent fails."""
    gaps = []
    
    for claim_id, claim in claim_matrix.items():
        evidence_count = len(claim.get("evidence_ids", []))
        evidence_grade = claim.get("evidence_grade", "unknown")
        
        if evidence_count == 0:
            gap_type = "corroborating_evidence"
            priority = "high"
        elif evidence_grade in ["low", "unknown"]:
            gap_type = "statistical_support"
            priority = "medium"
        else:
            # We have evidence but might still need more
            gap_type = "corroborating_evidence"
            priority = "low"
        
        gaps.append({
            "claim_id": claim_id,
            "gap_type": gap_type,
            "gap_description": f"Need additional evidence to support claim {claim_id}",
            "suggested_search_terms": [claim.get("claim_type", "research")],
            "priority": priority
        })
    
    return gaps
