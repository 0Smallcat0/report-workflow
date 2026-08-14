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
    "table_caption_ratio",
    "table_provenance_ratio",
    "table_size_fitness",
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


# ----------------------------------------------------------------------
# What the delivered document does around its tables.
#
# The first three rules read prose. The deliverable is a DOCX, and nothing was
# looking at the furniture a reader uses to place a table: a numbered caption
# above it, an attribution under it, and a shape that fits on the page.
#
# Declared, because the same author whose arm is being measured added these
# after seeing all three documents: caption and attribution are properties the
# pipeline produces by construction and neither hand-written arm produces at
# all, so those two are close to "does the renderer run". `table_size_fitness`
# is the one of the three the pipeline can lose, and does.
# ----------------------------------------------------------------------

#: A numbered table caption in either language, as the renderer emits it and as
#: an author would type it.
_TABLE_CAPTION_RE = re.compile(
    r"^(?:表|圖|图)\s*\d+|^(?:Table|Figure)\s+\d+", re.IGNORECASE
)

#: The attribution line under a table: which file, which rows.
_TABLE_SOURCE_RE = re.compile(
    r"^(?:來源|来源|資料來源|资料来源|Source|Data source)\s*[：:]", re.IGNORECASE
)

#: A table a reader takes in without scrolling or turning it sideways. Both
#: bounds are the point at which the table stops being read and starts being
#: searched.
_TABLE_MAX_BODY_ROWS = 12
_TABLE_MAX_COLUMNS = 8


def _tables(text: str) -> list[dict]:
    """Every markdown table in the document, with what surrounds it."""
    lines = _strip_comments(text).split("\n")
    tables: list[dict] = []
    index = 0
    while index < len(lines) - 1:
        if not (_TABLE_ROW_RE.match(lines[index])
                and _TABLE_RULE_RE.match(lines[index + 1])):
            index += 1
            continue
        columns = len(lines[index].strip().strip("|").split("|"))
        end = index + 2
        body = 0
        while end < len(lines) and _TABLE_ROW_RE.match(lines[end]):
            body += 1
            end += 1
        above = index - 1
        while above >= 0 and not lines[above].strip():
            above -= 1
        below = end
        while below < len(lines) and not lines[below].strip():
            below += 1
        tables.append({
            "columns": columns,
            "body_rows": body,
            "above": lines[above].strip() if above >= 0 else "",
            "below": lines[below].strip() if below < len(lines) else "",
        })
        index = end
    return tables


def table_caption_ratio(text: str) -> float:
    """Share of tables carrying a numbered caption directly above them.

    "表 3. 品類佔比依價格帶" tells a reader what they are about to look at and
    gives the prose something to refer back to. An uncaptioned grid has to be
    identified from the columns.
    """
    tables = _tables(text)
    if not tables:
        return 0.0
    captioned = sum(1 for table in tables if _TABLE_CAPTION_RE.match(table["above"]))
    return round(captioned / len(tables), 4)


def table_provenance_ratio(text: str) -> float:
    """Share of tables followed by the file and row span they came from.

    A table whose numbers the reader cannot trace is the same problem as an
    uncited sentence. This is the one delivery-layer property this repository
    exists to produce, and until now no axis could see whether it was there.
    """
    tables = _tables(text)
    if not tables:
        return 0.0
    attributed = sum(1 for table in tables if _TABLE_SOURCE_RE.match(table["below"]))
    return round(attributed / len(tables), 4)


def table_size_fitness(text: str) -> float:
    """Share of tables small enough to be read rather than searched.

    A grouped table the tool builds can run to seventeen rows across eight
    columns because that is what the grouping produced; an author laying out a
    page splits it. Deliberately kept in the axis even though the pipeline is
    the arm that loses it: an instrument whose new dimensions all favour one
    arm is not an instrument.
    """
    tables = _tables(text)
    if not tables:
        return 0.0
    fit = sum(
        1 for table in tables
        if table["body_rows"] <= _TABLE_MAX_BODY_ROWS
        and table["columns"] <= _TABLE_MAX_COLUMNS
    )
    return round(fit / len(tables), 4)


def score_layout(text: str) -> dict:
    return {
        "heading_informativeness": heading_informativeness(text),
        "table_lead_in_ratio": table_lead_in_ratio(text),
        "paragraph_length_fitness": paragraph_length_fitness(text),
        "table_caption_ratio": table_caption_ratio(text),
        "table_provenance_ratio": table_provenance_ratio(text),
        "table_size_fitness": table_size_fitness(text),
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

#: What each vote has to say about who cast it.
#:
#: Until now a vote recorded the arm, the number, three scores and their
#: passages — and nothing at all about the voter. The rubric tells a reader
#: that anyone wanting an independent judgement can re-run the votes; without
#: an identity record there is no way to tell whether the archived ones were
#: independent, so that sentence could not be cashed.
#:
#: The three flags must all be false. One agent once wrote the rubric, then the
#: brief rules, then paragraphs satisfying those rules, then cast the vote that
#: scored them; each step defensible, the chain not. An arm's author scoring
#: their own arm is that chain reconnected, and relabelling the documents does
#: not undo it — a writer recognises their own sentences.
JUDGE_FLAGS = ("same_context_as_author", "saw_pipeline_code", "saw_task_prompt")


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
        judge = vote.get("judge")
        if not isinstance(judge, dict):
            problems.append(
                f"vote {vote.get('vote')} records no 'judge' block, so a reader "
                "cannot tell whether these votes were independent"
            )
        else:
            if not str(judge.get("model") or "").strip():
                problems.append(f"vote {vote.get('vote')} judge names no model")
            if not (judge.get("inputs") or []):
                problems.append(
                    f"vote {vote.get('vote')} judge lists no inputs, so what it was "
                    "shown cannot be reproduced"
                )
            for flag in JUDGE_FLAGS:
                if judge.get(flag) is not False:
                    problems.append(
                        f"vote {vote.get('vote')} judge has {flag}={judge.get(flag)!r}; "
                        "a vote cast with that access is not an independent judgement"
                    )
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
