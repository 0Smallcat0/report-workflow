"""The layout axis: what a reader sees before reading a word.

The existing scorers count what a document *states* — figures, tables, sources.
They cannot see whether the document is laid out to be read, and that gap is not
cosmetic: an unassisted control that lost on every counting dimension still read
better, because its headings said what it found, its tables were introduced, and
its paragraphs were paragraphs.

Three rules, deliberately few. Layout is structural, so a rule can measure it —
which is exactly why the argument axis is *not* here: a deterministic proxy for
"is the argument good" is the substitution that produced this repository's
over-design in the first place, and it is not going to be repeated at the
instrument layer.

Every dimension is "more is better", matching `run_report_quality_benchmark`.
"""
from __future__ import annotations

import re

LAYOUT_DIMENSIONS = (
    "heading_informativeness",
    "table_lead_in_ratio",
    "paragraph_length_fitness",
)

#: A markdown heading. The reconstructed DOCX text re-emits these from paragraph
#: styles, so all three arms are read the same way.
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")

#: The numbering an author puts in front of a heading — 「三、」「3.1」「（二）」.
#: Stripped before the heading is judged, because "3.1" is digits that say
#: nothing, and leaving them in scored a numbered outline as an informative one.
_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:[（(][一二三四五六七八九十百\d]+[)）]|[一二三四五六七八九十百]+[、.．]|\d+(?:\.\d+)*[、.．]?)\s*"
)

#: A colon introducing what the section found, and enough after it to be a
#: finding rather than a restatement.
_HEADING_CLAIM_RE = re.compile(r"[：:]\s*\S{6,}")

#: A stated quantity in the heading — 「544 件中只有 267 件可競爭」.
_HEADING_FIGURE_RE = re.compile(r"\d")

_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{3,}")

#: A lead-in has to be a sentence, not a label. Ten characters is the shortest
#: thing that can say what to look for in the table below it.
_MIN_LEAD_IN_CHARS = 10

#: The band a paragraph is readable in. Below it the "paragraph" is a fragment
#: or a caption; above it the reader is looking at a wall. Tuned for CJK, where
#: a character carries roughly twice what a latin one does.
_PARAGRAPH_MIN_CHARS = 60
_PARAGRAPH_MAX_CHARS = 500


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _headings(text: str) -> list[tuple[int, str]]:
    """(level, text) for every heading below the document title."""
    found = [
        (len(match.group(1)), match.group(2))
        for match in _HEADING_RE.finditer(_strip_comments(text))
    ]
    # The title names the document; it is not a place to state a finding, and
    # counting it dragged every document down by one fixed unit.
    return [(level, body) for level, body in found if level > 1]


def heading_informativeness(text: str) -> float:
    """Share of headings that say what the section found.

    「四、買家痛點」 names a topic; 「六、買家痛點：低分不是因為拍得差」 states a
    finding, and a reader skimming the second one has already learned something.
    A heading counts when it carries a claim after a colon, or a figure.
    """
    headings = _headings(text)
    if not headings:
        return 0.0
    informative = 0
    for _level, body in headings:
        residual = _ORDINAL_PREFIX_RE.sub("", body).strip()
        if _HEADING_CLAIM_RE.search(residual) or _HEADING_FIGURE_RE.search(residual):
            informative += 1
    return round(informative / len(headings), 4)


def _table_start_lines(lines: list[str]) -> list[int]:
    starts = []
    for index, line in enumerate(lines[:-1]):
        if _TABLE_ROW_RE.match(line) and _TABLE_RULE_RE.match(lines[index + 1]):
            starts.append(index)
    return starts


def table_lead_in_ratio(text: str) -> float:
    """Share of tables introduced by a sentence rather than dropped in.

    A table with a heading directly above it makes the reader work out what they
    are looking at. The drafting brief asks for a lead-in that says what to look
    for; this measures whether one is there, not whether it is any good.
    """
    lines = _strip_comments(text).split("\n")
    starts = _table_start_lines(lines)
    if not starts:
        return 0.0
    introduced = 0
    for start in starts:
        cursor = start - 1
        while cursor >= 0 and not lines[cursor].strip():
            cursor -= 1
        if cursor < 0:
            continue
        previous = lines[cursor].strip()
        if previous.startswith("#") or _TABLE_ROW_RE.match(previous):
            continue
        if len(previous) >= _MIN_LEAD_IN_CHARS:
            introduced += 1
    return round(introduced / len(starts), 4)


def _prose_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for block in re.split(r"\n\s*\n", _strip_comments(text)):
        stripped = block.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if all(_TABLE_ROW_RE.match(line) or _TABLE_RULE_RE.match(line)
               for line in stripped.split("\n")):
            continue
        paragraphs.append(stripped)
    return paragraphs


def paragraph_length_fitness(text: str) -> float:
    """Share of paragraphs long enough to make an argument, short enough to read.

    Punishes both failure modes a generated report falls into: the one-line
    fragment under every table, and the single paragraph carrying a whole
    section.
    """
    paragraphs = _prose_paragraphs(text)
    if not paragraphs:
        return 0.0
    fit = sum(
        1 for para in paragraphs
        if _PARAGRAPH_MIN_CHARS <= len(para) <= _PARAGRAPH_MAX_CHARS
    )
    return round(fit / len(paragraphs), 4)


def score_layout(text: str) -> dict:
    return {
        "heading_informativeness": heading_informativeness(text),
        "table_lead_in_ratio": table_lead_in_ratio(text),
        "paragraph_length_fitness": paragraph_length_fitness(text),
    }


# ----------------------------------------------------------------------
# The argument axis: judged, not computed.
# ----------------------------------------------------------------------

#: Scored 0-4 against `benchmarks/rubrics/argument_rubric.md` by an LLM judge,
#: three independent votes per document, median recorded. Not computed here on
#: purpose — see the rubric's "Why a judge and not a rule".
ARGUMENT_DIMENSIONS = (
    "claim_strength",
    "evidence_depth",
    "counter_specificity",
)

#: Three votes, so a median exists and one outlier cannot carry a dimension.
REQUIRED_VOTES = 3
MAX_ARGUMENT_SCORE = 4

#: A score with no passage behind it is an opinion. Requiring the passage is
#: what makes a vote something a third party can argue with rather than merely
#: disbelieve.
MIN_VOTE_EVIDENCE_CHARS = 10


def validate_votes(votes: list[dict]) -> list[str]:
    """Everything wrong with a set of votes, or an empty list.

    Checked rather than trusted, for the same reason the pipeline recomputes a
    registered derivation: the votes are a file, and a file that nothing checks
    is a file that can be edited into any result.
    """
    problems: list[str] = []
    if len(votes) != REQUIRED_VOTES:
        problems.append(f"expected {REQUIRED_VOTES} votes, found {len(votes)}")
    arms = {str(vote.get("arm", "")) for vote in votes}
    if len(arms) > 1:
        problems.append(f"votes mix arms: {', '.join(sorted(arms))}")
    numbers = sorted(vote.get("vote") for vote in votes)
    if numbers != list(range(1, len(votes) + 1)):
        problems.append(f"votes are not numbered 1..{len(votes)}: {numbers}")
    for vote in votes:
        for dimension in ARGUMENT_DIMENSIONS:
            entry = vote.get(dimension)
            if not isinstance(entry, dict):
                problems.append(f"vote {vote.get('vote')} is missing {dimension}")
                continue
            score = entry.get("score")
            if not isinstance(score, int) or not 0 <= score <= MAX_ARGUMENT_SCORE:
                problems.append(
                    f"vote {vote.get('vote')} {dimension} score {score!r} is not an "
                    f"integer 0-{MAX_ARGUMENT_SCORE}"
                )
            if len(str(entry.get("evidence") or "").strip()) < MIN_VOTE_EVIDENCE_CHARS:
                problems.append(
                    f"vote {vote.get('vote')} {dimension} cites no passage; a score "
                    "without one cannot be argued with"
                )
    return problems


def aggregate_argument_votes(votes: list[dict]) -> dict:
    """The median score per dimension, from three votes.

    Median rather than mean: with three votes the median is the majority
    position whenever one exists, and a single outlier moves nothing.
    """
    problems = validate_votes(votes)
    if problems:
        raise ValueError("argument votes are not usable: " + "; ".join(problems))
    scored = {}
    for dimension in ARGUMENT_DIMENSIONS:
        ordered = sorted(vote[dimension]["score"] for vote in votes)
        scored[dimension] = ordered[len(ordered) // 2]
    return scored


AXES = {
    "layout": LAYOUT_DIMENSIONS,
    "argument": ARGUMENT_DIMENSIONS,
}
