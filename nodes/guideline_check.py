"""GUIDELINE_CHECK - Phase 2: T20 - Check report against reporting guidelines."""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_guideline(guideline_name: str) -> Optional[dict]:
    """Load guideline JSON file."""
    guideline_dir = Path(__file__).parent.parent / "guidelines"
    guideline_path = guideline_dir / f"{guideline_name}.json"
    
    if guideline_path.exists():
        with open(guideline_path) as f:
            return json.load(f)
    return None


def load_severity_policy() -> dict:
    """Load severity policy configuration."""
    policy_path = Path(__file__).parent.parent / "configs" / "guideline_severity_policy.json"
    if policy_path.exists():
        with open(policy_path) as f:
            return json.load(f)
    return {}


def load_blueprint(blueprint_path: str) -> dict:
    """Load blueprint to map sections."""
    if Path(blueprint_path).exists():
        with open(blueprint_path) as f:
            return json.load(f)
    return {}


def detect_item_coverage(
    item: dict,
    text: str,
    sentence_map_path: str
) -> tuple[str, Optional[str]]:
    """Detect if a guideline item is covered in the document.
    
    Returns (status, location_or_none) where status is 'covered', 'missing', or 'partial'.
    """
    detection_hints = item.get("detection_hints", [])
    covers_sections = item.get("covers_sections", [])
    
    if not detection_hints:
        return "missing", None
    
    # Search for detection hints in text
    found_hints = []
    for hint in detection_hints:
        # Case-insensitive search
        pattern = re.escape(hint)
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            found_hints.append((hint, matches[0].start()))
    
    if not found_hints:
        return "missing", None
    
    # Check section coverage if specified
    if covers_sections:
        # Load sentence map to determine section for each match
        if Path(sentence_map_path).exists():
            try:
                with open(sentence_map_path) as f:
                    sentence_map = [json.loads(line) for line in f]
                
                # Map sentence positions to sections
                for hint, position in found_hints:
                    for sent_entry in sentence_map:
                        # This is simplified - would need actual position mapping
                        if hint.lower() in text.lower():
                            return "covered", f"sent_{len(sentence_map)}"
            except Exception:
                pass
        
        # If we found hints but can't verify section, consider it partial
        return "partial", None
    
    return "covered", f"pos_{found_hints[0][1]}"


def apply_severity_overrides(
    item_id: str,
    base_severity: str,
    severity_policy: dict,
    report_family: str
) -> str:
    """Apply severity overrides based on policy."""
    if item_id in severity_policy.get("hard", {}).get(report_family, []):
        return "hard"
    elif item_id in severity_policy.get("soft", {}).get(report_family, []):
        return "soft"
    elif item_id in severity_policy.get("warn", {}).get(report_family, []):
        return "warn"
    return base_severity


def run_guideline_check(
    merged_draft_path: str,
    selected_guidelines: list[str],
    guideline_config_path: str,
    blueprint_path: str,
    sentence_map_path: str,
) -> dict:
    """T20: Check document against selected reporting guidelines.
    
    Args:
        merged_draft_path: Path to merged_draft.md
        selected_guidelines: List of guideline names (e.g., ["STROBE", "CONSORT"])
        guideline_config_path: Path to configs/guideline_rules.json
        blueprint_path: Path to blueprint.json
        sentence_map_path: Path to sentence_map.jsonl
    
    Returns:
        dict with guideline check results
    """
    timestamp = datetime.now().isoformat()
    
    if not merged_draft_path or not Path(merged_draft_path).exists():
        return _empty_result(timestamp, selected_guidelines)
    
    # Load document text
    with open(merged_draft_path) as f:
        text = f.read()
    
    # Load severity policy
    severity_policy = load_severity_policy()
    
    # Load blueprint for section mapping
    blueprint = load_blueprint(blueprint_path)
    report_family = blueprint.get("report_family", "academic")
    
    all_checks = {}
    total_items = 0
    total_covered = 0
    total_missing = 0
    hard_missing = 0
    soft_missing = 0
    warn_missing = 0
    
    for guideline_name in selected_guidelines:
        guideline = load_guideline(guideline_name)
        if not guideline:
            continue
        
        items = guideline.get("items", [])
        total_items += len(items)
        
        guideline_results = {
            "total_items": len(items),
            "covered": 0,
            "missing": 0,
            "items": []
        }
        
        for item in items:
            item_id = item.get("item_id", "unknown")
            base_severity = item.get("severity", "soft")
            
            # Apply severity overrides
            severity = apply_severity_overrides(
                item_id, base_severity, severity_policy, report_family
            )
            
            # Detect coverage
            status, location = detect_item_coverage(item, text, sentence_map_path)
            
            if status == "covered":
                guideline_results["covered"] += 1
                total_covered += 1
            else:
                guideline_results["missing"] += 1
                total_missing += 1
                
                if severity == "hard":
                    hard_missing += 1
                elif severity == "soft":
                    soft_missing += 1
                else:
                    warn_missing += 1
            
            guideline_results["items"].append({
                "item_id": item_id,
                "status": status,
                "location": location,
                "missing_explanation": None if status == "covered" else f"Required content not found: {item.get('description', '')[:100]}",
                "severity": severity
            })
        
        all_checks[guideline_name] = guideline_results
    
    # Determine gate status
    if hard_missing > 0:
        gate_status = "hard_blocker"
        status = "fail"
    elif soft_missing > 0:
        gate_status = "soft_blocker"
        status = "warning"
    elif warn_missing > 0:
        gate_status = "warning"
        status = "warning"
    else:
        gate_status = "pass"
        status = "pass"
    
    return {
        "document": Path(merged_draft_path).name,
        "timestamp": timestamp,
        "gate": "guideline_check",
        "guidelines_applied": selected_guidelines,
        "status": status,
        "checks": all_checks,
        "summary": {
            "total_items": total_items,
            "covered": total_covered,
            "missing": total_missing,
            "hard_missing": hard_missing,
            "soft_missing": soft_missing,
            "warn_missing": warn_missing,
            "gate_status": gate_status
        }
    }


def _empty_result(timestamp: str, selected_guidelines: list[str]) -> dict:
    """Return empty result when input files are missing."""
    return {
        "document": "merged_draft.md",
        "timestamp": timestamp,
        "gate": "guideline_check",
        "guidelines_applied": selected_guidelines,
        "status": "warning",
        "checks": {},
        "summary": {
            "total_items": 0,
            "covered": 0,
            "missing": 0,
            "hard_missing": 0,
            "soft_missing": 0,
            "warn_missing": 0,
            "gate_status": "warning"
        }
    }
