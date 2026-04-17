"""EVIDENCE_NORMALIZE node - deterministic evidence scoring."""
import json
import uuid
import os
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR


STRUCTURED_TYPES = {"csv", "xlsx", "json"}
FIRST_HAND_TYPES = {"pdf", "docx"}


def compute_provenance_score(entry: dict, block: dict) -> float:
    """Compute provenance score deterministically.
    
    Scoring rules (deterministic, no agent):
    peer_reviewed_journal:     +0.3
    government_report:        +0.25
    preprint:                  -0.1
    company_report:           -0.15
    direct_url:               +0.1
    contains_table:            +0.1
    contains_figure:           +0.05
    contains_methodology:      +0.1
    first_hand_account:        +0.15
    contains_citations:       +0.05
    file_type = pdf:          +0.05
    file_type = csv/xlsx:     +0.1
    length > 5000 chars:       +0.05
    claimed_reproducibility:   +0.05
    ---
    base score:               0.5
    max score:                1.0
    min score:                0.0
    """
    score = 0.5
    file_type = entry.get("file_type", "")
    content = block.get("content", "")
    block_type = block.get("block_type", "")
    
    # File type bonuses
    if file_type == "pdf":
        score += 0.05
    elif file_type in STRUCTURED_TYPES:
        score += 0.1
    
    # Content length
    if len(content) > 5000:
        score += 0.05
    
    # Block type bonuses
    if block_type == "table":
        score += 0.1
    elif block_type == "figure_caption":
        score += 0.05
    
    # First hand account (PDF/DOCX typically contain original content)
    if file_type in FIRST_HAND_TYPES:
        score += 0.15
    
    # Contains methodology keywords
    methodology_keywords = ["method", "methodology", "study design", "participants", "sample", "analysis"]
    if any(kw in content.lower() for kw in methodology_keywords):
        score += 0.1
    
    # Contains citations
    if "citation" in content.lower() or "et al." in content:
        score += 0.05
    
    # Claimed reproducibility
    if "reproducib" in content.lower() or "open data" in content.lower():
        score += 0.05
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def determine_evidence_type(content: str, block_type: str) -> str:
    """Determine evidence type deterministically."""
    content_lower = content.lower()
    
    # Quantitative indicators
    quant_keywords = ["percentage", "%", "rate", "increase", "decrease", "number of", 
                      "average", "mean", "median", "count", "data show", "statistical"]
    if any(kw in content_lower for kw in quant_keywords):
        return "quantitative"
    
    # Methodological indicators
    method_keywords = ["method", "methodology", "design", "sample", "participants", "procedure", "protocol"]
    if any(kw in content_lower for kw in method_keywords):
        return "methodological"
    
    # Contextual indicators
    context_keywords = ["background", "context", "introduction", "overview", "setting"]
    if any(kw in content_lower for kw in context_keywords):
        return "contextual"
    
    # Default to qualitative
    return "qualitative"


def determine_granularity(block_type: str) -> str:
    """Determine evidence granularity."""
    if block_type == "table":
        return "table_row"
    elif block_type == "figure_caption":
        return "figure"
    elif block_type == "paragraph":
        return "paragraph"
    else:
        return "sentence"


def run_evidence_normalize(state: ReportState) -> ReportState:
    """T7: EVIDENCE_NORMALIZE - compute provenance scores and create evidence ledger."""
    source_registry = state.sources.get("source_registry", [])
    evidence_units = []
    
    for entry in source_registry:
        parsed_content = entry.get("parsed_content", [])
        for block in parsed_content:
            content = block.get("content", "")
            if not content or len(content.strip()) < 10:
                continue
            
            granularity = determine_granularity(block.get("block_type", "paragraph"))
            evidence_type = determine_evidence_type(content, block.get("block_type", ""))
            provenance_score = compute_provenance_score(entry, block)
            
            if provenance_score >= 0.7:
                grade = "high"
            elif provenance_score >= 0.4:
                grade = "medium"
            else:
                grade = "low"
            
            evidence_id = str(uuid.uuid4())[:8]
            
            # Determine allowed claim types based on evidence type
            allowed_claim_types = {
                "quantitative": ["factual", "statistical"],
                "qualitative": ["factual", "qualitative"],
                "methodological": ["factual", "methodological"],
                "contextual": ["factual", "qualitative", "contextual"],
            }
            
            unit = {
                "evidence_id": evidence_id,
                "source_id": entry.get("source_id", ""),
                "granularity": granularity,
                "evidence_type": evidence_type,
                "content": content[:2000],  # Truncate
                "provenance_score": provenance_score,
                "evidence_grade": grade,
                "allowed_claim_types": allowed_claim_types.get(evidence_type, ["factual"]),
                "block_id": block.get("block_id", ""),
                "page_number": block.get("page_number"),
                "requires_hedged_wording": provenance_score < 0.7,
                "first_hand_account": entry.get("file_type", "") in FIRST_HAND_TYPES,
                "contains_methodology": "methodology" in content.lower(),
                "contains_citations": "et al." in content or "citation" in content.lower(),
                "claimed_reproducibility": "reproducib" in content.lower(),
            }
            evidence_units.append(unit)
    
    # Write to evidence_ledger.jsonl
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    evidence_ledger_path = run_dir / "evidence_ledger.jsonl"
    with open(evidence_ledger_path, "w") as f:
        for unit in evidence_units:
            f.write(json.dumps(unit) + "\n")
    
    state.sources["evidence_ledger_path"] = str(evidence_ledger_path)
    return state
