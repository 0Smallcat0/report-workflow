"""Regression tests: a rendered report must never end with a dangling
"References" heading that has nothing under it.

Found by auditing a rendered benchmark report (2026-07-15): the fixture drafts
carried no references, the reference list file was empty, and the document
still rendered a bare "References" heading as its final paragraph. Both render
paths are covered — the markdown pre-pass that pandoc consumes
(``_split_body_references``) and the python-docx fallback
(``_add_hanging_indent_references``).
"""
import unittest

from docx import Document

from report_workflow.nodes.docx_render import (
    _add_hanging_indent_references,
    _split_body_references,
)


class SplitBodyReferencesTests(unittest.TestCase):
    def test_empty_trailing_references_section_is_removed(self):
        md = "# Title\n\nBody prose.\n\n## References\n"
        cleaned, refs_md = _split_body_references(md)
        self.assertEqual(refs_md, "")
        self.assertNotIn("References", cleaned)
        self.assertIn("Body prose.", cleaned)

    def test_whitespace_only_references_section_is_removed(self):
        md = "# Title\n\nBody prose.\n\n## References\n\n   \n\n"
        cleaned, refs_md = _split_body_references(md)
        self.assertEqual(refs_md, "")
        self.assertNotIn("References", cleaned)

    def test_populated_references_section_is_extracted(self):
        md = (
            "# Title\n\nBody prose.\n\n## References\n\n"
            "- Doe, J. (2025). A real source. Journal of Examples.\n"
            "- Roe, R. (2024). Another source. Example Press.\n"
        )
        cleaned, refs_md = _split_body_references(md)
        self.assertNotIn("## References", cleaned)
        self.assertIn("## References", refs_md)
        self.assertIn("Doe, J. (2025)", refs_md)
        self.assertIn("Roe, R. (2024)", refs_md)

    def test_document_without_references_is_unchanged(self):
        md = "# Title\n\nBody prose only.\n"
        cleaned, refs_md = _split_body_references(md)
        self.assertEqual(cleaned, md)
        self.assertEqual(refs_md, "")

    def test_mid_document_empty_references_does_not_swallow_next_section(self):
        md = "# Title\n\n## References\n\n## Appendix\n\nAppendix body.\n"
        cleaned, refs_md = _split_body_references(md)
        self.assertEqual(refs_md, "")
        self.assertIn("## Appendix", cleaned)
        self.assertIn("Appendix body.", cleaned)
        self.assertNotIn("## References", cleaned)


class HangingIndentReferencesTests(unittest.TestCase):
    def test_heading_only_reference_md_adds_nothing(self):
        doc = Document()
        before = len(doc.paragraphs)
        _add_hanging_indent_references(doc, "## References\n\n")
        self.assertEqual(len(doc.paragraphs), before)
        self.assertNotIn("References", [p.text for p in doc.paragraphs])

    def test_populated_reference_md_adds_heading_and_entries(self):
        doc = Document()
        _add_hanging_indent_references(
            doc,
            "## References\n\n- Doe, J. (2025). A real source.\n",
        )
        texts = [p.text for p in doc.paragraphs]
        self.assertIn("References", texts)
        self.assertTrue(any("Doe, J. (2025)" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
