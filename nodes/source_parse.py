"""SOURCE_PARSE node - parse files using structured/semi-structured/agent-fallback/validator."""
from pathlib import Path
from ..state import ReportState, SourceRegistryEntry, SourceContentBlock
from ..parsers.structured_parser import parse_structured
from ..parsers.semi_structured_parser import parse_semi_structured
from ..parsers.agent_fallback import parse_agent_fallback
from ..validators.parse_validator import validate_parsed_output, should_retry_with_fallback

STRUCTURED_TYPES = {"csv", "xlsx", "json"}
SEMI_STRUCTURED_TYPES = {"pdf", "docx", "txt"}


def parse_single_source(entry: dict) -> dict:
    """Parse a single source file using pipeline A→B→[C]→D."""
    file_type = entry.get("file_type", "")
    file_path = entry.get("file_name", "")
    
    # Try to find the file
    path = Path(file_path)
    if not path.exists():
        path = Path.cwd() / file_path
    if not path.exists():
        return {"blocks": [], "error": f"File not found: {file_path}"}
    
    entry["parse_attempts"] = entry.get("parse_attempts", 0) + 1
    
    # A: structured_parser
    if file_type in STRUCTURED_TYPES:
        result = parse_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
        # Retry once
        result = parse_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
    
    # B: semi_structured_parser
    if file_type in SEMI_STRUCTURED_TYPES:
        result = parse_semi_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
        # Retry once
        result = parse_semi_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
    
    # C: agent_fallback
    result = parse_agent_fallback(str(path), file_type)
    is_valid, reason = validate_parsed_output(result)
    if is_valid:
        return result
    
    # Still failing - skip source
    return {"blocks": [], "error": f"Failed to parse: {reason}", "success": False}


def run_source_parse(state: ReportState) -> ReportState:
    """T6: SOURCE_PARSE - parse all sources in corpus_manifest."""
    source_registry = state.sources.get("source_registry", [])
    
    updated_registry = []
    for entry in source_registry:
        parsed = parse_single_source(entry)
        
        # Convert blocks to SourceContentBlock models
        blocks = []
        for b in parsed.get("blocks", []):
            blocks.append(SourceContentBlock(
                block_id=b.get("block_id", ""),
                block_type=b.get("block_type", "paragraph"),
                content=b.get("content", ""),
                page_number=b.get("page_number"),
                table_data=b.get("table_data")
            ))
        
        entry["parsed_content"] = [b.model_dump() for b in blocks]
        updated_registry.append(entry)
    
    state.sources["source_registry"] = updated_registry
    return state
