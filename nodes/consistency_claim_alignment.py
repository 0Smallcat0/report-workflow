"""CONSISTENCY_CLAIM_ALIGNMENT - Claim strength vs evidence grade alignment."""
import json
import re
from pathlib import Path
from typing import Optional


# Keywords indicating claim strength
CLAIM_STRENGTH_KEYWORDS = {
    "superlative": ["proves", "demonstrates conclusively", "establishes definitively", 
                   "confirms unequivocally", "determines absolutely"],
    "high": ["significant", "dramatically", "strongly", "clearly", "markedly",
             "substantially", "notably", "considerably"],
    "moderate": ["suggests", "indicates", "appears", "demonstrates",
                 "provides evidence", "shows", "reveals"],
    "hedged": ["may", "might", "could", "possibly", "potentially", "perhaps"]
}

# Evidence grades
EVIDENCE_GRADES = ["high", "moderate", "low"]


def extract_claim_strength(sentence: str) -> tuple[str, list[str]]:
    """Extract claim strength level and keywords from sentence.
    
    Returns (strength_level, matched_keywords)
    """
    sentence_lower = sentence.lower()
    
    matched = []
    for level, keywords in CLAIM_STRENGTH_KEYWORDS.items():
        for keyword in keywords:
            if keyword in sentence_lower:
                matched.append(keyword)
    
    if not matched:
        return "neutral", []
    
    # Determine highest level
    if any(kw in matched for kw in CLAIM_STRENGTH_KEYWORDS["superlative"]):
        return "superlative", matched
    elif any(kw in matched for kw in CLAIM_STRENGTH_KEYWORDS["high"]):
        return "high", matched
    elif any(kw in matched for kw in CLAIM_STRENGTH_KEYWORDS["moderate"]):
        return "moderate", matched
    else:
        return "hedged", matched


def claim_alignment_checker(
    merged_draft_path: str,
    claim_matrix_path: str
) -> list[dict]:
    """Check if claim strength aligns with evidence grade."""
    issues = []
    
    if not Path(merged_draft_path).exists():
        return issues
    
    with open(merged_draft_path) as f:
        text = f.read()
    
    # Load claim matrix
    claim_matrix = {}
    if Path(claim_matrix_path).exists():
        try:
            with open(claim_matrix_path) as f:
                data = json.load(f)
                for claim in data.get("claims", []):
                    claim_matrix[claim["claim_id"]] = claim
        except Exception:
            pass
    
    # Extract figure captions and table footnotes
    caption_pattern = r'\*\*Figure\s+\d+[:.]?\s*(.+?)\*\*'
    footnote_pattern = r'\*\*Table\s+\d+[:.]?\s*(.+?)\*\*'
    
    # Find all sentences in captions and footnotes
    captions = re.findall(caption_pattern, text, re.DOTALL)
    footnotes = re.findall(footnote_pattern, text, re.DOTALL)
    
    all_captions = " ".join(captions) + " ".join(footnotes)
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', all_captions)
    
    for sent_idx, sentence in enumerate(sentences):
        if not sentence.strip():
            continue
        
        strength, keywords = extract_claim_strength(sentence)
        
        if not keywords:
            continue
        
        # Map to evidence grade
        if strength == "superlative":
            required_grade = "high"
        elif strength == "high":
            required_grade = "high"
        elif strength == "moderate":
            required_grade = "moderate"
        else:
            required_grade = "low"  # hedged claims work with any grade
        
        # Find associated claim if any
        # Simple heuristic: look for claim_id in sentence
        claim_refs = re.findall(r'claim[_-]?(\d+)', sentence.lower())
        
        for ref in claim_refs:
            claim_id = f"claim_{ref}"
            if claim_id in claim_matrix:
                evidence_grade = claim_matrix[claim_id].get("evidence_grade", "moderate")
                
                # Check alignment
                grade_rank = {"high": 3, "moderate": 2, "low": 1}
                req_rank = grade_rank.get(required_grade, 2)
                ev_rank = grade_rank.get(evidence_grade, 2)
                
                if strength == "superlative" and ev_rank < 3:
                    issues.append({
                        "location": f"caption_sent_{sent_idx}",
                        "problem": f"Superlative claim keyword '{keywords[0]}' used but evidence grade is {evidence_grade}",
                        "severity": "high",
                        "check": "claim_alignment"
                    })
                elif strength == "high" and ev_rank < 3:
                    issues.append({
                        "location": f"caption_sent_{sent_idx}",
                        "problem": f"High-strength keyword '{keywords[0]}' used but evidence grade is {evidence_grade}",
                        "severity": "medium",
                        "check": "claim_alignment"
                    })
    
    return issues
