"""The release-tag guard compares the git tag to __version__; keep it synced with pyproject."""
import json
import tomllib
import unittest
import unittest.mock
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

    def test_claude_plugin_manifest_describes_this_release(self):
        """The fourth place the version lives, and the second nobody runs.

        `.claude-plugin/plugin.json` is read by Claude Code at install time, not
        by this package, so a stale version there ships a plugin claiming to be
        something it is not. It also names the skill directory and the command
        that starts the MCP server; both are checked here because a rename
        elsewhere in the repository would otherwise break installation silently.
        """
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(report_workflow.__version__, manifest["version"])

        # Claude Code refuses `"skills": "./"` with "Path escapes plugin
        # directory", so the skill lives where the default layout expects it:
        # <plugin root>/skills/<name>/SKILL.md. Renaming that directory breaks
        # installation without breaking anything else, which is why it is pinned.
        skill_dirs = sorted(p.parent.name for p in ROOT.glob("skills/*/SKILL.md"))
        self.assertEqual(["report-workflow"], skill_dirs)
        self.assertEqual("./skills", manifest["skills"])

        server = manifest["mcpServers"]["report-workflow"]
        self.assertEqual("uvx", server["command"])
        self.assertIn("report-workflow-mcp", server["args"])
        # Both extras: [mcp] is the server itself, [render] carries pandoc, so a
        # plugin user gets real Word tables rather than the degraded fallback
        # without being asked to install anything by hand.
        self.assertIn("report-workflow[mcp,render]", server["args"])

        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        listed = {entry["name"] for entry in marketplace["plugins"]}
        self.assertIn(manifest["name"], listed)


class PublishedVersionTest(unittest.TestCase):
    """The fifth place the version lives is PyPI, and nothing compared it.

    `.claude-plugin/plugin.json` starts the server with
    `uvx --from report-workflow[mcp,render]`, which resolves from PyPI. So a
    release that is committed, tagged and never published leaves every installed
    plugin running the previous version — and testing through MCP then measures
    code that is not the code in this tree. That has already happened once: a
    fix was reported as not working when it was working and simply not shipped.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_version_sync", ROOT / "scripts" / "check_version_sync.py"
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_the_script_sees_the_same_version_this_package_reports(self):
        version, problems = self.module.check_declared()
        self.assertEqual(problems, [])
        self.assertEqual(version, report_workflow.__version__)

    def test_every_version_file_is_covered(self):
        """A file added later without being registered here drifts unwatched."""
        covered = set(self.module.declared_versions())
        for expected in (
            "pyproject.toml",
            "src/report_workflow/__init__.py",
            ".claude-plugin/plugin.json",
            "server.json",
        ):
            self.assertIn(expected, covered)

    def _published(self, version, *, releases, tags):
        with unittest.mock.patch.object(
            self.module, "_pypi_versions", return_value=set(releases)
        ), unittest.mock.patch.object(self.module, "_git_tags", return_value=set(tags)):
            return self.module.check_published(version)

    def _published_with_age(self, version, *, releases, tags, in_flight):
        with unittest.mock.patch.object(
            self.module, "_tag_is_in_flight", return_value=in_flight
        ):
            return self._published(version, releases=releases, tags=tags)

    def test_a_tag_that_never_published_is_a_failure(self):
        problems = self._published_with_age(
            "4.30.0", releases={"4.29.1"}, tags={"v4.29.1", "v4.30.0"}, in_flight=False
        )
        self.assertTrue(problems)
        self.assertIn("did not publish", problems[0])

    def test_a_tag_pushed_minutes_ago_is_still_publishing(self):
        """The CI run for a release push starts before the release finishes.

        Without this the guard failed on every release for a few minutes, over
        something that was not a defect — and a guard that cries wolf on every
        release is one people learn to ignore.
        """
        self.assertEqual(
            self._published_with_age(
                "4.30.0", releases={"4.29.1"}, tags={"v4.30.0"}, in_flight=True
            ),
            [],
        )

    def test_being_ahead_of_pypi_without_a_tag_is_fine(self):
        """Unreleased work is the normal state of the default branch."""
        self.assertEqual(
            self._published("4.30.0", releases={"4.29.1"}, tags={"v4.29.1"}), []
        )

    def test_a_published_release_is_fine(self):
        self.assertEqual(
            self._published("4.30.0", releases={"4.29.1", "4.30.0"}, tags={"v4.30.0"}), []
        )

    def test_pypi_being_ahead_of_the_repository_is_a_failure(self):
        """Eleven versions once shipped while the repository said otherwise."""
        problems = self._published(
            "4.29.1", releases={"4.29.1", "4.30.0"}, tags={"v4.29.1"}
        )
        self.assertTrue(problems)
        self.assertIn("newer than this", problems[0])

    def test_an_unreachable_pypi_is_reported_not_skipped(self):
        """A check that passes when it could not run is how drift survives."""
        import urllib.error

        with unittest.mock.patch.object(
            self.module, "_pypi_versions", side_effect=urllib.error.URLError("offline")
        ):
            problems = self.module.check_published("4.30.0")
        self.assertTrue(problems)
        self.assertIn("could not read", problems[0])


if __name__ == "__main__":
    unittest.main()
