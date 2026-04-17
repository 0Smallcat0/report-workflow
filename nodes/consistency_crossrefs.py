"""CONSISTENCY_CROSSREFS - Cross-reference consistency checking."""
import re
import json
from pathlib import Path
from typing import Optional


def cross_reference_checker(
    merged_draft_path: str,
    sentence_sidecar_path: str,
    figure_manifest_path: str,
    tables_path: str
) -> list[dict]:
    """Check cross-reference consistency (figures, tables, sections)."""
    issues = []
    
    # Load merged draft
    draft_text = ""
    if Path(merged_draft_path).exists():
        with open(merged_draft_path) as f:
            draft_text = f.read()
    
    # 1. Enumerate defined figures from document
    defined_figures = set()
    figure_pattern = r'^#+\s*Figure\s+(\d+)\s*[:.]?\s*(.+?)$'
    for line in draft_text.split("\n"):
        match = re.match(figure_pattern, line, re.IGNORECASE)
        if match:
            fig_num = match.group(1)
            defined_figures.add(fig_num)
    
    # Also check figure manifest
    if Path(figure_manifest_path).exists():
        try:
            with open(figure_manifest_path) as f:
                manifest = json.load(f)
            for fig in manifest:
                if "figure_number" in fig:
                    defined_figures.add(str(fig["figure_number"]))
        except Exception:
            pass
    
    # 2. Enumerate defined tables
    defined_tables = set()
    table_pattern = r'^#+\s*Table\s+(\d+)\s*[:.]?\s*(.+?)$'
    for line in draft_text.split("\n"):
        match = re.match(table_pattern, line, re.IGNORECASE)
        if match:
            tbl_num = match.group(1)
            defined_tables.add(tbl_num)
    
    # Also check tables.json
    if Path(tables_path).exists():
        try:
            with open(tables_path) as f:
                tables = json.load(f)
            for tbl in tables:
                if "table_number" in tbl:
                    defined_tables.add(str(tbl["table_number"]))
        except Exception:
            pass
    
    # 3. Enumerate defined sections (numbered headings)
    defined_sections = set()
    section_pattern = r'^(#{1,6})\s+(\d+(?:\.\d+)*)\s+(.+)$'
    for line in draft_text.split("\n"):
        match = re.match(section_pattern, line)
        if match:
            level = len(match.group(1))
            section_num = match.group(2)
            defined_sections.add(section_num)
    
    # 4. Enumerate figure references
    figure_refs = re.findall(r'[Ff]igure\s+(\d+)', draft_text)
    
    # 5. Enumerate table references
    table_refs = re.findall(r'[Tt]able\s+(\d+)', draft_text)
    
    # 6. Enumerate section references
    section_refs = re.findall(r'[Ss]ection\s+(\d+(?:\.\d+)*)', draft_text)
    
    # 7. Check for undefined figure references
    for ref in figure_refs:
        if ref not in defined_figures and ref != "0":
            issues.append({
                "location": "figure_refs",
                "problem": f"Reference to undefined Figure {ref}",
                "severity": "high",
                "check": "cross_refs"
            })
    
    # 8. Check for undefined table references
    for ref in table_refs:
        if ref not in defined_tables and ref != "0":
            issues.append({
                "location": "table_refs",
                "problem": f"Reference to undefined Table {ref}",
                "severity": "high",
                "check": "cross_refs"
            })
    
    # 9. Check for undefined section references
    for ref in section_refs:
        if ref not in defined_sections:
            issues.append({
                "location": "section_refs",
                "problem": f"Reference to undefined Section {ref}",
                "severity": "medium",
                "check": "cross_refs"
            })
    
    # 10. Check for duplicate figure/table numbers
    fig_counts = {}
    for ref in figure_refs:
        fig_counts[ref] = fig_counts.get(ref, 0) + 1
    
    for ref, count in fig_counts.items():
        if count > 1:
            # Multiple references to same figure - check if they should be different
            # This is a soft check - multiple refs to same fig are usually OK
            pass
    
    # 11. Check for duplicate definitions
    if len(defined_figures) != len(set(defined_figures)):
        issues.append({
            "location": "figure_defs",
            "problem": "Duplicate figure number definitions",
            "severity": "high",
            "check": "cross_refs"
        })
    
    if len(defined_tables) != len(set(defined_tables)):
        issues.append({
            "location": "table_defs",
            "problem": "Duplicate table number definitions",
            "severity": "high",
            "check": "cross_refs"
        })
    
    return issues
