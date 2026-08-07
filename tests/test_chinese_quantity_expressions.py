"""One corpus of Chinese quantity expressions, run against every reader of them.

Three places in this pipeline parse the same kind of string — the factuality
gates through `_extract_numbers_with_unit`, the chart recommender through
`parse_measure`, and source extraction — and each has been repaired on its own,
in its own round, without the others knowing what had been learned:

* FE bound a number to the CJK characters after it, so one particle blocked a
  true claim.
* The chart recommender could not read `~` or an en-dash range, so a price
  series was recommended as a table.
* Neither could read a rate written the Chinese way round — "每噸 500 美元" —
  because both looked only at what follows the number.

Every one of those punished an author for writing Chinese naturally, and each
was found separately by someone running into it. This file is the shared list,
so the next gap is closed everywhere it exists rather than in whichever module
happened to hit it first.

Where the two readers legitimately differ, the difference is asserted rather
than smoothed over — an unasserted difference is how they drifted apart.
"""
import unittest

from report_workflow.nodes.factuality_check import _extract_numbers_with_unit
from report_workflow.nodes.figure_utils import parse_measure


#: (text, expected value, expected unit as the factuality reader sees it).
#: Each row is a way a Chinese report actually writes a quantity.
QUANTITY_CORPUS: tuple[tuple[str, str, str], ...] = (
    # Rates, suffix form — how English writes them
    ("成本為 500 美元/噸", "500", "美元/噸"),
    ("單價 417 USD/t", "417", "USD/t"),
    # Rates, prefix form — how Chinese writes them
    ("成本為每噸 500 美元", "500", "美元/噸"),
    ("成本為每噸五百美元", "500", "美元/噸"),
    ("每公斤 12 美元", "12", "美元/公斤"),
    ("每人 3 件", "3", "件/人"),
    ("每吨 500 美元", "500", "美元/吨"),
    # Chinese numerals
    ("共關閉七座回收廠", "7", "座"),
    # Measure words that are not units of measure
    ("業者在 15 個月內關閉了 7 座回收廠", "15", "個月"),
    # Percentages and plain figures
    ("回收率可達 95% 以上", "95", "%"),
    ("價格為 8,259 美元/噸", "8259", "美元/噸"),
)

#: Expressions where "每" is present and must *not* become a denominator.
#: Each is a way of writing that would otherwise be misread as a rate.
NOT_A_RATE: tuple[tuple[str, str], ...] = (
    ("每 10 人中有 3 人", "每 is followed by a number, not a measure word"),
    ("每年 3 月", "a calendar month, not three months per year"),
    ("每次都失敗", "no number at all"),
    ("每況愈下", "每 is not being used as a quantifier"),
    ("每噸的成本結構複雜，售價 500 美元", "a clause boundary separates the two"),
)

#: Values written with the modifiers a real table carries. The factuality
#: reader takes these literally; the chart reader resolves them, and the two
#: are asserted separately below.
MODIFIED_VALUES: tuple[tuple[str, float], ...] = (
    ("~8,259", 8259.0),
    ("約 500", 500.0),
    ("21,570–21,760", 21665.0),   # a range, carried at its midpoint
    ("±5%", 5.0),
    ("US$417/噸", 417.0),
    ("1,000", 1000.0),
)


class FactualityReaderTests(unittest.TestCase):
    """What FE and FS see. A miss here blocks a correct claim."""

    def test_every_expression_yields_its_value_and_unit(self):
        for text, number, unit in QUANTITY_CORPUS:
            with self.subTest(text=text):
                found = [
                    (value.replace(",", ""), found_unit)
                    for value, found_unit in _extract_numbers_with_unit(text)
                ]
                self.assertIn((number, unit), found, f"{text!r} read as {found}")

    def test_a_quantifier_that_is_not_a_rate_stays_one(self):
        for text, why in NOT_A_RATE:
            with self.subTest(text=text, why=why):
                for _number, unit in _extract_numbers_with_unit(text):
                    self.assertNotIn("/", unit, f"{text!r} — {why}")


class ChartReaderTests(unittest.TestCase):
    """What the chart recommender sees. A miss here costs a figure."""

    def test_every_modified_value_parses(self):
        for text, value in MODIFIED_VALUES:
            with self.subTest(text=text):
                measure = parse_measure(text)
                self.assertIsNotNone(measure, f"{text!r} was not read as a number")
                self.assertAlmostEqual(measure.value, value)

    def test_a_softened_value_is_marked_as_one(self):
        """A midpoint presented as a reading is a quiet fiction."""
        self.assertTrue(parse_measure("21,570–21,760").is_range)
        self.assertTrue(parse_measure("~8,259").is_approximate)
        self.assertEqual(parse_measure("±5%").tolerance, 5.0)


class ReaderDifferenceTests(unittest.TestCase):
    """Where the two readers differ, on purpose, today.

    Asserted rather than left implicit: an undocumented difference is what let
    these two drift into needing three separate repairs. If one of these starts
    failing, the readers have converged and the note should be deleted — not
    the test loosened.
    """

    def test_the_chart_reader_cannot_read_a_prefix_rate_at_all(self):
        """A measured gap, found by this corpus on the day it was written.

        The factuality reader was taught "每噸 500 美元" because a gate was
        blocking correct sentences over it. The chart reader was not, and it
        does not merely drop the denominator — it fails to read the cell,
        which degrades the whole column to non-numeric and costs the figure.

        Left failing-as-asserted rather than quietly fixed alongside, because
        the round that added the prefix rule was scoped to the factuality
        path and widening a parser is how the chart reader acquired its
        earlier defects. Delete this test when the reader is taught the same
        rule; do not loosen it.
        """
        self.assertIsNone(
            parse_measure("每噸 500 美元"),
            "the chart reader now reads prefix rates — teach it the unit too "
            "and replace this test with the positive assertion",
        )

    def test_the_factuality_reader_does_not_resolve_a_range(self):
        """It compares stated figures; averaging one would invent a number."""
        found = _extract_numbers_with_unit("21,570–21,760")
        self.assertEqual([number for number, _unit in found], ["21,570", "21,760"])


class ProseIsNotAMeasurementTests(unittest.TestCase):
    """What a Chinese sentence counts, and what it merely says.

    An acceptance run over three CSVs hit sixteen factuality findings. Six were
    the gate catching real ungrounded arithmetic. Nine were this: ordinary
    Chinese prose read as quantities the data was then required to state, and
    the author's only route past the gate was to rewrite good sentences into
    stilted ones with the figures taken out -- which costs exactly the thing
    the gate exists to protect.
    """

    def _values(self, text: str) -> list[str]:
        return [number for number, _unit in _extract_numbers_with_unit(text)]

    def test_a_chinese_numeral_before_a_generic_classifier_counts_the_prose(self):
        for text in (
            "無人機馬達自成一個低價高週轉的次市場",
            "品牌層面是一個白牌市場",
            "其餘七個品類的佔比都不高",
            "這兩個價格帶的表現相反",
            "本研究受三項資料限制",
            "其餘三個專業詞的污染程度較低",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._values(text), [])

    def test_a_classifier_that_names_a_real_thing_still_counts(self):
        self.assertEqual(self._values("共三筆交易"), ["3"])
        self.assertEqual(self._values("為期兩年"), ["2"])
        self.assertEqual(self._values("五家廠商投標"), ["5"])
        # 個月 is a unit of time; longest-match keeps it out of the carve-out.
        self.assertEqual(
            _extract_numbers_with_unit("歷時三個月"), [("3", "個月")]
        )

    def test_the_digit_form_is_a_figure_and_stays_checked(self):
        # The carve-out reads the numeral's spelling, not the classifier alone:
        # an author writing a measured count writes it in digits.
        self.assertEqual(_extract_numbers_with_unit("6 個價格帶"), [("6", "個")])
        self.assertEqual(self._values("六個價格帶"), [])

    def test_a_bound_the_sentence_sets_is_not_a_value_it_read(self):
        # The evidence side has always treated "<0.01" as a limit rather than a
        # reading. 「沒有一個超過 15%」 asserts a ceiling the author chose; the data
        # never states 15%, and it does not need to.
        for text in (
            "其餘七個品類沒有一個超過 15%",
            "不超過 15% 的商品有品牌",
            "價格多在 250 美元以下",
            "至少 50 則評論才看得到轉換",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._values(text), [])

    def test_the_same_figure_stated_plainly_is_still_a_reading(self):
        self.assertEqual(self._values("該帶佔 15%"), ["15"])
        self.assertEqual(self._values("價格中位數 250 美元"), ["250"])

    def test_a_number_after_a_chinese_comma_is_visible(self):
        # NFKC folds U+FF0C to ASCII ",", and the thousands-separator lookbehind
        # then swallowed the figure -- in the most common position a number
        # occupies in Chinese prose.
        self.assertEqual(
            self._values("共 544 筆商品列，其中 119 筆沒有價格"), ["544", "119"]
        )
        self.assertEqual(self._values("共 1,234 筆"), ["1,234"])

    def test_corner_brackets_are_quotation_only_after_a_reporting_verb(self):
        from report_workflow.nodes.factuality_check import (
            _QUOTED_PHRASE_RE,
            _REPORTED_SPEECH_RE,
        )

        emphasis = "這個數字應讀成「只有原廠周邊會掛品牌」"
        self.assertEqual(_QUOTED_PHRASE_RE.findall(emphasis), [])
        self.assertEqual(_REPORTED_SPEECH_RE.findall(emphasis), [])

        reported = "一則評論寫道「連線常常斷掉」"
        self.assertEqual(_REPORTED_SPEECH_RE.findall(reported), ["連線常常斷掉"])

        # Every other quotation mark keeps its old meaning.
        self.assertEqual(
            [next(g for g in m if g)
             for m in _QUOTED_PHRASE_RE.findall('the paper says "compiles ASTs" here')],
            ["compiles ASTs"],
        )


class NumbersNeitherInventedNorLostTests(unittest.TestCase):
    """The fullwidth comma, twice, in opposite directions.

    NFKC folds U+FF0C to an ASCII comma, and two separate mechanisms then read
    it as a thousands separator. The first suppressed every figure written after
    one -- the most common position a number occupies in Chinese prose. The fix
    for that left the second: the thousands branch still matched *across* it, so
    two separately grounded figures either side of a clause break became one
    number that appears in no source because it does not exist.

    Fabricating a figure is the worse of the two. A suppressed number blocks a
    true sentence and the author notices; an invented one is reported as the
    author's own claim.
    """

    def _values(self, text: str) -> list[str]:
        return [number for number, _unit in _extract_numbers_with_unit(text)]

    def test_a_clause_break_is_not_a_thousands_separator(self):
        # 「跳升至 327，500-1,000 為 317」 states 327, then a new clause about the
        # 500-1,000 band, then 317. It came out as the single figure 327,500.
        self.assertEqual(
            self._values("跳升至 327，500–1,000 為 317"),
            ["327", "500", "1,000", "317"],
        )

    def test_a_real_thousands_separator_still_reads_as_one_number(self):
        self.assertEqual(self._values("共 1,234 筆"), ["1,234"])
        self.assertEqual(self._values("價格 12,345.67 美元"), ["12,345.67"])

    def test_a_number_after_a_clause_break_is_still_visible(self):
        self.assertEqual(
            self._values("共 544 筆商品列，其中 119 筆沒有價格"), ["544", "119"]
        )

    def test_a_limiting_phrase_makes_one_mean_a_single_one(self):
        # 「低分並非只有一家」 is "not just one brand". 家 counts real companies
        # elsewhere, so the classifier cannot be carved out wholesale -- what
        # marks the idiom is the phrase in front of it.
        for text in ("低分並非只有一家：MOCVOO 也是", "只有一家廠商達標", "不只一家"):
            with self.subTest(text=text):
                self.assertEqual(self._values(text), [])

    def test_counting_companies_still_counts(self):
        self.assertEqual(self._values("五家廠商投標"), ["5"])
        self.assertEqual(self._values("併購了一家公司"), ["1"])


if __name__ == "__main__":
    unittest.main()
