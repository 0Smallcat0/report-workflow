"""check-draft measured both ways on public papers: false alarms and planted errors.

Each case is one CC-BY arXiv paper and two drafts written about it by hand:

* a correct draft, every figure and quotation copied from the paper, plus a
  few figures the writer worked out (a sum, a difference) that the paper does
  not print. Any correct figure or quotation reported NOT_FOUND is a false
  alarm; a worked-out figure is expected NOT_FOUND and counted on its own.
* a planted draft, the same text with errors put in: a wrong digit, a wrong
  unit or scale, more decimals than the paper gives, a figure moved to another
  model or setting, a quotation with a word changed, added or dropped, and a
  quotation the paper never wrote. An error is caught when the item carrying
  it is NOT_FOUND.

LLaMA is the development case the matching rules were tuned on. QLoRA
(English draft) and Chain-of-Thought (Chinese draft about the English paper)
were written before check-draft was first run on them and are reported as
they came out::

    python scripts/run_draft_benchmark.py          # regenerate results.json + summary.md
    python scripts/run_draft_benchmark.py --check  # rerun and diff against the archive

No network and no model: the PDFs are in benchmarks/check_draft/sources/.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from report_workflow.draft_check import NOT_FOUND, check_draft, load_source, read_draft

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmarks" / "check_draft"
RUN_DATE = "2026-10-21"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / f"check_draft_{RUN_DATE}"

CASES = (
    {"name": "llama", "split": "dev", "source": "2302.13971v1.pdf",
     "draft": "llama_review.md", "planted": "llama_review_planted.md", "labels": "llama.json"},
    {"name": "qlora", "split": "held_out", "source": "2305.14314v1.pdf",
     "draft": "qlora_review.md", "planted": "qlora_review_planted.md", "labels": "qlora.json"},
    {"name": "cot_zh", "split": "held_out", "source": "2201.11903v6.pdf",
     "draft": "cot_review_zh.md", "planted": "cot_review_zh_planted.md", "labels": "cot_zh.json"},
)


def _items(results) -> list[dict]:
    rows = []
    for result in results:
        for item in result.items:
            rows.append({
                "sentence": result.sentence.number,
                "sentence_text": result.sentence.text,
                "kind": item.kind,
                "item": item.text,
                "status": item.status,
                "page": item.location.page if item.location and item.status != NOT_FOUND else None,
            })
    return rows


def _find(rows: list[dict], sentence_part: str, item: str, occurrence: int | None = None) -> dict:
    """The labelled item; ``occurrence`` picks one when the sentence states the figure twice."""
    hits = [row for row in rows if sentence_part in row["sentence_text"] and row["item"] == item]
    if occurrence is not None and occurrence < len(hits):
        return hits[occurrence]
    if len(hits) != 1:
        raise SystemExit(f"label matches {len(hits)} items: {item!r} in a sentence with {sentence_part!r}")
    return hits[0]


def _run(draft: Path, source) -> list[dict]:
    paragraphs = read_draft(draft)
    results, _others = check_draft(paragraphs, [source])
    return _items(results)


def evaluate_case(case: dict) -> dict:
    source_path = DATA / "sources" / case["source"]
    started = time.perf_counter()
    source = load_source(source_path)
    labels = json.loads((DATA / "labels" / case["labels"]).read_text(encoding="utf-8"))

    correct = _run(DATA / "drafts" / case["draft"], source)
    for label in labels.get("not_checked", []):
        if any(label["sentence"] in row["sentence_text"] and row["item"] == label["item"] for row in correct):
            raise SystemExit(f"expected unchecked but checked: {label['item']!r}")
    derived ={id(_find(correct, d["sentence"], d["item"])) for d in labels["derived"]}
    for row in correct:
        row["label"] = "derived" if id(row) in derived else "correct"

    planted = _run(DATA / "drafts" / case["planted"], source)
    planted_rows = set()
    for label in labels["planted"]:
        row = _find(planted, label["planted"], label["item"], label.get("occurrence"))
        row["label"] = label["type"]
        planted_rows.add(id(row))
    derived_planted = {id(_find(planted, d["sentence"], d["item"])) for d in labels["derived"]
                       if any(d["sentence"] in row["sentence_text"] for row in planted)}
    for row in planted:
        if id(row) in derived_planted:
            row["label"] = "derived"
        row.setdefault("label", "correct")
    elapsed = time.perf_counter() - started

    def tally(rows, label):
        chosen = [row for row in rows if row["label"] == label]
        return {"items": len(chosen), "not_found": sum(row["status"] == NOT_FOUND for row in chosen)}

    by_type: dict[str, dict] = {}
    for row in planted:
        if row["label"] in ("correct", "derived"):
            continue
        entry = by_type.setdefault(row["label"], {"planted": 0, "caught": 0})
        entry["planted"] += 1
        entry["caught"] += row["status"] == NOT_FOUND
    return {
        "name": case["name"],
        "split": case["split"],
        "source": case["source"],
        "source_sha256": source.sha256,
        "correct_draft": {
            "correct": tally(correct, "correct"),
            "derived": tally(correct, "derived"),
            "false_alarms": [row for row in correct if row["label"] == "correct" and row["status"] == NOT_FOUND],
        },
        "planted_draft": {
            "by_type": dict(sorted(by_type.items())),
            "untouched_correct": tally(planted, "correct"),
            "missed": [row for row in planted if row["label"] not in ("correct", "derived")
                       and row["status"] != NOT_FOUND],
        },
        "items": {"correct_draft": correct, "planted_draft": planted},
        "_seconds": round(elapsed, 1),
    }


def _sum(cases: list[dict]) -> dict:
    correct = sum(case["correct_draft"]["correct"]["items"] for case in cases)
    false_alarms = sum(case["correct_draft"]["correct"]["not_found"] for case in cases)
    untouched = sum(case["planted_draft"]["untouched_correct"]["items"] for case in cases)
    untouched_alarms = sum(case["planted_draft"]["untouched_correct"]["not_found"] for case in cases)
    types: Counter = Counter()
    caught: Counter = Counter()
    for case in cases:
        for kind, entry in case["planted_draft"]["by_type"].items():
            types[kind] += entry["planted"]
            caught[kind] += entry["caught"]
    return {
        "correct_items": correct, "false_alarms": false_alarms,
        "untouched_items_in_planted": untouched, "untouched_false_alarms": untouched_alarms,
        "planted": sum(types.values()), "caught": sum(caught.values()),
        "by_type": {kind: {"planted": types[kind], "caught": caught[kind]} for kind in sorted(types)},
        "derived_items": sum(case["correct_draft"]["derived"]["items"] for case in cases),
        "derived_not_found": sum(case["correct_draft"]["derived"]["not_found"] for case in cases),
    }


def evaluate() -> dict:
    cases = [evaluate_case(case) for case in CASES]
    return {
        "run_date": RUN_DATE,
        "cases": cases,
        "dev": _sum([case for case in cases if case["split"] == "dev"]),
        "held_out": _sum([case for case in cases if case["split"] == "held_out"]),
    }


def _canonical(results: dict) -> str:
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if not key.startswith("_")}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    return json.dumps(strip(results), sort_keys=True, ensure_ascii=False)


def _rate(part: int, whole: int) -> str:
    return f"{part}/{whole}" + (f" ({100 * part / whole:.0f}%)" if whole else "")


def write_summary(results: dict, path: Path) -> None:
    lines = [
        f"# check-draft benchmark ({results['run_date']})",
        "",
        "Rerun: `python scripts/run_draft_benchmark.py --check` (no network, no model).",
        "",
        "| split | correct items falsely flagged | planted errors caught | worked-out figures NOT_FOUND |",
        "|---|---|---|---|",
    ]
    for split in ("dev", "held_out"):
        total = results[split]
        lines.append(
            f"| {split} | {_rate(total['false_alarms'], total['correct_items'])}"
            f" (+{total['untouched_false_alarms']}/{total['untouched_items_in_planted']} in the planted drafts)"
            f" | {_rate(total['caught'], total['planted'])}"
            f" | {_rate(total['derived_not_found'], total['derived_items'])} |"
        )
    lines += ["", "## Planted errors by type", "", "| type | dev | held out |", "|---|---|---|"]
    kinds = sorted(set(results["dev"]["by_type"]) | set(results["held_out"]["by_type"]))
    for kind in kinds:
        cells = []
        for split in ("dev", "held_out"):
            entry = results[split]["by_type"].get(kind)
            cells.append(_rate(entry["caught"], entry["planted"]) if entry else "-")
        lines.append(f"| {kind} | {cells[0]} | {cells[1]} |")
    for case in results["cases"]:
        lines += ["", f"## {case['name']} ({case['split']}, {case['source']})", ""]
        alarms = case["correct_draft"]["false_alarms"]
        lines.append(f"False alarms on the correct draft: {len(alarms)}")
        for row in alarms:
            lines.append(f"- `{row['item']}` in sentence {row['sentence']}: {row['sentence_text']}")
        missed = case["planted_draft"]["missed"]
        lines.append("")
        lines.append(f"Planted errors missed: {len(missed)}")
        for row in missed:
            lines.append(f"- {row['label']}: `{row['item']}` (found on p. {row['page']}) in: {row['sentence_text']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Rerun and diff against results.json.")
    parser.add_argument("--case", help="Run one case and print it; writes nothing.")
    args = parser.parse_args()
    if args.case:
        case = evaluate_case(next(case for case in CASES if case["name"] == args.case))
        case.pop("items")
        print(json.dumps(case, indent=1, ensure_ascii=False))
        return 0
    results = evaluate()
    results_path = EVIDENCE_ROOT / "results.json"
    if args.check:
        if not results_path.exists():
            print(f"draft benchmark check failed: missing {results_path.relative_to(ROOT)}")
            return 1
        archived = json.loads(results_path.read_text(encoding="utf-8"))
        if _canonical(archived) != _canonical(results):
            print("draft benchmark check failed: results.json does not match a rerun")
            return 1
        print("draft benchmark check passed")
        return 0
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(results, EVIDENCE_ROOT / "summary.md")
    print(json.dumps({"dev": results["dev"], "held_out": results["held_out"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
