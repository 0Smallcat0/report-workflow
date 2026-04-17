"""RESEARCH_RETRIEVE - Phase 2: T22 - Retrieve additional research to fill evidence gaps."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .gap_analysis import gap_analysis
from .query_plan import query_plan

# Import adapters
try:
    from ..connectors.pubmed_adapter import search_pubmed
    from ..connectors.arxiv_adapter import search_arxiv
    from ..connectors.openalex_adapter import search_openalex
except ImportError:
    # Fallback if connectors not available
    search_pubmed = None
    search_arxiv = None
    search_openalex = None


def normalize_to_evidence_unit(hit: dict) -> dict:
    """Normalize a search hit to the evidence_unit format.
    
    Args:
        hit: Dict from search adapter with source-specific fields
    
    Returns:
        Normalized evidence unit dict
    """
    source = hit.get("source", "")
    
    evidence_unit = {
        "evidence_id": f"imported_{source}_{hit.get(f'{source}_id', 'unknown')}",
        "source": source,
        "source_id": hit.get(f"{source}_id", hit.get("openalex_id", "")),
        "title": hit.get("title", ""),
        "authors": hit.get("authors", []),
        "publication_date": hit.get("pub_date", ""),
        "abstract": hit.get("abstract", ""),
        "url": hit.get("url", ""),
        "evidence_type": "imported",
        "imported_from": source,
        "relevance_score": 0.5  # Default score
    }
    
    # Add source-specific fields
    if source == "pubmed":
        evidence_unit["pmid"] = hit.get("pmid", "")
        evidence_unit["journal"] = hit.get("journal", "")
        evidence_unit["doi"] = hit.get("doi", "")
    elif source == "arxiv":
        evidence_unit["arxiv_id"] = hit.get("arxiv_id", "")
        evidence_unit["comments"] = hit.get("comments", "")
        evidence_unit["journal_ref"] = hit.get("journal_ref", "")
        evidence_unit["primary_category"] = hit.get("primary_category", "")
    elif source == "openalex":
        evidence_unit["openalex_id"] = hit.get("openalex_id", "")
        evidence_unit["citation_count"] = hit.get("citation_count", 0)
        evidence_unit["open_access"] = hit.get("open_access", False)
    
    return evidence_unit


def verify_claim_with_evidence(claim: dict, evidence_units: list[dict]) -> str:
    """Compare imported evidence against claim to determine if it supports.
    
    Args:
        claim: Claim dict from claim matrix
        evidence_units: List of normalized evidence units
    
    Returns:
        Updated status: "supported", "partially_supported", or "unsupported"
    """
    if not evidence_units:
        return claim.get("status", "unsupported")
    
    # Simple verification based on presence of relevant evidence
    # In a real implementation, this would do semantic matching
    
    claim_keywords = claim.get("claim_type", "").lower().split()
    evidence_texts = [" ".join([e.get("title", ""), e.get("abstract", "")]).lower() 
                      for e in evidence_units]
    
    # Check if any evidence contains claim keywords
    matches = 0
    for keywords in claim_keywords:
        for text in evidence_texts:
            if keywords in text:
                matches += 1
                break
    
    if matches >= len(claim_keywords) * 0.5:
        return "supported"
    elif matches > 0:
        return "partially_supported"
    else:
        return claim.get("status", "unsupported")


def run_research_retrieve(
    report_spec_path: str,
    claim_matrix_path: str,
    evidence_ledger_path: str,
    selected_guidelines: list[str],
) -> dict:
    """T22: Retrieve additional research to fill evidence gaps.
    
    Steps:
    1. gap_analysis (AGENT) - Find claims with missing evidence
    2. query_plan (AGENT-ASSISTED) - Construct DB-specific queries
    3. Retrieval Adapters - Search PubMed, arXiv, OpenAlex
    4. Evidence Import - Normalize and import findings
    5. Claim Re-verification - Update claim statuses
    
    Args:
        report_spec_path: Path to report_spec.json
        claim_matrix_path: Path to claim_matrix.json
        evidence_ledger_path: Path to evidence_ledger.jsonl
        selected_guidelines: List of selected guidelines
    
    Returns:
        dict with paths to research_results.json, imported_evidence.jsonl, etc.
    """
    timestamp = datetime.now().isoformat()
    
    # Load report spec
    report_spec = {}
    if report_spec_path and Path(report_spec_path).exists():
        try:
            with open(report_spec_path) as f:
                report_spec = json.load(f)
        except Exception:
            pass
    
    # Load existing evidence ledger
    existing_evidence = []
    if evidence_ledger_path and Path(evidence_ledger_path).exists():
        try:
            with open(evidence_ledger_path) as f:
                for line in f:
                    existing_evidence.append(json.loads(line))
        except Exception:
            pass
    
    # Step 1: Gap analysis (AGENT)
    gaps = gap_analysis(claim_matrix_path)
    
    # Step 2: Query plan (AGENT-ASSISTED)
    queries = query_plan(gaps, report_spec)
    
    # Step 3: Retrieval from all databases
    all_results = []
    imported_evidence = []
    
    for query_entry in queries:
        claim_id = query_entry.get("claim_id", "")
        
        # Search each database
        pubmed_query = query_entry.get("pubmed_query", "")
        arxiv_query = query_entry.get("arxiv_query", "")
        openalex_query = query_entry.get("openalex_query", "")
        
        # Search PubMed
        if search_pubmed and pubmed_query:
            try:
                pubmed_results = search_pubmed(pubmed_query, max_results=5)
                for hit in pubmed_results:
                    hit["claim_id"] = claim_id
                    all_results.append(hit)
                    imported_evidence.append(normalize_to_evidence_unit(hit))
            except Exception as e:
                print(f"[ResearchRetrieve] PubMed search error: {e}")
        
        # Search arXiv
        if search_arxiv and arxiv_query:
            try:
                arxiv_results = search_arxiv(arxiv_query, max_results=5)
                for hit in arxiv_results:
                    hit["claim_id"] = claim_id
                    all_results.append(hit)
                    imported_evidence.append(normalize_to_evidence_unit(hit))
            except Exception as e:
                print(f"[ResearchRetrieve] arXiv search error: {e}")
        
        # Search OpenAlex
        if search_openalex and openalex_query:
            try:
                openalex_results = search_openalex(openalex_query, max_results=5)
                for hit in openalex_results:
                    hit["claim_id"] = claim_id
                    all_results.append(hit)
                    imported_evidence.append(normalize_to_evidence_unit(hit))
            except Exception as e:
                print(f"[ResearchRetrieve] OpenAlex search error: {e}")
    
    # Step 4: Load claim matrix for verification
    claim_matrix = {}
    if claim_matrix_path and Path(claim_matrix_path).exists():
        try:
            with open(claim_matrix_path) as f:
                data = json.load(f)
                for claim in data.get("claims", []):
                    claim_matrix[claim["claim_id"]] = claim
        except Exception:
            pass
    
    # Step 5: Claim re-verification
    # Group imported evidence by claim_id
    evidence_by_claim = {}
    for ev in imported_evidence:
        cid = ev.get("claim_id", "")
        if cid not in evidence_by_claim:
            evidence_by_claim[cid] = []
        evidence_by_claim[cid].append(ev)
    
    requires_claim_replan = False
    updated_claims = []
    
    for claim_id, claim in claim_matrix.items():
        old_status = claim.get("status", "unsupported")
        
        # Get evidence for this claim
        claim_evidence = evidence_by_claim.get(claim_id, [])
        
        # Verify claim with new evidence
        new_status = verify_claim_with_evidence(claim, claim_evidence)
        
        if new_status != old_status and new_status in ["supported", "partially_supported"]:
            requires_claim_replan = True
            updated_claims.append({
                "claim_id": claim_id,
                "old_status": old_status,
                "new_status": new_status,
                "new_evidence_count": len(claim_evidence)
            })
    
    # Write output files
    run_dir = Path.home() / ".hermes" / "workflow_runs"
    
    # Write research_results.json
    research_results_path = run_dir / "research_results.json"
    with open(research_results_path, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "total_results": len(all_results),
            "gaps_analyzed": len(gaps),
            "queries_generated": len(queries),
            "results_by_source": {
                "pubmed": sum(1 for r in all_results if r.get("source") == "pubmed"),
                "arxiv": sum(1 for r in all_results if r.get("source") == "arxiv"),
                "openalex": sum(1 for r in all_results if r.get("source") == "openalex")
            },
            "results": all_results
        }, f, indent=2)
    
    # Write imported_evidence.jsonl
    imported_evidence_path = run_dir / "imported_evidence.jsonl"
    with open(imported_evidence_path, "w") as f:
        for ev in imported_evidence:
            f.write(json.dumps(ev) + "\n")
    
    # Write claim_gap_report.json
    claim_gap_report_path = run_dir / "claim_gap_report.json"
    with open(claim_gap_report_path, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "gaps": gaps,
            "queries": queries,
            "updated_claims": updated_claims
        }, f, indent=2)
    
    # Write updated_evidence_ledger.jsonl (append imported to existing)
    updated_evidence_ledger_path = run_dir / "updated_evidence_ledger.jsonl"
    with open(updated_evidence_ledger_path, "w") as f:
        # Write existing evidence
        for ev in existing_evidence:
            f.write(json.dumps(ev) + "\n")
        # Write imported evidence
        for ev in imported_evidence:
            f.write(json.dumps(ev) + "\n")
    
    return {
        "research_results_path": str(research_results_path),
        "imported_evidence_path": str(imported_evidence_path),
        "claim_gap_report_path": str(claim_gap_report_path),
        "updated_evidence_ledger_path": str(updated_evidence_ledger_path),
        "requires_claim_replan": requires_claim_replan,
        "timestamp": timestamp,
        "gate": "research_retrieve"
    }
