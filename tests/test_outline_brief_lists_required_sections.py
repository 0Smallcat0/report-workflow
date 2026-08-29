"""The outline brief has to name every section the validator will demand.

A first run writes exactly what the brief shows. The brief's Required Output
block hard-coded a single `results` section, while
`validate_required_outline_sections` refuses an outline missing any section the
blueprint marks required — nine of them for `academic_paper`. So the documented
shape was rejected by the gate that reads it, and the author's only way forward
was to read the blueprint and infer what the brief had left out.

The two must be generated from the same list, and this asserts they are.
"""
import unittest

from report_workflow.nodes.agent_tasks import outline_brief_section_ids
from report_workflow.nodes.section_contract import validate_required_outline_sections
from report_workflow.errors import QAHardBlockError


BLUEPRINT = {
    "section_order": ["abstract", "introduction", "methods", "results", "conclusion"],
    "sections": {
        "abstract": {"section_id": "abstract", "required": True},
        "introduction": {"section_id": "introduction", "required": True},
        "methods": {"section_id": "methods", "required": True},
        "results": {"section_id": "results", "required": True},
        "conclusion": {"section_id": "conclusion", "required": True},
        "appendix": {"section_id": "appendix", "required": False},
    },
}


class OutlineBriefMatchesTheValidatorTests(unittest.TestCase):
    def test_the_brief_names_every_required_section(self):
        shown = outline_brief_section_ids(BLUEPRINT)
        for section_id, section in BLUEPRINT["sections"].items():
            if section.get("required"):
                self.assertIn(
                    section_id, shown,
                    f"{section_id} is required but the brief never shows it",
                )

    def test_an_outline_built_from_the_brief_passes_the_validator(self):
        outline_sections = {sid: {"section_id": sid} for sid in outline_brief_section_ids(BLUEPRINT)}
        validate_required_outline_sections(BLUEPRINT, outline_sections)

    def test_a_brief_missing_a_section_is_what_the_validator_rejects(self):
        # The shape the brief used to document: results alone.
        with self.assertRaises(QAHardBlockError):
            validate_required_outline_sections(BLUEPRINT, {"results": {"section_id": "results"}})


if __name__ == "__main__":
    unittest.main()
