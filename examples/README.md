# Examples

Runnable, self-contained demonstrations. No LLM, no network, no API key.

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
