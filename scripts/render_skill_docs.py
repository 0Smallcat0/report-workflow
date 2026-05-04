"""Render generated skill documentation blocks from agent_skill/skill.yaml."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


START_MARKER = "<!-- report-workflow:tool-surface:start -->"
END_MARKER = "<!-- report-workflow:tool-surface:end -->"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def load_tool_names(skill_yaml_path: Path) -> list[str]:
    data = yaml.safe_load(skill_yaml_path.read_text(encoding="utf-8"))
    return [str(tool["name"]) for tool in data["tools"]]


def render_tool_surface(tool_names: list[str]) -> str:
    lines = [START_MARKER]
    lines.extend(f"- `{tool_name}`" for tool_name in tool_names)
    lines.append(END_MARKER)
    return "\n".join(lines)


def replace_generated_block(text: str, rendered_block: str) -> str:
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError("missing generated tool-surface markers")
    end += len(END_MARKER)
    return text[:start] + rendered_block + text[end:]


def render_docs(repo_root: Path, *, write: bool = False) -> list[dict[str, object]]:
    repo_root = repo_root.resolve()
    rendered_block = render_tool_surface(load_tool_names(repo_root / "agent_skill" / "skill.yaml"))
    targets = [
        repo_root / "agent_skill" / "SKILL.md",
        repo_root / "CLAUDE.md",
    ]
    results: list[dict[str, object]] = []

    for target in targets:
        original = target.read_text(encoding="utf-8")
        updated = replace_generated_block(original, rendered_block)
        changed = updated != original
        if write and changed:
            target.write_text(updated, encoding="utf-8")
        results.append({"path": target, "changed": changed})

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or update generated report-workflow skill doc blocks."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail if generated blocks are stale.")
    mode.add_argument("--write", action="store_true", help="Update generated blocks in place.")
    args = parser.parse_args()

    results = render_docs(repo_root_from_script(), write=args.write)
    stale = [result for result in results if result["changed"]]
    for result in results:
        status = "stale" if result["changed"] else "ok"
        action = "updated" if args.write and result["changed"] else status
        print(f"{action}: {result['path']}")

    if args.check and stale:
        print("generated skill documentation is stale; rerun with --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
