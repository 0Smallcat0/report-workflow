"""Do the places this version lives agree, and did the tag actually ship?

The version is written in four files and read by four different consumers, and
they drift independently. Two failures have already happened here:

* Eleven tags shipped to PyPI while the repository's own release page still
  advertised a version from the previous month.
* A release was committed and tagged and never published, so
  `.claude-plugin/plugin.json` pointed `uvx` at a PyPI version that did not
  contain the fixes. Testing through MCP then measured the *old* code and
  reported the fixes as not working — they were, they were just not shipped.

Both were invisible until someone happened to look. This makes them CI
failures instead.

Being ahead of PyPI is normal: that is what unreleased work looks like. What
is not normal is a tag that exists without the matching release on PyPI, or
PyPI carrying a version this repository has never heard of.

    python scripts/check_version_sync.py           # offline: the four files
    python scripts/check_version_sync.py --pypi    # also: tags and PyPI
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPI_JSON_URL = "https://pypi.org/pypi/report-workflow/json"
PYPI_TIMEOUT_SECONDS = 20


def declared_versions() -> dict[str, str]:
    """Every version string in the repository, by the file that holds it."""
    versions: dict[str, str] = {}

    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        versions["pyproject.toml"] = tomllib.load(handle)["project"]["version"]

    init_text = (REPO_ROOT / "src" / "report_workflow" / "__init__.py").read_text(
        encoding="utf-8"
    )
    for line in init_text.splitlines():
        if line.startswith("__version__"):
            versions["src/report_workflow/__init__.py"] = (
                line.split("=", 1)[1].strip().strip("\"'")
            )
            break

    plugin = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    versions[".claude-plugin/plugin.json"] = str(plugin.get("version", ""))

    server = json.loads((REPO_ROOT / "server.json").read_text(encoding="utf-8"))
    versions["server.json"] = str(server.get("version", ""))
    for index, package in enumerate(server.get("packages", [])):
        versions[f"server.json packages[{index}]"] = str(package.get("version", ""))

    return versions


def check_declared() -> tuple[str, list[str]]:
    """Return the agreed version, and any disagreements."""
    versions = declared_versions()
    distinct = sorted(set(versions.values()))
    if len(distinct) == 1:
        return distinct[0], []
    listed = "\n".join(f"    {where}: {value}" for where, value in sorted(versions.items()))
    return versions["pyproject.toml"], [
        "the repository states more than one version:\n" + listed
    ]


def _git_tags() -> set[str]:
    result = subprocess.run(
        ["git", "tag", "--list"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _pypi_versions() -> set[str]:
    with urllib.request.urlopen(PYPI_JSON_URL, timeout=PYPI_TIMEOUT_SECONDS) as response:
        payload = json.load(response)
    return set(payload.get("releases", {}))


def _as_tuple(text: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in text.split("."))


def check_published(version: str) -> list[str]:
    """Has the tag for this version actually reached PyPI?

    A network failure is reported as a failure rather than skipped. A check
    that quietly passes when it could not run is how the drift it exists to
    catch went unnoticed for eleven releases.
    """
    try:
        published = _pypi_versions()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return [f"could not read the published versions from PyPI: {exc}"]

    problems: list[str] = []
    tags = _git_tags()

    if f"v{version}" in tags and version not in published:
        problems.append(
            f"tag v{version} exists but PyPI has no {version}. The tag did not publish, "
            f"so `uvx --from report-workflow ...` — which is what "
            f".claude-plugin/plugin.json runs — still installs an older release. "
            f"Re-push the tag, or check the release workflow run."
        )

    try:
        newer = sorted(
            (
                candidate
                for candidate in published
                if _as_tuple(candidate) > _as_tuple(version)
            ),
            key=_as_tuple,
        )
    except TypeError:
        newer = []
    if newer:
        problems.append(
            f"PyPI already carries {', '.join(newer)}, which is newer than this "
            f"repository's {version}. Something published from outside this tree, or "
            f"a version bump was reverted."
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pypi",
        action="store_true",
        help="also compare against git tags and the versions published to PyPI",
    )
    args = parser.parse_args(argv)

    version, problems = check_declared()
    if not problems and args.pypi:
        problems.extend(check_published(version))

    if problems:
        print("version sync check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    scope = "repository and PyPI" if args.pypi else "repository"
    print(f"version sync check passed: {scope} agree on {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
