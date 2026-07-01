"""Render generated skill documentation from agent_skill/skill.yaml.

Generates two things from the single source of truth (skill.yaml):

1. The `report-workflow:tool-surface` marker block (a flat tool-name list) in
   agent_skill/SKILL.md.
2. The full harness-neutral tool catalog at agent_skill/reference/tools.md.

Run `python scripts/render_skill_docs.py --check` to fail on drift, or
`--write` to regenerate in place.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


START_MARKER = "<!-- report-workflow:tool-surface:start -->"
END_MARKER = "<!-- report-workflow:tool-surface:end -->"

TOOLS_DOC_RELATIVE = Path("agent_skill") / "reference" / "tools.md"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def load_tools(skill_yaml_path: Path) -> list[dict]:
    data = yaml.safe_load(skill_yaml_path.read_text(encoding="utf-8"))
    return list(data["tools"])


def load_tool_names(skill_yaml_path: Path) -> list[str]:
    return [str(tool["name"]) for tool in load_tools(skill_yaml_path)]


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def render_tool_surface(tool_names: list[str]) -> str:
    lines = [START_MARKER]
    lines.extend(f"- `{tool_name}`" for tool_name in tool_names)
    lines.append(END_MARKER)
    return "\n".join(lines)


def render_tools_doc(tools: list[dict]) -> str:
    lines = [
        "# Tool Reference",
        "",
        "Generated from `agent_skill/skill.yaml` by `scripts/render_skill_docs.py`.",
        "Do not edit by hand; run `python scripts/render_skill_docs.py --write`.",
        "",
        "The tools are Python functions in `report_workflow.agent_wrapper` that return",
        "JSON-serializable dicts. See the SKILL.md \"Invoking the Tools\" section for how",
        "to call them in each harness (Codex tool, CLI, or `python -c`).",
        "",
    ]
    for tool in tools:
        name = _normalize_text(tool["name"])
        description = _normalize_text(tool.get("description"))
        lines.append(f"## `{name}`")
        lines.append("")
        if description:
            lines.append(description)
            lines.append("")
        parameters = tool.get("parameters") or []
        if parameters:
            lines.append("Parameters:")
            lines.append("")
            for param in parameters:
                pname = _normalize_text(param.get("name"))
                ptype = _normalize_text(param.get("type"))
                required = "required" if param.get("required") else "optional"
                pdesc = _normalize_text(param.get("description"))
                prefix = f"- `{pname}` ({ptype}, {required})"
                lines.append(f"{prefix}: {pdesc}" if pdesc else prefix)
            lines.append("")
        else:
            lines.append("Parameters: none.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_generated_block(text: str, rendered_block: str) -> str:
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError("missing generated tool-surface markers")
    end += len(END_MARKER)
    return text[:start] + rendered_block + text[end:]


def render_docs(repo_root: Path, *, write: bool = False) -> list[dict[str, object]]:
    repo_root = repo_root.resolve()
    tools = load_tools(repo_root / "agent_skill" / "skill.yaml")
    rendered_block = render_tool_surface([str(tool["name"]) for tool in tools])
    results: list[dict[str, object]] = []

    # 1. Marker block in SKILL.md.
    for target in (repo_root / "agent_skill" / "SKILL.md",):
        original = target.read_text(encoding="utf-8")
        updated = replace_generated_block(original, rendered_block)
        changed = updated != original
        if write and changed:
            target.write_text(updated, encoding="utf-8")
        results.append({"path": target, "changed": changed})

    # 2. Full generated tool catalog.
    tools_doc_path = repo_root / TOOLS_DOC_RELATIVE
    rendered_doc = render_tools_doc(tools)
    original_doc = tools_doc_path.read_text(encoding="utf-8") if tools_doc_path.exists() else ""
    doc_changed = rendered_doc != original_doc
    if write and doc_changed:
        tools_doc_path.parent.mkdir(parents=True, exist_ok=True)
        tools_doc_path.write_text(rendered_doc, encoding="utf-8")
    results.append({"path": tools_doc_path, "changed": doc_changed})

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or update generated report-workflow skill docs."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Fail if generated docs are stale.")
    mode.add_argument("--write", action="store_true", help="Update generated docs in place.")
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
