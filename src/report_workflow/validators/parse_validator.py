"""Parse validator - validates parsed output."""


def block_text(block: dict) -> str:
    """Return comparable text for paragraph or table-like parser blocks."""
    content = block.get("content", "")
    if content and content.strip():
        return content

    table_data = block.get("table_data")
    if not table_data:
        return ""

    rows = []
    for row in table_data:
        rows.append(" ".join(str(cell) for cell in row if cell is not None))
    return "\n".join(rows)


def validate_parsed_output(parsed: dict) -> tuple[bool, str]:
    """Validate parsed output.
    
    Returns (is_valid, reason)
    """
    blocks = parsed.get("blocks", [])
    
    # Check: non-empty content
    if not blocks:
        return False, "No content blocks found"
    
    # Check: at least one block
    if len(blocks) == 0:
        return False, "Empty block list"
    
    # Check: content not too short
    total_content = " ".join(block_text(b) for b in blocks)
    if len(total_content.strip()) < 10:
        return False, f"Content too short ({len(total_content)} chars)"
    
    # Check: success flag or has content
    if parsed.get("success") is False and not total_content.strip():
        return False, "Parser reported failure and no content available"
    
    return True, "Valid"
