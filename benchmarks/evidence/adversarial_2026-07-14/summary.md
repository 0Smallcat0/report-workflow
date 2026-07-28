# Adversarial Anti-Hallucination Benchmark (2026-07-14)

- Corpus: **67 cases** — 24 honest controls, 43 hallucinated claims across 14 attack families plus 6 documented evasion variants.
- Gate stack under test: FA (linkage) -> FB (statistical backing) -> FE (deep-audit content overlap) -> FD (wording vs evidence grade).
- Deterministic, offline, no LLM: verdicts come from the exact checker functions in `src/report_workflow/nodes/factuality_check.py`.
- Corpus hash: `1b63b761e21f54ec4b78854dcf5be00219496630d8131367ab06c3f897f7159e`

## Headline comparison

| Checker | Recall (hallucinations blocked) | False-positive rate (honest blocked) | Precision |
| --- | --- | --- | --- |
| `no_gate` | 0.0% (0/43) | 0.0% (0/24) | 0.0% |
| `citation_presence` | 9.3% (4/43) | 0.0% (0/24) | 100.0% |
| `full_gate_stack` | 86.1% (37/43) | 0.0% (0/24) | 100.0% |

`citation_presence` is the shallow check many retrieval pipelines stop at:
the citation ID exists, therefore the sentence is treated as grounded. It
never reads the evidence content, so every content-level fabrication ships.

## Catch rate by attack family (full gate stack)

| Attack family | Cases | Caught | Catch rate | Gate(s) that fired |
| --- | --- | --- | --- | --- |
| cjk_fabrication | 2 | 2 | 100.0% | FE |
| cross_language_mismatch | 3 | 3 | 100.0% | FE |
| dangling_claim | 1 | 1 | 100.0% | FA |
| fabricated_citation | 3 | 3 | 100.0% | FA |
| fabricated_quote | 5 | 5 | 100.0% | FE |
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
| cs03 | evasion_cross_script_no_shared_token | unrelated Chinese claim, no Latin token and no digits to check |
| fc01 | evasion_future_as_completed | minutes say the team will do it in Q3; the claim says it is done |
| x01 | evasion_bare_number | invented count evades FE because a trailing number without a unit token is not extracted |
| x02 | evasion_negation_flip | drops the 'should not' from the evidence; lexical overlap cannot see negation |
| x05 | evasion_hedged_interpretation | invented interpretation with enough shared vocabulary to pass term overlap |
| x06 | evasion_value_misattribution | 9.0% is real but belongs to the manual baseline; attribution needs semantics |

## Determinism proof

- 5 consecutive in-process runs produced identical verdicts: `identical = True`.
- Verdict hash (sha256 over all full-stack verdicts): `0c549e606464f38db100ea43299e4fe8364d9c038ac864438d70a0d1ba22cb32`.
- `python scripts/run_adversarial_benchmark.py --check` recomputes every verdict
  from source and fails if any verdict, metric, or hash drifts from this archive —
  the same command runs in CI on Linux, so the hash is also a cross-platform
  reproducibility check.
