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

# Section types whose text is not prose making assertions, so there is nothing
# for a claim to be about. A cover page carries a title, a course, an author and
# a date; a reference list carries sources; an appendix carries raw material.
# Demanding claim ids for these forces the author to invent a link.
CLAIMLESS_SECTION_TYPES = frozenset({"front_matter", "references", "appendix"})

# Fallback for blueprints that predate `section_type` on every section.
_CLAIMLESS_SECTION_IDS = frozenset({"cover", "references", "appendix"})


def section_requires_claims(blueprint: dict, section_id: str) -> bool:
    """Check whether a section must list the claims it covers.

    Decided by what kind of section it is, not by its id: a required cover page
    can no more cite evidence than a reference list can, and hardcoding ids
    meant every profile had to be remembered separately.
    """
    section = (blueprint.get("sections") or {}).get(section_id) or {}
    section_type = section.get("section_type", "")
    if section_type:
        return section_type not in CLAIMLESS_SECTION_TYPES
    return section_id not in _CLAIMLESS_SECTION_IDS
