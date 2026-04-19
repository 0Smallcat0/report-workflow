from report_workflow.errors import QAHardBlockError

def planned_section_ids(blueprint: dict, outline: dict) -> list[str]:
    """Return the ordered list of sections from the blueprint that are actually planned in the outline."""
    outline_secs = outline.get("sections", {})
    return [sec for sec in blueprint.get("section_order", []) if sec in outline_secs]

def validate_required_outline_sections(blueprint: dict, outline_sections: dict) -> None:
    """Validate that all required sections from blueprint are present in the outline."""
    sections = blueprint.get("sections", {})
    if sections:
        required = [sec_id for sec_id, sec in sections.items() if sec.get("required", False)]
    else:
        required = blueprint.get("required_sections", blueprint.get("section_order", []))
    missing = [sec for sec in required if sec not in outline_sections]
    if missing:
        raise QAHardBlockError(f"Outline missing required sections: {missing}")

def section_requires_claims(blueprint: dict, section_id: str) -> bool:
    """Check if a section requires claims. References and appendix usually do not."""
    return section_id not in {"references", "appendix"}
