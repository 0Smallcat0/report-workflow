"""CHART_RECOMMENDER - Deterministic chart type recommendation based on claim data."""
import json
from pathlib import Path
from typing import Optional


# Chart type recommendations based on evidence characteristics
CHART_SUITABILITY = {
    "bar_chart": {
        "evidence_types": ["categorical_comparison", "group_comparison"],
        "min_groups": 2,
        "max_groups": 5,
        "required_fields": ["categories", "values", "n_per_category"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    },
    "line_chart": {
        "evidence_types": ["continuous_trend", "time_series", "longitudinal"],
        "min_points": 3,
        "required_fields": ["x_values", "y_values"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    },
    "scatter": {
        "evidence_types": ["correlation", "continuous_comparison"],
        "min_points": 5,
        "required_fields": ["x_values", "y_values", "paired"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    },
    "heatmap": {
        "evidence_types": ["categorical_matrix"],
        "required_fields": ["row_categories", "col_categories", "matrix_values"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    },
    "forest_plot": {
        "evidence_types": ["effect_sizes", "meta_analysis"],
        "min_studies": 2,
        "required_fields": ["effect_size", "ci_lower", "ci_upper", "study_labels"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    },
    "diagram": {
        "evidence_types": ["process", "mechanism", "architecture", "pathway"],
        "required_fields": ["nodes", "relationships"],
        "score_weights": {
            "evidence_type_match": 0.5,
            "data_completeness": 0.3,
            "evidence_grade": 0.2
        }
    }
}

# Evidence grade to score mapping
GRADE_SCORES = {
    "high": 1.0,
    "moderate": 0.7,
    "low": 0.4,
    "unknown": 0.2
}


def determine_evidence_type(claim: dict) -> str:
    """Determine evidence type from claim characteristics."""
    claim_type = claim.get("claim_type", "")
    evidence_ids = claim.get("evidence_ids", [])
    
    # Check for statistical keywords
    stat_keywords = ["correlation", "trend", "change over time", "time series", "longitudinal"]
    categorical_keywords = ["comparison", "group", "category", "versus", "among"]
    effect_keywords = ["effect size", "meta-analysis", "pooled", "relative risk", "odds ratio"]
    process_keywords = ["process", "mechanism", "pathway", "workflow", "algorithm"]
    
    for kw in stat_keywords:
        if kw in claim_type.lower():
            return "continuous_trend"
    
    for kw in categorical_keywords:
        if kw in claim_type.lower():
            return "categorical_comparison"
    
    for kw in effect_keywords:
        if kw in claim_type.lower():
            return "effect_sizes"
    
    for kw in process_keywords:
        if kw in claim_type.lower():
            return "process"
    
    # Default based on number of evidence items
    if len(evidence_ids) >= 5:
        return "meta_analysis"
    elif len(evidence_ids) >= 2:
        return "group_comparison"
    else:
        return "single_finding"


def score_chart_type(
    chart_type: str,
    claim: dict,
    evidence: list[dict]
) -> float:
    """Score how suitable a chart type is for a claim (0-1)."""
    config = CHART_SUITABILITY.get(chart_type, {})
    if not config:
        return 0.0
    
    weights = config.get("score_weights", {})
    score = 0.0
    
    # 1. Evidence type match
    evidence_type = determine_evidence_type(claim)
    if evidence_type in config.get("evidence_types", []):
        score += weights.get("evidence_type_match", 0.5)
    else:
        score += weights.get("evidence_type_match", 0.5) * 0.3  # Partial credit
    
    # 2. Data completeness
    required_fields = config.get("required_fields", [])
    if required_fields:
        present_fields = 0
        for field in required_fields:
            if _check_field_present(field, evidence):
                present_fields += 1
        completeness = present_fields / len(required_fields)
        score += weights.get("data_completeness", 0.3) * completeness
    else:
        score += weights.get("data_completeness", 0.3)
    
    # 3. Evidence grade
    grade = claim.get("evidence_grade", "unknown")
    grade_score = GRADE_SCORES.get(grade, 0.2)
    score += weights.get("evidence_grade", 0.2) * grade_score
    
    return min(score, 1.0)


def _check_field_present(field: str, evidence: list[dict]) -> bool:
    """Check if a required field is present in evidence."""
    field_mappings = {
        "categories": ["category", "categories", "group", "groups"],
        "values": ["value", "values", "mean", "median", "count", "percentage"],
        "n_per_category": ["n", "sample_size", "count", "participants"],
        "x_values": ["x", "time", "dose", "concentration"],
        "y_values": ["y", "outcome", "response", "effect"],
        "paired": ["paired", "pairwise", "matched"],
        "row_categories": ["row_category", "row_categories", "rows"],
        "col_categories": ["col_category", "col_categories", "columns"],
        "matrix_values": ["matrix", "values", "counts"],
        "effect_size": ["effect_size", "es", "mean_difference", "risk_ratio"],
        "ci_lower": ["ci_lower", "conf_int_lower", "lower_ci"],
        "ci_upper": ["ci_upper", "conf_int_upper", "upper_ci"],
        "study_labels": ["study", "studies", "label", "study_label", "author"],
        "nodes": ["node", "nodes", "step", "component"],
        "relationships": ["relationship", "relationships", "edge", "edges", "connection"]
    }
    
    possible_keys = field_mappings.get(field, [field])
    
    for ev in evidence:
        for key in possible_keys:
            if key in ev or key.replace("_", " ") in str(ev).lower():
                return True
    return False


def recommend_chart(claim: dict, evidence: list[dict]) -> tuple[Optional[str], float]:
    """Recommend the best chart type for a claim.
    
    Returns (chart_type, score) or (None, 0.0) if no chart is suitable.
    """
    # Score all chart types
    scores = {}
    for chart_type in CHART_SUITABILITY:
        scores[chart_type] = score_chart_type(chart_type, claim, evidence)
    
    # Find best scoring chart type
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    
    # Threshold: score < 0.4 means no chart recommended
    if best_score < 0.4:
        return None, 0.0
    
    return best_type, best_score


def chart_recommender(
    claim_matrix_path: str,
    evidence_ledger_path: str
) -> list[dict]:
    """Generate chart recommendations for each claim.
    
    Returns list of recommendation dicts with claim_id, chart_type, score, and contract.
    """
    recommendations = []
    
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
    
    # Load evidence ledger
    evidence_ledger = []
    if evidence_ledger_path and Path(evidence_ledger_path).exists():
        try:
            with open(evidence_ledger_path) as f:
                for line in f:
                    evidence_ledger.append(json.loads(line))
        except Exception:
            pass
    
    # Build evidence lookup by ID
    evidence_by_id = {e.get("evidence_id", i): e for i, e in enumerate(evidence_ledger)}
    
    # Evaluate each claim
    for claim_id, claim in claim_matrix.items():
        evidence_ids = claim.get("evidence_ids", [])
        claim_evidence = [evidence_by_id.get(eid, {}) for eid in evidence_ids]
        
        # Get recommendation
        chart_type, score = recommend_chart(claim, claim_evidence)
        
        if chart_type:
            recommendations.append({
                "claim_id": claim_id,
                "chart_type": chart_type,
                "score": score,
                "contract": {
                    "chart_type": chart_type,
                    "claim_id": claim_id,
                    "required_fields": CHART_SUITABILITY[chart_type].get("required_fields", []),
                    "evidence_grade": claim.get("evidence_grade", "unknown")
                }
            })
    
    return recommendations
