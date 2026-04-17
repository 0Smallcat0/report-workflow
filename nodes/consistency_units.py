"""CONSISTENCY_UNITS - Unit format consistency checking."""
import re
from pathlib import Path
from typing import Optional


# Dictionary of allowed unit variants per unit family
UNIT_VARIANTS = {
    # Volume units (case variations)
    "volume": ["mL", "ml", "ML", "l", "L", "μL", "uL", "UL"],
    # Mass units
    "mass": ["mg", "Mg", "g", "kg", "μg", "ug", "ng"],
    # Concentration
    "concentration": ["mg/mL", "mg/ml", "mg/L", "μg/mL", "ug/mL", "μg/ml", "ng/mL"],
    # Time
    "time": ["ms", "msec", "s", "sec", "min", "hour", "hr", "day"],
    # Temperature
    "temperature": ["°C", "celsius", "C", "K", "kelvin"],
    # Pressure
    "pressure": ["mmHg", "kPa", "Pa", "atm"],
    # Percentage
    "percentage": ["%", "percent", "percentage"],
    # Probability
    "probability": ["p", "p-value", "p value", "P"],
}

# Map unit to its canonical form
UNIT_CANONICAL = {}
for family, variants in UNIT_VARIANTS.items():
    for variant in variants:
        UNIT_CANONICAL[variant.lower()] = family


def extract_units(text: str) -> list[dict]:
    """Extract units with context from text."""
    units = []
    
    # Pattern for unit expressions (number + unit)
    patterns = [
        # Standard notation: 40 mg/mL
        r'(\d+(?:\.\d+)?)\s*([A-Za-z°μ]/[A-Za-z°μ]+)',
        # Percentage: 40%
        r'(\d+(?:\.\d+)?)\s*(%)',
        # With special characters: μL, °C
        r'(\d+(?:\.\d+)?)\s*(μ[A-Za-z]+)',
        # p-value style
        r'(p)\s*(<|<=|>|>=)\s*(\d+(?:\.\d+)?)',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            unit_text = match.group(0)
            units.append({
                "text": unit_text,
                "position": match.start(),
                "groups": match.groups()
            })
    
    return units


def unit_format_checker(merged_draft_path: str) -> list[dict]:
    """Check unit format consistency."""
    issues = []
    
    if not Path(merged_draft_path).exists():
        return issues
    
    with open(merged_draft_path) as f:
        text = f.read()
    
    # Extract all units
    units = extract_units(text)
    
    # Group by unit type
    unit_groups = {}
    for unit in units:
        unit_text = unit["text"]
        # Normalize for comparison: lowercase + remove spaces; slashes are preserved
        normalized = unit_text.lower().replace(" ", "")
        
        if normalized not in unit_groups:
            unit_groups[normalized] = []
        unit_groups[normalized].append(unit)
    
    # Check for inconsistent unit usage
    for group_key, group_units in unit_groups.items():
        if len(group_units) < 2:
            continue
        
        # Check if they all have the same form
        forms = [u["text"] for u in group_units]
        unique_forms = set(forms)
        
        if len(unique_forms) > 1:
            # Inconsistent usage found
            # Determine severity
            positions = [u["position"] for u in group_units]
            span = max(positions) - min(positions)
            
            # If close together, high severity
            text_segments = text[min(positions):max(positions)+50]
            paragraph_count = text_segments.count("\n\n") + 1
            
            if paragraph_count == 1:
                severity = "high"
            elif span < 500:
                severity = "medium"
            else:
                severity = "low"
            
            issues.append({
                "location": f"pos_{group_units[0]['position']}",
                "problem": f"Inconsistent unit format: {' / '.join(unique_forms)} used interchangeably",
                "severity": severity,
                "check": "units"
            })
    
    # Check p-value spacing consistency
    pvalue_pattern = r'p\s*[<>=]\s*\d+'
    pvalues = re.findall(pvalue_pattern, text)
    
    inconsistent_pvals = []
    for pv in pvalues:
        if " " not in pv and "p <" not in pv and "p<" not in pv:
            inconsistent_pvals.append(pv)
    
    if len(set(pvalues)) > 1:
        # Multiple styles found
        issues.append({
            "location": "p-values",
            "problem": f"Inconsistent p-value formatting: {', '.join(set(pvalues))}",
            "severity": "medium",
            "check": "units"
        })
    
    # Check scientific notation consistency
    sci_pattern = r'\d+\.?\d*[eE][+-]?\d+'
    sci_matches = re.findall(sci_pattern, text)
    
    if sci_matches:
        # Check if mixed notation (some with leading digit, some without)
        has_leading = [m for m in sci_matches if m.startswith("0")]
        has_full = [m for m in sci_matches if not m.startswith("0")]
        
        if has_leading and has_full:
            issues.append({
                "location": "scientific notation",
                "problem": f"Mixed scientific notation: {' / '.join(set(sci_matches[:5]))}",
                "severity": "low",
                "check": "units"
            })
    
    return issues
