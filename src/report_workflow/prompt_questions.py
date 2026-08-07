"""The questions a task statement asks, extracted so a conclusion can be held to them.

A report can state four hundred checked figures and still never say whether to
enter the market. The unassisted control this pipeline is measured against did
say it — one sentence, in its conclusion, answering the two things the brief
asked — and three assisted runs in a row did not, because nothing required it.
Density is enforced by gates; answering the question was left to the author's
memory, and the author was busy placing tables.

So the questions are pulled out of the task statement here, deterministically,
and handed to two places at once: the outline brief, which shows the author what
was found, and OUTLINE_PLAN, which requires the conclusion section to bind a
claim to each one. The author answers by index and never retypes the question,
so a mis-extraction shows up in the brief rather than being quietly answered
with something else.

This is not ``research_questions`` (PAPER_SCOPE_FREEZE). Those are declared by
the author, which is the right shape for a paper stating its own scope and the
wrong shape here: an author who supplies the questions supplies ones they have
already answered.

Extraction is deliberately shallow. A clause is a question when it carries an
interrogative marker, not when a parser believes it is interrogative: Chinese
task statements ask without a question mark far more often than with one
("評估是否值得進入，從哪個切點進"), and the rules tried here that were cleverer
than a marker list either missed those or read "分析成本結構" as a question.
"""
from __future__ import annotations

import re

#: Where one clause of a task statement ends. Commas are included: a Chinese
#: brief routinely asks two things in one sentence separated by a comma, and
#: splitting only on full stops returns both as a single unanswerable blob.
_CLAUSE_SPLIT_RE = re.compile(r"[。．.；;！!？?\n，,、]+")

#: Interrogative markers. A clause carrying one is a question the report owes an
#: answer to. A written-out list rather than a derived rule: 是否 and 值不值得
#: are the two that decide a market brief, and neither ends in a question mark.
_QUESTION_MARKERS = (
    "值不值得", "值得嗎", "值得吗", "是否", "要不要", "該不該", "该不该",
    "能不能", "有沒有", "有没有", "可不可",
    "哪些", "哪個", "哪个", "哪一", "哪裡", "哪里", "哪家", "何者", "何處",
    "如何", "怎麼", "怎么", "怎樣", "怎样", "為什麼", "为什么", "為何", "为何",
    "多少", "幾成", "几成", "多大", "多高",
    "whether", "which", "what", "how", "why", "should", "worth",
)

#: A clause shorter than this is punctuation noise; one longer is a paragraph
#: that happens to contain the word "how".
_MIN_QUESTION_CHARS = 4
_MAX_QUESTION_CHARS = 120

#: Past this the requirement stops being a check and becomes a chore. A task
#: statement asking nine things is asking for a scope negotiation.
MAX_QUESTIONS = 4


def _is_question(clause: str) -> bool:
    lowered = clause.lower()
    for marker in _QUESTION_MARKERS:
        haystack = clause if marker[0] > "\x7f" else lowered
        if marker in haystack:
            return True
    return False


def extract_questions(prompt: str) -> list[str]:
    """The questions the task statement asks, in the order it asks them.

    Returns an empty list when the statement asks for work rather than answers
    ("分析四個品類的回收經濟性"), which is the common case and must stay free of
    the requirement: a gate that fires on every brief teaches authors to satisfy
    it rather than to answer anything.
    """
    found: list[str] = []
    for raw in _CLAUSE_SPLIT_RE.split(str(prompt or "")):
        clause = raw.strip()
        if not _MIN_QUESTION_CHARS <= len(clause) <= _MAX_QUESTION_CHARS:
            continue
        if not _is_question(clause):
            continue
        if clause in found:
            continue
        found.append(clause)
        if len(found) >= MAX_QUESTIONS:
            break
    return found
