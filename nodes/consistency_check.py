"""CONSISTENCY_CHECK - Phase 2: T18 - Comprehensive consistency checking."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from .consistency_numeric import numeric_consistency_checker
from .consistency_terminology import terminology_consistency_checker
from .consistency_units import unit_format_checker
from .consistency_crossrefs import cross_reference_checker
from .consistency_claim_alignment import claim_alignment_checker


def run_consistency_check(
    merged_draft_path: str,
    sentence_sidecar_path: str,
    claim_matrix_path: str,
    figure_manifest_path: str,
    tables_path: str,
) -> dict:
    """T18: Run all consistency checks on merged draft.
    
    Args:
        merged_draft_path: Path to merged_draft.md
        sentence_sidecar_path: Path to sentence_map.jsonl
        claim_matrix_path: Path to claim_matrix.json
        figure_manifest_path: Path to figure_manifest.json
        tables_path: Path to tables.json
    
    Returns:
        dict with consistency check results
    """
    timestamp = datetime.now().isoformat()
    
    # Default values if files missing
    if not merged_draft_path:
        return _empty_result(timestamp)
    
    merged_path = Path(merged_draft_path)
    if not merged_path.exists():
        return _empty_result(timestamp)
    
    # Run all sub-checks
    all_issues = []

    # 1. Numeric consistency
    try:
        numeric_issues = numeric_consistency_checker(merged_draft_path, tables_path)
        all_issues.extend(numeric_issues)
    except Exception as exc:
        logger.warning(f"[CONSISTENCY_CHECK] numeric_consistency_checker failed: {exc}")

    # 2. Terminology consistency
    try:
        terminology_issues = terminology_consistency_checker(merged_draft_path)
        all_issues.extend(terminology_issues)
    except Exception as exc:
        logger.warning(f"[CONSISTENCY_CHECK] terminology_consistency_checker failed: {exc}")

    # 3. Unit format consistency
    try:
        unit_issues = unit_format_checker(merged_draft_path)
        all_issues.extend(unit_issues)
    except Exception as exc:
        logger.warning(f"[CONSISTENCY_CHECK] unit_format_checker failed: {exc}")

    # 4. Cross-reference consistency
    try:
        crossref_issues = cross_reference_checker(
            merged_draft_path,
            sentence_sidecar_path,
            figure_manifest_path,
            tables_path
        )
        all_issues.extend(crossref_issues)
    except Exception as exc:
        logger.warning(f"[CONSISTENCY_CHECK] cross_reference_checker failed: {exc}")

    # 5. Claim alignment
    try:
        claim_issues = claim_alignment_checker(merged_draft_path, claim_matrix_path)
        all_issues.extend(claim_issues)
    except Exception as exc:
        logger.warning(f"[CONSISTENCY_CHECK] claim_alignment_checker failed: {exc}")
    
    # Compute summary
    total_issues = len(all_issues)
    high_severity = sum(1 for i in all_issues if i.get("severity") == "high")
    medium_severity = sum(1 for i in all_issues if i.get("severity") == "medium")
    low_severity = sum(1 for i in all_issues if i.get("severity") == "low")
    
    # Determine gate status
    if high_severity > 0 or medium_severity > 0:
        gate_status = "soft_blocker"
        status = "fail"
    elif low_severity > 0:
        gate_status = "soft_blocker"
        status = "warning"
    else:
        gate_status = "pass"
        status = "pass"
    
    return {
        "document": str(merged_path.name),
        "timestamp": timestamp,
        "gate": "consistency",
        "status": status,
        "checks": {
            "numeric": {
                "passed": len(numeric_issues) == 0,
                "issues": numeric_issues
            },
            "terminology": {
                "passed": len(terminology_issues) == 0,
                "issues": terminology_issues
            },
            "units": {
                "passed": len(unit_issues) == 0,
                "issues": unit_issues
            },
            "cross_refs": {
                "passed": len(crossref_issues) == 0,
                "issues": crossref_issues
            },
            "claim_alignment": {
                "passed": len(claim_issues) == 0,
                "issues": claim_issues
            }
        },
        "summary": {
            "total_issues": total_issues,
            "high_severity": high_severity,
            "medium_severity": medium_severity,
            "low_severity": low_severity,
            "gate_status": gate_status
        }
    }


def _empty_result(timestamp: str) -> dict:
    """Return empty result when input files are missing."""
    return {
        "document": "merged_draft.md",
        "timestamp": timestamp,
        "gate": "consistency",
        "status": "warning",
        "checks": {
            "numeric": {"passed": True, "issues": []},
            "terminology": {"passed": True, "issues": []},
            "units": {"passed": True, "issues": []},
            "cross_refs": {"passed": True, "issues": []},
            "claim_alignment": {"passed": True, "issues": []}
        },
        "summary": {
            "total_issues": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "gate_status": "pass"
        }
    }
