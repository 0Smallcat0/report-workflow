"""Writing a report from raw data, which is what the tool is mostly used for.

Every positive measurement this project had was taken by feeding it a report
someone had already written. Fed three CSVs instead — 544 products, 544
category rows, 473 reviews — it lost to an unassisted write-up of the same
files on every dimension but figure count: 26 numbers in the body against
703, no tables against thirteen, and a 402 KB DOCX of which the author's own
prose was 1.7%.

Three separate faults, one test file:

* the reference list was 1,071 product and thumbnail URLs read out of data
  columns;
* no ledger row stated a count, a median or a share, so no claim could cite
  one and the sentences needing them went unwritten;
* the content gate did not run on the publish path, and the number check that
  did run compared digit strings, so an unrelated review count "supported" a
  claim about the sample size.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from report_workflow.derived_evidence import (
    Dataset,
    DerivationError,
    build_requested_units,
    compute,
    dataset_summary_units,
    select_rows,
)
from report_workflow.nodes.cited_sources import extract_cited_sources
from report_workflow.nodes.factuality_check import run_factuality_check_fe

CREATED_AT = datetime(2026, 8, 6, tzinfo=timezone.utc).isoformat()

CATEGORIES = ["攝影", "競速", "玩具"]
COUNTS = [12, 6, 6]


def _product_rows() -> list[dict]:
    rows = []
    index = 0
    for category, count in zip(CATEGORIES, COUNTS):
        for _ in range(count):
            index += 1
            rows.append({
                "asin": f"B0{index:04d}",
                "brand": ["DJI", "Autel", "Ryze"][index % 3],
                "category": category,
                "price": f"${10 + index * 5}.99",
                "rating": f"{3 + index % 2}.1",
                "review_count": str(index * 7),
                "product_link": f"https://www.amazon.com/dp/B0{index:04d}",
                "image_url": f"https://m.media-amazon.com/images/I/{index}x.jpg",
            })
    return rows


def _registry(rows: list[dict]) -> list[dict]:
    return [{
        "source_id": "s1",
        "file_name": "products.csv",
        "file_path": "products.csv",
        "file_type": "csv",
        "parsed_content": [
            {
                "block_id": f"block_{index}",
                "block_type": "table_row",
                "content": json.dumps(row, ensure_ascii=False),
            }
            for index, row in enumerate(rows)
        ],
    }]


def _fe(claim_text: str, evidence: dict, claim_type: str = "statistical") -> dict:
    claim = {
        "claim_id": "c1",
        "claim_text": claim_text,
        "claim_type": claim_type,
        "evidence_ids": [evidence["evidence_id"]],
    }
    checked = [{"claim_id": "c1", "status": "verified", "checker": "FA", "reason": ""}]
    return run_factuality_check_fe(checked, {"claims": [claim]}, [evidence])[0]


def _row_evidence(record: dict) -> dict:
    return {
        "evidence_id": "e1",
        "content": json.dumps(record, ensure_ascii=False),
        "block_type": "table_row",
        "evidence_type": "quantitative",
        "allowed_claim_types": ["factual", "statistical"],
        "source_role": "primary_source",
    }


class DataColumnsAreNotCitationsTests(unittest.TestCase):
    """A cell is a fact about one record, not a source the document read."""

    def test_a_product_export_cites_nothing(self):
        self.assertEqual(extract_cited_sources(_registry(_product_rows())), [])

    def test_a_named_column_is_read_and_its_neighbours_are_not(self):
        registry = _registry([{
            "source_url": "https://www.oecd.org/env/outlook.pdf",
            "product_link": "https://www.amazon.com/dp/B0001",
            "image_url": "https://m.media-amazon.com/images/I/1.jpg",
        }] * 2)
        found = extract_cited_sources(registry, ["source_url"])
        self.assertEqual(
            [row["url"] for row in found], ["https://www.oecd.org/env/outlook.pdf"]
        )

    def test_a_thumbnail_is_never_a_reference_even_in_prose(self):
        registry = [{
            "source_id": "s2",
            "file_name": "notes.md",
            "file_type": "md",
            "parsed_content": [{
                "block_id": "m1",
                "content": (
                    "見 [報告](https://www.oecd.org/a) 、"
                    "https://m.media-amazon.com/images/I/71.jpg 與 "
                    "https://example.org/chart.png"
                ),
            }],
        }]
        self.assertEqual(
            [row["url"] for row in extract_cited_sources(registry)],
            ["https://www.oecd.org/a"],
        )

    def test_prose_citations_still_reach_the_registry(self):
        """The behaviour this must not undo: a report's own sources."""
        registry = [{
            "source_id": "s3",
            "file_name": "market.md",
            "file_type": "md",
            "parsed_content": [
                {
                    "block_id": f"m{index}",
                    "content": f"見 https://house{index}.example.org/report",
                }
                for index in range(39)
            ],
        }]
        self.assertEqual(len(extract_cited_sources(registry)), 39)


class StatisticsAreEvidenceTests(unittest.TestCase):
    """The ledger has to be able to answer what the report asks."""

    def setUp(self):
        self.rows = _product_rows()
        self.registry = _registry(self.rows)
        self.dataset = Dataset(self.registry[0], self.rows)

    def test_summary_units_state_the_sample_size_and_the_quartiles(self):
        joined = " ".join(
            unit["content"]
            for unit in dataset_summary_units(self.registry, CREATED_AT, zh=True)
        )
        self.assertIn("24", joined)
        self.assertIn("中位數", joined)
        self.assertIn("攝影 12 筆", joined)
        self.assertIn("HHI", joined)

    def test_every_summary_unit_records_how_it_was_derived(self):
        for unit in dataset_summary_units(self.registry, CREATED_AT):
            with self.subTest(evidence_id=unit["evidence_id"]):
                derivation = unit["derivation"]
                self.assertIn(
                    derivation["method"],
                    {"row_count", "column_summary_stats", "group_counts", "group_table"},
                )
                self.assertEqual(derivation["source_file"], "products.csv")
                self.assertEqual(derivation["rows_total"], 24)
                self.assertTrue(derivation["input_columns"])

    def test_an_id_column_gets_no_statistics(self):
        joined = " ".join(
            str(unit["derivation"]["input_columns"])
            for unit in dataset_summary_units(self.registry, CREATED_AT)
            if unit["derivation"]["method"] != "row_count"
        )
        for column in ("asin", "image_url", "product_link"):
            self.assertNotIn(column, joined)

    def test_a_row_set_and_an_operation_is_citable(self):
        units, problems = build_requested_units(
            [{
                "id": "photo", "source": "products.csv", "rows": "category=攝影",
                "op": "count", "label": "攝影類商品數",
            }],
            self.registry, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        self.assertEqual(units[0]["evidence_id"], "E_D_photo")
        self.assertIn("12", units[0]["content"])
        self.assertEqual(units[0]["derivation"]["row_filter"], "category=攝影")

    def test_a_claim_citing_the_row_set_count_passes(self):
        units, _problems = build_requested_units(
            [{
                "id": "photo", "source": "products.csv", "rows": "category=攝影",
                "op": "count", "label": "攝影類商品數",
            }],
            self.registry, CREATED_AT, zh=True,
        )
        result = _fe("攝影類共 12 筆。", units[0])
        self.assertEqual(result["status"], "verified", result.get("reason"))

    def test_an_author_computed_figure_is_recomputed_not_trusted(self):
        _units, problems = build_requested_units(
            [{
                "id": "hhi", "source": "products.csv", "op": "hhi",
                "column": "brand", "expect": 9999,
            }],
            self.registry, CREATED_AT,
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("9999", problems[0]["error"])

    def test_a_correct_author_computed_figure_is_accepted(self):
        computed = compute(self.dataset, {"op": "hhi", "column": "brand"})
        units, problems = build_requested_units(
            [{
                "id": "hhi", "source": "products.csv", "op": "hhi",
                "column": "brand", "expect": round(computed["value"], 2),
            }],
            self.registry, CREATED_AT,
        )
        self.assertEqual(problems, [])
        self.assertEqual(units[0]["derivation"]["method"], "hhi")

    def test_a_price_column_written_with_a_currency_sign_still_has_a_median(self):
        result = compute(self.dataset, {"op": "median", "column": "price"})
        self.assertEqual(result["unit"], "USD")
        self.assertGreater(result["value"], 0)

    def test_a_filter_naming_a_column_that_does_not_exist_says_so(self):
        with self.assertRaises(DerivationError) as caught:
            select_rows(self.dataset, "colour=紅")
        self.assertIn("colour", str(caught.exception))


class EvidenceMustSupportTheClaimTests(unittest.TestCase):
    """A matching digit is not support."""

    def test_an_unrelated_field_cannot_certify_a_sample_size(self):
        result = _fe(
            "本樣本共收錄 544 筆商品。",
            _row_evidence({"asin": "B0EXAMPLE1", "review_count": 544, "rating": 4.3}),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("single data row", result["reason"])

    def test_a_price_with_a_currency_prefix_is_readable(self):
        result = _fe(
            "該商品標價為 71.99 美元。",
            _row_evidence({"asin": "B0X", "price": "$71.99", "rating": 4.1}),
            claim_type="factual",
        )
        self.assertEqual(result["status"], "verified", result.get("reason"))

    def test_the_same_price_without_the_prefix_is_unaffected(self):
        result = _fe(
            "該商品標價為 71.99 美元。",
            _row_evidence({"asin": "B0X", "price": "71.99", "rating": 4.1}),
            claim_type="factual",
        )
        self.assertEqual(result["status"], "verified", result.get("reason"))

    def test_a_claim_naming_a_column_may_not_borrow_another_columns_number(self):
        result = _fe(
            "The price of this listing is 4.3.",
            _row_evidence({"asin": "B0X", "price": "$71.99", "rating": "4.3"}),
            claim_type="factual",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("rating", result["reason"])

    def test_a_derived_statistic_can_ground_a_dataset_claim(self):
        units = dataset_summary_units(_registry(_product_rows()), CREATED_AT, zh=True)
        shape = next(
            unit for unit in units if unit["derivation"]["method"] == "row_count"
        )
        result = _fe("本樣本共收錄 24 筆商品。", shape)
        self.assertEqual(result["status"], "verified", result.get("reason"))


class ReportedChecksMatchTheChecksRunTests(unittest.TestCase):
    """"Factuality: pass (44 verified)" described a run with no content check."""

    def test_the_factuality_report_names_its_checkers(self):
        from report_workflow.run_workflow import prepare_workflow, validate_workflow
        from report_workflow.state import WORKFLOW_RUNS_DIR

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "notes.md"
            source.write_text(
                "# 回收\n\n回收率可達 95%，主要受前處理雜質控制影響，各廠差距不小。\n",
                encoding="utf-8",
            )
            with patch(
                "report_workflow.preflight.importlib.util.find_spec",
                side_effect=lambda name, *a, **k: object(),
            ):
                state = prepare_workflow(
                    "分析回收經濟性", [str(source)], str(Path(tmpdir) / "out"),
                    report_profile="business_report",
                )
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            ledger = [
                json.loads(line)
                for line in (run_dir / "evidence_ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            row = next(item for item in ledger if "95" in item["content"])
            (run_dir / "claim_matrix.json").write_text(
                json.dumps({"claims": [
                    {
                        "claim_id": claim_id,
                        "claim_text": row["content"][:120],
                        "claim_type": "factual",
                        "risk_level": "low",
                        "status": "supported",
                        "evidence_ids": [row["evidence_id"]],
                        "requires_hedged_wording": True,
                        "claim_role": "primary" if claim_id == "c1" else "supporting",
                    }
                    # The counter-evidence section this blueprint requires needs
                    # claims of its own; it may not name the ones it carries.
                    for claim_id in ("c1", "c_limit_1", "c_limit_2")
                ]}, ensure_ascii=False),
                encoding="utf-8",
            )

            order = state.plan["blueprint"]["section_order"]
            claimless = {"references", "appendix"}

            def _section_claim_ids(section_id: str) -> list[str]:
                if section_id in claimless:
                    return []
                return ["c_limit_1", "c_limit_2"] if section_id == "limitations" else ["c1"]

            outline_sections = {
                section_id: {
                    "section_id": section_id,
                    "goals": f"cover {section_id}",
                    "claim_ids": _section_claim_ids(section_id),
                    "paragraph_order": ["context", "content", "conclusion"],
                    "figure_ids": [],
                }
                for section_id in order
            }
            if "limitations" in outline_sections:
                outline_sections["limitations"]["undermines"] = ["c1"]
            (run_dir / "outline.json").write_text(
                json.dumps({"sections": outline_sections}, ensure_ascii=False),
                encoding="utf-8",
            )

            plan_path = run_dir / "section_drafts" / "figure_plan.json"
            if plan_path.exists():
                payload = json.loads(plan_path.read_text(encoding="utf-8"))
                payload["figures"] = []
                plan_path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )

            section_dir = run_dir / "section_drafts"
            section_dir.mkdir(exist_ok=True)
            sentences = []
            for section_id in order:
                if section_id in claimless:
                    (section_dir / f"{section_id}.md").write_text(
                        f"# {section_id}\n\n本節由流程自動產生。\n", encoding="utf-8"
                    )
                    continue
                (section_dir / f"{section_id}.md").write_text(
                    f"# {section_id}\n\n就本節而言，{row['content'][:120]} "
                    f"[CITE:{row['evidence_id']}]。\n",
                    encoding="utf-8",
                )
                sentences.append({
                    "sentence_id": f"s_{section_id}",
                    "section_id": section_id,
                    "claim_ids": _section_claim_ids(section_id),
                    "evidence_ids": [row["evidence_id"]],
                    "citation_ids": [row["evidence_id"]],
                    "wording_strength": "hedged",
                    "draft_origin": "agent_draft",
                })
            with open(run_dir / "sentence_map.jsonl", "w", encoding="utf-8") as handle:
                for sentence in sentences:
                    handle.write(json.dumps(sentence, ensure_ascii=False) + "\n")

            validated = validate_workflow(state.job_id)
            report = json.loads(
                Path(validated.qa["factuality_report_path"]).read_text(encoding="utf-8")
            )
            self.assertIn(
                "FE", report["checkers_run"],
                "the content gate must run on the publish path",
            )
            self.assertIn("FA", report["checkers_run"])
            self.assertTrue(report["verified_means"])
            for checker in report["checkers_run"]:
                self.assertIn(checker, report["checker_descriptions"])


if __name__ == "__main__":
    unittest.main()
