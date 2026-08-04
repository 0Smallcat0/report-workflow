# Agent Onboarding: Report Workflow

Conceptual entry point. `report-workflow` is a deterministic source-to-report
pipeline: given source files, it produces a structured, evidence-linked,
DOCX-ready report package. The Python package does **not** call an LLM — the
pipeline owns parsing, evidence normalization, validation gates, rendering,
checkpoints, and packaging, while the external agent owns judgment, claim
planning, outlining, and drafting.

Three phases: **Prepare** (parse sources, freeze a `report_profile`, write task
briefs) → **Author** (the agent writes claims, outline, drafts, sentence map) →
**Validate + Render** (deterministic validation, citation resolution, factuality
and profile checks, DOCX render, and `published/qa/` packaging).

Where to go next:

- Full development contract (layout, commands, stage lists, artifact contract,
  hard gates, extension points) → **[AGENTS.md](AGENTS.md)** (authoritative).
- Operating the skill to generate a report → `skills/report-workflow/SKILL.md` and its
  `reference/` files (profiles, authoring, figures, engineering-lab, revision).
- Human-facing overview and install → `README.md`.
