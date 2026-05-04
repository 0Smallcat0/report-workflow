"""Sync the repo-local report-workflow skill into a Codex skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


SKILL_FILES = ("SKILL.md", "skill.yaml", "agent_instructions.md")


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def sync_skill(source_dir: Path, dest_dir: Path, write: bool) -> list[tuple[Path, Path]]:
    operations: list[tuple[Path, Path]] = []
    for file_name in SKILL_FILES:
        source = source_dir / file_name
        if not source.exists():
            raise FileNotFoundError(f"missing source skill file: {source}")
        operations.append((source, dest_dir / file_name))

    if write:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for source, dest in operations:
            shutil.copy2(source, dest)

    return operations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or update the report-workflow Codex skill from agent_skill/."
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=default_codex_home() / "skills" / "report-workflow",
        help="Destination skill directory. Defaults to $CODEX_HOME/skills/report-workflow.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Copy files. Without this flag, only print the planned operations.",
    )
    args = parser.parse_args()

    source_dir = repo_root_from_script() / "agent_skill"
    operations = sync_skill(source_dir, args.dest.expanduser(), args.write)

    mode = "copied" if args.write else "would copy"
    for source, dest in operations:
        print(f"{mode}: {source} -> {dest}")
    if not args.write:
        print("dry run only; rerun with --write to update the installed skill")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
