"""CITATION_BIND node - bind citations to evidence."""
import json
import re
import os
import anthropic
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..citation_formatters.apa import format_apa_citation

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


def resolve_citations(merged_md: str, evidence_ledger: list[dict], citation_audit: list[dict]) -> tuple[str, list[dict]]:
    """Resolve [CITE:cite_id] references to formatted APA citations.
    
    Deterministic binding first, agent only for disambiguation.
    """
    # Pattern to find citation references
    cite_pattern = re.compile(r'\[CITE:([^\]]+)\]')
    
    resolved_md = merged_md
    resolved_refs = []
    
    # Build evidence lookup by evidence_id
    evidence_by_id = {e["evidence_id"]: e for e in evidence_ledger}
    
    # Build source lookup
    source_by_id = {}
    for e in evidence_ledger:
        source_by_id[e["source_id"]] = e
    
    # Process each citation
    new_audit = []
    for match in cite_pattern.finditer(merged_md):
        cite_id = match.group(1)
        
        audit_entry = {
            "cite_id": cite_id,
            "evidence_ids": [cite_id],  # Default assumption
            "resolved": False
        }
        
        # Try deterministic lookup
        if cite_id in evidence_by_id:
            evidence = evidence_by_id[cite_id]
            source_id = evidence.get("source_id", "")
            # Format citation - use a cite_id format for the citation
            file_type = evidence.get("file_type", "unknown")
            replacement = f"[{format_apa_citation({'file_name': file_type, 'file_type': file_type})}]"
            resolved_md = resolved_md.replace(match.group(0), replacement, 1)
            audit_entry["evidence_ids"] = [cite_id]
            audit_entry["resolved"] = True
        else:
            # Try source lookup
            if cite_id in source_by_id:
                evidence = source_by_id[cite_id]
                replacement = f"[{format_apa_citation({'file_name': cite_id, 'file_type': 'unknown'})}]"
                resolved_md = resolved_md.replace(match.group(0), replacement, 1)
                audit_entry["resolved"] = True
            else:
                # Unresolved: cite_id not in evidence or source lookups
                import sys
                print(f"[CITATION_BIND] unresolved cite_id={cite_id!r} at match {match.group(0)!r}", file=sys.stderr)
        
        new_audit.append(audit_entry)
    
    # Add unresolved audit entries
    for entry in citation_audit:
        if not any(a["cite_id"] == entry["cite_id"] for a in new_audit):
            new_audit.append(entry)
    
    # Append references section
    references = []
    seen_sources = set()
    for e in evidence_ledger:
        source_id = e.get("source_id", "")
        if source_id and source_id not in seen_sources:
            seen_sources.add(source_id)
            ref = format_apa_citation({"file_name": source_id, "file_type": "unknown"})
            if ref not in references:
                references.append(ref)
    
    if references:
        resolved_md += "\n\n## References\n\n"
        for ref in references:
            resolved_md += f"- {ref}\n"
    
    return resolved_md, new_audit


def run_citation_bind(state: ReportState) -> ReportState:
    """T12: CITATION_BIND - bind citations to evidence."""
    merged_md_path = state.drafts.get("merged_draft_md")
    if not merged_md_path or not Path(merged_md_path).exists():
        state.drafts["merged_draft_cited_md"] = state.drafts.get("merged_draft_md")
        return state
    
    with open(merged_md_path) as f:
        merged_md = f.read()
    
    # Load evidence ledger
    evidence_ledger_path = state.sources.get("evidence_ledger_path")
    evidence_ledger = []
    if evidence_ledger_path:
        try:
            with open(evidence_ledger_path) as f:
                for line in f:
                    evidence_ledger.append(json.loads(line))
        except Exception:
            pass
    
    citation_audit = state.citations.get("citation_audit", [])
    
    # Resolve citations
    resolved_md, new_audit = resolve_citations(merged_md, evidence_ledger, citation_audit)
    
    # Write resolved document
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    cited_path = run_dir / "merged_draft_cited.md"
    with open(cited_path, "w") as f:
        f.write(resolved_md)
    
    state.drafts["merged_draft_cited_md"] = str(cited_path)
    state.citations["citation_audit"] = new_audit
    
    return state
