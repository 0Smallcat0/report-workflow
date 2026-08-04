# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

The authoritative repository guide is **[AGENTS.md](AGENTS.md)** — concepts,
project layout, commands, stage lists, artifact contract, hard gates, and
extension points all live there as the single source of truth. Read it first.

- Operating the skill to generate a report → `skills/report-workflow/SKILL.md` and its
  `reference/` files (the tool surface is documented there and in
  `skills/report-workflow/reference/tools.md`).
- Human-facing overview and install → `README.md`.

Quick start:

```powershell
pip install -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

Do not reintroduce `report_family`, `--family`, detail, subtype, or variant
selectors; `report_profile` is the only public report-shape selector. See
AGENTS.md "Public Contract" and "Hard Gates" for the rules.
