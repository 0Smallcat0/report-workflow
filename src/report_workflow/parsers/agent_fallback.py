"""Agent fallback parser is intentionally unavailable in the local MVP."""


def parse_agent_fallback(file_path: str, file_type: str) -> dict:
    """Return an explicit non-support result instead of pretending to parse."""
    return {
        "blocks": [],
        "error": (
            "agent fallback parser is not implemented in the local MVP; "
            f"deterministic parser could not handle file_type={file_type!r}"
        ),
        "success": False,
    }
