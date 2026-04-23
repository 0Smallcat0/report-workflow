"""Tests for Mermaid diagram auto-conversion in docx_render."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from report_workflow.nodes.docx_render import (
    _find_mmdc,
    _convert_mermaid_blocks,
    _MERMAID_BLOCK_RE,
)


class MermaidBlockRegexTests(unittest.TestCase):
    """Test the mermaid code fence regex."""

    def test_matches_simple_block(self):
        md = '```mermaid\ngraph LR\n  A --> B\n```'
        matches = _MERMAID_BLOCK_RE.findall(md)
        self.assertEqual(len(matches), 1)
        self.assertIn("graph LR", matches[0])

    def test_matches_multiple_blocks(self):
        md = '```mermaid\ngraph LR\n  A-->B\n```\n\nSome text.\n\n```mermaid\nsequenceDiagram\n  A->>B: Hello\n```'
        matches = _MERMAID_BLOCK_RE.findall(md)
        self.assertEqual(len(matches), 2)

    def test_no_match_for_other_code_fences(self):
        md = '```python\nprint("hello")\n```'
        matches = _MERMAID_BLOCK_RE.findall(md)
        self.assertEqual(len(matches), 0)

    def test_no_match_for_plain_text(self):
        md = 'This is just text with no code fences.'
        matches = _MERMAID_BLOCK_RE.findall(md)
        self.assertEqual(len(matches), 0)


class FindMmdcTests(unittest.TestCase):
    """Test _find_mmdc discovery."""

    @patch("shutil.which", return_value=None)
    def test_returns_none_when_not_installed(self, mock_which):
        result = _find_mmdc()
        self.assertIsNone(result)

    @patch("shutil.which", return_value="/usr/local/bin/mmdc")
    def test_returns_path_when_on_path(self, mock_which):
        result = _find_mmdc()
        self.assertEqual(result, "/usr/local/bin/mmdc")


class ConvertMermaidBlocksTests(unittest.TestCase):
    """Test _convert_mermaid_blocks function."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def test_no_mermaid_blocks_passthrough(self):
        md = "# Title\n\nSome text with no mermaid.\n"
        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(result, md)
        self.assertEqual(count, 0)

    @patch("report_workflow.nodes.docx_render._find_mmdc", return_value=None)
    def test_mmdc_not_installed_passthrough(self, mock_find):
        md = '```mermaid\ngraph LR\n  A-->B\n```'
        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(result, md)
        self.assertEqual(count, 0)

    @patch("report_workflow.nodes.docx_render._find_mmdc", return_value="/usr/bin/mmdc")
    @patch("subprocess.run")
    def test_successful_conversion(self, mock_run, mock_find):
        md = 'Before\n\n```mermaid\ngraph LR\n  A-->B\n```\n\nAfter'

        # Mock successful mmdc run
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Create the expected output PNG so the check passes
        figures_dir = self.tmpdir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        (figures_dir / "mermaid_figure_1.png").write_bytes(b"fake png")

        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(count, 1)
        self.assertIn("![Figure 1]", result)
        self.assertNotIn("```mermaid", result)
        self.assertIn("Before", result)
        self.assertIn("After", result)

    @patch("report_workflow.nodes.docx_render._find_mmdc", return_value="/usr/bin/mmdc")
    @patch("subprocess.run")
    def test_failed_conversion_preserves_block(self, mock_run, mock_find):
        md = '```mermaid\ngraph LR\n  A-->B\n```'

        # Mock failed mmdc run
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(count, 0)
        self.assertIn("```mermaid", result)

    @patch("report_workflow.nodes.docx_render._find_mmdc", return_value="/usr/bin/mmdc")
    @patch("subprocess.run")
    def test_multiple_blocks_numbered(self, mock_run, mock_find):
        md = '```mermaid\ngraph A\n```\n\n```mermaid\ngraph B\n```\n\n```mermaid\ngraph C\n```'

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Create all expected PNGs
        figures_dir = self.tmpdir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, 4):
            (figures_dir / f"mermaid_figure_{i}.png").write_bytes(b"fake")

        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(count, 3)
        self.assertIn("![Figure 1]", result)
        self.assertIn("![Figure 2]", result)
        self.assertIn("![Figure 3]", result)

    @patch("report_workflow.nodes.docx_render._find_mmdc", return_value="/usr/bin/mmdc")
    @patch("subprocess.run", side_effect=Exception("subprocess crash"))
    def test_exception_preserves_block(self, mock_run, mock_find):
        md = '```mermaid\ngraph LR\n  A-->B\n```'
        result, count = _convert_mermaid_blocks(md, self.tmpdir)
        self.assertEqual(count, 0)
        self.assertIn("```mermaid", result)


if __name__ == "__main__":
    unittest.main()
