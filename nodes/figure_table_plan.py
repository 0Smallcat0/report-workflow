"""FIGURE_TABLE_PLAN - Phase 2: T21 - Plan figures and tables for the report."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .chart_recommender import chart_recommender
from .figure_contract_checker import figure_contract_checker
from .caption_interpreter import caption_interpreter


def run_figure_table_plan(
    claim_matrix_path: str,
    evidence_ledger_path: str,
    outline_path: str,
    report_family: str,
) -> dict:
    """T21: Plan figures and tables for the report.
    
    Args:
        claim_matrix_path: Path to claim_matrix.json
        evidence_ledger_path: Path to evidence_ledger.jsonl
        outline_path: Path to outline.json
        report_family: Report family (academic, work, hybrid)
    
    Returns:
        dict with paths to figure_manifest.json, tables.json, figure_contract_report.json
    """
    timestamp = datetime.now().isoformat()
    
    # Determine run_dir - use a temp location for standalone operation
    run_dir = Path.home() / ".hermes" / "workflow_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Load outline for context
    outline = {}
    if outline_path and Path(outline_path).exists():
        try:
            with open(outline_path) as f:
                outline = json.load(f)
        except Exception:
            pass
    
    # Step 1: chart_recommender - score claims for visualization suitability
    figure_recommendations = chart_recommender(claim_matrix_path, evidence_ledger_path)
    
    # Step 2: figure_contract_checker - validate required data fields
    validation_reports = figure_contract_checker(figure_recommendations, evidence_ledger_path)
    
    # Build figure contracts for caption generation
    valid_contracts = []
    for report in validation_reports:
        if report["data_available"]:
            # Find the corresponding recommendation
            for rec in figure_recommendations:
                if rec["claim_id"] == report["claim_id"]:
                    valid_contracts.append(rec["contract"])
                    break
    
    # Step 3: caption_interpreter (AGENT) - generate draft captions
    # Load claim matrix for context
    claim_matrix_data = {}
    if claim_matrix_path and Path(claim_matrix_path).exists():
        try:
            with open(claim_matrix_path) as f:
                claim_matrix_data = json.load(f)
        except Exception:
            pass
    
    figure_captions = caption_interpreter(valid_contracts, claim_matrix_data)
    
    # Build figure manifest
    figure_manifest = []
    for fc in figure_captions:
        manifest_entry = {
            "figure_number": fc["figure_number"],
            "caption": fc["caption"],
            "chart_type": fc["contract"].get("chart_type", ""),
            "claim_id": fc["contract"].get("claim_id", ""),
            "evidence_grade": fc["contract"].get("evidence_grade", "unknown")
        }
        figure_manifest.append(manifest_entry)
    
    # Build tables manifest
    tables_manifest = _generate_table_recommendations(claim_matrix_path, evidence_ledger_path)
    
    # Build figure contract report
    figure_contract_report = []
    for rec in figure_recommendations:
        # Find corresponding validation report
        validation = None
        for vr in validation_reports:
            if vr["claim_id"] == rec["claim_id"]:
                validation = vr
                break
        
        figure_contract_report.append({
            "claim_id": rec["claim_id"],
            "chart_type": rec["chart_type"],
            "score": rec["score"],
            "data_available": validation["data_available"] if validation else False,
            "missing_fields": validation["missing_fields"] if validation else [],
            "issues": validation["issues"] if validation else []
        })
    
    # Write output files
    figure_manifest_path = run_dir / "figure_manifest.json"
    with open(figure_manifest_path, "w") as f:
        json.dump(figure_manifest, f, indent=2)
    
    tables_path = run_dir / "tables.json"
    with open(tables_path, "w") as f:
        json.dump(tables_manifest, f, indent=2)
    
    figure_contract_report_path = run_dir / "figure_contract_report.json"
    with open(figure_contract_report_path, "w") as f:
        json.dump(figure_contract_report, f, indent=2)
    
    return {
        "figure_manifest_path": str(figure_manifest_path),
        "tables_path": str(tables_path),
        "figure_contract_report_path": str(figure_contract_report_path),
        "timestamp": timestamp,
        "gate": "figure_table_plan"
    }


def _generate_table_recommendations(claim_matrix_path: str, evidence_ledger_path: str) -> list[dict]:
    """Generate table recommendations based on claims and evidence.
    
    Simplified implementation - creates summary tables for key claims.
    """
    tables = []
    
    # Load claim matrix
    claims = []
    if claim_matrix_path and Path(claim_matrix_path).exists():
        try:
            with open(claim_matrix_path) as f:
                data = json.load(f)
                claims = data.get("claims", [])
        except Exception:
            pass
    
    # Create summary table for claims with evidence
    if claims:
        summary_rows = []
        for claim in claims:
            row = {
                "claim_id": claim.get("claim_id", ""),
                "claim_type": claim.get("claim_type", ""),
                "evidence_grade": claim.get("evidence_grade", "unknown"),
                "evidence_count": len(claim.get("evidence_ids", []))
            }
            summary_rows.append(row)
        
        if summary_rows:
            tables.append({
                "table_number": 1,
                "title": "Summary of Claims",
                "description": "Overview of all claims in the report",
                "data": summary_rows,
                "columns": ["claim_id", "claim_type", "evidence_grade", "evidence_count"]
            })
    
    return tables
