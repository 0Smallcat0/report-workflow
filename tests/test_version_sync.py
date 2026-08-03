"""The release-tag guard compares the git tag to __version__; keep it synced with pyproject."""
import json
import tomllib
import unittest
from pathlib import Path

import report_workflow

ROOT = Path(__file__).resolve().parent.parent


class VersionSyncTest(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        pyproject = ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(report_workflow.__version__, data["project"]["version"])

    def test_mcp_registry_entry_describes_this_release(self):
        """A third place the version lives, and the only one nobody runs.

        `server.json` is read by the MCP Registry, not by this package, so a
        stale version there is invisible until a publish is rejected. The
        registry also verifies PyPI ownership by finding `mcp-name: <name>` in
        the *published* README, which means the marker has to agree with
        server.json and has to ship inside the release itself.
        """
        spec = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
        self.assertEqual(report_workflow.__version__, spec["version"])
        for package in spec["packages"]:
            self.assertEqual(report_workflow.__version__, package["version"])

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"mcp-name: {spec['name']}", readme)


if __name__ == "__main__":
    unittest.main()
