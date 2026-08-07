"""FACTUALITY_CHECK node - verify claim/evidence/sentence linkage.

IMPORTANT data source note:
  - claim_matrix is read from claim_matrix.json on disk (NOT from state.plan.claim_matrix)
  - evidence_ledger is read from state.sources["evidence_ledger_path"] on disk (NOT from checkpoint)
  - factuality_report.json is written fresh each run to the job run directory

When debugging FE failures: edit claim_matrix.json and evidence_ledger.jsonl directly.
Checkpoint files are NOT read by this node.
"""
import json
import re
import unicodedata
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import run_dir_for
from ..state import ReportState, WORKFLOW_RUNS_DIR

BLOCKING_CLAIM_STATUSES = {"blocked", "unverified", "disputed"}


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                payload = json.loads(line)
                if isinstance(payload, dict) and "_contract" in payload:
                    continue
                rows.append(payload)
    return rows


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def _claim_id(claim: dict) -> str:
    return claim.get("claim_id") or claim.get("id") or ""


def _default_allowed_claim_types(evidence_type: str) -> list[str]:
    return {
        "quantitative": ["factual", "statistical"],
        "qualitative": ["factual", "qualitative"],
        "methodological": ["factual", "methodological"],
        "contextual": ["factual", "qualitative", "contextual"],
    }.get(evidence_type, ["factual"])


def _allowed_claim_types(evidence: dict) -> list[str]:
    explicit = evidence.get("allowed_claim_types")
    allowed = set(explicit) if explicit else set(_default_allowed_claim_types(evidence.get("evidence_type", "")))

    source_role = evidence.get("source_role", "")
    if source_role in {"graph_analysis", "research_document", "primary_source", "internal_project_source"}:
        allowed.update({"factual", "qualitative", "methodological", "contextual"})
    elif source_role == "code_artifact":
        allowed.update({"factual", "qualitative", "methodological", "contextual", "implementation"})

    return sorted(allowed)


def run_factuality_check_fa(
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify deterministic claim/evidence/sentence linkage."""
    claims = claim_matrix.get("claims", [])
    evidence_by_id = {
        evidence.get("evidence_id"): evidence
        for evidence in (evidence_ledger or [])
        if evidence.get("evidence_id")
    }
    sentence_claim_ids = {
        claim_id
        for sent in sentence_map
        for claim_id in sent.get("claim_ids", [])
    }
    sentence_evidence_ids_by_claim: dict[str, set[str]] = {}
    for sent in sentence_map:
        for claim_id in sent.get("claim_ids", []):
            sentence_evidence_ids_by_claim.setdefault(claim_id, set()).update(sent.get("evidence_ids", []))

    results = []
    for claim in claims:
        claim_id = _claim_id(claim)
        claim_evidence_ids = set(claim.get("evidence_ids", []))
        reasons = []

        if not claim_id:
            reasons.append("Claim is missing claim_id")
        claim_status = str(claim.get("status", "supported")).lower()
        if claim_status in BLOCKING_CLAIM_STATUSES:
            reasons.append(f"Claim status is not publishable: {claim_status}")
        if not claim_evidence_ids:
            reasons.append("No evidence mapped to claim")
        if claim_id and claim_id not in sentence_claim_ids:
            reasons.append("Claim does not appear in sentence_map")

        missing_evidence = sorted(eid for eid in claim_evidence_ids if eid not in evidence_by_id)
        if evidence_by_id and missing_evidence:
            reasons.append(f"Claim references unknown evidence: {', '.join(missing_evidence)}")

        sentence_evidence_ids = sentence_evidence_ids_by_claim.get(claim_id, set())
        unknown_sentence_evidence = sorted(eid for eid in sentence_evidence_ids if evidence_by_id and eid not in evidence_by_id)
        if unknown_sentence_evidence:
            reasons.append(f"Sentence map references unknown evidence: {', '.join(unknown_sentence_evidence)}")
        if claim_evidence_ids and not (claim_evidence_ids & sentence_evidence_ids):
            reasons.append("Sentence map does not link claim to its evidence")

        claim_type = claim.get("claim_type", "factual")
        unsupported = []
        for evidence_id in sorted(claim_evidence_ids):
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            if claim_type not in _allowed_claim_types(evidence):
                # An id alone leaves the author nothing to act on when several
                # rows of one table answer to it: the message names a row they
                # cannot see and cannot choose between, so the only repair is
                # deleting the citation. Naming the block and the types that
                # row does allow says which row was consulted and what it
                # would accept.
                block_id = evidence.get("block_id") or ""
                allowed = ", ".join(_allowed_claim_types(evidence)) or "none"
                located = f"{evidence_id} ({block_id})" if block_id else evidence_id
                unsupported.append(f"{located} allows: {allowed}")
        if unsupported:
            reasons.append(
                f"Claim type {claim_type!r} is not allowed by evidence: {'; '.join(unsupported)}"
            )

        if reasons:
            results.append({
                "claim_id": claim_id or "<missing>",
                "status": "blocked",
                "checker": "FA",
                "reason": "; ".join(reasons),
            })
        else:
            results.append({
                "claim_id": claim_id,
                "status": "verified",
                "checker": "FA",
                "reason": "Claim/evidence/sentence linkage confirmed",
            })

    return results


def run_factuality_check_fb(
    checked_claims: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify statistical claims are backed by appropriate evidence.

    Uses _allowed_claim_types() which respects explicit allowed_claim_types
    overrides in evidence records, not just the evidence_type field.
    """
    evidence_by_id = {
        evidence.get("evidence_id"): evidence
        for evidence in (evidence_ledger or [])
        if evidence.get("evidence_id")
    }
    claims_by_id = {_claim_id(claim): claim for claim in claim_matrix.get("claims", [])}

    results = []
    for checked in checked_claims:
        if checked["status"] == "blocked":
            results.append(checked)
            continue

        claim = claims_by_id.get(checked["claim_id"], {})
        claim_type = claim.get("claim_type", "factual")
        if claim_type != "statistical":
            results.append(checked)
            continue

        # Check if any linked evidence allows this claim type
        # Use _allowed_claim_types which respects explicit overrides
        linked = [evidence_by_id.get(eid) for eid in claim.get("evidence_ids", [])]
        has_support = any(
            evidence and claim_type in _allowed_claim_types(evidence)
            for evidence in linked
        )
        if has_support:
            results.append({
                **checked,
                "checker": "FA+FB",
                "reason": "Claim/evidence linkage and quantitative support confirmed",
            })
        else:
            results.append({
                "claim_id": checked["claim_id"],
                "status": "blocked",
                "checker": "FB",
                "reason": "Statistical claim lacks quantitative evidence",
            })

    return results


# ----------------------------------------------------------------------
# Fix #5: Content overlap checker
# ----------------------------------------------------------------------


def run_factuality_check_fe(
    checked_claims: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify claim content is grounded in evidence content (not just ID linkage).

    Fix #5: Uses _check_content_overlap() to catch:
    - claims citing numbers/terms absent from evidence
    - statistical claims whose numeric values differ from evidence
    - claims stating more decimal precision than the evidence provides
    - quoted text (4+ chars) not appearing verbatim in evidence
    - non-CJK claims citing CJK-only evidence with no shared vocabulary
    """
    evidence_by_id = {
        ev.get("evidence_id"): ev
        for ev in (evidence_ledger or [])
        if ev.get("evidence_id")
    }
    claims_by_id = {_claim_id(claim): claim for claim in claim_matrix.get("claims", [])}

    results = []
    for checked in checked_claims:
        if checked["status"] == "blocked":
            results.append(checked)
            continue

        claim = claims_by_id.get(checked["claim_id"], {})
        claim_evidence_ids = claim.get("evidence_ids", [])

        if not claim_evidence_ids:
            results.append(checked)
            continue

        # Citing several sources means the claim rests on their union, not on
        # each one alone. Demanding that every cited entry satisfy every check
        # blocked ordinary honest claims: a measurement row carries no prose
        # for the term check, and the method paragraph that produced it
        # carries no number for the numeric check, so citing both failed twice
        # over. A check now counts as failed only when no cited evidence
        # satisfied it. With a single citation this is exactly the old rule.
        examined = 0
        failures: dict[tuple, str] = {}
        failure_counts: dict[tuple, int] = {}
        for evidence_id in claim_evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            examined += 1
            # One vote per evidence, not per occurrence. The counter used to
            # increment for every finding returned, and a claim that writes the
            # same figure twice -- 「0-10 則」 and 「10-50 則」 name two bands and
            # one number -- produced two findings from a single failing
            # citation. Against two cited entries that alone reached
            # `>= examined`, so the union rule was defeated by repetition: the
            # other citation did state the number, and the claim was blocked
            # anyway. It only ever bit multi-citation claims, which is the case
            # the rule exists to protect.
            findings = _content_overlap_findings(claim, evidence)
            for key in {key for key, _reason in findings}:
                failure_counts[key] = failure_counts.get(key, 0) + 1
            for key, reason in findings:
                failures.setdefault(key, reason)

        all_reasons = [
            reason for key, reason in failures.items()
            if failure_counts[key] >= examined
        ]

        if all_reasons:
            results.append({
                "claim_id": checked["claim_id"],
                "status": "blocked",
                "checker": "FE",
                "reason": "; ".join(all_reasons[:3]),  # cap at 3 reasons
            })
        else:
            results.append(checked)

    return results


# ----------------------------------------------------------------------
# F2: Provenance-driven wording strength enforcement
# ----------------------------------------------------------------------
# Allowed wording_strength per evidence_grade.
# evidence_grade=high  → may use measured / hedged / weak
# evidence_grade=medium→ may use hedged / weak only
# evidence_grade=low   → may use hedged only
_ALLOWED_WORDING_BY_GRADE = {
    "high": {"measured", "hedged", "weak"},
    "medium": {"hedged", "weak"},
    "low": {"hedged"},
}
_VALID_WORDING_STRENGTHS = {"measured", "hedged", "weak"}


# ----------------------------------------------------------------------
# Fix #5: Claim-evidence content overlap checker
# ----------------------------------------------------------------------
# Verifies that claim content is actually supported by evidence content,
# not just by ID linkage. Catches:
#   - claims citing numbers/terms that don't appear in the evidence
#   - statistical claims whose numeric values/units differ from evidence
#   - quote claims where the quoted text differs from evidence
# ----------------------------------------------------------------------


_NUMERIC_IN_CLAIM_RE = re.compile(
    r"""
    (?<![A-Za-z0-9.])                # boundary without consuming CJK text
    (                                 # number
        \d{1,3}(?:,\d{3})*(?:\.\d+)?(?:[eE][+-]?\d+)?
    )
    \s*                               # supports "5 cm" and "5cm"
    (?![a-zA-Z]')                     # reject possessive: "386's" is not a unit
    (                                 # unit
        [a-zA-Z%\u00b0\u4e00-\u9fff]+(?:/?[a-zA-Z%\u00b0\u4e00-\u9fff]*)?
    )
    """,
    re.VERBOSE,
)


_CJK_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
               "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CJK_UNITS = {"十": 10, "百": 100, "千": 1000}
#: A Chinese numeral carrying a unit. Two guards, both learned by breaking
#: the corpus with a first attempt that had neither:
#:
#: "第" marks an ordinal, not a quantity — 第三季 is the third quarter, and
#: reading it as "3 季" made an honest claim about a plan look like a
#: fabricated measurement.
#:
#: The unit is capped at two characters. An unbounded CJK run swallowed the
#: rest of the sentence, so "三季導入" became a number with the unit
#: "季導入", which nothing could ever match.
_CJK_NUMBER_RE = re.compile(
    r"(?<!第)([零〇一二兩三四五六七八九十百千]+(?:點[零〇一二三四五六七八九]+)?)"
    r"\s*([a-zA-Z%°]+|[一-鿿]{1,2})"
)


def _cjk_numeral_value(text: str) -> float | None:
    """A Chinese numeral as a number, or None when it is not worth guessing.

    The numeric check reads digits, so a claim spelling its number out —
    "降至三點二分鐘" — was never checked against the evidence at all, while
    the same claim written 3.2 was caught. Full-width digits already worked,
    because NFKC folds them; Chinese numerals are a different notation, not a
    different width.

    Deliberately narrow. 萬, 億 and 百分之 are refused rather than guessed at,
    because a wrong reading here does not merely miss a fabrication — it
    blocks an honest claim, which is the worse failure.
    """
    if not text or any(c in text for c in "萬万億亿分"):
        return None
    whole, _, fraction = text.partition("點")
    total = 0
    section = 0
    digit: int | None = None
    for char in whole:
        if char in _CJK_DIGITS:
            digit = _CJK_DIGITS[char]
        elif char in _CJK_UNITS:
            section += (1 if digit is None else digit) * _CJK_UNITS[char]
            digit = None
        else:
            return None
    total = section + (digit or 0)
    if not fraction:
        return float(total)
    places = []
    for char in fraction:
        if char not in _CJK_DIGITS:
            return None
        places.append(str(_CJK_DIGITS[char]))
    return float(f"{total}.{''.join(places)}")


#: Chinese has no spaces, so "the characters after the number" is not a unit —
#: it is the rest of the sentence. The old extractor bound them together and
#: compared the whole token, which meant a claim passed only if it repeated the
#: source's exact character sequence: "8,259美元/噸的低點" never matched the
#: evidence's "8,259美元/噸", and one particle — 的 — was enough to block a
#: true claim. That rewards transcription and punishes paraphrase, which is
#: backwards for a tool whose purpose is helping someone write.
#:
#: A CJK unit is therefore taken from this vocabulary, longest match first, and
#: nothing else after the number is read as a unit. ASCII units keep their word
#: boundary, which never had this problem, so "226 edges" is unaffected.
_CJK_UNIT_WORDS = (
    # time
    "個月", "月", "年", "日", "天", "週", "周", "小時", "小时", "分鐘", "分钟", "秒",
    "季", "季度", "世紀", "世纪",
    # counting / measure words
    "座", "個", "个", "家", "間", "间", "名", "人", "次", "筆", "笔", "件", "台", "部",
    "種", "种", "項", "项", "條", "条", "張", "张", "位", "頁", "页", "章", "節", "节",
    "版", "廠", "厂", "站", "組", "组", "批", "層", "层", "倍", "成",
    # mass / length / volume
    "公噸", "噸", "吨", "公斤", "公克", "克", "毫克", "公里", "公尺", "公分", "毫米",
    "英里", "英尺", "公升", "升", "毫升", "立方公尺", "平方公尺", "坪", "畝", "亩",
    # money
    "美元", "歐元", "欧元", "日圓", "日元", "人民幣", "人民币", "新臺幣", "新台幣",
    "港幣", "港币", "億元", "亿元", "萬元", "万元", "元",
    # physical / rate
    "度電", "度电", "攝氏度", "摄氏度", "度", "百分點", "百分点", "百分比",
    "千瓦", "兆瓦", "瓦", "伏特", "安培", "歐姆", "欧姆", "赫茲", "赫兹",
)

#: Longest first, so 個月 wins over 個 and 公噸 over 噸.
_CJK_UNIT_RE = re.compile(
    "(?:%s)" % "|".join(sorted(_CJK_UNIT_WORDS, key=len, reverse=True))
)

_ASCII_UNIT_RE = re.compile(r"[a-zA-Z%°]+")

#: A number, unit optional. It has to be optional: a date written "2025-06"
#: states two numbers and no unit, and a claim saying "2025 年 6 月" cites both
#: of them. Requiring a unit meant the evidence's 2025 was never extracted at
#: all, so a correct claim about that date could not be matched to it.
#:
#: The comma in the lookbehind is there to stop "1,234" matching at "234" and
#: reporting a number the text does not state. Written as a plain character
#: class it also rejected every number written after a *Chinese* comma: this
#: text is NFKC-normalised first, which folds U+FF0C to ASCII ",", and
#: 「共 544 筆商品列，其中 119 筆無價格」 is an entirely ordinary sentence. So a
#: claim could state a figure in that position, plainly, and the gate would
#: report the drafted sentences as not stating it — on a Chinese report, in the
#: single most common place a number appears. Only a comma with a digit in
#: front of it is a thousands separator; a comma ending a clause is punctuation.
_BARE_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9.])(?<!\d,)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
)

_APOSTROPHE_SUFFIX_RE = re.compile(r"'[strelmv]|'ll|'ve|'d\b")


def _unit_after(text: str, position: int) -> str:
    """The unit stated immediately after a number, or "" when none is.

    A slash-compound is taken whole — 美元/噸 and MJ/kg are single units, and
    reading only the numerator would let a price per tonne match a price per
    kilogram.
    """
    rest = text[position:]
    stripped = rest.lstrip(" \t　")
    offset = len(rest) - len(stripped)

    match = _CJK_UNIT_RE.match(stripped) or _ASCII_UNIT_RE.match(stripped)
    if not match:
        return ""
    unit = _APOSTROPHE_SUFFIX_RE.sub("", match.group(0))
    if not unit:
        return ""

    after = position + offset + match.end()
    if text[after:after + 1] == "/":
        tail = text[after + 1:]
        tail_match = _CJK_UNIT_RE.match(tail) or _ASCII_UNIT_RE.match(tail)
        if tail_match:
            unit = f"{unit}/{tail_match.group(0)}"
    return unit


#: A rate written the way Chinese writes one: the denominator first, as
#: "每" plus a measure word. English puts it after the number — "500 USD/t" —
#: and reading only what follows the number found the numerator and dropped
#: the denominator entirely, so "每噸 500 美元" came back as 500 美元 and did
#: not match a claim stating 500 美元/噸.
#:
#: This is the third time the same failure has appeared: a Chinese way of
#: writing a quantity is not recognised, the gate blocks a correct sentence,
#: and the author learns to copy the source instead of writing. Nothing about
#: it is specific to Chinese numerals — "每噸 500 美元" fails with Arabic
#: digits too.
_PER_PREFIX_RE = re.compile(
    r"每\s*(?P<unit>%s)" % "|".join(sorted(_CJK_UNIT_WORDS, key=len, reverse=True))
)

#: How far a "每X" may sit from its number. "每噸的成本結構複雜，售價 500 美元"
#: names a rate in the first clause and a price in the second; they are not one
#: quantity, and joining them would invent a figure nobody wrote.
_PER_PREFIX_MAX_GAP = 8

#: Punctuation that ends the reach of a prefix, whatever the gap.
_CLAUSE_BREAK_RE = re.compile(r"[，。；：！？、,;:!?\n]")

#: Calendar words. "每年 3 月" is a date, not three months per year, and the
#: combination would turn a month into a rate.
_CALENDAR_UNITS = frozenset({"年", "月", "日", "天", "週", "周", "季", "季度", "世紀", "世纪"})


def _per_prefix_unit(text: str, number_start: int) -> str:
    """The "每X" denominator governing a number, or "" when none does."""
    window = text[max(0, number_start - (_PER_PREFIX_MAX_GAP + 6)):number_start]
    match = None
    for candidate in _PER_PREFIX_RE.finditer(window):
        match = candidate
    if match is None:
        return ""
    between = window[match.end():]
    if len(between) > _PER_PREFIX_MAX_GAP or _CLAUSE_BREAK_RE.search(between):
        return ""
    return match.group("unit")


def _combined_unit(text: str, number_start: int, suffix_unit: str) -> str:
    """Join a "每X" denominator to the unit written after the number."""
    prefix = _per_prefix_unit(text, number_start)
    if not prefix:
        return suffix_unit
    # A calendar word on both sides is a date, not a rate.
    if prefix in _CALENDAR_UNITS and suffix_unit in _CALENDAR_UNITS:
        return suffix_unit
    return f"{suffix_unit}/{prefix}" if suffix_unit else f"/{prefix}"


#: Classifiers that count abstract items rather than measure anything: a
#: category, a point in an argument, a market. Only consulted for numerals
#: written in Chinese -- the digit form is a figure and stays checked.
_RHETORICAL_CLASSIFIERS = frozenset({"個", "个", "項", "项", "件", "種", "种", "類", "类"})


#: A ceiling or a floor the author chose, not a reading they took. The
#: evidence side has always treated "<0.01" this way -- a limit is not a
#: measurement -- and the claim side had no equivalent, so 「其餘七個品類沒有
#: 一個超過 15%」 was refused for stating a 15% the data never states. It does
#: not need to: the sentence asserts a bound, and the largest value in the
#: table it cites is 14.15%.
_CJK_BOUND_BEFORE_RE = re.compile(
    r"(?:不超過|未超過|沒有超過|沒超過|不高於|不低於|不多於|不少於|不足|不到|低於|少於|多於|高於|超過|至多|最多|至少|最少)"
    r"\s*(?:[約約莫大約]\s*)?$"
)
_CJK_BOUND_AFTER_RE = re.compile(r"^\s*(?:[^\s]{0,3}?)(?:以下|以上|以內|以内)")


def _is_bounded_claim_number(text: str, start: int, end: int) -> bool:
    """Is this figure a limit the sentence sets, rather than a value it reads?"""
    if _CJK_BOUND_BEFORE_RE.search(text[max(0, start - 6):start]):
        return True
    return bool(_CJK_BOUND_AFTER_RE.match(text[end:end + 6]))


#: NFKC folds the fullwidth comma to ASCII, which is right for every other
#: purpose and wrong for exactly one: the thousands-separator branch of the
#: number pattern then reads across it. 「跳升至 327，500-1,000 為 317」 states
#: two separately grounded figures either side of ordinary Chinese
#: punctuation, and came out as the single number 327,500 -- which no
#: evidence contains, because it does not exist. Fabricating a figure is a
#: worse failure than the mirror bug that suppressed one.
#:
#: Held apart through the fold, so the clause break stays a clause break.
#: Same length in, same length out: every offset below still points where it
#: did.
_FULLWIDTH_COMMA = "\uff0c"
_COMMA_SHIELD = "\u0001"


#: 只有一家, 並非只有一家, 不只一家 -- a limiting phrase in front of 一 plus a
#: classifier makes it "a single one", which the sentence is denying or
#: asserting as a whole rather than counting.
_LIMITING_PHRASE_RE = re.compile(
    r"(?:只有|僅有|仅有|不只|不止|不僅|不仅|並非|并非)\s*$"
)


def _normalize_for_numbers(text: str) -> str:
    shielded = (text or "").replace(_FULLWIDTH_COMMA, _COMMA_SHIELD)
    return unicodedata.normalize("NFKC", shielded).replace(
        _COMMA_SHIELD, _FULLWIDTH_COMMA
    )


def _extract_numbers_with_unit(text: str) -> list[tuple[str, str]]:
    """Return list of (number_str, unit_str) from text."""
    results = []
    normalized = _normalize_for_numbers(text)
    for m in _BARE_NUMBER_RE.finditer(normalized):
        suffix = _unit_after(normalized, m.end())
        unit = _combined_unit(normalized, m.start(1), suffix)
        # "標價 $71.99" states a currency the same way "71.99 美元" does; only
        # the side it is written on differs.
        if _is_bounded_claim_number(normalized, m.start(1), m.end(1)):
            continue
        results.append((
            m.group(1).lstrip("~"),
            unit or _currency_before(normalized, m.start(1)),
        ))
    for m in _CJK_NUMBER_RE.finditer(normalized):
        value = _cjk_numeral_value(m.group(1))
        if value is None:
            continue
        suffix = _unit_after(normalized, m.end(1))
        # A lone 一/兩/三 with no unit after it is almost always a word, not a
        # count: 兩者, 三欄, 一致, 一般, 十分. Read as quantities they became
        # claim numbers 2, 3 and 1 that no evidence states, and the gate blocked
        # sentences whose arithmetic was never in question. The same character
        # in front of a unit — 三筆, 兩年 — still counts, because that is where
        # the notation actually appears.
        if len(m.group(1)) == 1 and not suffix:
            continue
        # 「DJI 一家就佔 92 筆」 says DJI *alone*, not one company: 一 followed
        # by a counter and then 就/獨/便 is a quantifier idiom, and reading it
        # as the quantity 1 blocked a sentence whose only figure was the 92.
        if m.group(1) == "一" and normalized[m.end(1) + 1:m.end(1) + 2] in ("就", "獨", "便"):
            continue
        # 「低分並非只有一家」 means "not just one brand", and 家 counts real
        # companies elsewhere ("五家廠商"), so the classifier cannot be
        # carved out wholesale. What marks the idiom is the limiting phrase
        # in front of it. 超過一家 is a genuine bound and is already handled
        # as one.
        if m.group(1) == "一" and _LIMITING_PHRASE_RE.search(
            normalized[max(0, m.start(1) - 4):m.start(1)]
        ):
            continue
        # 「自成一個次市場」, 「其餘七個品類」, 「受三項資料限制」. A Chinese
        # numeral in front of a generic classifier is counting the prose --
        # an indefinite article, or the items in the list that follows -- not
        # reading a figure off the data. Seven of the sixteen findings in an
        # acceptance run were this, every one of them wrong, and the author's
        # only way past was to rewrite good Chinese into stilted Chinese with
        # the numbers taken out. A measured quantity in this register is
        # written in digits, and 「6 個價格帶」 is still checked; so is 三筆,
        # 兩年, 五家 and 三個月, whose classifiers name real things.
        if suffix in _RHETORICAL_CLASSIFIERS:
            continue
        if _is_bounded_claim_number(normalized, m.start(1), m.end(1)):
            continue
        results.append((
            f"{value:g}",
            _combined_unit(normalized, m.start(1), suffix),
        ))
    return results


_BOUND_PREFIX_RE = re.compile(r"^(<=|>=|<|>|≤|≥|≦|≧)\s*")


#: A currency written in front of the amount, which is how every price column
#: in a real export is written. The row parser fed each cell to the number
#: parser as-is, "$71.99" failed to parse, and the cell was dropped — so for a
#: catalogue of 544 priced products, *every price in the file* was invisible
#: to the gate. A claim stating a price it had read correctly was refused with
#: "evidence states: 4.1", the rating being the only cell that had parsed.
#:
#: Same treatment ``~`` and the bound prefixes already get: strip the marker,
#: keep the number, and keep what the marker said — here the currency, which
#: is a unit and belongs in the unit comparison.
_CURRENCY_PREFIX_RE = re.compile(
    r"^\s*(?:(US|NT|HK|AU|CA|SG|RMB)\s*)?([$€£¥₩])\s*",
    re.IGNORECASE,
)

_SYMBOL_CURRENCY = {"$": "usd", "€": "eur", "£": "gbp", "¥": "jpy", "₩": "krw"}
_PREFIXED_CURRENCY = {
    "us": "usd", "nt": "twd", "hk": "hkd",
    "au": "aud", "ca": "cad", "sg": "sgd", "rmb": "cny",
}


def _strip_currency(text: str) -> tuple[str, str]:
    """Split "US$71.99" into ("71.99", "usd"); pass anything else through.

    An unprefixed "$" is read as USD. That is a guess, and a narrow one: it is
    only ever used as the evidence side of a unit comparison, where the
    alternative was no unit at all and therefore no number at all.
    """
    match = _CURRENCY_PREFIX_RE.match(text or "")
    if not match:
        return text, ""
    prefix, symbol = (match.group(1) or "").casefold(), match.group(2)
    unit = _PREFIXED_CURRENCY.get(prefix) or _SYMBOL_CURRENCY.get(symbol, "")
    return text[match.end():].strip(), unit


_TRAILING_CURRENCY_RE = re.compile(
    r"(?:(US|NT|HK|AU|CA|SG|RMB)\s*)?([$€£¥₩])\s*$", re.IGNORECASE
)


def _currency_before(text: str, position: int) -> str:
    """The currency written immediately in front of a number in prose."""
    match = _TRAILING_CURRENCY_RE.search(text[max(0, position - 5):position])
    if not match:
        return ""
    prefix = (match.group(1) or "").casefold()
    return _PREFIXED_CURRENCY.get(prefix) or _SYMBOL_CURRENCY.get(match.group(2), "")


#: Units a column header states as a suffix rather than in brackets. A real
#: CSV is written by whoever exported it, and "recovery_rate_pct" is at least
#: as common as "recovery rate (%)". Only tokens that name a unit are here:
#: "rate", "count" and "value" are deliberately absent, because a column
#: called recovery_rate states no unit and inventing one for it would let a
#: claim in any unit match it.
_HEADER_UNIT_SUFFIXES = frozenset({
    "pct", "percent", "percentage", "ppm", "ppb",
    "usd", "eur", "gbp", "jpy", "cny", "rmb", "twd", "ntd", "krw",
    "kg", "g", "mg", "t", "ton", "tons", "tonne", "tonnes", "lb", "lbs",
    "km", "m", "cm", "mm", "nm", "mi", "ft", "in",
    "s", "sec", "secs", "second", "seconds", "min", "mins", "minute", "minutes",
    "h", "hr", "hrs", "hour", "hours", "day", "days", "week", "weeks",
    "month", "months", "year", "years", "yr", "yrs",
    "v", "mv", "kv", "a", "ma", "w", "kw", "mw", "gw", "kwh", "mwh",
    "j", "kj", "mj", "gj", "pa", "kpa", "mpa", "bar", "psi",
    "c", "f", "k", "deg", "degc", "degf", "celsius", "fahrenheit",
    "rpm", "hz", "khz", "mhz", "ghz", "db", "l", "ml", "gal",
    "°c", "°f", "℃", "℉",
    "噸", "公噸", "公斤", "公克", "克", "毫克", "公里", "公尺", "公分", "毫米",
    "元", "美元", "度", "座", "家", "件", "次", "人", "年", "月", "日",
    "小時", "分鐘", "秒", "百分比",
})

#: A bracketed unit, in either width. The halfwidth-only pattern this replaces
#: is why a Chinese export headed "價格（USD/噸）" reported no unit at all: the
#: brackets a Chinese keyboard produces are U+FF08/U+FF09, and the check for
#: "(" never saw them. Square brackets are the other common convention.
_HEADER_BRACKET_RE = re.compile(r"[(（\[［]([^)）\]］]{1,24})[)）\]］]")

#: How a header separates its unit suffix from its name.
_HEADER_SUFFIX_SPLIT_RE = re.compile(r"[\s_\-.,、/]+")


def _unit_from_header(header: str) -> str:
    """The unit a column header states, or "" when it states none.

    A unit used to be read only from a halfwidth parenthetical or a bare "%".
    Everything else came back unitless, and because an unstated unit is
    compared as unknown, a claim in any unit matched such a column — while a
    claim naming the right unit against a column that *did* state one failed
    for saying more than the header did. Both directions were wrong, and the
    common shapes (snake_case suffixes, fullwidth brackets) fell in the gap.

    The bracketed form is taken verbatim rather than through unit_signature:
    that function builds a grouping key for charts and folds "°C" to "degc",
    which no claim ever writes, so "48.6 °C" failed to match the column
    holding it.
    """
    text = str(header or "").strip()
    if not text:
        return ""

    bracketed = _HEADER_BRACKET_RE.findall(text)
    if bracketed:
        return bracketed[-1].strip()

    if "%" in text or "％" in text:
        return "%"

    # A trailing token, but only when the header has more than one: a column
    # simply called "kg" is a unit; a column called "hours" is the reading
    # itself, and either way naming it costs nothing. A single-token header
    # that is not in the vocabulary states no unit.
    tokens = [token for token in _HEADER_SUFFIX_SPLIT_RE.split(text) if token]
    if tokens and tokens[-1].casefold() in _HEADER_UNIT_SUFFIXES:
        return tokens[-1]
    return ""


def _row_numbers_with_unit(content: str) -> tuple[list, list] | None:
    """Number/unit pairs from a serialized table row: (measured, bounded).

    A CSV row keeps its units in the column names and its numbers in the
    cells — `{"Efficiency (%)": "88.4"}`. The text extractor needs the unit
    written next to the number, so it found nothing at all in a row of
    measurements, and every honest claim citing one was blocked with
    "evidence has: (none)" while the row plainly held the figure.

    Bounded cells come back separately. "<0.01" is a detection limit, not a
    reading, and must not satisfy a claim stating 0.01 as measured.

    None when the content is not a serialized row, so prose evidence keeps
    its existing behaviour.
    """
    try:
        record = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(record, dict):
        return None

    measured: list[tuple[str, str, str]] = []
    bounded: list[tuple[str, str, str]] = []
    for key, value in record.items():
        unit = _unit_from_header(str(key))
        text = unicodedata.normalize("NFKC", str(value)).strip()
        bound = _BOUND_PREFIX_RE.match(text)
        if bound:
            text = text[bound.end():].strip()
        text, currency = _strip_currency(text)
        # The header wins when it states a unit: "price (USD)" is what the
        # exporter meant, and a stray symbol in one cell should not override
        # it. Where the header says nothing, the symbol is all there is.
        unit = unit or currency
        text = text.rstrip("%")
        if not text:
            continue
        try:
            _normalize_number_str(text)
        except ValueError:
            continue
        if bound:
            bounded.append((text, unit, f"{bound.group(1)}{text}"))
        else:
            measured.append((text, unit, str(key)))
    return measured, bounded


def _normalize_number_str(s: str) -> float:
    """Parse a number string to float, stripping commas and ~ prefix."""
    import re as _re
    # Strip commas (thousands separator) and ~ prefix (evidence "approximately" marker)
    # e.g. "~451,947" → "451947", "9,696" → "9696"
    s = s.lstrip('~').replace(',', '')
    s = _re.sub(r'[eE][+-]?\d+', lambda m: str(float(m.group(0))), s)
    return float(s)


def _same_value(claim_val: float, evidence_num: str) -> bool:
    """Is this evidence number the same quantity the claim states?"""
    try:
        return abs(claim_val - _normalize_number_str(evidence_num)) <= abs(claim_val * 0.01) + 1e-9
    except ValueError:
        return False


def _decimal_places(num_str: str) -> int:
    """Count the decimal places a number string explicitly states."""
    s = num_str.lstrip("~").replace(",", "")
    mantissa = re.split(r"[eE]", s, maxsplit=1)[0]
    return len(mantissa.split(".", 1)[1]) if "." in mantissa else 0


_UNIT_ALIASES = {
    "percent": "%",
    "pct": "%",
    "percentage": "%",
    "tonne": "t",
    "tonnes": "t",
    "ton": "t",
    "tons": "t",
    "噸": "t",
    "公噸": "t",
    "美元": "usd",
    "美金": "usd",
    "新臺幣": "twd",
    "新台幣": "twd",
    "人民幣": "cny",
    "人民币": "cny",
    "\u516c\u5206": "cm",
    "\u5398\u7c73": "cm",
    "\u6beb\u7c73": "mm",
    "\u516c\u5398": "mm",
    "\u516c\u5c3a": "m",
    "\u7c73": "m",
    "\u4f0f\u7279": "v",
    "\u5b89\u57f9": "a",
    "\u6b50\u59c6": "ohm",
    "\u6b27\u59c6": "ohm",
    "\u79d2": "s",
    "\u5206\u9418": "min",
    "\u5206\u949f": "min",
    "\u5c0f\u6642": "h",
    "\u5c0f\u65f6": "h",
    "\u767e\u5206\u6bd4": "%",
    "\uff05": "%",
    # Currency, written as a symbol on one side and a word on the other. A
    # price column holding "$71.99" and a claim written "71.99 \u7f8e\u5143" state the
    # same unit; without these they were two different units and the claim was
    # refused.
    "$": "usd",
    "us$": "usd",
    "nt$": "twd",
    "hk$": "hkd",
    "\u20ac": "eur",
    "\u00a3": "gbp",
    "\u00a5": "jpy",
    "\u20a9": "krw",
    "\u6b50\u5143": "eur",
    "\u6b27\u5143": "eur",
    "\u65e5\u5713": "jpy",
    "\u65e5\u5143": "jpy",
    "\u6e2f\u5e63": "hkd",
    "\u6e2f\u5e01": "hkd",
    # Generic counters. 個, 組, 項, 筆 and 種 state that something was
    # counted and nothing else — there is no dimension in them to disagree
    # about. Held apart, a report describing the tool's own six-row table as
    # 「六個價格帶」 was refused because the table calls them 「6組」: the value is
    # right, the claim is true, and the author is being required to adopt the
    # pipeline's measure word to describe the pipeline's own output. A reading
    # in 座 still does not support a claim in 公噸.
    "個": "count", "个": "count",
    "組": "count", "组": "count",
    "項": "count", "项": "count",
    "筆": "count", "笔": "count",
    "種": "count", "种": "count",
}


def _singular_unit(unit: str) -> str:
    if unit.endswith("s") and len(unit) > 1:
        return unit[:-1]
    return unit


def _normalize_unit(unit: str) -> str:
    """A comparison key for a unit, per slash-separated component.

    Aliasing the whole string only ever matched a compound to itself, so a
    column headed "價格（USD/噸）" and a claim written "8,259 美元/噸" were held
    to be different units — the same figure, in the same unit, spelled by two
    people. Each side of the slash is aliased on its own so the two agree.
    """
    normalized = unicodedata.normalize("NFKC", unit or "").strip().casefold()
    normalized = normalized.replace(" ", "")
    if normalized in _UNIT_ALIASES:
        return _UNIT_ALIASES[normalized]
    if "/" in normalized:
        return "/".join(
            _UNIT_ALIASES.get(part, part) for part in normalized.split("/")
        )
    return normalized


def _units_match(claim_unit: str, evidence_unit: str) -> bool:
    """Do these two units agree, treating an unstated unit as unknown?

    An unstated unit is not a unit named "" that differs from every other; it
    is the absence of information. "2025-06" states no unit and a claim citing
    it says "2025 年 6 月", and refusing that pairing blocked correct claims
    about dates, versions, and anything else written without one. Where both
    sides do state a unit, the comparison is as strict as it ever was — a
    reading in 座 does not support a claim in 公噸.
    """
    claim_norm = _normalize_unit(claim_unit)
    evidence_norm = _normalize_unit(evidence_unit)
    if not claim_norm or not evidence_norm:
        return True
    return claim_norm == evidence_norm or _singular_unit(claim_norm) == _singular_unit(evidence_norm)


def _cjk_chars(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text or "")
    return re.findall(r"[\u3400-\u9fff]", normalized)


def _cjk_bigrams(chars: list[str]) -> set[str]:
    return {
        "".join(chars[index:index + 2])
        for index in range(max(0, len(chars) - 1))
    }


def _check_term_overlap(
    claim_text: str,
    evidence_content: str,
    source_role: str,
    *,
    cross_language: bool = False,
    row_shaped: bool = False,
) -> list[str]:
    """English key-term coverage of the claim against evidence content.

    With ``cross_language=True`` the same check runs for a non-CJK claim that
    cites CJK-heavy evidence: bilingual evidence rows can still satisfy it via
    their embedded English terms, but a claim sharing no vocabulary with its
    citation is reported instead of silently passing.
    """
    term_re = re.compile(r"\b[a-zA-Z]{5,}\b")
    claim_terms = term_re.findall(claim_text.lower())
    stopwords = {
        "should", "would", "could", "might", "must", "shall", "which",
        "where", "when", "while", "there", "their", "these", "those",
        "however", "therefore", "because", "result", "results", "study",
        "analysis", "method", "methods", "paper", "research", "report",
    }
    key_terms = [t for t in claim_terms if t not in stopwords]
    if not key_terms:
        return []
    evidence_lower = evidence_content.lower()
    matched = sum(1 for t in key_terms if t in evidence_lower)
    coverage = matched / len(key_terms)
    # Use lower threshold for code evidence (code vocab ≠ academic vocab).
    # A data row is the same case and worse: its whole vocabulary is its
    # column headers, so "effectiveness reached 83.1% at the highest flow
    # rate" was failed for "reached" and "highest" — narrative words no row
    # can contain. The numbers in such a claim are checked separately, and
    # against the row's own header/value pairs.
    threshold = 0.20 if (source_role == "code_artifact" or row_shaped) else 0.40
    if coverage >= threshold:
        return []
    missing = [t for t in key_terms if t not in evidence_lower]
    label = (
        "Cross-language claim terms not in evidence"
        if cross_language
        else "Claim key terms not in evidence"
    )
    return [
        f"{label} ({coverage:.0%} coverage, "
        f"threshold={threshold:.0%}): {', '.join(missing[:5])}"
    ]


def _check_cjk_overlap(
    claim_text: str,
    evidence_content: str,
    *,
    row_shaped: bool = False,
) -> list[str]:
    claim_chars = _cjk_chars(claim_text)
    evidence_chars = _cjk_chars(evidence_content)
    if len(claim_chars) < 4 or len(evidence_chars) < 4:
        return []

    claim_grams = _cjk_bigrams(claim_chars)
    evidence_grams = _cjk_bigrams(evidence_chars)
    if not claim_grams:
        return []

    matched = claim_grams & evidence_grams
    coverage = len(matched) / len(claim_grams)
    # The English branch already lowers its floor for a data row, on the
    # grounds that a row's whole vocabulary is its column headers. A derived
    # statistic is the same case one step further out: its wording is
    # generated from column names, so a claim written in a person's words
    # shares almost no bigrams with it — "本樣本共收錄 544 筆商品" against
    # "本檔共 544 筆資料列" is the same fact and 0% overlap. What is
    # substantive for this evidence is the numeric check, and that one is
    # strict.
    threshold = 0.10 if row_shaped else 0.25
    if coverage >= threshold:
        return []

    missing = sorted(claim_grams - evidence_grams)
    return [
        "Chinese claim terms not in evidence "
        f"({coverage:.0%} bigram coverage, threshold={threshold:.0%}): "
        + ", ".join(missing[:5])
    ]


#: A quotation, in the marks each language actually uses. The scanner looked
#: for ASCII double quotes only, so a Chinese claim quoting its source was
#: never checked against it: 報告指出「結構化流程無法縮短處理時間」 — a quote
#: that inverts what the evidence says — passed, while its English twin was
#: caught verbatim. Fabricated quotation is the thing this gate exists for,
#: and it was unguarded in the language the tool is mostly used in.
#:
#: The four-character floor is the English rule's own, kept rather than
#: lowered: Chinese uses 「」 for emphasis as well as quotation, and a two- or
#: three-character 「重要」 is a writer stressing a term, not citing one.
#: 「」 is deliberately absent. In Chinese it marks emphasis and scare-quotes at
#: least as often as quotation -- 「應讀成『只有原廠周邊會掛品牌』」 was refused for
#: not reproducing verbatim a phrase the author had flagged as their own reading.
#: 『』 is the form that means quotation when 「」 does not, and a real citation in
#: Chinese technical prose is introduced by a reporting verb, which is handled
#: below.
_QUOTED_PHRASE_RE = re.compile(
    r'"([^"]{4,200})"'
    r"|『([^』]{4,200})』"
    r"|“([^”]{4,200})”"
)

#: 「」 still means quotation after a reporting verb: 評論寫道「…」. Only then.
_REPORTED_SPEECH_RE = re.compile(
    r"(?:說|說道|寫道|表示|指出|稱|提到|引述|原文|回覆|評論|留言|批評|抱怨)"
    r"\s*[:：]?\s*「([^」]{4,200})」"
)

_QUESTION_SPEAKER_RE = re.compile(r"^\s*(問|answer|question|q|a)\s*[:：.]\s*", re.IGNORECASE)
_ASSERTION_END_RE = re.compile(r"[。．.!！;；]")


def _is_heading_only(evidence: dict) -> bool:
    """True when the evidence is a heading, which asserts nothing.

    A heading names a section; it does not say anything that could be true or
    false. Term overlap let one ground the claim that restated it — and in
    Chinese, where a heading has no spaces, "板式熱交換器有效度量測" contains
    every key term of "本實驗量測板式熱交換器的有效度。", so coverage reached
    100% and a label certified the claim. The English heading beside it was
    refused, but only by the accident of its terms not matching.

    Same shape as a question standing alone, and refused for the same reason.

    Decided on the parser's own block type rather than on how the text looks.
    A marker test was written first and refused "3. 79.3% 為第三次試驗的有效度"
    — a numbered line that states a measurement, which is how notes are kept.
    Refusing a sound claim is worse than the gap this closes, and the parser
    already knows the answer without guessing.
    """
    return str(evidence.get("block_type", "")) == "heading"


def _is_question_only(text: str) -> bool:
    """True when the text asks something and asserts nothing.

    An interview transcript, a FAQ or minutes with a Q&A section put
    questions in the ledger alongside answers, and term overlap let one
    ground the very claim it was asking about: "問：目前最花時間的環節是
    什麼？" grounded "退款是目前最花時間的環節。" The evidence posed the
    question; the answer came from nowhere.

    A line that also asserts something is left alone — only a bare question
    is refused.
    """
    stripped = _QUESTION_SPEAKER_RE.sub("", (text or "").strip()).strip()
    if not stripped.endswith(("?", "？")):
        return False
    return not _ASSERTION_END_RE.search(stripped[:-1])


#: Block types that are one record out of a table. A derived statistic is
#: deliberately not one of them: it is a statement about a whole selection of
#: rows, and the single-row rules below must not apply to it.
_RAW_ROW_BLOCK_TYPES = frozenset({"csv_row", "table_row", "data_row"})

#: Words by which a claim says it is talking about the whole dataset rather
#: than about one record.
#:
#: The failure this closes: the claim "本樣本共收錄 544 筆商品" was certified
#: by the row {"asin": "B0EXAMPLE1", "review_count": 544, "rating": 4.3} —
#: one product that happens to have 544 reviews. Nothing in that row says
#: anything about how many products there are. The check was comparing digit
#: strings, and 544 == 544.
#:
#: A single row cannot ground a statement about the sample, whatever digits it
#: contains. The repair is not to refuse the sentence but to send it to the
#: evidence that does answer it — the derived statistics built from the same
#: rows at prepare time.
_DATASET_SCOPE_RE = re.compile(
    r"樣本|母體|母体|全體|全体|全部|所有|整體|整体|總共|总共|共計|共计|合計|合计"
    r"|總計|总计|全檔|全档|平均|中位數|中位数|佔比|占比|分布|分佈|各類|各类"
    r"|\ball\b|\bsample\b|\btotal\b|\boverall\b|\baverage\b|\bmean\b|\bmedian\b"
    r"|\baggregate\b|\bdataset\b|\bacross\b|\bcombined\b|\bdistribution\b",
    re.IGNORECASE,
)

_COLUMN_BRACKET_RE = re.compile(r"[(（\[［].*?[)）\]］]")


def _is_dataset_scope_claim(claim_text: str) -> bool:
    return bool(_DATASET_SCOPE_RE.search(claim_text or ""))


def _claim_names_column(claim_text: str, column: str) -> bool:
    """True when the claim mentions this column by name.

    Deliberately one-directional. A claim that names no column is left alone,
    because column names are English in exports whose reports are written in
    Chinese and demanding a mention would block honest work. But a claim that
    *does* name one has told us which cell it is talking about, and a number
    from a different cell is then not its evidence.
    """
    text = (claim_text or "").casefold()
    name = _COLUMN_BRACKET_RE.sub(" ", str(column or ""))
    for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", name):
        if token.casefold() in text:
            return True
    return any(token in (claim_text or "") for token in re.findall(r"[㐀-鿿]{2,}", name))


_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9²³/-]{1,}")
_LATIN_TOKEN_STOPWORDS = {"the", "and", "for", "with", "per", "vs", "et", "al"}


def _check_cross_script_tokens(claim_text: str, evidence_content: str) -> list[str]:
    """Check a CJK claim against Latin evidence on what the two can share.

    Across scripts the only vocabulary both sides write the same way is the
    technical kind a Chinese sentence keeps in Latin — NTU, CRM, R², a cited
    author's name. Where the claim carries such a token, it must appear in
    the evidence.

    A claim carrying none is passed: there is genuinely nothing to compare,
    and reporting it would block the ordinary honest case of a Chinese
    sentence summarising an English source in Chinese words. That gap is
    recorded as a documented evasion rather than papered over.
    """
    tokens = [
        token for token in _LATIN_TOKEN_RE.findall(claim_text)
        if token.lower() not in _LATIN_TOKEN_STOPWORDS
    ]
    if not tokens:
        return []
    evidence_lower = evidence_content.lower()
    missing = [token for token in tokens if token.lower() not in evidence_lower]
    coverage = 1 - len(missing) / len(tokens)
    # Same 0.40 floor the English term check uses, deliberately: two shapes
    # of the same rule in one file is how the neighbouring branch came to be
    # forgotten in the first place.
    if coverage >= 0.40:
        return []
    return [
        f"Claim terms not in evidence ({coverage:.0%} coverage across scripts, "
        f"threshold=40%): " + ", ".join(sorted(set(missing))[:5])
    ]


def _check_content_overlap(claim: dict, evidence: dict) -> list[str]:
    """Mismatch reasons for one claim against one evidence entry."""
    return [reason for _key, reason in _content_overlap_findings(claim, evidence)]


def _content_overlap_findings(
    claim: dict,
    evidence: dict,
) -> list[tuple[tuple, str]]:
    """Verify claim content is grounded in evidence content.

    Returns (key, reason) pairs; empty means this evidence satisfies every
    check. The key names which check failed — ("number", "88.4", "%"),
    ("quote", …), ("terms",) — so a caller weighing several cited evidence
    can ask whether *any* of them satisfied a given check, rather than
    demanding that every one satisfy all of them.

    Checks:
    1. Quote overlap: if claim has "quoted text" markers, verify the quote
       appears verbatim (or near-verbatim) in evidence content.
    2. Numeric overlap: if claim mentions a number+unit, that exact pair
       must appear in evidence content (not just the same topic).
    3. Term overlap: key terms (≥5 chars, non-stopword) from claim should
       appear in evidence content.
    """
    import re

    claim_text = claim.get("claim_text", "")
    evidence_content = evidence.get("content", "") or evidence.get("quote", "")
    reasons = []

    if not evidence_content:
        return [(("content",), "Evidence content is empty — cannot verify claim grounding")]

    if _is_heading_only(evidence):
        return [((
            "heading",
        ), (
            "Evidence is a section heading and states nothing, so it cannot "
            "ground this claim — cite the text under the heading instead: "
            f"{evidence_content[:60]}"
        ))]

    if _is_question_only(evidence_content):
        return [((
            "question",
        ), (
            "Evidence only asks a question and states no answer, so it cannot "
            f"ground this claim: {evidence_content.strip()[:80]!r}"
        ))]

    # 1. Quote overlap check — look for "quoted text" patterns in claim
    #    e.g., 'The system "compiles ASTs" is key' → check "compiles ASTs" in evidence
    #    Minimum length 4: short fabricated quotes ("audited") must not slip
    #    under the scanner; anything shorter is punctuation-level noise.
    quoted_phrases = [
        next(group for group in match if group)
        for match in _QUOTED_PHRASE_RE.findall(claim_text)
    ] + _REPORTED_SPEECH_RE.findall(claim_text)
    for phrase in quoted_phrases:
        # Strip trailing punctuation for matching
        phrase_stripped = phrase.rstrip('.,;:')
        if phrase_stripped.lower() not in evidence_content.lower():
            reasons.append((
                ("quote", phrase_stripped.lower()),
                f"Quoted phrase {phrase_stripped!r} not found verbatim in evidence",
            ))

    # 2. Numeric overlap check — claim numbers must appear in evidence
    claim_numbers = _extract_numbers_with_unit(claim_text)
    row_pairs = _row_numbers_with_unit(evidence_content)
    row_measured, row_bounded = row_pairs if row_pairs else ([], [])
    is_raw_row = (
        row_pairs is not None
        and str(evidence.get("block_type", "")) in _RAW_ROW_BLOCK_TYPES
    )

    if is_raw_row and claim_numbers and _is_dataset_scope_claim(claim_text):
        return [((
            "dataset_scope",
        ), (
            "Claim states something about the whole dataset, but the evidence is "
            "a single data row, which says nothing about how many rows there are "
            "or how they are distributed — a matching digit in one record is a "
            "coincidence, not support. Cite the derived statistics built from "
            f"these rows, or register the one you need. Row: {evidence_content[:80]}"
        ))]

    named_columns = (
        {column for _n, _u, column in row_measured if _claim_names_column(claim_text, column)}
        if is_raw_row
        else set()
    )

    for num_str, unit in claim_numbers:
        try:
            claim_val = _normalize_number_str(num_str)
        except ValueError:
            continue

        # Search for same value in evidence (with same unit).
        #
        # A serialized row is read only through its cells. Scanning the raw
        # JSON text as well now that a bare number needs no unit would pull
        # "0.01" straight out of the string "<0.01" — the detection limit the
        # row parser deliberately files as a bound and not as a reading — and
        # a claim stating it as measured would pass.
        evidence_numbers = (
            list(row_measured)
            if row_pairs is not None
            else [
                (number, number_unit, "")
                for number, number_unit in _extract_numbers_with_unit(evidence_content)
            ]
        )
        # A claim that named a column is asking about that column. Reading its
        # figure out of a different cell is the same coincidence as reading a
        # sample size out of a review count, one row narrower.
        misplaced: list[str] = []
        if named_columns:
            kept = []
            for ev_num, ev_unit, ev_column in evidence_numbers:
                if ev_column in named_columns:
                    kept.append((ev_num, ev_unit, ev_column))
                elif _same_value(claim_val, ev_num) and _units_match(unit, ev_unit):
                    misplaced.append(f"{ev_column}={ev_num}")
            evidence_numbers = kept
        found = False
        bounded_match: tuple[str, str] | None = None
        for ev_num, ev_unit, ev_text in row_bounded:
            if not _units_match(unit, ev_unit):
                continue
            try:
                if abs(claim_val - _normalize_number_str(ev_num)) <= abs(claim_val * 0.01) + 1e-9:
                    bounded_match = (ev_text, ev_unit)
                    break
            except ValueError:
                continue
        inflated_match: tuple[str, str] | None = None
        for ev_num, ev_unit, _ev_column in evidence_numbers:
            # Units must match (after normalization)
            if not _units_match(unit, ev_unit):
                continue
            try:
                ev_val = _normalize_number_str(ev_num)
            except ValueError:
                continue
            # Allow 1% tolerance for floating point
            if abs(claim_val - ev_val) > abs(claim_val * 0.01) + 1e-9:
                continue
            if claim_val != ev_val and _decimal_places(num_str) > _decimal_places(ev_num):
                # Within tolerance, but the claim states more decimal places
                # than the evidence provides: "3.53%" is not a rounding of
                # "3.5%", it is precision the source never asserted.
                inflated_match = (ev_num, ev_unit)
                continue
            found = True
            break

        if not found:
            number_key = ("number", num_str, unit)
            if misplaced:
                reasons.append((number_key, (
                    f"Claim number {num_str!r}{unit} appears in this row only under "
                    f"{', '.join(misplaced)}, which is not the column the claim "
                    f"names ({', '.join(sorted(named_columns))}). A value in a "
                    "different field does not support it."
                )))
            elif bounded_match:
                reasons.append((number_key, (
                    f"Claim number {num_str!r}{unit} states as measured what the "
                    f"evidence gives only as a bound "
                    f"({bounded_match[0]!r}{bounded_match[1]} is a limit, "
                    f"not a reading)"
                )))
            elif inflated_match:
                reasons.append((number_key, (
                    f"Claim number {num_str!r}{unit} asserts more decimal "
                    f"precision than the evidence value "
                    f"{inflated_match[0]!r}{inflated_match[1]} supports"
                )))
            else:
                # Two different failures used to be reported with one sentence,
                # and an author could not tell which had happened: whether they
                # had written a number the source does not contain, or written
                # the right number against the wrong unit. The first is theirs
                # to fix; the second is often the gate being too strict, and
                # they could not distinguish them.
                unit_conflicts = sorted({
                    f"{ev_num}{ev_unit}"
                    for ev_num, ev_unit, _column in evidence_numbers
                    if _same_value(claim_val, ev_num) and not _units_match(unit, ev_unit)
                })
                ev_nums_str = ", ".join(
                    f"{n}{u}" for n, u, _column in evidence_numbers
                ) or "(none)"
                if unit_conflicts:
                    reasons.append((number_key, (
                        f"Claim number {num_str!r}{unit} states a unit the evidence "
                        f"does not: the evidence gives this value as "
                        f"{', '.join(unit_conflicts)}"
                    )))
                else:
                    reasons.append((number_key, (
                        f"Claim number {num_str!r}{unit} is not stated in the evidence "
                        f"(evidence states: {ev_nums_str})"
                    )))

    # 3. Term overlap — key terms from claim should appear in evidence.
    #    CJK-heavy evidence takes the bigram path for CJK claims. A non-CJK
    #    claim citing CJK-heavy evidence no longer gets a free pass: it falls
    #    back to the English term check (bilingual evidence rows still pass
    #    via their embedded English terms; garbled or purely-CJK evidence
    #    cannot ground an English claim, so it is reported).
    def _is_likely_non_ascii(text: str) -> bool:
        """Return True if text is >30% non-ASCII (CJK, Arabic, etc.)."""
        if not text:
            return False
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        total = len(text)
        return total > 0 and (total - ascii_chars) / total > 0.3

    source_role = evidence.get("source_role", "primary_source")
    row_shaped = (
        row_pairs is not None
        or str(evidence.get("block_type", "")) == "derived_statistic"
    )
    if _is_likely_non_ascii(evidence_content):
        if len(_cjk_chars(claim_text)) >= 4:
            term_reasons = _check_cjk_overlap(
                claim_text, evidence_content, row_shaped=row_shaped
            )
        else:
            term_reasons = _check_term_overlap(
                claim_text, evidence_content, source_role,
                cross_language=True, row_shaped=row_shaped,
            )
    elif len(_cjk_chars(claim_text)) >= 4:
        # A Chinese claim citing English evidence — a report written in
        # Chinese that cites the English literature, which is the ordinary
        # case here. The English term check finds no [a-zA-Z]{5,} in a
        # Chinese claim, returns an empty key-term list and passes
        # unconditionally, so this was the one direction of the four with no
        # vocabulary check at all. The mirror (English claim, CJK evidence)
        # was closed earlier; this is its neighbour.
        term_reasons = _check_cross_script_tokens(claim_text, evidence_content)
    else:
        term_reasons = _check_term_overlap(
            claim_text, evidence_content, source_role, row_shaped=row_shaped
        )
    # One key for both paths: they are two implementations of the same
    # "does the claim's vocabulary appear here" question, and a claim citing
    # a Chinese source and an English one is satisfied by either.
    reasons.extend((("terms",), reason) for reason in term_reasons)

    return reasons


def run_factuality_check_fd(
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict] | None = None,
) -> list[dict]:
    """Verify that wording_strength is consistent with evidence_grade.

    A sentence backed by low-grade evidence may not assert conclusions
    with "measured" certainty — it must be hedged.
    """
    evidence_by_id = {
        ev.get("evidence_id"): ev
        for ev in (evidence_ledger or [])
        if ev.get("evidence_id")
    }

    # Build claim_id → set of evidence_ids
    claims = claim_matrix.get("claims", [])
    claim_evidence_ids: dict[str, set[str]] = {}
    for claim in claims:
        cid = _claim_id(claim)
        if cid:
            claim_evidence_ids[cid] = set(claim.get("evidence_ids", []))

    results = []
    for sent in sentence_map:
        sentence_id = sent.get("sentence_id") or sent.get("sent_id", "<missing>")
        wording = str(sent.get("wording_strength") or "").lower()

        # Collect all evidence grades for this sentence via its claims
        linked_evidence_ids: list[str] = list(sent.get("evidence_ids", []))
        for cid in sent.get("claim_ids", []):
            linked_evidence_ids.extend(claim_evidence_ids.get(cid, []))

        if not linked_evidence_ids:
            continue

        # Determine the minimum (weakest) evidence grade
        grades = []
        for eid in linked_evidence_ids:
            ev = evidence_by_id.get(eid)
            if ev:
                g = str(ev.get("evidence_grade") or "low").lower()
                if g in _ALLOWED_WORDING_BY_GRADE:
                    grades.append(g)

        if not grades:
            continue

        # Use the weakest grade to validate wording
        weakest_grade = min(
            grades,
            key=lambda g: list(_ALLOWED_WORDING_BY_GRADE.keys()).index(g),
        )
        allowed = _ALLOWED_WORDING_BY_GRADE.get(weakest_grade, set())

        if wording and wording not in _VALID_WORDING_STRENGTHS:
            continue

        if wording and wording not in allowed:
            results.append({
                "sentence_id": sentence_id,
                "status": "blocked",
                "checker": "FD",
                "reason": (
                    f"Wording strength '{wording}' is not allowed for "
                    f"evidence_grade='{weakest_grade}' "
                    f"(allowed: {', '.join(sorted(allowed))})"
                ),
            })

    return results


def _revision_sidecar_mode(
    state: ReportState,
    sentence_map: list[dict],
    claim_matrix: dict,
    evidence_ledger: list[dict],
) -> bool:
    return (
        state.spec.get("task_intent") == "revise_existing"
        and bool(sentence_map)
        and bool(claim_matrix.get("claims"))
        and bool(evidence_ledger)
    )


#: A currency code or symbol with no number after it, and a thousands group
#: with no leading digits. Neither occurs in ordinary writing; both are the
#: fingerprint of a string-processing accident upstream — a shell that expanded
#: `$500` as a variable, a template that dropped a field, a regex that ate a
#: digit run. The sentence stays fluent afterwards, which is what makes it
#: dangerous: "每噸年產能約 US,000 的資本門檻" reads like a finished sentence and
#: a proofreader does not stop on it, where "US$9,999" would have been caught.
#: Only the symbol-prefix forms — "US$", "NT$", "HK$" — with the symbol and
#: the amount gone. The ISO codes are deliberately absent: "USD/噸" and "TWD/kg"
#: are how a column header legitimately names a unit, and flagging those would
#: report every price table in the corpus. What mangling produces is the *stem*
#: of a symbol form: US$500/噸 loses "$500" and leaves "US/噸".
_MANGLED_AMOUNT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:US|NT|HK)(?=[/／])", "currency code with no amount"),
    (r"\b(?:US|NT|HK)\s*[,，]\s*\d", "currency code followed by a thousands group"),
    (r"[$€£¥₩＄]\s*(?![\d.])", "currency symbol with no amount"),
    (r"(?:約|约|approximately|approx\.?)\s*[/／]", "approximation marker with no amount"),
)

_MANGLED_AMOUNT_RE = tuple(
    (re.compile(pattern), reason) for pattern, reason in _MANGLED_AMOUNT_PATTERNS
)

#: Paragraphs, not sentences. Splitting on sentence punctuation cut URLs and
#: decimals in half — "https://…/2025/lfp-recycling" became two fragments, and
#: the half holding the citation then appeared to state no numbers at all.
#:
#: A paragraph is also the safer unit on the merits. It is a superset of the
#: sentences bound to a claim, so the check can miss a number that moved to a
#: neighbouring sentence, but it cannot invent a miss — and a false block here
#: costs an author a correct draft, which is the failure mode this project has
#: already had to repair once in FE.
_DRAFT_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")

#: Workflow markers, removed before any number is read out of a sentence. An
#: evidence id is mostly hex — `[CITE:E_e8aa9edd_9532732fd7]` — so leaving the
#: marker in place fed "9532732" to the numeric extractor as though the author
#: had written it, and the comparison then ran against digits nobody typed.
_WORKFLOW_MARKER_RE = re.compile(r"\[(?:CITE|FIGURE|TABLE|Source|graphify):[^\]]*\]", re.IGNORECASE)


def find_mangled_amounts(text: str) -> list[tuple[str, str]]:
    """Fragments where a number was lost, as (fragment, reason).

    Cheap, and independent of any claim binding — it guards prose that no
    claim covers, which is exactly where the claim-level check below cannot
    reach.
    """
    findings: list[tuple[str, str]] = []
    for pattern, reason in _MANGLED_AMOUNT_RE:
        for match in pattern.finditer(text or ""):
            start = max(match.start() - 12, 0)
            fragment = " ".join(text[start:match.end() + 12].split())
            findings.append((fragment, reason))
    return findings


def _claim_sentences(merged_text: str, evidence_ids: set[str]) -> list[str]:
    """Sentences of the draft that cite this claim's evidence.

    The sentence map records which claim a sentence serves but not the words
    it used, so the binding that can actually be read back is the [CITE:]
    marker standing in the prose. That is the same link the rest of the
    pipeline resolves, so a sentence found here is a sentence the reader will
    see attached to this claim.
    """
    if not evidence_ids:
        return []
    passages = []
    for passage in _DRAFT_PARAGRAPH_SPLIT_RE.split(merged_text or ""):
        cited = {
            cite_id.strip()
            for raw in re.findall(r"\[CITE:([^\]]+)\]", passage)
            for cite_id in re.split(r"[,;]", raw)
        }
        if cited & evidence_ids:
            passages.append(_WORKFLOW_MARKER_RE.sub(" ", passage))
    return passages


def _bound_figure_numbers(state, claim_id: str, outline: dict) -> list[tuple[str, str]]:
    """Numbers in the figures and tables the claim's sections carry.

    A figure is a legitimate place to state a number. Requiring the prose to
    repeat every value the table beside it already shows would push an author
    into writing the table out twice.
    """
    section_ids = {
        section_id
        for section_id, section in (outline.get("sections") or {}).items()
        if isinstance(section, dict) and claim_id in (section.get("claim_ids") or [])
    }
    if not section_ids:
        return []

    plan_path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
    if not plan_path.exists():
        return []
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    numbers: list[tuple[str, str]] = []
    for figure in payload.get("figures", []) or []:
        if not isinstance(figure, dict):
            continue
        if figure.get("section_id") and figure["section_id"] not in section_ids:
            continue
        numbers.extend(
            _extract_numbers_with_unit(json.dumps(figure.get("data") or {}, ensure_ascii=False))
        )
    return numbers


def _covered(claim_number: tuple[str, str], available: list[tuple[str, str]]) -> bool:
    number, unit = claim_number
    try:
        value = _normalize_number_str(number)
    except ValueError:
        return True
    for other, other_unit in available:
        if not _units_match(unit, other_unit):
            continue
        try:
            if abs(value - _normalize_number_str(other)) <= abs(value * 0.01) + 1e-9:
                return True
        except ValueError:
            continue
    return False


def run_factuality_check_fs(
    merged_text: str,
    claim_matrix: dict,
    state=None,
    outline: dict | None = None,
) -> list[dict]:
    """FS: does the drafted prose actually state what its claim asserts?

    FA checks that claim, evidence and sentence are linked. FE checks that the
    claim's numbers are in its evidence. Nothing checked the third leg — that
    the sentence the reader ends up with says the number the claim promised —
    so a figure could vanish between the claim matrix and the prose with every
    gate passing.

    That is not hypothetical. A claim asserting "US$500/噸 ... capex 約
    US$1,000/噸年產能" was drafted as "需約 US/噸的產品售價 ... 資本支出約
    US,000", the amounts eaten by a shell expanding `$500` as a variable. Every
    gate passed and it reached the delivered document.

    Compared per claim rather than per sentence, and against the union of
    everything the claim is attached to. One claim is often written as two or
    three sentences, and a sentence may set up rather than restate; demanding
    that each sentence repeat every figure would recreate the "copy the source
    or be blocked" failure FE was just repaired for.
    """
    results: list[dict] = []
    for claim in claim_matrix.get("claims", []):
        claim_id = _claim_id(claim)
        if str(claim.get("status", "supported")).lower() in BLOCKING_CLAIM_STATUSES:
            continue

        asserted = _extract_numbers_with_unit(claim.get("claim_text", ""))
        if not asserted:
            continue

        evidence_ids = {str(eid) for eid in claim.get("evidence_ids", []) if eid}
        sentences = _claim_sentences(merged_text, evidence_ids)
        if not sentences:
            # No sentence in the draft carries this claim's citation. FA owns
            # that failure; reporting it again here would double-block it.
            continue

        available = _extract_numbers_with_unit(" ".join(sentences))
        if state is not None and outline is not None:
            available.extend(_bound_figure_numbers(state, claim_id, outline))

        missing = [pair for pair in asserted if not _covered(pair, available)]
        if not missing:
            results.append({
                "claim_id": claim_id,
                "status": "verified",
                "checker": "FS",
                "reason": "Draft states every figure the claim asserts",
            })
            continue

        rendered = ", ".join(f"{number}{unit}" for number, unit in missing)
        stated = ", ".join(f"{number}{unit}" for number, unit in available) or "(none)"
        results.append({
            "claim_id": claim_id,
            "status": "blocked",
            "checker": "FS",
            "reason": (
                f"Claim asserts {rendered}, which the drafted sentences do not state "
                f"(they state: {stated}). Either write the figure into the prose, put it "
                f"in a figure or table the section carries, or narrow the claim."
            ),
        })
    return results


def run_factuality_check(state: ReportState) -> ReportState:
    """T13: FACTUALITY_CHECK - verify claims vs evidence."""
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path", ""))
    evidence_ledger = _load_jsonl(state.sources.get("evidence_ledger_path", ""))
    claim_matrix = _load_json(run_dir / "claim_matrix.json") or state.plan.get("claim_matrix", {})
    outline = _load_json(run_dir / "outline.json") or state.plan.get("outline", {})

    if not sentence_map:
        raise QAHardBlockError("Sentence map is empty")
    if not evidence_ledger:
        raise QAHardBlockError("Evidence ledger is empty")
    if not claim_matrix.get("claims"):
        raise QAHardBlockError("Claim matrix is empty")

    results_fa = run_factuality_check_fa(sentence_map, claim_matrix, evidence_ledger)
    all_results = run_factuality_check_fb(results_fa, claim_matrix, evidence_ledger)
    checkers_run = ["FA", "FB"]

    # FE — does the claim's content appear in the evidence it cites?
    #
    # This used to run only under --deep-audit, which meant it did not run on
    # the publish path at all. Everything a caller saw said otherwise: the
    # plugin advertises that every claim must trace to its sources, and the
    # delivery summary reported "Factuality: pass (44 verified)". What had
    # actually been checked was FA (the ids line up) and FS (the prose repeats
    # the claim's own figures) — both internal consistency, neither a
    # comparison against the evidence. A median nobody had recorded passed
    # because the author wrote the same number twice.
    #
    # An off-by-default gate that the summary reports as passing is worse than
    # no gate: it spends the reader's trust without doing the work.
    deep_audit = state.flags.get("deep_audit", False)
    revision_sidecar_mode = _revision_sidecar_mode(state, sentence_map, claim_matrix, evidence_ledger)
    advisory_results: list[dict] = []
    if deep_audit or not revision_sidecar_mode:
        all_results = run_factuality_check_fe(all_results, claim_matrix, evidence_ledger)
        checkers_run.append("FE")

    # FS: the drafted prose must state what its claim asserts. Unlike FE this
    # runs on every job, not only under --deep-audit: the failure it catches
    # is a number going missing between the claim matrix and the page, which
    # no other gate looks at and which has already shipped once.
    merged_text = ""
    merged_path = state.drafts.get("merged_draft_md") or str(run_dir / "merged_draft.md")
    if merged_path and Path(merged_path).exists():
        merged_text = Path(merged_path).read_text(encoding="utf-8")
    if merged_text and not revision_sidecar_mode:
        all_results.extend(
            run_factuality_check_fs(merged_text, claim_matrix, state, outline)
        )
        checkers_run.append("FS")

    # F2: wording strength vs evidence grade (FD)
    results_fd = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
    if revision_sidecar_mode and not deep_audit:
        advisory_results.extend({**result, "status": "advisory"} for result in results_fd)
    else:
        all_results.extend(results_fd)
        checkers_run.append("FD")

    blocked_count = sum(1 for result in all_results if result["status"] == "blocked")
    verified_count = sum(1 for result in all_results if result["status"] == "verified")

    run_dir.mkdir(parents=True, exist_ok=True)
    factuality_report = {
        "claims": all_results,
        "advisory": advisory_results,
        "blocked_count": blocked_count,
        "verified_count": verified_count,
        # Which gates actually ran, and what a "verified" line means. Reporting
        # a count without either was how "Factuality: pass (44 verified)" came
        # to describe a run in which no claim had been compared against its
        # evidence at all.
        "checkers_run": checkers_run,
        "checker_descriptions": {
            "FA": "claim, evidence and sentence ids link up",
            "FB": "a statistical claim cites quantitative evidence",
            "FE": "the claim's numbers, quotes and terms appear in the evidence it cites",
            "FS": "the drafted prose states every figure its claim asserts",
            "FD": "wording strength is allowed by the weakest cited evidence grade",
        },
        "verified_means": (
            "Every checker listed in checkers_run examined this claim and found "
            "no violation. It is a deterministic, lexical comparison against the "
            "supplied evidence — not an external fact check, and not a judgement "
            "that the claim is true."
        ),
        "sidecars_consumed": {
            "claim_matrix": bool(claim_matrix.get("claims")),
            "sentence_map": bool(sentence_map),
            "evidence_ledger": bool(evidence_ledger),
            "outline": bool(outline.get("sections")),
        },
        "deep_audit": bool(deep_audit),
        "revision_sidecar_mode": bool(revision_sidecar_mode),
    }

    factuality_path = run_dir / "factuality_report.json"
    with open(factuality_path, "w", encoding="utf-8") as f:
        json.dump(factuality_report, f, indent=2)

    state.qa["factuality_report_path"] = str(factuality_path)
    return state
