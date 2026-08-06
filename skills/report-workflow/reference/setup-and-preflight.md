# Setup and Preflight

Detailed setup, dependency, and preflight-decision reference for `report-workflow`.
Load this when preparing a run, resolving a missing dependency, or building the
`preflight_decisions` record. The short flow lives in `SKILL.md`.

## Contents

- [Required Runtime](#required-runtime)
- [Run `check_environment` First](#run-check_environment-first)
- [Windows UTF-8 (Chinese text)](#windows-utf-8-chinese-text)
- [Preflight Decision Examples](#preflight-decision-examples)

## Required Runtime

- Python 3.11+
- `pip install -e .` from the repository root
- Pandoc 3.x for high-quality DOCX rendering. Without pandoc, the pipeline falls
  back to a limited `python-docx` renderer with degraded table, list, and layout
  fidelity.

Optional integrations:

- `mmdc` (`npm install -g @mermaid-js/mermaid-cli`) for Mermaid-to-PNG diagrams.
- `TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY` for optional web
  research and claim verification.
- `notebooklm-py` plus a notebook ID for optional NotebookLM knowledge sync.

## Run `check_environment` First

Call `check_environment` before every `start_report`. It returns the pending
installs, the features to ask the user about, a human-readable `message`, and the
`required_preflight_decisions` template you should fill in.

Then ask the user about every pending install and optional integration. After
installing a dependency, rerun `check_environment` to verify. Do not treat an
`install` or `installed` decision as proof when `check_environment` still reports the
dependency missing: required dependencies must actually pass preflight before
start.

`start_report` requires `preflight_confirmed=True` **and** a complete
`preflight_decisions` record. `preflight_confirmed=True` alone is rejected. The
raw CLI `prepare` entry point requires the same record via
`--preflight-decisions <file.json>`, so command-line runs cannot bypass this
user-confirmation step.

## Windows UTF-8 (Chinese text)

On Windows runs that include Chinese text, configure the console and Python stdio
for UTF-8 before calling the CLI or inline Python helpers:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
```

This avoids cp950 crashes or mojibake in preflight output, template fields, and
Chinese source notes.

## Preflight Decision Examples

Always start from the `required_preflight_decisions` object returned by
`check_environment`. These are common completed shapes, not shortcuts.

All required setup ready, optional integrations skipped:

```python
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Pandoc missing and the user explicitly accepts degraded DOCX rendering:

```python
allow_degraded_render=True,
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {
        "pandoc": "accept_degraded"
    },
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Web research and NotebookLM enabled after the user confirms the backend/API key
and provides a notebook ID:

```python
enable_research=True,
enable_notebook_sync=True,
notebooklm_notebook_id="notebook-id-from-user",
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "enable",
        "notebook_sync": "enable"
    }
}
```

If `check_environment` still reports a required dependency missing, install and rerun
setup. Do not force-start by changing the decision record.
