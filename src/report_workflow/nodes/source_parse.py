"""SOURCE_PARSE node - parse files using structured/semi-structured/agent-fallback/validator."""
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, SourceContentBlock
from ..runtime_support import write_json_artifact
from ..parsers.structured_parser import parse_structured
from ..parsers.semi_structured_parser import parse_semi_structured
from ..parsers.code_parser import parse_code
from ..parsers.agent_fallback import parse_agent_fallback
from ..validators.parse_validator import validate_parsed_output

STRUCTURED_TYPES = {"csv", "xlsx", "json"}
SEMI_STRUCTURED_TYPES = {"pdf", "docx", "txt", "md"}
CODE_TYPES = {"py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "cs", "go", "rs", "rb", "php", "swift", "kt", "scala"}


def parse_single_source(entry: dict) -> dict:
    """Parse a single source file using deterministic parsers first."""
    file_type = entry.get("file_type", "")
    file_path = entry.get("file_path") or entry.get("file_name", "")

    path = Path(file_path)
    if not path.exists():
        path = Path.cwd() / file_path
    if not path.exists():
        return {"blocks": [], "error": f"File not found: {file_path}", "success": False}

    entry["parse_attempts"] = entry.get("parse_attempts", 0) + 1

    reason = ""
    if file_type in STRUCTURED_TYPES:
        result = parse_structured(str(path), file_type)
        is_valid, _ = validate_parsed_output(result)
        if is_valid:
            return result

        result = parse_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
    elif file_type in SEMI_STRUCTURED_TYPES:
        result = parse_semi_structured(str(path), file_type)
        is_valid, _ = validate_parsed_output(result)
        if is_valid:
            return result

        result = parse_semi_structured(str(path), file_type)
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
    elif file_type in CODE_TYPES:
        # Code files: structural parse (class/function) or fixed chunks
        result = parse_code(str(path))
        is_valid, _ = validate_parsed_output(result)
        if is_valid:
            return result

        result = parse_code(str(path))
        is_valid, reason = validate_parsed_output(result)
        if is_valid:
            return result
    else:
        reason = f"Unsupported file type: {file_type}"

    result = parse_agent_fallback(str(path), file_type)
    is_valid, fallback_reason = validate_parsed_output(result)
    if is_valid:
        return result

    return {
        "blocks": [],
        "error": result.get("error") or fallback_reason or reason,
        "success": False,
    }


def run_source_parse(state: ReportState) -> ReportState:
    """T6: SOURCE_PARSE - parse all sources in source_registry.

    Skips entries with artifact_role == 'base_document';
    those are handled by BASE_DOCUMENT_PARSE.
    """
    source_registry = state.sources.get("source_registry", [])
    if not source_registry:
        raise QAHardBlockError("No registered sources to parse")

    updated_registry = []
    for entry in source_registry:
        # base_document entries are handled by BASE_DOCUMENT_PARSE, skip here
        if entry.get("artifact_role") == "base_document":
            entry["parse_status"] = "skipped"
            entry["parse_error"] = None
            updated_registry.append(entry)
            continue

        parsed = parse_single_source(entry)
        is_valid, reason = validate_parsed_output(parsed)

        blocks = []
        for block in parsed.get("blocks", []):
            blocks.append(SourceContentBlock(
                block_id=block.get("block_id", ""),
                block_type=block.get("block_type", "paragraph"),
                content=block.get("content", ""),
                page_number=block.get("page_number"),
                table_data=block.get("table_data"),
                source_file_path=block.get("source_file_path"),
                line_start=block.get("line_start"),
                line_end=block.get("line_end"),
                content_hash=block.get("content_hash"),
                quote=block.get("quote"),
            ))

        entry["parsed_content"] = [block.model_dump() for block in blocks]
        if is_valid:
            entry["parse_status"] = "parsed"
            entry["parse_error"] = None
        else:
            entry["parse_status"] = "failed"
            entry["parse_error"] = parsed.get("error") or reason
            if entry.get("artifact_role", "source_data") == "source_data":
                raise QAHardBlockError(
                    f"Failed to parse source {entry.get('file_name')}: {entry['parse_error']}"
                )

        updated_registry.append(entry)

    if not any(entry.get("parsed_content") for entry in updated_registry):
        raise QAHardBlockError("No source content was parsed")

    state.sources["source_registry"] = updated_registry
    state.sources["source_registry_path"] = write_json_artifact(state, "source_registry.json", updated_registry)
    return state
