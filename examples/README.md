# Examples

Runnable, self-contained demonstrations. No LLM, no network, no API key.

## `source_to_report.py`

The whole path: three ordinary files in `data/` plus one sentence of intent,
out the other end a finished `published/report.docx` with a table of contents,
page numbers, a real Word table, a chart drawn from the monthly figures, and a
QA pack recording why each sentence was allowed to ship.

```bash
python examples/source_to_report.py
```

The middle phase is the part this package does not do. Preparing the evidence
ledger and validating/rendering the result are deterministic; choosing the
claims and writing the prose is your agent's job, and the script does it with
fixed text instead of a model so the example runs offline. Swap `SOURCES` and
`PROMPT` at the top for your own material.

Full fidelity needs pandoc 3.x; without it the renderer falls back to
`python-docx` with degraded tables and layout. Unlike the gate demo below, this
one is not run in CI — it renders a real document, which CI has no renderer for.

## `anti_hallucination_gate.py`

Runs the pipeline's real factuality checkers
(`report_workflow.nodes.factuality_check`) against a tiny in-file evidence ledger
to show the core guarantee: an honest draft publishes clean, while an invented
statistic and a fabricated citation are each hard-blocked with the specific gate
and reason that caught them.

```bash
python examples/anti_hallucination_gate.py
```

Expected: the honest run reports `3 verified, 0 blocked`; the hallucinated run
reports `1 verified, 2 blocked` — **FE** catches the invented number (not present
in the evidence content) and **FA** catches the citation to evidence that does
not exist. The script exits `0` only if that outcome holds, so it doubles as a
regression check and runs in CI.
