# Benchmark Prepare Smoke

Date: 2026-05-13

Scope: prepare-stage smoke only. This verifies that the benchmark fixture can
enter the deterministic workflow for every built-in `report_profile` and reach
the normal `awaiting_agent_artifacts` state. It does not replace full
author-validate-render-publish benchmark runs.

Command:

```powershell
$env:PYTHONPATH='src'
@'
from pathlib import Path
from report_workflow.run_workflow import prepare_workflow

profiles = [
    'engineering_lab_report',
    'academic_paper',
    'business_report',
    'proposal',
    'admissions_report',
    'admissions_project_report',
    'custom',
]
fixture = str(Path('benchmarks/fixtures/controlled_source.md').resolve())
for profile in profiles:
    state = prepare_workflow(
        f'Benchmark smoke for {profile}',
        [fixture],
        'out/benchmark-smoke',
        report_profile=profile,
    )
    print(f'{profile}: {state.status} {state.job_id}')
'@ | python -
```

Observed results:

| `report_profile` | Status | Job ID |
| --- | --- | --- |
| `engineering_lab_report` | `awaiting_agent_artifacts` | `run_a5f2eccb` |
| `academic_paper` | `awaiting_agent_artifacts` | `run_7373129b` |
| `business_report` | `awaiting_agent_artifacts` | `run_0f6ac220` |
| `proposal` | `awaiting_agent_artifacts` | `run_70e04be1` |
| `admissions_report` | `awaiting_agent_artifacts` | `run_17d5c0b7` |
| `admissions_project_report` | `awaiting_agent_artifacts` | `run_b670220b` |
| `custom` | `awaiting_agent_artifacts` | `run_385e46df` |

Next benchmark step: create agent-authored artifacts for each profile, publish
the controlled reports, and archive representative QA summaries outside ignored
runtime folders before promoting any deterministic hard-gate changes.
