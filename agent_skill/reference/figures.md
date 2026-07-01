# Figures: Non-Quantitative Illustrations vs Data Charts

Load this reference when a report needs a figure, diagram, schematic, or chart.
It applies only while generating or revising a report with `report-workflow`. For
standalone image, diagram, or slide requests, use the appropriate visual skill
directly instead of broadening this workflow.

## Contents

- [Choose the Visual Surface](#choose-the-visual-surface)
- [Compact Illustration Taxonomy](#compact-illustration-taxonomy)
- [Profile Defaults](#profile-defaults)
- [Generated Illustration Insertion Contract](#generated-illustration-insertion-contract)
- [Evidence Boundary for AI Illustrations](#evidence-boundary-for-ai-illustrations)
- [Reusable Illustration Prompt Pattern](#reusable-illustration-prompt-pattern)

## Choose the Visual Surface

Actively choose the visual surface before drafting. Do not wait for the user to
ask for a figure when a non-quantitative visual would make a method, mechanism,
setup, workflow, architecture, or concept easier to understand.

- **Data charts** — use the deterministic workflow chart path for any accepted
  `source_data` values, plotted comparisons, scored matrices, axes, or
  source-backed quantitative claims: `figure_recommendations.json`,
  `section_drafts/figure_plan.json`, `FIGURE_PLAN_AUDIT`, and `FIGURE_BUILD`. No
  AI-generated image may replace a source-data-backed chart, table, plotted
  value, materiality matrix, ranking, or quantitative comparison.
- **Mermaid diagrams** — use when the figure should stay editable as a flowchart,
  process, decision tree, architecture, sequence, or state diagram.
- **AI illustrations** — use image generation or request an illustration asset
  when the report needs a polished non-quantitative schematic rather than an
  editable diagram.

## Compact Illustration Taxonomy

Non-quantitative illustration assets, by visual family:

- **Academic/scientific**: graphical abstract, method pipeline, mechanism/pathway,
  multi-scale or nested view, lifecycle/cycle, qualitative condition comparison,
  or conceptual framework.
- **Engineering**: apparatus/test setup, system or control architecture, test
  bench workflow, device/material cross-section, or safety/operation concept.
- **Business-report/corporate-report**: value chain, value creation model,
  business model or capability map, process map/swimlane/BPMN-lite,
  stakeholder/ecosystem map, roadmap/change journey, or qualitative
  risk/control/materiality map.

## Profile Defaults

- `engineering_lab_report`: use non-quantitative illustrations selectively for
  apparatus/setup, experiment workflow, control/system architecture, test bench
  workflow, cross-section, safety concept, or operation concept.
- `business_report`, `proposal`, `admissions_report`,
  `admissions_project_report`, and `custom`: proactively consider 1-2 value
  chain, concept map, roadmap, stakeholder/ecosystem, process overview, or
  operating-model visuals when they improve readability and do not claim data.
- `academic_paper`: use only publication-style graphical abstract, method,
  mechanism, conceptual, or multi-scale figures that do not imply unsupported
  results.

When Codex image generation or the `imagegen` skill is available and the user
expects a complete report, generate the non-quantitative illustration asset
instead of leaving only a prompt. If image generation is unavailable, write the
reusable prompt and mark the figure as pending external asset creation.

## Generated Illustration Insertion Contract

- Save or copy generated PNG assets into the current run directory under
  `figures/<descriptive_slug>.png`; leave the original generated image in place.
- Embed these assets directly in the relevant `section_drafts/*.md` with Markdown
  image syntax such as `![Schematic - Apparatus setup](figures/apparatus_setup.png)`.
- Do not add direct imagegen assets to `section_drafts/figure_plan.json`, outline
  `figure_ids`, or `[FIGURE:<id>]` placeholders. Those are for deterministic
  `FIGURE_BUILD` manifest-backed charts unless the workflow explicitly produced a
  matching manifest entry.
- Avoid numbered prose references such as "Figure 1" for direct imagegen assets
  unless they are backed by an existing outline/manifest figure ID. Use nearby
  wording such as "the schematic below" plus a short unnumbered caption.

## Evidence Boundary for AI Illustrations

AI-generated academic, engineering, or corporate illustrations are illustrative
assets only. They must not invent numeric values, axes, tick marks, color-scale
ranges, equations, measured outcomes, comparison results, rankings, scores,
experimental results, or source-backed claims. If the figure needs measurements,
plotted values, scored positions, or evidence-backed priorities, use the
deterministic chart path or keep the exact values in a table.

## Reusable Illustration Prompt Pattern

```text
Goal/concept: <one-sentence concept the figure explains>
Visual family: <academic/scientific | engineering | business-report/corporate-report>
Figure type (examples, non-exhaustive): <apparatus setup | test bench workflow |
device/material cross-section | safety/operation concept | method pipeline |
system/control architecture | scientific schematic | mechanism/pathway |
multi-scale/nested view | lifecycle/cycle | graphical abstract | value chain |
value creation model | business model/capability map |
process map/swimlane/BPMN-lite | stakeholder/ecosystem map |
roadmap/change journey | qualitative risk/control/materiality map |
concept illustration>
Layout style: <linear | circular | parallel | nested | storyboard | map/network>
Audience: <technical reviewers | lab instructor | executives | admissions reviewers>
Required labels: <labels that are source-supported or explicitly requested>
Source basis: <accepted source ids, user instructions, or "conceptual only">
Evidence boundary: <what the visual may explain, and what it must not claim>
Forbidden content: no fabricated data, axes, tick marks, color scales,
equations, measured outcomes, rankings, scores, comparison results,
experimental results, or claims not present in the sources
Style: white background, publication font, precise geometry, muted palette,
3-4 colors maximum, clear visual hierarchy, readable in grayscale
```
