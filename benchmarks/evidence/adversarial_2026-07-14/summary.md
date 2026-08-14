# Adversarial Anti-Hallucination Benchmark (2026-07-14)

- Corpus: **73 cases** — 27 honest controls, 46 hallucinated claims across 17 attack families plus 5 documented evasion variants.
- Gate stack under test: FA (linkage) -> FB (statistical backing) -> FE (deep-audit content overlap) -> FD (wording vs evidence grade).
- Deterministic, offline, no LLM: verdicts come from the exact checker functions in `src/report_workflow/nodes/factuality_check.py`.
- Corpus hash: `55cfd5e41f1651ffa15f73768fd06489f9fd370074e2b5ad54570727193109ed`

## Headline comparison

| Checker | Recall (hallucinations blocked) | False-positive rate (honest blocked) | Precision |
| --- | --- | --- | --- |
| `no_gate` | 0.0% (0/46) | 0.0% (0/27) | 0.0% |
| `citation_presence` | 8.7% (4/46) | 0.0% (0/27) | 100.0% |
| `full_gate_stack` | 89.1% (41/46) | 0.0% (0/27) | 100.0% |

`citation_presence` is the shallow check many retrieval pipelines stop at:
the citation ID exists, therefore the sentence is treated as grounded. It
never reads the evidence content, so every content-level fabrication ships.

## Catch rate by attack family (full gate stack)

| Attack family | Cases | Caught | Catch rate | Gate(s) that fired |
| --- | --- | --- | --- | --- |
| band_label_drift | 1 | 1 | 100.0% | FL |
| cjk_fabrication | 2 | 2 | 100.0% | FE |
| cross_column_direction | 1 | 1 | 100.0% | FT2 |
| cross_language_mismatch | 4 | 4 | 100.0% | FE |
| dangling_claim | 1 | 1 | 100.0% | FA |
| fabricated_citation | 3 | 3 | 100.0% | FA |
| fabricated_quote | 5 | 5 | 100.0% | FE |
| invented_quantity | 1 | 1 | 100.0% | FE |
| invented_statistic | 7 | 7 | 100.0% | FE |
| missing_evidence | 1 | 1 | 100.0% | FA |
| off_topic_citation | 2 | 2 | 100.0% | FE |
| precision_inflation | 2 | 2 | 100.0% | FE |
| question_as_answer | 1 | 1 | 100.0% | FE |
| status_laundering | 2 | 2 | 100.0% | FA |
| type_mismatch | 2 | 2 | 100.0% | FA |
| unit_mismatch | 3 | 3 | 100.0% | FE |
| wording_grade_violation | 3 | 3 | 100.0% | FD |

## Documented evasions (residual risk)

Hallucinations the current gates do **not** catch, kept in the corpus on
purpose. They define the measured boundary of the deterministic approach
and feed the limitations section of `docs/DESIGN.md`:

| Case | Family | Why it slips through |
| --- | --- | --- |
| nf01 | evasion_negation_flip | the source says it fell; negation needs modality, not vocabulary |
| fc01 | evasion_future_as_completed | minutes say the team will do it in Q3; the claim says it is done |
| x02 | evasion_negation_flip | drops the 'should not' from the evidence; lexical overlap cannot see negation |
| x05 | evasion_hedged_interpretation | invented interpretation with enough shared vocabulary to pass term overlap |
| x06 | evasion_value_misattribution | 9.0% is real but belongs to the manual baseline; attribution needs semantics |

## Determinism proof

- 5 consecutive in-process runs produced identical verdicts: `identical = True`.
- Verdict hash (sha256 over all full-stack verdicts): `1faa32b90bd32defe4e529a930cfb317bd79dc0427fa72ea9c06b848d5901a0f`.
- `python scripts/run_adversarial_benchmark.py --check` recomputes every verdict
  from source and fails if any verdict, metric, or hash drifts from this archive —
  the same command runs in CI on Linux, so the hash is also a cross-platform
  reproducibility check.
