"""Parse validator - validates parsed output."""
from typing import Any


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
    total_content = " ".join(b.get("content", "") for b in blocks)
    if len(total_content.strip()) < 50:
        return False, f"Content too short ({len(total_content)} chars)"
    
    # Check: success flag or has content
    if parsed.get("success") is False and not total_content.strip():
        return False, "Parser reported failure and no content available"
    
    return True, "Valid"


def should_retry_with_fallback(parsed: dict) -> bool:
    """Determine if we should retry with fallback parser."""
    is_valid, _ = validate_parsed_output(parsed)
    return not is_valid
