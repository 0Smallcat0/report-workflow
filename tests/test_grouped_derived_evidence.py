"""Aggregation the tool performs, instead of aggregation the author registers.

Every scalar operation answers one question, so a six-band table with three
columns cost eighteen registrations. A real run spent 117 of them to produce
three tables, and the report that came out had 238 numbers in it against 703
in an unassisted write-up of the same files. The shape of the request was the
cost, not the analysis.

So: one request returns a whole grid, two files can be joined before it is
grouped, and the obvious crossings are computed at intake without anybody
asking. What is measured here is the arithmetic in each cell, the provenance
that travels with it, and the fault that stranded an earlier run — a ledger
whose bytes moved on every rerun, which made every artifact stamped against it
stale and left nothing publishable.
"""
import json
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

from report_workflow.derived_evidence import (
    build_requested_units,
    dataset_summary_units,
    join_datasets,
    structured_datasets,
)
from report_workflow.nodes.source_tables import (
    collect_source_tables,
    replace_table_placeholders,
)

CREATED_AT = datetime(2026, 8, 7, tzinfo=timezone.utc).isoformat()

#: Six listings whose prices straddle three bands, so a band table has
#: something to say in every row and the arithmetic is checkable by hand.
PRODUCTS = [
    {"asin": "A1", "brand": "DJI", "price": "$20.00", "rating": "4.5", "category": "camera"},
    {"asin": "A2", "brand": "DJI", "price": "$25.00", "rating": "3.0", "category": "camera"},
    {"asin": "A3", "brand": "Autel", "price": "$60.00", "rating": "4.0", "category": "camera"},
    {"asin": "A4", "brand": "Autel", "price": "$80.00", "rating": "5.0", "category": "racing"},
    {"asin": "A5", "brand": "Ryze", "price": "$150.00", "rating": "3.5", "category": "racing"},
    {"asin": "A6", "brand": "Ryze", "price": "", "rating": "4.0", "category": "racing"},
]

REVIEWS = [
    {"review_id": "R1", "asin": "A1", "review_rating": "5.0"},
    {"review_id": "R2", "asin": "A1", "review_rating": "3.0"},
    {"review_id": "R3", "asin": "A5", "review_rating": "2.0"},
    {"review_id": "R4", "asin": "ZZ", "review_rating": "1.0"},
]


def _source(source_id: str, file_name: str, rows: list[dict]) -> dict:
    return {
        "source_id": source_id,
        "file_name": file_name,
        "file_path": file_name,
        "file_type": "csv",
        "parsed_content": [
            {"block_type": "csv_row", "content": json.dumps(row, ensure_ascii=False)}
            for row in rows
        ],
    }


REGISTRY = [
    _source("s1", "products.csv", PRODUCTS),
    _source("s2", "reviews.csv", REVIEWS),
]


def _only(units: list[dict], evidence_id: str) -> dict:
    matches = [unit for unit in units if unit["evidence_id"] == evidence_id]
    assert len(matches) == 1, f"{evidence_id}: {[u['evidence_id'] for u in units]}"
    return matches[0]


def _cells(unit: dict) -> dict[str, list[str]]:
    return {row[0]: row[1:] for row in unit["table_grid"]["rows"]}


class OneRequestReturnsATableTests(unittest.TestCase):
    def _band_table(self) -> dict:
        units, problems = build_requested_units(
            [{
                "id": "band",
                "source": "products.csv",
                "label": "Price band against rating",
                "group_by": {"column": "price", "buckets": [0, 50, 100], "label": "Band"},
                "measures": [
                    {"op": "count", "label": "Listings"},
                    {"op": "mean", "column": "rating", "label": "Mean rating"},
                    {"op": "share", "rows": "rating < 4", "label": "Under four"},
                    {"op": "share", "label": "Share of catalogue"},
                ],
            }],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        return _only(units, "E_D_band")

    def test_one_registration_produces_every_band(self):
        unit = self._band_table()
        cells = _cells(unit)
        # 0-50 holds A1 and A2, 50-100 holds A3 and A4, 100+ holds A5. A6 has
        # no price and is reported as ungrouped rather than dropped in silence.
        self.assertEqual(
            [row[0] for row in unit["table_grid"]["rows"]],
            ["0–50", "50–100", "100+", "All"],
        )
        self.assertEqual(cells["0–50"][0], "2")
        self.assertEqual(cells["50–100"][0], "2")
        self.assertEqual(cells["100+"][0], "1")
        self.assertEqual(unit["derivation"]["rows_ungrouped"], 1)

    def test_each_cell_is_the_arithmetic_over_its_own_group(self):
        cells = _cells(self._band_table())
        self.assertEqual(cells["0–50"][1], "3.75")    # (4.5 + 3.0) / 2
        self.assertEqual(cells["50–100"][1], "4.50")  # (4.0 + 5.0) / 2
        self.assertEqual(cells["100+"][1], "3.50")

    def test_a_filtered_share_is_a_rate_inside_the_group(self):
        cells = _cells(self._band_table())
        self.assertEqual(cells["0–50"][2], "50.00%")   # A2 of {A1, A2}
        self.assertEqual(cells["50–100"][2], "0.00%")
        self.assertEqual(cells["100+"][2], "100.00%")

    def test_an_unfiltered_share_is_the_group_against_the_whole(self):
        # Taken against its own group this is 100% in every row, which is a
        # column of noise; the only reading that says anything is the group's
        # weight in the selection.
        cells = _cells(self._band_table())
        self.assertEqual(cells["0–50"][3], "33.33%")   # 2 of 6
        self.assertEqual(cells["100+"][3], "16.67%")

    def test_the_content_states_every_cell_so_a_gate_can_find_it(self):
        content = self._band_table()["content"]
        for value in ("3.75", "4.50", "50.00%", "0–50", "100+"):
            self.assertIn(value, content)

    def test_a_categorical_column_needs_no_buckets(self):
        units, problems = build_requested_units(
            [{
                "id": "mix",
                "source": "products.csv",
                "group_by": {"column": "category"},
                "measures": [{"op": "count"}, {"op": "median", "column": "price"}],
            }],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        cells = _cells(_only(units, "E_D_mix"))
        self.assertEqual(cells["camera"][0], "3")
        self.assertEqual(cells["racing"][0], "3")

    def test_bucket_edges_are_the_authors_and_are_checked(self):
        _units, problems = build_requested_units(
            [{
                "id": "bad",
                "source": "products.csv",
                "group_by": {"column": "price", "buckets": [100, 50]},
                "measures": [{"op": "count"}],
            }],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("increase", problems[0]["error"])

    def test_a_grouped_request_without_measures_says_so(self):
        _units, problems = build_requested_units(
            [{"id": "nope", "source": "products.csv",
              "group_by": {"column": "category"}}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("measures", problems[0]["error"])

    def test_the_derivation_records_how_each_column_was_built(self):
        derivation = self._band_table()["derivation"]
        self.assertEqual(derivation["method"], "group_table")
        self.assertEqual(derivation["group_by"], "price")
        self.assertEqual(derivation["buckets"], [0.0, 50.0, 100.0])
        self.assertEqual(
            [measure["op"] for measure in derivation["measures"]],
            ["count", "mean", "share", "share"],
        )


class JoinedSourcesTests(unittest.TestCase):
    def _joined(self) -> dict:
        units, problems = build_requested_units(
            [{
                "id": "band_reviews",
                "source": ["reviews.csv", "products.csv"],
                "join": {"on": "asin", "how": "inner"},
                "group_by": {"column": "price", "buckets": [0, 50, 100]},
                "measures": [
                    {"op": "count", "label": "Reviews"},
                    {"op": "mean", "column": "review_rating", "label": "Mean stars"},
                ],
            }],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        return _only(units, "E_D_band_reviews")

    def test_a_figure_neither_file_states_becomes_available(self):
        # Price lives in products, the star rating lives in reviews, and "what
        # do buyers say about each price band" lives in neither.
        cells = _cells(self._joined())
        self.assertEqual(cells["0–50"][0], "2")
        self.assertEqual(cells["0–50"][1], "4.00")   # (5.0 + 3.0) / 2
        self.assertEqual(cells["100+"][1], "2.00")

    def test_rows_that_find_no_partner_are_counted_not_swallowed(self):
        unit = self._joined()
        join = unit["derivation"]["join"]
        self.assertEqual(join["left_unmatched"], 1)    # R4 names no listing
        self.assertEqual(join["joined_rows"], 3)
        self.assertEqual(join["right_unmatched"], 4)   # A2, A3, A4, A6
        self.assertIn("found no partner", unit["content"])

    def test_a_column_present_in_both_files_is_renamed_not_overwritten(self):
        datasets = {dataset.file_name: dataset for dataset in structured_datasets(REGISTRY)}
        frame = join_datasets(
            datasets["reviews.csv"], datasets["products.csv"], {"on": "asin"}
        )
        self.assertEqual(frame.join_info["renamed_columns"], {})
        self.assertIn("price", frame.columns)

        other = structured_datasets([_source("s3", "extra.csv", [
            {"asin": "A1", "rating": "1.0"}, {"asin": "A5", "rating": "2.0"},
        ])])[0]
        collided = join_datasets(datasets["products.csv"], other, {"on": "asin"})
        self.assertEqual(
            collided.join_info["renamed_columns"], {"rating": "rating__extra"}
        )
        first = collided.rows[0]
        self.assertEqual(first["rating"], "4.5")        # the left file's value
        self.assertEqual(first["rating__extra"], "1.0")

    def test_two_sources_without_a_join_are_refused(self):
        _units, problems = build_requested_units(
            [{"id": "x", "source": ["reviews.csv", "products.csv"],
              "group_by": {"column": "price", "buckets": [0, 50]},
              "measures": [{"op": "count"}]}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("join", problems[0]["error"])

    def test_only_inner_joins_are_offered(self):
        _units, problems = build_requested_units(
            [{"id": "x", "source": ["reviews.csv", "products.csv"],
              "join": {"on": "asin", "how": "left"},
              "group_by": {"column": "price", "buckets": [0, 50]},
              "measures": [{"op": "count"}]}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("inner", problems[0]["error"])


class CrossTablesNobodyAskedForTests(unittest.TestCase):
    def test_each_category_column_is_crossed_with_the_numeric_ones(self):
        tables = [
            unit for unit in dataset_summary_units(REGISTRY, CREATED_AT)
            if unit.get("table_grid")
        ]
        crossed = {unit["derivation"]["group_by"] for unit in tables}
        self.assertIn("category", crossed)
        self.assertIn("brand", crossed)
        by_category = next(
            unit for unit in tables if unit["derivation"]["group_by"] == "category"
        )
        headers = by_category["table_grid"]["headers"]
        self.assertIn("rows", headers)
        self.assertTrue(any("rating" in header for header in headers))

    def test_an_automatic_table_never_invents_a_numeric_band(self):
        # Where to cut a price axis is the finding, not an input to it.
        for unit in dataset_summary_units(REGISTRY, CREATED_AT):
            self.assertNotEqual(unit["derivation"].get("grouping"), "buckets")

    def test_who_asked_is_recorded_so_the_manual_burden_can_be_counted(self):
        auto = dataset_summary_units(REGISTRY, CREATED_AT)
        self.assertTrue(all(unit["origin"] == "auto" for unit in auto))
        requested, _problems = build_requested_units(
            [{"id": "n", "source": "products.csv", "op": "count"}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual([unit["origin"] for unit in requested], ["requested"])


class DerivedTablesReachTheDocumentTests(unittest.TestCase):
    def _units(self) -> list[dict]:
        units, problems = build_requested_units(
            [{"id": "band", "source": "products.csv",
              "group_by": {"column": "price", "buckets": [0, 50, 100]},
              "measures": [{"op": "count"}]}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        return units

    def test_a_grouped_table_is_placeable_with_a_table_marker(self):
        units = self._units()
        tables = collect_source_tables(units)
        # The evidence id always works; the author's own id is the name they
        # will reach for, so it resolves too when nothing else claims it.
        self.assertIn("E_D_band", tables)
        self.assertIn("band", tables)

        markdown, placed, unresolved = replace_table_placeholders(
            "Prices split as follows.\n\n[TABLE:band Price bands]\n", units
        )
        self.assertEqual((placed, unresolved), (1, []))
        self.assertIn("| 0–50 |", markdown)
        self.assertIn("Table 1. Price bands", markdown)

    def test_the_placed_table_carries_where_its_numbers_came_from(self):
        markdown, _placed, _unresolved = replace_table_placeholders(
            "[TABLE:band]", self._units()
        )
        self.assertIn("Source: products.csv", markdown)


class LedgerBytesStayPutTests(unittest.TestCase):
    """The regression that had no test.

    ``created_at`` was regenerated on every run, so every derived line changed,
    so the ledger hash changed, so every artifact stamped against it was stale
    — and no run that had registered a derivation could publish. It was fixed
    by carrying the first-seen timestamp forward, and nothing guarded the fix.
    """

    def test_registering_the_same_derivations_twice_leaves_the_ledger_alone(self):
        from report_workflow.nodes.derived_evidence import apply_derived_evidence

        requests = [
            {"id": "n", "source": "products.csv", "op": "count"},
            {"id": "band", "source": "products.csv",
             "group_by": {"column": "price", "buckets": [0, 50, 100]},
             "measures": [{"op": "count"}, {"op": "mean", "column": "rating"}]},
        ]
        with tempfile.TemporaryDirectory() as workspace:
            run_dir = Path(workspace) / "job"
            run_dir.mkdir()
            (run_dir / "derived_evidence.json").write_text(
                json.dumps({"derivations": requests}), encoding="utf-8"
            )
            ledger = run_dir / "evidence_ledger.jsonl"
            ledger.write_text("", encoding="utf-8")

            class _State:
                job_id = "job"
                spec = {"user_prompt": "write a market report"}
                sources = {
                    "evidence_ledger_path": str(ledger),
                    "source_registry": REGISTRY,
                }

            with unittest.mock.patch(
                "report_workflow.nodes.derived_evidence.WORKFLOW_RUNS_DIR",
                Path(workspace),
            ):
                apply_derived_evidence(_State())
                first = ledger.read_bytes()
                apply_derived_evidence(_State())
                second = ledger.read_bytes()

        self.assertTrue(first, "the ledger should not be empty")
        self.assertEqual(first, second)


class BrickLayingIsRefusedTests(unittest.TestCase):
    """The grouped form existing was not enough to get it used.

    Two acceptance runs registered 22 and then 47 derivations against the same
    three files. The second was 41 scalars and 6 tables, and six of those
    scalars were mean-and-negative-rate across three price bands: a two by
    three table, spelled out. Nothing was wrong with any single request, which
    is exactly why nothing stopped it — every one returns a working number, and
    the author never finds out the table was one call away.
    """

    def _problems(self, requests: list[dict]) -> dict[str, str]:
        _units, problems = build_requested_units(requests, REGISTRY, CREATED_AT)
        return {problem["id"]: problem["error"] for problem in problems}

    def test_the_same_shape_three_times_over_is_one_table(self):
        problems = self._problems([
            {"id": "low", "source": "products.csv", "op": "mean",
             "column": "rating", "rows": "price<50"},
            {"id": "mid", "source": "products.csv", "op": "mean",
             "column": "rating", "rows": "price>=50 & price<100"},
            {"id": "high", "source": "products.csv", "op": "mean",
             "column": "rating", "rows": "price>=100"},
        ])
        self.assertEqual(sorted(problems), ["high", "low", "mid"])
        message = problems["low"]
        self.assertIn("group_by", message)
        self.assertIn('"column": "price"', message)
        # A numeric slice needs edges the author picks; the refusal says so
        # rather than choosing them.
        self.assertIn("buckets", message)

    def test_the_refusal_carries_the_request_that_replaces_it(self):
        problems = self._problems([
            {"id": "a", "source": "products.csv", "op": "count", "rows": "category=camera"},
            {"id": "b", "source": "products.csv", "op": "count", "rows": "category=racing"},
            {"id": "c", "source": "products.csv", "op": "count", "rows": "category=toy"},
        ])
        replacement = json.loads(
            problems["a"][problems["a"].index("{"):problems["a"].rindex("}") + 1]
        )
        self.assertEqual(replacement["group_by"], {"column": "category"})
        self.assertEqual(replacement["measures"], [{"op": "count"}])
        # A categorical grouping needs no edges, and the message must not
        # invent any.
        self.assertNotIn("buckets", problems["a"])
        _units, _problems = build_requested_units(
            [{**replacement, "id": "mix"}], REGISTRY, CREATED_AT
        )
        self.assertEqual(_problems, [])

    def test_two_of_a_shape_is_a_comparison_not_a_table(self):
        self.assertEqual(self._problems([
            {"id": "a", "source": "products.csv", "op": "count", "rows": "category=camera"},
            {"id": "b", "source": "products.csv", "op": "count", "rows": "category=racing"},
        ]), {})

    def test_unrelated_scalars_are_left_alone(self):
        self.assertEqual(self._problems([
            {"id": "n", "source": "products.csv", "op": "count"},
            {"id": "hhi", "source": "products.csv", "op": "hhi", "column": "brand"},
            {"id": "med", "source": "products.csv", "op": "median", "column": "price"},
            {"id": "one", "source": "products.csv", "op": "max",
             "column": "price", "rows": "brand=DJI"},
        ]), {})


class TheBriefLeadsWithTheBuiltTablesTests(unittest.TestCase):
    def test_ready_tables_are_listed_before_the_column_summaries(self):
        from report_workflow.nodes.agent_tasks import _derived_stats_guidance

        with tempfile.TemporaryDirectory() as workspace:
            ledger = Path(workspace) / "evidence_ledger.jsonl"
            ledger.write_text(
                "\n".join(
                    json.dumps(unit, ensure_ascii=False)
                    for unit in dataset_summary_units(REGISTRY, CREATED_AT)
                ) + "\n",
                encoding="utf-8",
            )
            guidance = _derived_stats_guidance(str(ledger))

        tables_at = guidance.index("Tables already built and ready to place")
        summaries_at = guidance.index("Single-column summaries computed at intake")
        self.assertLess(tables_at, summaries_at)
        # The marker to place one has to be in the section, or the author has
        # a list of tables and no way to use them.
        self.assertIn("[TABLE:", guidance[tables_at:summaries_at])


if __name__ == "__main__":
    unittest.main()
