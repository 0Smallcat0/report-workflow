"""CONSISTENCY_NUMERIC - Numeric consistency checking."""
import re
import json
from pathlib import Path
from typing import Optional


def parse_number(text: str) -> Optional[float]:
    """Parse a number string to float, handling various formats."""
    if not text:
        return None
    # Remove commas, spaces
    text = text.strip().replace(",", "").replace(" ", "")
    
    # Handle percent signs
    is_percent = "%" in text
    text = text.replace("%", "")
    
    # Handle scientific notation
    text = text.lower()
    if "e+" in text or "e-" in text or "e" in text:
        try:
            val = float(text)
            return val / 100.0 if is_percent else val
        except ValueError:
            return None
    
    # Handle fractions like 1/2
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 2:
            try:
                val = float(parts[0]) / float(parts[1])
                return val / 100.0 if is_percent else val
            except ValueError:
                return None
    
    # Handle parentheses for negatives: (42) -> -42
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    
    try:
        val = float(text)
        return val / 100.0 if is_percent else val
    except ValueError:
        return None


def extract_numeric_tokens(text: str, context_words: int = 5) -> list[dict]:
    """Extract numeric tokens with surrounding context."""
    # Match numbers including decimals, negatives, percents, scientific notation
    pattern = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?'
    tokens = []
    
    words = text.split()
    for i, word in enumerate(words):
        if re.match(pattern, word):
            # Get context window
            start = max(0, i - context_words)
            end = min(len(words), i + context_words + 1)
            context = " ".join(words[start:end])
            value = parse_number(word)
            tokens.append({
                "token": word,
                "value": value,
                "position": i,
                "context": context
            })
    return tokens


def numeric_consistency_checker(
    merged_draft_path: str,
    tables_path: str
) -> list[dict]:
    """Check numeric consistency between prose and tables."""
    issues = []
    
    # Load merged draft
    draft_text = ""
    if Path(merged_draft_path).exists():
        with open(merged_draft_path) as f:
            draft_text = f.read()
    
    # Extract prose numbers
    prose_numbers = extract_numeric_tokens(draft_text)
    
    # Load table numbers
    table_numbers = []
    if Path(tables_path).exists():
        try:
            with open(tables_path) as f:
                tables_data = json.load(f)
            for table in tables_data:
                for row in table.get("data", []):
                    for cell in row:
                        if isinstance(cell, (int, float)):
                            table_numbers.append({
                                "value": float(cell),
                                "context": str(table.get("title", ""))
                            })
                        elif isinstance(cell, str):
                            val = parse_number(cell)
                            if val is not None:
                                table_numbers.append({
                                    "value": val,
                                    "context": str(table.get("title", ""))
                                })
        except Exception:
            pass
    
    # Check prose numbers against table numbers (within 5% tolerance)
    for prose_num in prose_numbers:
        if prose_num["value"] is None:
            continue
        for table_num in table_numbers:
            if table_num["value"] == 0:
                continue
            rel_diff = abs(prose_num["value"] - table_num["value"]) / abs(table_num["value"])
            if rel_diff < 0.05 and prose_num["value"] != table_num["value"]:
                # Form conflict (e.g., 40% vs 0.40)
                issues.append({
                    "location": f"context:{prose_num['position']}",
                    "problem": f"Numeric form conflict: '{prose_num['token']}' vs table value {table_num['value']} (difference {rel_diff*100:.1f}%)",
                    "severity": "medium",
                    "check": "numeric"
                })
    
    # Check for magnitude conflicts (same context but very different values)
    prose_by_context = {}
    for pnum in prose_numbers:
        if pnum["value"] is not None:
            # Group by rounded value to find magnitude issues
            key = int(pnum["value"])
            if key not in prose_by_context:
                prose_by_context[key] = []
            prose_by_context[key].append(pnum)
    
    for key, values in prose_by_context.items():
        if len(values) > 1:
            # Check if values are significantly different
            for i, v1 in enumerate(values):
                for v2 in values[i+1:]:
                    if v1["value"] is not None and v2["value"] is not None:
                        if v1["value"] != v2["value"]:
                            rel_diff = abs(v1["value"] - v2["value"]) / max(abs(v1["value"]), abs(v2["value"]), 1)
                            if rel_diff > 0.1:  # >10% difference
                                issues.append({
                                    "location": f"context:{v1['position']}",
                                    "problem": f"Magnitude conflict: '{v1['token']}' vs '{v2['token']}' in similar contexts",
                                    "severity": "high",
                                    "check": "numeric"
                                })
    
    return issues
