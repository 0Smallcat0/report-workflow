"""FIGURE_CONTRACT_CHECKER - Validates required data fields for figure contracts."""
import json
from pathlib import Path
from typing import Optional


# Required fields per chart type
CHART_REQUIREMENTS = {
    "bar_chart": {
        "required": ["categories", "values", "n_per_category"],
        "numeric_fields": ["values", "n_per_category"],
        "validation": {
            "categories": lambda v: isinstance(v, list) and len(v) >= 2,
            "values": lambda v: isinstance(v, list) and all(isinstance(x, (int, float)) for x in v),
            "n_per_category": lambda v: isinstance(v, list) and all(isinstance(x, (int, float)) for x in v)
        }
    },
    "line_chart": {
        "required": ["x_values", "y_values"],
        "numeric_fields": ["x_values", "y_values"],
        "validation": {
            "x_values": lambda v: isinstance(v, list) and len(v) >= 2,
            "y_values": lambda v: isinstance(v, list) and len(v) == len(v)  # Will check pairing later
        }
    },
    "scatter": {
        "required": ["x_values", "y_values", "paired"],
        "numeric_fields": ["x_values", "y_values"],
        "validation": {
            "x_values": lambda v: isinstance(v, list) and len(v) >= 5,
            "y_values": lambda v: isinstance(v, list) and len(v) >= 5,
            "paired": lambda v: v == True or (isinstance(v, list) and len(v) >= 5)
        }
    },
    "heatmap": {
        "required": ["row_categories", "col_categories", "matrix_values"],
        "numeric_fields": ["matrix_values"],
        "validation": {
            "row_categories": lambda v: isinstance(v, list) and len(v) >= 2,
            "col_categories": lambda v: isinstance(v, list) and len(v) >= 2,
            "matrix_values": lambda v: isinstance(v, list) and all(isinstance(row, list) for row in v)
        }
    },
    "forest_plot": {
        "required": ["effect_size", "ci_lower", "ci_upper", "study_labels"],
        "numeric_fields": ["effect_size", "ci_lower", "ci_upper"],
        "validation": {
            "effect_size": lambda v: isinstance(v, list) and len(v) >= 2,
            "ci_lower": lambda v: isinstance(v, list) and all(isinstance(x, (int, float)) for x in v),
            "ci_upper": lambda v: isinstance(v, list) and all(isinstance(x, (int, float)) for x in v),
            "study_labels": lambda v: isinstance(v, list) and len(v) >= 2
        }
    },
    "diagram": {
        "required": ["nodes", "relationships"],
        "validation": {
            "nodes": lambda v: isinstance(v, list) and len(v) >= 2,
            "relationships": lambda v: isinstance(v, list)
        }
    }
}


def figure_contract_checker(
    figure_contracts: list[dict],
    evidence_ledger_path: str
) -> list[dict]:
    """Validate that required data fields are present in evidence for each figure contract.
    
    Args:
        figure_contracts: List of figure contract dicts from chart_recommender
        evidence_ledger_path: Path to evidence ledger JSONL
    
    Returns:
        List of validation reports per figure
    """
    # Load evidence ledger
    evidence_by_id = {}
    if evidence_ledger_path and Path(evidence_ledger_path).exists():
        try:
            with open(evidence_ledger_path) as f:
                for line in f:
                    ev = json.loads(line)
                    evidence_by_id[ev.get("evidence_id", "")] = ev
        except Exception:
            pass
    
    validation_reports = []
    
    for contract in figure_contracts:
        chart_type = contract.get("chart_type", "")
        claim_id = contract.get("claim_id", "")
        required_fields = contract.get("required_fields", [])
        
        requirements = CHART_REQUIREMENTS.get(chart_type, {})
        
        report = {
            "claim_id": claim_id,
            "chart_type": chart_type,
            "data_available": True,
            "missing_fields": [],
            "issues": []
        }
        
        # Check each required field
        for field in required_fields:
            # Try to find field in evidence
            field_found = False
            field_data = None
            
            for ev_id, ev_data in evidence_by_id.items():
                # Check top-level
                if field in ev_data:
                    field_found = True
                    field_data = ev_data[field]
                    break
                
                # Check nested under 'data' key
                if "data" in ev_data and isinstance(ev_data["data"], dict):
                    if field in ev_data["data"]:
                        field_found = True
                        field_data = ev_data["data"][field]
                        break
            
            if not field_found:
                report["missing_fields"].append(field)
                report["data_available"] = False
                report["issues"].append(f"Missing required field: {field}")
            else:
                # Validate field format
                validation_fn = requirements.get("validation", {}).get(field)
                if validation_fn and not validation_fn(field_data):
                    report["issues"].append(f"Field {field} has invalid format")
        
        # Special validation for scatter: x and y must have same length
        if chart_type == "scatter":
            x_vals = None
            y_vals = None
            for ev_id, ev_data in evidence_by_id.items():
                if "x_values" in ev_data:
                    x_vals = ev_data["x_values"]
                if "y_values" in ev_data:
                    y_vals = ev_data["y_values"]
            
            if x_vals and y_vals and len(x_vals) != len(y_vals):
                report["issues"].append("Scatter plot x and y values must have equal length")
                report["data_available"] = False
        
        # Special validation for forest plot: CI lower must be < upper
        if chart_type == "forest_plot":
            ci_lower = None
            ci_upper = None
            for ev_id, ev_data in evidence_by_id.items():
                if "ci_lower" in ev_data:
                    ci_lower = ev_data["ci_lower"]
                if "ci_upper" in ev_data:
                    ci_upper = ev_data["ci_upper"]
            
            if ci_lower and ci_upper:
                for i, (lower, upper) in enumerate(zip(ci_lower, ci_upper)):
                    if lower >= upper:
                        report["issues"].append(f"CI lower bound >= upper bound at index {i}")
                        report["data_available"] = False
        
        validation_reports.append(report)
    
    return validation_reports
