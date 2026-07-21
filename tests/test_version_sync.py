"""The release-tag guard compares the git tag to __version__; keep it synced with pyproject."""
import tomllib
import unittest
from pathlib import Path

import report_workflow


class VersionSyncTest(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(report_workflow.__version__, data["project"]["version"])


if __name__ == "__main__":
    unittest.main()
