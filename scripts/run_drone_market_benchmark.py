"""Is the delivered report better than a person's, or than an AI writing directly?

Three reports over the same three CSVs and the same task statement, all three
recorded, all three scored by the same functions:

- **hand** — `drone_market_unassisted.md`, written with no tooling.
- **tool** — `drone_market_tool_arm.md`, the delivered DOCX of a real run of
  prepare → author → validate → render, reconstructed as text. Re-recorded every
  round; it is the only arm that moves.
- **llm_direct** — `drone_market_llm_direct.md`, an AI given the CSVs and asked
  for the report, with no pipeline in the loop.

Three axes. **Numeric density** comes from `run_report_quality_benchmark`,
imported rather than copied so a scorer change cannot improve one arm and not
another. **Layout** is rules, in `report_axes`. **Argument** is an LLM judge
against a fixed rubric, three votes per arm, median recorded — because every
deterministic proxy for "is this argued well" measures a shape a document can
have while arguing nothing, and substituting the proxy for the thing is what
produced this repository's over-design in the first place.

There is no live pipeline run here any more. The arm that used to be generated
on the fly was authored mechanically — one lead-in per table, no argument
between them — which isolated the harness from the writer and, in doing so,
guaranteed a zero on the axis the comparison now turns on. What is being asked
is whether the delivered document is better. A mechanical author cannot answer
that, so it is gone.

    python scripts/run_drone_market_benchmark.py --check   # fail on drift
    python scripts/run_drone_market_benchmark.py --write   # regenerate archive
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_axes import (  # noqa: E402
    ARGUMENT_DIMENSIONS,
    LAYOUT_DIMENSIONS,
    aggregate_argument_votes,
    score_layout,
    validate_votes,
)
from run_report_quality_benchmark import DIMENSIONS as NUMERIC_DIMENSIONS  # noqa: E402
from run_report_quality_benchmark import score_document  # noqa: E402

FIXTURES = REPO_ROOT / "benchmarks" / "fixtures"
SOURCE_DIR = FIXTURES / "drone_market"
EVIDENCE_ROOT = REPO_ROOT / "benchmarks" / "evidence" / "drone_market_2026-08-07"
VOTES_PATH = EVIDENCE_ROOT / "argument_votes.json"
RUBRIC_PATH = REPO_ROOT / "benchmarks" / "rubrics" / "argument_rubric.md"

ARMS = {
    "hand": FIXTURES / "drone_market_unassisted.md",
    "tool": FIXTURES / "drone_market_tool_arm.md",
    "llm_direct": FIXTURES / "drone_market_llm_direct.md",
}

#: The task statement all three arms were given, unchanged.
PROMPT = (
    "根據 Amazon US 無人機類商品資料撰寫一份市場研究報告，涵蓋品類結構、價格帶分布、"
    "品牌集中度、買家痛點四個面向，結論必須能支撐「這個市場值不值得進入、"
    "從哪個切點進入」的判斷。"
)

AXES = (
    ("numeric", NUMERIC_DIMENSIONS),
    ("layout", LAYOUT_DIMENSIONS),
    ("argument", ARGUMENT_DIMENSIONS),
)


def source_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SOURCE_DIR.glob("*.csv"))
    )


def load_votes() -> dict:
    if not VOTES_PATH.exists():
        return {}
    return json.loads(VOTES_PATH.read_text(encoding="utf-8"))


def score_arm(text: str, source: str, votes: list[dict] | None) -> dict:
    scored = {"numeric": score_document(text, source), "layout": score_layout(text)}
    scored["argument"] = aggregate_argument_votes(votes) if votes else {
        dimension: None for dimension in ARGUMENT_DIMENSIONS
    }
    return scored


def build_results() -> dict:
    source = source_text()
    votes = load_votes()
    scores = {
        arm: score_arm(path.read_text(encoding="utf-8"), source, votes.get(arm))
        for arm, path in ARMS.items()
    }

    comparison = []
    for axis, dimensions in AXES:
        for dimension in dimensions:
            row = {"axis": axis, "dimension": dimension}
            row.update({arm: scores[arm][axis][dimension] for arm in ARMS})
            comparison.append(row)

    return {
        "prompt": PROMPT,
        "source": sorted(
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in SOURCE_DIR.glob("*.csv")
        ),
        "arms": {
            arm: str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for arm, path in ARMS.items()
        },
        "rubric": str(RUBRIC_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "scores": scores,
        "comparison": comparison,
        "verdict": verdict(scores),
    }


def _axis_record(scores: dict, axis: str, left: str, right: str) -> tuple[int, int]:
    """(dimensions `left` wins, dimensions `left` loses) against `right`."""
    wins = losses = 0
    for dimension in dict(AXES)[axis]:
        a, b = scores[left][axis][dimension], scores[right][axis][dimension]
        if a is None or b is None:
            continue
        if a > b:
            wins += 1
        elif a < b:
            losses += 1
    return wins, losses


def verdict(scores: dict) -> dict:
    """Where the tool arm stands against the stop condition.

    The condition: the tool arm wins every axis against the AI-direct arm, and
    loses at most one axis to the hand-written control. An axis is won when the
    arm leads on more of its dimensions than it trails.
    """
    axes = {}
    for axis, _dimensions in AXES:
        against_llm = _axis_record(scores, axis, "tool", "llm_direct")
        against_hand = _axis_record(scores, axis, "tool", "hand")
        axes[axis] = {
            "vs_llm_direct": {"wins": against_llm[0], "losses": against_llm[1],
                              "won": against_llm[0] > against_llm[1]},
            "vs_hand": {"wins": against_hand[0], "losses": against_hand[1],
                        "won": against_hand[0] > against_hand[1]},
        }
    beats_llm = all(axis["vs_llm_direct"]["won"] for axis in axes.values())
    lost_to_hand = sum(0 if axis["vs_hand"]["won"] else 1 for axis in axes.values())
    return {
        "axes": axes,
        "beats_llm_direct_on_every_axis": beats_llm,
        "axes_lost_to_hand": lost_to_hand,
        "stop_condition_met": beats_llm and lost_to_hand <= 1,
    }


def _summary_markdown(results: dict) -> str:
    lines = [
        "# Drone-market benchmark: three reports, one source, three axes",
        "",
        "Same three CSVs, same task statement, all three arms recorded, one set of",
        "scorers. Reproduce with `python scripts/run_drone_market_benchmark.py --check`.",
        "",
    ]
    for arm, path in results["arms"].items():
        lines.append(f"- **{arm}** — `{path}`")
    lines.extend([
        f"- Argument rubric: `{results['rubric']}`",
        "",
        "| Axis | Dimension | hand | tool | llm_direct |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for row in results["comparison"]:
        lines.append(
            f"| {row['axis']} | {row['dimension']} | {row['hand']} | {row['tool']} "
            f"| {row['llm_direct']} |"
        )

    verdict_block = results["verdict"]
    lines.extend([
        "",
        "## Where the tool arm stands",
        "",
        "The stop condition for this round: the tool arm wins every axis against the",
        "AI-direct arm, and loses at most one axis to the hand-written control.",
        "",
        "| Axis | vs llm_direct | vs hand |",
        "| --- | --- | --- |",
    ])
    for axis, record in verdict_block["axes"].items():
        left, right = record["vs_llm_direct"], record["vs_hand"]
        lines.append(
            f"| {axis} | {left['wins']}W {left['losses']}L "
            f"{'won' if left['won'] else 'not yet'} | {right['wins']}W {right['losses']}L "
            f"{'won' if right['won'] else 'not yet'} |"
        )
    lines.extend([
        "",
        f"Beats the AI-direct arm on every axis: "
        f"**{verdict_block['beats_llm_direct_on_every_axis']}**. "
        f"Axes lost to the hand-written control: "
        f"**{verdict_block['axes_lost_to_hand']}**. "
        f"Stop condition met: **{verdict_block['stop_condition_met']}**.",
        "",
        "## What this claims, and what it does not",
        "",
        "It claims the delivered document can be compared to a person's and to an",
        "AI's on the same three axes, and reports where it leads and where it trails.",
        "",
        "The argument votes are no longer the authoring agent's own. Each is cast by a",
        "separate judge given the three documents relabelled and shuffled, the rubric,",
        "and the CSVs — and told nothing about how any arm was produced.",
        "",
        "That change was not cosmetic. Under self-scoring the arms read hand 3/3/4,",
        "tool 4/3/4, AI-direct 4/3/4. The first blind round returned hand 4/4/4, tool",
        "3/3/4, AI-direct 4/4/4 — the tool arm inflated, the hand-written control",
        "deflated, and the verdict on the argument axis reversed. A score can be raised",
        "by writing to the anchor when the same agent writes the anchor, the paragraph",
        "and the vote; that is what had happened.",
        "",
        "It still does not claim the scores are objective. Three judges reading one",
        "rubric disagree by a point on most dimensions, which is why the median of",
        "three is recorded rather than any single vote. What the archive gives is a",
        "passage per score, so a fourth reader can disagree with a specific one.",
        "",
        "The hand-written and AI-direct arms are recorded artifacts rather than live",
        "generations. That is deliberate: a baseline regenerated each run makes the",
        "comparison move for reasons unrelated to the pipeline. Neither is a strawman —",
        "the hand-written arm was ahead of the pipeline when it was recorded, and the",
        "AI-direct arm is the strongest of four independent drafts.",
    ])
    return "\n".join(lines) + "\n"


def write_archive(results: dict) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_ROOT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EVIDENCE_ROOT / "summary.md").write_text(_summary_markdown(results), encoding="utf-8")


def check_archive() -> list[str]:
    """Re-score the three recorded documents and diff against the archive.

    Nothing is rendered here: a render depends on the machine, and the check that
    exists to prove a result reproduces must not be the least reproducible thing
    in the repository. What is verified is what can be held fixed — that the
    scorers, given these three documents and these votes, still produce these
    numbers.
    """
    archived_path = EVIDENCE_ROOT / "results.json"
    if not archived_path.exists():
        return ["no archived drone-market results; run with --write"]
    archived = json.loads(archived_path.read_text(encoding="utf-8"))

    issues: list[str] = []
    votes = load_votes()
    for arm in ARMS:
        arm_votes = votes.get(arm)
        if not arm_votes:
            issues.append(f"{arm} has no archived argument votes")
            continue
        issues.extend(f"{arm}: {problem}" for problem in validate_votes(arm_votes))
    if issues:
        return issues

    fresh = build_results()
    for arm in ARMS:
        for axis, _dimensions in AXES:
            if archived["scores"][arm][axis] != fresh["scores"][arm][axis]:
                issues.append(
                    f"{arm}/{axis} drifted from the archive: "
                    f"archived {archived['scores'][arm][axis]}, "
                    f"recomputed {fresh['scores'][arm][axis]}"
                )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the archive has drifted")
    parser.add_argument("--write", action="store_true", help="regenerate the archive")
    args = parser.parse_args(argv)

    if args.check:
        issues = check_archive()
        if issues:
            print("drone-market benchmark check failed:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print("drone-market benchmark check passed")
        return 0

    results = build_results()
    write_archive(results)
    print(_summary_markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
