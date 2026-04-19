"""APA citation formatter."""
from typing import Optional


def format_apa_citation(
    source_metadata: dict,
    evidence_content: Optional[str] = None
) -> str:
    """Format a citation in APA style.
    
    Minimal formatter for journal articles, reports, web pages, documents.
    """
    source_type = source_metadata.get("file_type", "unknown")
    file_name = source_metadata.get("file_name", "Unknown")
    
    # For structured data sources, derive a reasonable citation
    if source_type in ("csv", "xlsx", "json"):
        return f"Data file: {file_name}."
    
    # For documents, create a generic APA reference
    if source_type == "pdf":
        return f"{file_name} [PDF document]."
    elif source_type == "docx":
        return f"{file_name} [Word document]."
    elif source_type == "txt":
        return f"{file_name} [Text file]."
    else:
        return f"{file_name}."


def format_reference_entry(
    source_id: str,
    source_metadata: dict,
    evidence: dict
) -> str:
    """Format a complete reference entry for the references section."""
    citation = format_apa_citation(source_metadata, evidence.get("content", ""))
    return citation
