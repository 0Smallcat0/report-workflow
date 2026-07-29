"""SOURCE_PARSE node - parse files using structured/semi-structured/agent-fallback/validator."""
from pathlib import Path

from ..errors import QAHardBlockError
from ..state import ReportState, SourceContentBlock
from ..config import PROJECT_ROOT
from ..runtime_support import write_json_artifact
from ..parsers.structured_parser import parse_structured
from ..parsers.semi_structured_parser import parse_semi_structured
from ..parsers.code_parser import parse_code
from ..parsers.agent_fallback import parse_agent_fallback
from ..validators.parse_validator import validate_parsed_output

STRUCTURED_TYPES = {"csv", "xlsx", "json", "toml"}
SEMI_STRUCTURED_TYPES = {"pdf", "docx", "txt", "md"}
CODE_TYPES = {"py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "cs", "go", "rs", "rb", "php", "swift", "kt", "scala"}


def parse_single_source(entry: dict) -> dict:
    """Parse a single source file using deterministic parsers first."""
    file_type = entry.get("file_type", "")
    file_path = entry.get("file_path") or entry.get("file_name", "")

    path = Path(file_path)
    if not path.exists():
        path = PROJECT_ROOT / file_path
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
        # Say it in the reader's terms. A student who attached lecture slides
        # was told "agent fallback parser is not implemented in the local MVP;
        # deterministic parser could not handle file_type='pptx'" — three
        # phrases about this build's internals and not one about their file or
        # what to do with it. The comment below already names this failure for
        # the empty-file case; the unsupported branch left result as None, so
        # primary_error stayed unset and the fallback's wording won here too.
        result = None
        supported = ", ".join(
            sorted(set(STRUCTURED_TYPES) | set(SEMI_STRUCTURED_TYPES) | set(CODE_TYPES))
        )
        reason = (
            f".{file_type} files are not read by this tool. Supported: {supported}. "
            "Export the content to one of those — slides and pages usually go to "
            ".pdf, and plain notes to .md or .txt — and attach that instead."
        )

    # What the type-specific parser itself concluded is the most specific
    # diagnosis available — "Package not found" for a file that is not really a
    # .docx, or no readable content for an empty one. The fallback below
    # replaces `result`, so decide this first. Preferring the fallback's
    # "not implemented in the local MVP" told a user who attached a zero-byte
    # file that Markdown is unsupported: a statement about this build, offered
    # as if it described their file.
    primary_error = None
    if isinstance(result, dict):
        primary_error = result.get("error")
        if not primary_error and not result.get("blocks"):
            primary_error = "the file contains no readable content"

    fallback = parse_agent_fallback(str(path), file_type)
    is_valid, fallback_reason = validate_parsed_output(fallback)
    if is_valid:
        return fallback

    return {
        "blocks": [],
        # `reason` outranks the fallback's wording: when a parser produced a
        # dict, primary_error already holds the specific diagnosis, so reason
        # only decides the case where no parser ran at all — the unsupported
        # type, where it is the most specific thing anyone knows.
        "error": primary_error or reason or fallback.get("error") or fallback_reason,
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
    unreadable: list[str] = []
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
            # `reason` is what the type-specific validator concluded — the file
            # is empty, or python-docx could not open it. `parsed["error"]` is
            # the fallback parser announcing that it does not exist in this
            # build. Preferring the latter told a user who attached a zero-byte
            # file that Markdown is unsupported, blaming the format for a
            # condition of their file. The diagnosis was already in hand.
            # Most specific diagnosis first. The fallback's "not implemented in
            # the local MVP" is the only one that describes this build rather
            # than the file, so it comes last: preferring it told a user who
            # attached a zero-byte file that Markdown is unsupported.
            entry["parse_error"] = parsed.get("error") or reason
            if entry.get("artifact_role", "source_data") == "source_data":
                # Collected, not raised here. Raising on the first one meant an
                # author with three unreadable attachments discovered them one
                # per run: fix, resubmit, meet the next. One pass already knows
                # about all of them.
                unreadable.append(
                    f"{entry.get('file_name')}: {entry['parse_error']}"
                )

        updated_registry.append(entry)

    if unreadable:
        if len(unreadable) == 1:
            raise QAHardBlockError(f"Failed to parse source {unreadable[0]}")
        listed = "; ".join(unreadable)
        raise QAHardBlockError(
            f"Failed to parse {len(unreadable)} sources — {listed}"
        )

    if not any(entry.get("parsed_content") for entry in updated_registry):
        # In revise_existing mode with only base_document entries, BASE_DOCUMENT_PARSE handles them downstream
        task_intent = state.spec.get("task_intent", "new_draft")
        only_base_docs = all(
            entry.get("artifact_role") == "base_document"
            for entry in updated_registry
        )
        if not (task_intent == "revise_existing" and only_base_docs):
            raise QAHardBlockError("No source content was parsed")

    state.sources["source_registry"] = updated_registry
    state.sources["source_registry_path"] = write_json_artifact(state, "source_registry.json", updated_registry)
    return state
