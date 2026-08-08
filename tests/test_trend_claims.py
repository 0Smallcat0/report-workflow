"""Can a report read a trend out of a table that does not have one?

Every other factuality checker compares text with text. FE asks whether the
claim's numbers are in the evidence; FS asks whether the prose repeats the
claim's numbers. Both pass a sentence built entirely from real figures that
tells the reader something the figures do not say.

That is not a hypothetical either. A blind judge reading four relabelled
reports against a fixed rubric found it in the one this pipeline produced:
「銷量級距愈高的組別，價格中位數也愈高」, citing a fifteen-row sales-tier
table and quoting two of its rows. Over all fifteen tiers the three
highest-volume groups carry the three lowest prices. Both quoted numbers were
real and present in the cited evidence, so every gate passed it.

The table below is that table, kept as it was computed. What is measured here
is the checker built for it — and, in the cases that must not fire, the cost
of building it.
"""
import unittest

from report_workflow.nodes.factuality_check import run_factuality_check_ft


#: The sales-tier cross table the pipeline builds from amazon_products.csv,
#: as recorded. Categories, so the rows arrive ordered by group size and the
#: tier order has to be recovered from the labels.
SALES_TABLE = {
    "evidence_id": "E_sales",
    "table_grid": {
        "headers": ["sales", "掛牌數", "price 中位數", "review_count 中位數"],
        "rows": [
            ["100+ bought in past month", "46", "89.99 USD", "198.00"],
            ["50+ bought in past month", "34", "57.99 USD", "121.00"],
            ["200+ bought in past month", "22", "119.98 USD", "794.00"],
            ["500+ bought in past month", "16", "139.99 USD", "806.00"],
            ["400+ bought in past month", "12", "47.99 USD", "413.00"],
            ["1K+ bought in past month", "11", "41.36 USD", "776.50"],
            ["300+ bought in past month", "11", "236.00 USD", "327.00"],
            ["2K+ bought in past month", "5", "59.97 USD", "1,166.00"],
            ["3K+ bought in past month", "2", "214.49 USD", "1,796.50"],
            ["10K+ bought in past month", "1", "35.99 USD", "33,535.00"],
            ["合計", "160", "69.99 USD", "328.00"],
        ],
    },
    "derivation": {"grouping": "categories", "groups": 10, "group_by": "sales"},
}

#: Six price bands with a column that wanders — 25, 81, 67, 77, 102, 21 — while
#: its two ends agree with the pair an author would quote. The honest case the
#: checker has to leave alone.
PRICE_BAND_TABLE = {
    "evidence_id": "E_band",
    "table_grid": {
        "headers": ["價格帶 (USD)", "評論數", "商品數", "平均星等"],
        "rows": [
            ["0–30", "25", "4", "4.32"],
            ["30–50", "81", "10", "4.30"],
            ["50–100", "67", "11", "4.28"],
            ["100–200", "77", "11", "4.09"],
            ["200–500", "102", "12", "4.66"],
            ["500+", "21", "2", "4.52"],
            ["合計", "373", "50", "4.36"],
        ],
    },
    "derivation": {"grouping": "buckets", "groups": 6, "group_by": "price"},
}

#: The seven price bands of the supply table, as computed. Its 平均星等 column
#: dips through the middle and comes out higher than it went in, which is what
#: makes a pair quoted from the middle of it unrepresentative.
SUPPLY_BAND_TABLE = {
    "evidence_id": "E_supply",
    "table_grid": {
        "headers": ["價格帶 (USD)", "掛牌數", "平均星等", "累積評論中位數"],
        "rows": [
            ["0–30", "99", "4.24", "24.00"],
            ["30–50", "80", "4.18", "106.00"],
            ["50–100", "63", "4.37", "22.00"],
            ["100–200", "64", "4.16", "63.00"],
            ["200–500", "53", "4.29", "327.00"],
            ["500–800", "13", "4.50", "321.00"],
            ["800+", "53", "4.45", "65.50"],
            ["合計", "425", "4.26", "51.50"],
        ],
    },
    "derivation": {"grouping": "buckets", "groups": 7, "group_by": "price"},
}

#: Brands. No order at all, so no trend over them is recomputable.
BRAND_TABLE = {
    "evidence_id": "E_brand",
    "table_grid": {
        "headers": ["brand", "掛牌數", "price 中位數"],
        "rows": [
            ["DJI", "92", "247.50 USD"],
            ["Holy Stone", "10", "89.99 USD"],
            ["Contixo", "8", "129.99 USD"],
            ["Potensic", "7", "99.99 USD"],
            ["合計", "117", "199.00 USD"],
        ],
    },
    "derivation": {"grouping": "categories", "groups": 4, "group_by": "brand"},
}


def matrix(claim_text: str, evidence_ids: list[str], claim_id: str = "c1") -> dict:
    return {"claims": [{
        "claim_id": claim_id,
        "claim_text": claim_text,
        "claim_type": "statistical",
        "status": "supported",
        "evidence_ids": evidence_ids,
    }]}


def draft(prose: str, evidence_ids: list[str]) -> str:
    cites = " ".join(f"[CITE:{eid}]" for eid in evidence_ids)
    return f"{prose} {cites}\n"


#: The claim as it was written and shipped: two of fifteen rows, quoted
#: accurately, generalised into a direction.
RECORDED_CLAIM = (
    "帶銷量欄位的掛牌裡，500+ bought in past month 這一組 16 件的 price 中位數 "
    "139.99 USD、累積評論中位數 806.00，而 100+ 那一組 46 件的 price 中位數 "
    "89.99 USD、累積評論中位數只有 198.00。"
)
RECORDED_PROSE = "銷量級距愈高的組別，價格中位數也愈高——這與「低價帶才走量」的直覺相反。"


class RecordedDefectTests(unittest.TestCase):
    """The claim that passed every gate must not pass this one."""

    def _run(self, prose=RECORDED_PROSE, claim=RECORDED_CLAIM, tables=(SALES_TABLE,)):
        ids = [table["evidence_id"] for table in tables]
        return run_factuality_check_ft(
            draft(f"{claim} {prose}", ids), matrix(claim, ids), list(tables)
        )

    def test_blocks_the_claim_the_judge_found(self):
        results = self._run()
        blocked = [row for row in results if row["status"] == "blocked"]
        self.assertEqual(len(blocked), 1, results)
        self.assertEqual(blocked[0]["checker"], "FT")

    def test_reason_names_the_column_and_prints_the_real_ordering(self):
        reason = self._run()[0]["reason"]
        self.assertIn("price 中位數", reason)
        # The tiers the claim did not show, in tier order, with their prices.
        self.assertIn("50+ 57.99", reason)
        self.assertIn("10K+ 35.99", reason)
        self.assertIn("2 of 10", reason)

    def test_the_column_that_does_rise_is_not_blocked(self):
        """Same table, same pair of groups, the other column.

        review_count median really does climb with the sales tier. A checker
        that fired here would be refusing the true half of the sentence along
        with the false half, and the author would have no way to tell which.
        """
        claim = (
            "500+ bought in past month 這一組的累積評論中位數 806.00，"
            "而 100+ 那一組只有 198.00。"
        )
        results = self._run(claim=claim)
        self.assertEqual([row["status"] for row in results], ["verified"])

    def test_no_direction_asserted_is_not_checked(self):
        """Two values reported side by side assert nothing to recompute."""
        results = self._run(prose="兩組的價差說明這個貨架不是一個價格層。")
        self.assertEqual(results, [])

    def test_one_named_group_is_not_a_pair(self):
        """And a claim the checker stood down on is reported as neither."""
        claim = "500+ bought in past month 這一組 16 件的 price 中位數是 139.99 USD。"
        self.assertEqual(self._run(claim=claim), [])


class HonestTrendTests(unittest.TestCase):
    """What the checker must not cost.

    A first cut blocked on a bare majority of discordant group pairs. Run
    against one authored report it took out six claims whose prose never
    generalised about the column it flagged — the tables were simply noisy.
    Requiring the two ends to disagree as well left exactly the one real
    finding. These are the cases that difference protects.
    """

    def test_noisy_column_with_agreeing_ends_is_left_alone(self):
        claim = "0–30 有 25 則評論、4 件商品；500+ 只有 21 則評論、2 件商品。"
        prose = "評論數隨價格帶上升而變薄，這個反向關係是這份資料裡最強的結構訊號。"
        ids = ["E_band"]
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ids), matrix(claim, ids), [PRICE_BAND_TABLE]
        )
        self.assertEqual([row["status"] for row in results], ["verified"], results)

    def test_unordered_categories_stand_the_checker_down(self):
        """A trend over brand names is not arithmetic this tool can redo.

        Refusing the sentence anyway would be blocking honest work over a
        limitation of the checker, which is the failure mode this repository
        spent a release removing.
        """
        claim = "DJI 92 件的 price 中位數 247.50 USD，Holy Stone 10 件是 89.99 USD。"
        prose = "掛牌數愈多的品牌，價格中位數也愈高。"
        ids = ["E_brand"]
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ids), matrix(claim, ids), [BRAND_TABLE]
        )
        self.assertEqual(results, [])

    def test_a_neighbours_trend_sentence_does_not_convict_this_claim(self):
        """The failure that showed up in one of five acceptance reports.

        Draft paragraphs are matched to a claim by the `[CITE:]` markers in
        them, so two claims citing the same table share each other's prose. A
        version of this checker that took the quoted pair from that shared text
        hard-blocked a correct report: the direction came from the neighbour,
        and the claim's 63 and 64 matched two cells of a column it never
        discussed — one a review-count median, the other a listing count.

        The pair now has to be named in the claim itself.
        """
        claim = "100–200 這一帶共 64 筆，評論數中位數 63，低於四星比率是七帶最高。"
        neighbour = "低評率並不隨價格單調下降，100–200 反而高於 0–30。"
        merged = draft(claim, ["E_supply"]) + "\n" + draft(neighbour, ["E_supply"])
        results = run_factuality_check_ft(merged, matrix(claim, ["E_supply"]),
                                          [SUPPLY_BAND_TABLE])
        self.assertEqual(results, [])

    def test_a_grid_that_does_not_say_how_many_rows_are_groups_is_declined(self):
        """Read one row too long, a band table has 合計 for its top end.

        The ends test turns on that value, so a caller-supplied grid without a
        group count is left alone rather than reordered on a guess.
        """
        table = dict(SUPPLY_BAND_TABLE, evidence_id="E_nogroups",
                     derivation={"grouping": "buckets", "group_by": "price"})
        claim = "30–50 這一帶平均星等 4.18，100–200 掉到 4.16。"
        prose = "價格帶愈高，平均星等愈低。"
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ["E_nogroups"]),
            matrix(claim, ["E_nogroups"]), [table],
        )
        self.assertEqual(results, [])

    def test_evidence_without_a_computed_table_is_not_checked(self):
        claim = "全樣本 544 筆掛牌中攝影佔 44.67%。"
        prose = "品類愈大，掛牌愈多。"
        plain = {"evidence_id": "E_plain", "content": "544 筆掛牌，攝影 243 筆。"}
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ["E_plain"]), matrix(claim, ["E_plain"]), [plain]
        )
        self.assertEqual(results, [])


class BucketOrderingTests(unittest.TestCase):
    """Bands carry their own order; the checker must use it.

    Bucket labels are not magnitudes it can parse — "0–30" and "500+" order by
    where the derivation put them, not by the number in front. The row order
    is the band order, and the derivation says how many rows are bands rather
    than the total underneath them.
    """

    def test_a_pair_from_the_middle_of_the_bands_is_blocked(self):
        """30–50 at 4.18 and 100–200 at 4.16 read as a decline.

        The direction comes from the two cells the claim wrote down, not from
        the words around them — a sentence can call a rise a fall and FE will
        not notice, but the pair it quotes is unambiguous. Over all seven bands
        the rating comes out at 4.45 having started at 4.24, and fifteen of the
        twenty-one ordered band pairs go up rather than down.
        """
        claim = "30–50 這一帶平均星等 4.18，100–200 掉到 4.16。"
        prose = "價格帶愈高，平均星等愈低。"
        ids = ["E_supply"]
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ids), matrix(claim, ids), [SUPPLY_BAND_TABLE]
        )
        blocked = [row for row in results if row["status"] == "blocked"]
        self.assertEqual(len(blocked), 1, results)
        self.assertIn("平均星等", blocked[0]["reason"])
        self.assertIn("0–30 4.24", blocked[0]["reason"])

    def test_the_total_row_is_not_a_band(self):
        """合計 sits below the bands and would flatten any ordering.

        Excluded by the derivation's group count rather than by matching its
        label, so a group legitimately named "All" is still a group.
        """
        claim = "0–30 有 25 則評論，200–500 有 102 則。"
        prose = "價格帶愈高，評論數愈多。"
        ids = ["E_band"]
        results = run_factuality_check_ft(
            draft(f"{claim} {prose}", ids), matrix(claim, ids), [PRICE_BAND_TABLE]
        )
        reason = " ".join(row.get("reason", "") for row in results)
        self.assertNotIn("373", reason)


if __name__ == "__main__":
    unittest.main()
