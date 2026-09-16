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
from run_report_quality_benchmark import check_frozen_body, score_document  # noqa: E402

FIXTURES = REPO_ROOT / "benchmarks" / "fixtures"
SOURCE_DIR = FIXTURES / "drone_market"
#: The current round. `drone_market_2026-08-07` and `drone_market_2026-08-14`
#: are the previous ones and stay as they were recorded — the tool arm each of
#: them scored no longer exists, and an archive rewritten in place cannot show
#: what moved.
EVIDENCE_ROOT = REPO_ROOT / "benchmarks" / "evidence" / "drone_market_2026-09-16"
VOTES_PATH = EVIDENCE_ROOT / "argument_votes.json"
RUBRIC_PATH = REPO_ROOT / "benchmarks" / "rubrics" / "argument_rubric.md"

ARMS = {
    "hand": FIXTURES / "drone_market_unassisted.md",
    "tool": FIXTURES / "drone_market_tool_arm.md",
    "llm_direct": FIXTURES / "drone_market_llm_direct.md",
}

#: Every arm carries a `Body SHA-256:` line in its header and every one is
#: recomputed here. The name is `HASHED_ARMS` rather than `FROZEN_ARMS`,
#: because the tool arm is not frozen: `scripts/record_tool_arm.py` rewrites it
#: whenever the pipeline changes what reaches the deliverable, and rewriting it
#: rewrites the hash in the same pass.
#:
#: The two are the same check doing two different jobs. On the hand and
#: AI-direct arms it catches an edit to a document that is never supposed to
#: change. On the tool arm it catches an edit made *by hand* instead of by a
#: re-recording — the case where someone improves the fixture's prose without
#: the pipeline having produced it, so the archive describes a document the
#: current code would not generate.
HASHED_ARMS = ("hand", "tool", "llm_direct")

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


#: Why the tool arm was re-recorded, and what moved when it was.
#:
#: Always printed, above the table. A reader who sees `external_sources` fall
#: from 12 to 0 will otherwise conclude the delivered report lost its sourcing,
#: and what actually happened is that the twelve were never external.
_WHAT_CHANGED = [
    "## What changed this round",
    "",
    "**The tool arm was re-recorded and the argument axis was re-judged.** The",
    "previous recording could no longer be reproduced at all: `e401849` added the",
    "FL checker, which hard-blocks three of the arm's own claims for calling a",
    "table row labelled `1–2` 「1–3 星區間」 — the defect the 2026-08-14 archive",
    "recorded and deliberately left unrepaired. From that commit onward the",
    "recording script failed at validate and CI's re-record job was red. The three",
    "labels now name the row FL points at, which is what its message prescribes,",
    "and that is the only change to the author's prose.",
    "",
    "**What moved on the counted axes is the citation apparatus, not the writing.**",
    "`80994fb`, `4d501b8` and `2b5472a` moved the derivations out of the report",
    "into `published/calculation_record.docx` and replaced the `[S1]` markers with",
    "「（本研究計算，表 N）」:",
    "",
    "- `external_sources` 12 → 0. All twelve lived in the old `# 資料來源` list:",
    "  six Amazon URLs and six quoted `(來源:…csv)` strings naming the input files.",
    "  Not one of them was a source outside this data set — the dimension was",
    "  counting the pipeline's own record of its own derivations.",
    "- `verifiable_numbers` 137 → 167. Thirty numbers added, none removed, and all",
    "  thirty are digits inside `表 N` pointers. The arm states no more checkable",
    "  figures than it did before.",
    "- `verifiable_number_ratio` 0.5269 → 0.5759, on those same thirty digits —",
    "  which is what turns that dimension from a loss into a win against the",
    "  AI-direct arm.",
    "- `paragraph_length_fitness` 0.5333 → 0.4074. The authored paragraphs are",
    "  unchanged in shape: 22 fit, 31 under 60 characters, 1 over 500, before and",
    "  after. The twenty-one source-list entries that left the document took 18",
    "  fit paragraphs out of the denominator with them.",
    "",
    "Two of those dimensions do not measure what their names say, and both move",
    "when the citation format changes. That is a defect in the instrument. It is",
    "recorded here rather than banked as a result.",
    "",
    "**The argument axis tied on every dimension.** Three blind judges returned",
    "hand 4/4/4, tool 4/4/4, AI-direct 4/4/4; one judge scored the tool arm 3 on",
    "`claim_strength` and was outvoted by the median. An axis is won by leading on",
    "more dimensions than you trail, so 0–0 is not a win and **the stop condition",
    "is not met this round** — not because anything was lost, but because the",
    "rubric's top band no longer separates these three documents.",
    "",
    "**Three judges is three contexts, not three instruments.** All three votes",
    "here — and all three in the 2026-08-14 archive — were cast by `claude-opus-5`",
    "in a fresh context on the same relabelled pack under the same prompt. Fresh",
    "contexts remove the author's knowledge of which arm is which; they do not make",
    "the readings independent, because one model's blind spots are in all three of",
    "them. So a unanimous 4/4/4 is weaker than it looks: it is consistent with the",
    "documents being indistinguishable at the top band, and equally consistent with",
    "one model's ceiling being reached. The median-of-three protocol treats these",
    "votes as independent readers, and on this evidence they are not. Separating",
    "the two readings needs a judge that is not this model.",
    "",
    "Two things about this panel belong in the record. All three judges found the",
    "AI-direct arm's arithmetic error (544 − 148 − 63 − 46 − 8 = 279, printed as",
    "267) and the contaminated table under its strongest counter-evidence, which",
    "are the two defects the previous panel docked it two points for — and this",
    "panel docked it nothing, taking them as not overturning its conclusions. The",
    "measurement that keeps reproducing here is the panel's own variance. And the",
    "judging prompt carried one sentence earlier rounds may not have had: that the",
    "three documents need not be spread across the scale. It was there to stop",
    "forced differentiation, and one judge differentiated anyway, but it is a",
    "deviation from whatever the earlier prompt said and it points toward the",
    "ceiling this round hit.",
    "",
]

#: What these numbers are an upper bound on.
_SCOPE_CAVEAT = [
    "## What these scores are an upper bound on",
    "",
    "The tool arm is the only arm that moves. Its prose was written against the",
    "same task, the same three CSVs and the same rubric by an author holding three",
    "blind judges' itemised deductions on the previous version, and this round",
    "repaired the one defect that panel found in it. Scores holding up under those",
    "conditions is close to guaranteed.",
    "",
    "How much of that is the pipeline and how much is a second attempt at one exam,",
    "**this design cannot separate**. Read the numbers as this task's ceiling for",
    "this pipeline, not as what it would score on a task it has not seen.",
    "",
    "What would separate them is a held-out task: new sources, a new question, no",
    "prior judging to write against. There is not one, and there will not be one",
    "soon — building it means a second hand-written control and a second AI-direct",
    "arm, which is the expensive half of this benchmark. That is the largest known",
    "limitation of this archive, and it is a limitation rather than a to-do.",
    "",
]


def _summary_markdown(results: dict) -> str:
    lines = [
        "# Drone-market benchmark: three reports, one source, three axes",
        "",
        "Same three CSVs, same task statement, all three arms recorded, one set of",
        "scorers. Reproduce with `python scripts/run_drone_market_benchmark.py --check`.",
        "",
    ]
    # Why the arm that moves moved, before the table it moved in. An archive
    # announcing that it met its stop condition owes the reader the width of
    # that condition in the same place.
    lines.extend(_WHAT_CHANGED)
    if results["verdict"]["stop_condition_met"]:
        lines.extend(_SCOPE_CAVEAT)
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
        "",
        "## The instrument, and the round it changed in",
        "",
        "This round did not touch it: the scorers, the axes and the rubric are the",
        "ones the 2026-08-14 archive used, which is what makes the two comparable.",
        "",
        "In that round the layout axis went from three dimensions to six. The first",
        "three read prose; the deliverable is a DOCX and nothing was looking at the",
        "furniture around a table. Added: `table_caption_ratio`,",
        "`table_provenance_ratio`, `table_size_fitness`.",
        "",
        "Declared because of who added them. The same author who rewrote the tool arm",
        "chose these three, after reading all three documents. Two of them — caption and",
        "attribution — are properties the renderer produces by construction and neither",
        "hand-written arm produces at all, so they run 1.0 against 0.0 and are closer to",
        "\"did the renderer run\" than to \"is this better laid out\". The third,",
        "`table_size_fitness`, is the one the pipeline loses, to both other arms; it is",
        "in the axis for that reason. Discount the layout axis accordingly.",
        "",
        "The numeric and argument axes were not touched, and the rubric was not touched.",
        "The tool arm was measured on the unchanged three-dimension layout axis before",
        "these were added, and that measurement is in the commit that introduced them.",
    ])
    if not results["verdict"]["stop_condition_met"]:
        lines.extend(["", *_SCOPE_CAVEAT])
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
    issues: list[str] = [
        problem for arm in HASHED_ARMS for problem in check_frozen_body(ARMS[arm])
    ]
    archived_path = EVIDENCE_ROOT / "results.json"
    if not archived_path.exists():
        return issues + ["no archived drone-market results; run with --write"]
    archived = json.loads(archived_path.read_text(encoding="utf-8"))

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
