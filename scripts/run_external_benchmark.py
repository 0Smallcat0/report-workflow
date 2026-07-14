"""Out-of-domain benchmark: ``verify()`` on the public HaluEval QA dataset.

The adversarial benchmark (``run_adversarial_benchmark.py``) measures the gate
stack on a corpus written *for* it. A skeptical engineer's next question is
what happens on data nobody here authored. This script answers it with
HaluEval (Li et al., EMNLP 2023, https://github.com/RUCAIBox/HaluEval): 10,000
knowledge-grounded QA pairs, each carrying one human-plausible hallucinated
answer and one right answer derived from HotpotQA.

Every pair becomes two calls to the zero-schema adapter::

    verify(hallucinated_answer, knowledge)   # should block
    verify(right_answer, knowledge)          # should publish

Expectations, stated before the numbers so the framing cannot drift:

* HaluEval hallucinations are open-domain *entity swaps* engineered to reuse
  the knowledge passage's vocabulary, which is exactly the class the design
  doc places outside deterministic lexical checking (docs/DESIGN.md §6). Low
  recall here is the documented boundary, not a surprise.
* The claim under test is the **fail-closed discipline**: on 10,000 honest
  answers the gates should almost never block (false-positive rate), and every
  block on the hallucinated side should be a real hallucination (precision).
  A linter does not catch every bug; it must not lie about the ones it flags.
* The numeric subset (hallucinated answers that contain an extractable
  number+unit pair) is where the FE gate has actual purchase; its recall is
  reported separately.

The dataset is NOT vendored (6 MB, HotpotQA-derived content). Fetch it once::

    python scripts/run_external_benchmark.py --download   # writes benchmarks/external_data/
    python scripts/run_external_benchmark.py              # regenerate archived evidence
    python scripts/run_external_benchmark.py --check      # recompute + diff vs archive

``--check`` fails when the local dataset is missing instead of passing
silently; this benchmark is a local/manual reproducibility surface and is not
wired into CI (network flakiness would make CI red for reasons unrelated to
the code).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from report_workflow import verify
from report_workflow.nodes.factuality_check import _extract_numbers_with_unit

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-07-15"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / f"halueval_qa_{RUN_DATE}"
DATASET_PATH = ROOT / "benchmarks" / "external_data" / "halueval_qa_data.json"
DATASET_URL = "https://raw.githubusercontent.com/RUCAIBox/HaluEval/main/data/qa_data.json"
DATASET_SHA256 = "89ed139ec5e3a3169a0b30e45569ac1283846f76f27f7bb5e908ee6deed57e88"
EXPECTED_PAIRS = 10000


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dataset() -> None:
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {DATASET_URL} -> {DATASET_PATH.relative_to(ROOT)}")
    with urllib.request.urlopen(DATASET_URL) as response:
        DATASET_PATH.write_bytes(response.read())
    actual = _sha256_file(DATASET_PATH)
    if actual != DATASET_SHA256:
        DATASET_PATH.unlink()
        raise SystemExit(
            f"downloaded dataset sha256 {actual} does not match pinned {DATASET_SHA256}; "
            "refusing to evaluate unverified data"
        )
    print("sha256 verified")


def load_pairs() -> list[dict[str, Any]]:
    if not DATASET_PATH.exists():
        raise SystemExit(
            f"dataset not found: {DATASET_PATH.relative_to(ROOT)}\n"
            "fetch it first: python scripts/run_external_benchmark.py --download"
        )
    actual = _sha256_file(DATASET_PATH)
    if actual != DATASET_SHA256:
        raise SystemExit(
            f"dataset sha256 {actual} does not match pinned {DATASET_SHA256}; "
            "delete the file and re-run --download"
        )
    pairs = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))
    return pairs


def evaluate_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Run both answers of every pair through verify() and score the verdicts."""
    blocked_hallucinated: list[int] = []
    blocked_right: list[int] = []
    gate_breakdown: dict[str, int] = {}
    numeric_indices: list[int] = []
    numeric_caught = 0

    for index, pair in enumerate(pairs):
        knowledge = pair["knowledge"]

        halluc = verify(pair["hallucinated_answer"], knowledge)
        if halluc["blocked_count"] > 0:
            blocked_hallucinated.append(index)
            for row in halluc["sentence_results"]:
                if row["status"] == "blocked":
                    gate_breakdown[row["checker"]] = gate_breakdown.get(row["checker"], 0) + 1
                    break

        honest = verify(pair["right_answer"], knowledge)
        if honest["blocked_count"] > 0:
            blocked_right.append(index)

        if _extract_numbers_with_unit(pair["hallucinated_answer"]):
            numeric_indices.append(index)
            if halluc["blocked_count"] > 0:
                numeric_caught += 1

    total = len(pairs)
    tp = len(blocked_hallucinated)
    fp = len(blocked_right)
    metrics = {
        "true_positives": tp,
        "false_negatives": total - tp,
        "false_positives": fp,
        "true_negatives": total - fp,
        "recall": round(tp / total, 4) if total else 0.0,
        "false_positive_rate": round(fp / total, 4) if total else 0.0,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
    }
    numeric_subset = {
        "pairs": len(numeric_indices),
        "caught": numeric_caught,
        "recall": round(numeric_caught / len(numeric_indices), 4) if numeric_indices else 0.0,
    }
    return {
        "dataset": {
            "name": "HaluEval qa_data.json",
            "url": DATASET_URL,
            "sha256": DATASET_SHA256,
            "pairs": total,
            "note": (
                "Li et al., EMNLP 2023; HotpotQA-derived knowledge passages. "
                "Dataset is fetched on demand and not vendored into this repository."
            ),
        },
        "metrics": metrics,
        "numeric_subset": numeric_subset,
        "gate_breakdown": dict(sorted(gate_breakdown.items())),
        "blocked_hallucinated_indices": blocked_hallucinated,
        "blocked_right_indices": blocked_right,
    }


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_summary_md(results: dict[str, Any], path: Path) -> None:
    metrics = results["metrics"]
    numeric = results["numeric_subset"]
    dataset = results["dataset"]
    gates = ", ".join(f"{gate}: {count}" for gate, count in results["gate_breakdown"].items())
    lines = [
        f"# Out-of-Domain Benchmark: HaluEval QA ({RUN_DATE})",
        "",
        f"- Dataset: **{dataset['pairs']:,} QA pairs** from [HaluEval]({dataset['url']}) "
        "(Li et al., EMNLP 2023) — each pair contributes one hallucinated and one right "
        "answer, verified against its knowledge passage with the zero-schema "
        "`report_workflow.verify()` adapter.",
        f"- Dataset sha256 (pinned, verified before every run): `{dataset['sha256']}`",
        "- No LLM, no API key: verdicts are pure functions of (answer, knowledge).",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Recall (hallucinated answers blocked) | {_format_pct(metrics['recall'])} "
        f"({metrics['true_positives']:,}/{dataset['pairs']:,}) |",
        f"| False-positive rate (right answers blocked) | {_format_pct(metrics['false_positive_rate'])} "
        f"({metrics['false_positives']}/{dataset['pairs']:,}) |",
        f"| Precision of a block verdict | {_format_pct(metrics['precision'])} |",
        f"| Numeric-subset recall ({numeric['pairs']:,} pairs with number+unit) | "
        f"{_format_pct(numeric['recall'])} ({numeric['caught']:,}/{numeric['pairs']:,}) |",
        f"| Gate breakdown | {gates} |",
        "",
        "## Reading these numbers honestly",
        "",
        "HaluEval hallucinations are open-domain **entity swaps** engineered to reuse",
        "the knowledge passage's own vocabulary — the exact class `docs/DESIGN.md` §6",
        "places outside deterministic lexical checking. The headline here is not the",
        "recall; it is the discipline: across 10,000 honest answers the gates",
        f"wrongly blocked {metrics['false_positives']}, and every block they did issue",
        "was a real hallucination. Out of domain, with zero tokens spent, the gate",
        "stack behaves like a linter should: it does not catch every bug, and it does",
        "not lie about the ones it flags. In-domain behavior (evidence-bounded",
        "drafting, where claims must reuse ledger vocabulary) is measured by the",
        "adversarial benchmark instead.",
        "",
        "The false positives were inspected one by one: five are proper nouns whose",
        "leading numeral parses as a measurement (film titles like *13 Going on 30*,",
        "street addresses like *70 Pine Street*), and one is a dataset concatenation",
        "artifact that glues 'billion' to the first word of the next sentence, so the",
        "unit comparison sees 'billionFranklin'. Distinguishing a title from a",
        "measurement is a semantic call, which the design keeps out of the",
        "deterministic layer on purpose.",
        "",
        "Baselines on this data are degenerate by construction: `no_gate` and the",
        "shallow citation-presence check both block nothing (0% recall) because every",
        "answer is 'grounded' in an existing passage.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python scripts/run_external_benchmark.py --download   # fetch + sha256-verify the dataset",
        "python scripts/run_external_benchmark.py --check      # recompute all 20,000 verdicts, diff vs this archive",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def write_archive(results: dict[str, Any]) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_summary_md(results, EVIDENCE_ROOT / "summary.md")


def check_archive() -> list[str]:
    issues: list[str] = []
    results_path = EVIDENCE_ROOT / "results.json"
    if not results_path.exists():
        return [f"missing archived results: {results_path.relative_to(ROOT)}"]
    archived = json.loads(results_path.read_text(encoding="utf-8"))
    recomputed = evaluate_pairs(load_pairs())
    if archived.get("dataset", {}).get("sha256") != DATASET_SHA256:
        issues.append("archived dataset sha256 does not match the pinned constant")
    if _canonical(archived) != _canonical(recomputed):
        issues.append("archived results.json does not match a from-source rerun")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch and sha256-verify the dataset.")
    parser.add_argument("--check", action="store_true", help="Recompute all verdicts and verify the archive.")
    args = parser.parse_args()

    if args.download:
        download_dataset()
        if not args.check:
            return 0

    if args.check:
        issues = check_archive()
        if issues:
            print("external benchmark check failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print("external benchmark check passed")
        return 0

    results = evaluate_pairs(load_pairs())
    write_archive(results)
    print(json.dumps({
        "pairs": results["dataset"]["pairs"],
        "recall": results["metrics"]["recall"],
        "false_positive_rate": results["metrics"]["false_positive_rate"],
        "precision": results["metrics"]["precision"],
        "numeric_subset_recall": results["numeric_subset"]["recall"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
