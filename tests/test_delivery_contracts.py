import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

from report_workflow.nodes.base_document_parse import _parse_markdown_sections
from report_workflow.nodes.docx_render import _style_tables_post_render
from report_workflow.nodes.style_pass import _apply_style_polish
from report_workflow.nodes.admissions_monograph_polish import polish_admissions_monograph
from report_workflow.nodes.reference_reality_check import _classify_reference
from report_workflow.nodes.front_matter_build import _build_front_matter
from report_workflow.nodes.front_matter_build import run_front_matter_build
from report_workflow.nodes.final_publish import run_final_publish
from report_workflow.profiles import infer_report_profile, normalize_profile_id
from report_workflow.nodes.reference_verify import _is_publication_reference_candidate
from report_workflow.nodes.project_identity_gate import run_project_identity_gate
from report_workflow.nodes.figure_quality import run_figure_quality
from report_workflow.nodes.admissions_tone_gate import run_admissions_tone_gate
from report_workflow.nodes.reference_relevance_gate import run_reference_relevance_gate
from report_workflow.nodes.claim_plan import run_claim_plan
from report_workflow.nodes.evidence_normalize import run_evidence_normalize
from report_workflow.nodes.revision_apply import run_revision_apply
from report_workflow.agent_wrapper import submit_and_publish_report
from report_workflow.artifact_contract import (
    find_repo_hygiene_issues,
    load_artifact_contract,
    remap_evidence_ids,
    stable_evidence_id,
    validate_evidence_ledger_provenance,
    write_base_document_integrity,
)
from report_workflow.errors import QAHardBlockError
from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR


def _strategy_project_identity():
    return {
        "required_terms": ["deterministic compilation", "StrategyIR", "AST", "Taiwan equities"],
        "required_context_terms": ["compiler architecture", "domain-specific intermediate representation"],
        "forbidden_terms": ["U.S. equity markets", "StrategySpec JSON"],
        "canonical_title_terms": ["deterministic", "compilation", "StrategyIR", "compiler"],
        "domain_context": "Taiwan equities",
        "author_metadata": {},
    }


class MarkdownBaseDocumentParseTests(unittest.TestCase):
    def test_markdown_base_document_sections_are_extracted(self):
        md = """# Project Title

**Author:** Example

## Abstract

Abstract body.

## 1. Introduction

Intro body.

## 2. Research Scope and Design Framing

Scope body.

## 3. Methods

Methods body.

## References

Reference body.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "base.md"
            path.write_text(md, encoding="utf-8")

            sections = _parse_markdown_sections(str(path))

        self.assertEqual(sections["abstract"], "Abstract body.")
        self.assertEqual(sections["introduction"], "Intro body.")
        self.assertEqual(sections["research_scope"], "Scope body.")
        self.assertEqual(sections["methods"], "Methods body.")
        self.assertEqual(sections["references"], "Reference body.")
        self.assertIn("Project Title", sections["preamble"])

    def test_markdown_subsections_remain_with_parent_section(self):
        md = """# Title

## 3. Methods

### 3.1 Research Design

Design body.

### 3.2 Corpus

Corpus body.

## 4. Results

### 4.1 Graph Structure

Results body.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "base.md"
            path.write_text(md, encoding="utf-8")
            sections = _parse_markdown_sections(str(path))

        self.assertIn("### 3.1 Research Design", sections["methods"])
        self.assertIn("Corpus body.", sections["methods"])
        self.assertIn("### 4.1 Graph Structure", sections["results"])


class StylePassMarkdownPreservationTests(unittest.TestCase):
    def test_style_pass_preserves_tables_figures_and_headings(self):
        md = """# Results

This section utilizes the results.

![Figure 1. Hub ranking](figures/hub.png)

Figure 1. Hub ranking from graph analysis.

| Metric | Value |
|--------|-------|
| Graph Nodes | 5,171 |
| Graph Edges | 9,764 |

## Details

- Item one
- Item two
"""
        polished, _issues = _apply_style_polish(md)

        self.assertIn("![Figure 1. Hub ranking](figures/hub.png)", polished)
        self.assertIn("| Metric | Value |", polished)
        self.assertIn("| Graph Nodes | 5,171 |", polished)
        self.assertIn("## Details", polished)
        self.assertIn("- Item one", polished)
        self.assertIn("uses the results", polished)


class DocxTableStyleFallbackTests(unittest.TestCase):
    def test_table_styling_does_not_require_table_grid_style(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "table.docx"
            doc = Document()
            table = doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Metric"
            table.cell(0, 1).text = "Value"
            table.cell(1, 0).text = "Graph Nodes"
            table.cell(1, 1).text = "5,171"
            doc.save(path)

            _style_tables_post_render(str(path))

            rendered = Document(str(path))
            self.assertEqual(len(rendered.tables), 1)
            self.assertEqual(rendered.tables[0].cell(1, 1).text, "5,171")


class AdmissionsMonographPolishTests(unittest.TestCase):
    def test_polish_removes_stock_report_scaffolding_without_touching_tables(self):
        md = """# Introduction

This work presents a deterministic compilation architecture. The paper is organized as follows. Section 2 establishes scope.

| Metric | Value |
|--------|-------|
| Graph Nodes | 5,171 |
"""
        polished, changed = polish_admissions_monograph(md)

        self.assertIn("This project develops a deterministic compilation architecture.", polished)
        self.assertNotIn("The paper is organized as follows", polished)
        self.assertIn("| Graph Nodes | 5,171 |", polished)
        self.assertTrue(changed)


class ReferenceRealityClassificationTests(unittest.TestCase):
    def test_book_reference_is_not_forced_to_human_review(self):
        category, reason = _classify_reference({
            "ref_id": "Aho, A. V. (2006). *Compilers: Principles, Techniques, and Tools*. Addison-Wesley.",
            "raw": "Aho, A. V. (2006). *Compilers: Principles, Techniques, and Tools*. Addison-Wesley.",
            "status": "skipped",
            "checks": [{"type": "skipped", "reason": "no_doi_or_arxiv"}],
            "errors": [],
        })
        self.assertEqual(category, "publisher_or_book_plausible")

    def test_failed_doi_is_hard_failure_category(self):
        category, reason = _classify_reference({
            "ref_id": "Bad DOI",
            "status": "failed",
            "checks": [{"type": "doi", "verified": False}],
            "errors": ["DOI not found"],
        })
        self.assertEqual(category, "failed_external_verification")

    def test_year_like_journal_volume_is_not_arxiv_candidate(self):
        self.assertTrue(
            _is_publication_reference_candidate(
                "Cytron, R. (1991). Efficiently computing static single assignment form. "
                "*ACM Transactions on Programming Languages and Systems*, 13(4), 451-490. "
                "https://doi.org/10.1145/115372.115320"
            )
        )


class FrontMatterPrecedenceTests(unittest.TestCase):
    def test_structured_title_wins_over_base_preamble_title(self):
        state = ReportState.new("revise report", ["base.md"], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "revise_existing"
        state.spec["front_matter"] = {
            "title": "Short Explicit Title",
            "author_block": "Author Name",
            "affiliation_block": "Affiliation",
            "correspondence": "email@example.com",
            "keywords": ["deterministic compilation", "StrategyIR", "AST compilation"],
        }
        state.plan["blueprint"] = {"front_matter": {}}
        state.sources["base_document_sections"] = {
            "preamble": "# Very Long Base Title: A Subtitle That Should Not Override Explicit Structured Metadata\n\n---"
        }

        front_matter = _build_front_matter(state)

        self.assertEqual(front_matter["title"], "Short Explicit Title")

    def test_markdown_bold_front_matter_is_cleaned(self):
        state = ReportState.new("revise report", ["base.md"], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"front_matter": {}}
        state.sources["base_document_sections"] = {
            "preamble": (
                "# Deterministic Compilation Architecture\n\n---\n\n"
                "**Author:** Example Student\n"
                "**Affiliation:** Department of Engineering, Example University\n"
                "**Correspondence:** student@example.edu\n"
                "**Keywords:** deterministic compilation, StrategyIR, AST compilation\n"
            )
        }

        front_matter = _build_front_matter(state)

        self.assertEqual(front_matter["author_block"], "Example Student")
        self.assertEqual(
            front_matter["affiliation_block"],
            "Department of Engineering, Example University",
        )
        self.assertEqual(front_matter["correspondence"], "student@example.edu")
        self.assertEqual(front_matter["keywords"][0], "deterministic compilation")

    def test_generic_research_metadata_hard_fails(self):
        state = ReportState.new("write report", ["source.md"], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_report"
        state.spec["front_matter"] = {
            "title": "Deterministic Compilation Architecture",
            "author_block": "Research Author",
            "affiliation_block": "Department of Computer Science, Research University",
            "correspondence": "research@university.edu",
            "keywords": ["deterministic compilation", "StrategyIR", "AST compilation"],
        }
        state.plan["blueprint"] = {"front_matter": {}}

        with self.assertRaises(QAHardBlockError):
            run_front_matter_build(state)

    def test_admissions_project_report_allows_missing_publication_metadata(self):
        state = ReportState.new("write admissions project report", ["source.md"], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_project_report"
        state.plan["blueprint"] = {
            "front_matter": {
                "title": "Quant Strategy Validation Platform",
                "keywords": ["Taiwan equities", "validation"],
            }
        }

        result = run_front_matter_build(state)

        self.assertEqual(result.plan["front_matter"]["title"], "Quant Strategy Validation Platform")


class QualityGateContractTests(unittest.TestCase):
    def test_stable_evidence_id_repeats_for_same_source_span(self):
        entry = {"source_id": "abc123", "file_name": "source.md"}
        block = {"line_start": 10, "line_end": 12, "content_hash": "deadbeefcafebabe", "content": "same"}

        self.assertEqual(stable_evidence_id(entry, block), stable_evidence_id(entry, block))

    def test_claim_plan_blocks_cross_run_evidence_ids_early(self):
        state = ReportState.new("report", [], "out")
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        evidence_id = "E_current_123"
        (run_dir / "evidence_ledger.jsonl").write_text(
            json.dumps({"evidence_id": evidence_id}) + "\n",
            encoding="utf-8",
        )
        state.sources["evidence_ledger_path"] = str(run_dir / "evidence_ledger.jsonl")
        (run_dir / "claim_matrix.json").write_text(json.dumps({
            "claims": [{
                "claim_id": "c1",
                "claim_text": "Claim copied from another run.",
                "evidence_ids": ["E_old_999"],
                "claim_role": "primary",
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_claim_plan(state)
        self.assertIn("remap-evidence", str(ctx.exception))

    def test_remap_evidence_dry_run_and_write_updates_artifacts(self):
        old = ReportState.new("old", [], "out")
        new = ReportState.new("new", [], "out")
        old_dir = WORKFLOW_RUNS_DIR / old.job_id
        new_dir = WORKFLOW_RUNS_DIR / new.job_id
        old_ev = {
            "evidence_id": "old123",
            "source_file_name": "source.md",
            "line_start": 1,
            "line_end": 2,
            "content_hash": "hash-a",
            "quote": "same quote",
        }
        new_ev = {**old_ev, "evidence_id": "new456"}
        (old_dir / "evidence_ledger.jsonl").write_text(json.dumps(old_ev) + "\n", encoding="utf-8")
        (new_dir / "evidence_ledger.jsonl").write_text(json.dumps(new_ev) + "\n", encoding="utf-8")
        (new_dir / "source_registry.json").write_text("[]", encoding="utf-8")
        (new_dir / "claim_matrix.json").write_text(json.dumps({
            "claims": [{"claim_id": "c1", "claim_text": "Claim", "evidence_ids": ["old123"], "claim_role": "primary"}]
        }), encoding="utf-8")
        (new_dir / "outline.json").write_text(json.dumps({
            "sections": {"results": {"claim_ids": ["c1"]}}
        }), encoding="utf-8")
        (new_dir / "sentence_map.jsonl").write_text(
            json.dumps({"sentence_id": "s1", "section_id": "results", "claim_ids": ["c1"], "evidence_ids": ["old123"], "citation_ids": ["old123"]}) + "\n",
            encoding="utf-8",
        )
        section_dir = new_dir / "section_drafts"
        section_dir.mkdir(exist_ok=True)
        (section_dir / "results.md").write_text("Result [CITE:old123].", encoding="utf-8")

        dry = remap_evidence_ids(new.job_id, old.job_id, write=False)
        self.assertEqual(dry["mapping"]["old123"], "new456")
        self.assertIn("old123", (new_dir / "claim_matrix.json").read_text(encoding="utf-8"))

        written = remap_evidence_ids(new.job_id, old.job_id, write=True)
        self.assertEqual(written["status"], "ok")
        self.assertIn("new456", (new_dir / "claim_matrix.json").read_text(encoding="utf-8"))
        self.assertIn("[CITE:new456]", (section_dir / "results.md").read_text(encoding="utf-8"))
        self.assertEqual(load_artifact_contract(new_dir / "claim_matrix.json")["job_id"], new.job_id)

    def test_revision_apply_blocks_no_op_change(self):
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.sources["base_document_sections"] = {"abstract": "This work presents a system."}
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "abstract",
                "change_type": "replace",
                "original_text": "This work presents",
                "new_text": "This work presents",
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError):
            run_revision_apply(state)

    def test_revision_apply_blocks_figure_reference_deletion_without_reason(self):
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"section_order": ["results"]}
        state.sources["base_document_sections"] = {"results": "Figure 1 shows the architecture."}
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        sections_path = run_dir / "base_document_sections.json"
        sections_path.write_text(json.dumps(state.sources["base_document_sections"]), encoding="utf-8")
        state.sources["base_document_sections_path"] = str(sections_path)
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "results",
                "change_type": "delete",
                "original_text": "Figure 1 shows the architecture.",
                "new_text": "",
                "editorial": True,
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_revision_apply(state)
        self.assertIn("remove_figure_reference", str(ctx.exception))

    def test_revision_apply_blocks_chinese_figure_and_table_deletion(self):
        # The same guard, on the language this tool is mostly used in. Matching
        # only "Figure"/"Table" left a Chinese report with no protection at all.
        for label, body, expected in (
            ("figure", "圖 1. 系統架構\n如圖 1 所示。", "remove_figure_reference"),
            ("table", "表 1. 參數設定\n如表 1 所示。", "remove_table_reference"),
        ):
            with self.subTest(label):
                state = ReportState.new("revise", [], "out")
                state.spec["task_intent"] = "revise_existing"
                state.plan["blueprint"] = {"section_order": ["results"]}
                state.sources["base_document_sections"] = {"results": body}
                run_dir = WORKFLOW_RUNS_DIR / state.job_id
                sections_path = run_dir / "base_document_sections.json"
                sections_path.write_text(
                    json.dumps(state.sources["base_document_sections"], ensure_ascii=False),
                    encoding="utf-8",
                )
                state.sources["base_document_sections_path"] = str(sections_path)
                (run_dir / "revision_plan.json").write_text(json.dumps({
                    "changes": [{
                        "section_id": "results",
                        "change_type": "delete",
                        "original_text": body,
                        "new_text": "",
                        "editorial": True,
                    }]
                }, ensure_ascii=False), encoding="utf-8")

                with self.assertRaises(QAHardBlockError) as ctx:
                    run_revision_apply(state)
                self.assertIn(expected, str(ctx.exception))

    def test_a_title_row_above_the_header_does_not_become_the_header(self):
        # A monthly export opens with its own name in A1. Read as the header,
        # the title named the first column, the rest became Unnamed, the real
        # header turned into a citable data row, and in CSV the one-cell header
        # truncated every row to a single column — two measurements gone.
        import tempfile
        from report_workflow.parsers.structured_parser import parse_csv

        tmpdir = Path(tempfile.mkdtemp())
        path = tmpdir / "月報.csv"
        path.write_text(
            "2025 年第一季產線月報\n\n月份,不良率(%),產量(件)\n1,1.8,1230\n",
            encoding="utf-8",
        )
        rows = parse_csv(str(path))
        self.assertEqual(rows, [{"月份": "1", "不良率(%)": "1.8", "產量(件)": "1230"}])

    def test_a_merged_word_header_keeps_both_readings(self):
        # A spec sheet merges one label across two columns. python-docx hands
        # back the label twice with a newline between, which broke the header
        # into rows of different widths; the row A1 / 5 / 7 then reached the
        # ledger as one reading keyed on text nobody wrote.
        import tempfile
        from docx import Document
        from report_workflow.parsers.semi_structured_parser import parse_semi_structured
        from report_workflow.nodes.evidence_normalize import _table_row_blocks

        tmpdir = Path(tempfile.mkdtemp())
        document = Document()
        table = document.add_table(rows=2, cols=3)
        header = table.rows[0].cells
        header[0].text = "機台"
        header[1].text = "解析度(μm)"
        header[2].text = "解析度(μm)"
        header[1].merge(header[2])
        body = table.rows[1].cells
        body[0].text = "A1"
        body[1].text = "5"
        body[2].text = "7"
        path = tmpdir / "規格.docx"
        document.save(str(path))

        blocks = parse_semi_structured(str(path), "docx")["blocks"]
        table_block = next(b for b in blocks if b["block_type"] == "table")
        self.assertNotIn("\n", table_block["table_data"][0][1])

        rows = _table_row_blocks(table_block)
        self.assertEqual(
            json.loads(rows[0]["content"]),
            {"機台": "A1", "解析度(μm)": "5", "解析度(μm) [2]": "7"},
        )

    def test_every_sheet_of_a_workbook_reaches_the_records(self):
        # One year per tab is how these workbooks arrive. Only the first sheet
        # was read, so the other year's rows never reached the ledger and
        # nothing said they existed.
        import tempfile
        from openpyxl import Workbook
        from report_workflow.parsers.structured_parser import parse_xlsx

        tmpdir = Path(tempfile.mkdtemp())
        book = Workbook()
        first = book.active
        first.title = "2025"
        first.append(["月份", "不良率(%)"])
        first.append([1, 1.8])
        second = book.create_sheet("2024")
        second.append(["月份", "不良率(%)"])
        second.append([1, 4.2])
        path = tmpdir / "年度比較.xlsx"
        book.save(str(path))

        records = parse_xlsx(str(path))
        self.assertEqual(
            records,
            [
                {"sheet": "2025", "月份": 1, "不良率(%)": 1.8},
                {"sheet": "2024", "月份": 1, "不良率(%)": 4.2},
            ],
        )

    def test_a_single_sheet_workbook_gains_no_extra_column(self):
        import tempfile
        from openpyxl import Workbook
        from report_workflow.parsers.structured_parser import parse_xlsx

        tmpdir = Path(tempfile.mkdtemp())
        book = Workbook()
        sheet = book.active
        sheet.append(["月份", "不良率(%)"])
        sheet.append([1, 1.8])
        path = tmpdir / "單分頁.xlsx"
        book.save(str(path))

        self.assertEqual(parse_xlsx(str(path)), [{"月份": 1, "不良率(%)": 1.8}])

    def test_a_header_with_a_blank_corner_is_not_skipped(self):
        # The guard must not reach past a real header: a matrix table leaves
        # its corner cell empty and still holds two or more values.
        import tempfile
        from report_workflow.parsers.structured_parser import parse_csv

        tmpdir = Path(tempfile.mkdtemp())
        path = tmpdir / "matrix.csv"
        path.write_text(",甲線,乙線\n1月,1.8,2.1\n", encoding="utf-8")
        rows = parse_csv(str(path))
        self.assertEqual(rows, [{"": "1月", "甲線": "1.8", "乙線": "2.1"}])

    def test_a_plain_table_is_untouched(self):
        import tempfile
        from report_workflow.parsers.structured_parser import parse_csv

        tmpdir = Path(tempfile.mkdtemp())
        path = tmpdir / "plain.csv"
        path.write_text("月份,不良率(%)\n1,1.8\n", encoding="utf-8")
        self.assertEqual(parse_csv(str(path)), [{"月份": "1", "不良率(%)": "1.8"}])

    def test_a_source_missing_at_publish_time_is_not_skipped_in_silence(self):
        # A source moved between prepare and publish was skipped without a
        # word: the bundle shipped short, artifacts.json listed only what made
        # it, and the report kept citing claims traced to the absent file.
        import tempfile
        import uuid
        from report_workflow.nodes.artifacts import run_artifacts

        tmpdir = Path(tempfile.mkdtemp())
        present = tmpdir / "kept.csv"
        present.write_text("a,b\n1,2\n", encoding="utf-8")
        absent = tmpdir / "gone.csv"

        state = ReportState.new("report", [], str(tmpdir / "out"))
        state.job_id = f"test_missing_source_{uuid.uuid4().hex}"
        state.qa["qa_decision"] = "pass"
        state.qa["artifact_completeness_status"] = "pass"
        state.spec["uploaded_files"] = [str(present), str(absent)]

        with self.assertRaises(QAHardBlockError) as ctx:
            run_artifacts(state)
        self.assertIn("gone.csv", str(ctx.exception))

    def test_a_missing_base_document_is_named_as_a_base_document(self):
        # A base document is not a cited source — it is the document being
        # revised. The role comes from the registry, which stores resolved
        # paths while uploaded_files keeps the caller's spelling, so the two
        # are compared resolved; matching raw strings labelled every base
        # document a plain source.
        import tempfile
        import uuid
        from report_workflow.nodes.artifacts import run_artifacts

        tmpdir = Path(tempfile.mkdtemp())
        absent = tmpdir / "原稿.docx"

        state = ReportState.new("revise", [], str(tmpdir / "out"))
        state.job_id = f"test_missing_base_{uuid.uuid4().hex}"
        state.qa["qa_decision"] = "pass"
        state.qa["artifact_completeness_status"] = "pass"
        # The caller's spelling goes through a redundant "." segment; the
        # registry holds the resolved form, as the real pipeline writes it.
        state.spec["uploaded_files"] = [str(tmpdir / "." / "原稿.docx")]
        state.sources["source_registry"] = [{
            "source_id": "S", "file_name": "原稿.docx",
            "file_path": str(absent.resolve()), "artifact_role": "base_document",
        }]

        with self.assertRaises(QAHardBlockError) as ctx:
            run_artifacts(state)
        self.assertIn("base_document", str(ctx.exception))

    def test_publishing_still_succeeds_when_every_source_is_present(self):
        import tempfile
        import uuid
        from report_workflow.nodes.artifacts import run_artifacts

        tmpdir = Path(tempfile.mkdtemp())
        for name in ("a.csv", "b.csv"):
            (tmpdir / name).write_text("x,y\n1,2\n", encoding="utf-8")

        state = ReportState.new("report", [], str(tmpdir / "out"))
        state.job_id = f"test_present_sources_{uuid.uuid4().hex}"
        state.qa["qa_decision"] = "pass"
        state.qa["artifact_completeness_status"] = "pass"
        state.spec["uploaded_files"] = [str(tmpdir / "a.csv"), str(tmpdir / "b.csv")]

        state = run_artifacts(state)
        published = Path(state.output["published_dir"]) / "sources"
        self.assertEqual(sorted(p.name for p in published.iterdir()), ["a.csv", "b.csv"])

    def test_same_named_sources_both_reach_the_published_bundle(self):
        # Both files landed on published/sources/月報.csv, so the bundle kept
        # whichever was copied last. A reader checking the report's 2024 claim
        # opened the survivor and read 2025's numbers.
        from report_workflow.nodes.artifacts import _unique_source_names

        names = _unique_source_names([
            r"C:\a\2024\月報.csv",
            r"C:\a\2025\月報.csv",
            r"C:\a\規格.pdf",
        ])
        self.assertEqual(names[r"C:\a\2024\月報.csv"], "2024_月報.csv")
        self.assertEqual(names[r"C:\a\2025\月報.csv"], "2025_月報.csv")
        self.assertEqual(names[r"C:\a\規格.pdf"], "規格.pdf")

    def test_identically_foldered_sources_still_get_distinct_names(self):
        from report_workflow.nodes.artifacts import _unique_source_names

        names = _unique_source_names([r"C:\a\data\月報.csv", r"C:\b\data\月報.csv"])
        self.assertEqual(len(set(names.values())), 2)

    def test_a_blocked_render_names_the_text_that_tripped_it(self):
        # "Raw prompt fragment leaked into publication text" with no fragment
        # quoted leaves nothing to search the drafts for.
        from report_workflow.nodes.docx_render import _pre_render_sanity_check

        prompt = "比較 2024 與 2025 產線不良率"
        issues = _pre_render_sanity_check(
            f"# 報告\n\n{prompt}\n", forbidden_fragments=[prompt]
        )
        leak = [i for i in issues if "Raw prompt fragment" in i]
        self.assertTrue(leak, issues)
        self.assertIn(prompt, leak[0])

    def test_same_named_sources_are_told_apart_in_the_brief(self):
        # Monthly exports arrive as 2024/月報.csv and 2025/月報.csv. Shown as
        # "月報.csv" twice, an author picking between two rows of numbers has
        # nothing to pick by, and citing the wrong year passes every gate.
        from report_workflow.nodes.agent_tasks import _source_labels

        labels = _source_labels([
            {"source_file_name": "月報.csv", "source_file_path": r"C:\a\2024\月報.csv"},
            {"source_file_name": "月報.csv", "source_file_path": r"C:\a\2025\月報.csv"},
            {"source_file_name": "規格.pdf", "source_file_path": r"C:\a\規格.pdf"},
        ])
        self.assertEqual(labels[r"C:\a\2024\月報.csv"], "2024/月報.csv")
        self.assertEqual(labels[r"C:\a\2025\月報.csv"], "2025/月報.csv")
        self.assertEqual(labels[r"C:\a\規格.pdf"], "規格.pdf")

    def test_a_lone_source_keeps_its_plain_name(self):
        from report_workflow.nodes.agent_tasks import _source_labels

        labels = _source_labels(
            [{"source_file_name": "月報.csv", "source_file_path": r"C:\a\2024\月報.csv"}]
        )
        self.assertEqual(labels[r"C:\a\2024\月報.csv"], "月報.csv")

    def test_identical_parent_names_fall_back_to_the_full_path(self):
        from report_workflow.nodes.agent_tasks import _source_labels

        labels = _source_labels([
            {"source_file_name": "月報.csv", "source_file_path": r"C:\a\data\月報.csv"},
            {"source_file_name": "月報.csv", "source_file_path": r"C:\b\data\月報.csv"},
        ])
        self.assertEqual(len(set(labels.values())), 2)
        self.assertIn(r"C:\a\data\月報.csv", labels.values())

    def test_removing_a_whole_section_does_not_demand_a_figure_decision(self):
        # remove_section is already a declared structural change, recorded in
        # removed_sections. Counting its figures left the author one exit:
        # figure_preservation_decision='remove_because_no_source_asset', which
        # asserts the asset does not exist when it plainly does — a false entry
        # in the audit trail the gate exists to protect.
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"section_order": ["results"]}
        state.sources["base_document_sections"] = {
            "results": "導入後不良率下降。\n圖 1. 月別不良率。",
            "discussion": "樣本期間偏短。",
        }
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        sections_path = run_dir / "base_document_sections.json"
        sections_path.write_text(
            json.dumps(state.sources["base_document_sections"], ensure_ascii=False),
            encoding="utf-8",
        )
        state.sources["base_document_sections_path"] = str(sections_path)
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{"section_id": "results", "change_type": "remove_section"}]
        }, ensure_ascii=False), encoding="utf-8")

        state = run_revision_apply(state)
        report = json.loads(
            Path(state.runtime["revision_diff_report_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(report["removed_sections"], ["results"])

    def test_a_caption_deleted_without_removing_its_section_still_blocks(self):
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"section_order": ["results"]}
        state.sources["base_document_sections"] = {
            "results": "導入後不良率下降。\n圖 1. 月別不良率。",
        }
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        sections_path = run_dir / "base_document_sections.json"
        sections_path.write_text(
            json.dumps(state.sources["base_document_sections"], ensure_ascii=False),
            encoding="utf-8",
        )
        state.sources["base_document_sections_path"] = str(sections_path)
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "results",
                "change_type": "delete",
                "original_text": "圖 1. 月別不良率。",
                "new_text": "",
                "editorial": True,
            }]
        }, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_revision_apply(state)
        self.assertIn("remove_figure_reference", str(ctx.exception))

    def test_chinese_reference_ids_ignore_ordinary_prose(self):
        # 圖 and 表 are common morphemes; a prose mention is not a reference.
        # Counting them would hard-block honest sentences, which is worse than
        # missing an uncaptioned figure.
        from report_workflow.nodes.revision_apply import _reference_ids

        prose = {"s": "\n".join([
            "本團隊發表 2 篇相關論文。",
            "受訪者代表 3 家供應商。",
            "量表 5 點尺度計分。",
            "試圖 3 次後放棄。",
        ])}
        self.assertEqual(_reference_ids(prose, "Figure"), set())
        self.assertEqual(_reference_ids(prose, "Table"), set())

        captioned = {"s": "圖 1. 效能對流量。\n表 2. 參數設定\n本團隊發表 2 篇論文。"}
        self.assertEqual(_reference_ids(captioned, "Figure"), {"1"})
        self.assertEqual(_reference_ids(captioned, "Table"), {"2"})

    def test_revision_apply_requires_preservation_decision_for_figure_removal(self):
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"section_order": ["results"]}
        state.sources["base_document_sections"] = {"results": "Figure 1 shows the architecture."}
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        sections_path = run_dir / "base_document_sections.json"
        sections_path.write_text(json.dumps(state.sources["base_document_sections"]), encoding="utf-8")
        state.sources["base_document_sections_path"] = str(sections_path)
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "results",
                "change_type": "delete",
                "original_text": "Figure 1 shows the architecture.",
                "new_text": "",
                "change_reason": "remove_figure_reference",
                "editorial": True,
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_revision_apply(state)
        self.assertIn("figure_preservation_decision", str(ctx.exception))

    def test_revision_apply_blocks_figure_removal_when_prompt_requires_preserve(self):
        state = ReportState.new("revise and preserve figure/table references", [], "out")
        state.spec["task_intent"] = "revise_existing"
        state.plan["blueprint"] = {"section_order": ["results"]}
        state.sources["base_document_sections"] = {"results": "Figure 1 shows the architecture."}
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        sections_path = run_dir / "base_document_sections.json"
        sections_path.write_text(json.dumps(state.sources["base_document_sections"]), encoding="utf-8")
        state.sources["base_document_sections_path"] = str(sections_path)
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "results",
                "change_type": "delete",
                "original_text": "Figure 1 shows the architecture.",
                "new_text": "",
                "change_reason": "remove_figure_reference",
                "figure_preservation_decision": "remove_because_no_source_asset",
                "editorial": True,
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_revision_apply(state)
        self.assertIn("preservation", str(ctx.exception).lower())

    def test_base_document_integrity_blocks_direct_section_mutation(self):
        state = ReportState.new("revise", [], "out")
        state.spec["task_intent"] = "revise_existing"
        original = {"results": "Figure 1 shows the architecture."}
        write_base_document_integrity(
            state,
            original,
            {"file_path": __file__, "file_name": "base.md"},
        )
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        (run_dir / "base_document_sections.json").write_text(
            json.dumps({"results": "The architecture is described."}),
            encoding="utf-8",
        )
        state.sources["base_document_sections_path"] = str(run_dir / "base_document_sections.json")
        (run_dir / "revision_plan.json").write_text(json.dumps({
            "changes": [{
                "section_id": "results",
                "change_type": "replace",
                "original_text": "architecture",
                "new_text": "compiler architecture",
            }]
        }), encoding="utf-8")

        with self.assertRaises(QAHardBlockError) as ctx:
            run_revision_apply(state)
        self.assertIn("immutable parse snapshot", str(ctx.exception))

    def test_evidence_provenance_blocks_hand_authored_primary_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / "evidence_ledger.jsonl"
            ledger.write_text(json.dumps({
                "evidence_id": "E003",
                "source_role": "primary_source",
                "content": "Hand-authored evidence without parser trace.",
            }) + "\n", encoding="utf-8")
            with self.assertRaises(QAHardBlockError):
                validate_evidence_ledger_provenance(ledger)

    def test_evidence_provenance_blocks_base_document_role(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / "evidence_ledger.jsonl"
            ledger.write_text(json.dumps({
                "evidence_id": "E001",
                "source_role": "base_document",
                "source_id": "src1",
                "source_file_name": "revised_report.md",
                "content": "Copied from base document.",
                "content_hash": "abc123",
            }) + "\n", encoding="utf-8")
            with self.assertRaises(QAHardBlockError):
                validate_evidence_ledger_provenance(ledger)

    def test_evidence_normalize_adds_missing_content_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("normalize parser blocks", [], tmpdir)
            state.sources["source_registry"] = [{
                "source_id": "S001",
                "file_name": "sample.pdf",
                "file_path": __file__,
                "file_type": "pdf",
                "file_size": 100,
                "artifact_role": "source_data",
                "parsed_content": [{
                    "block_id": "B001",
                    "block_type": "paragraph",
                    "content": "This method paragraph has enough source content to become evidence.",
                }],
            }]

            run_evidence_normalize(state)

            ledger = Path(state.sources["evidence_ledger_path"])
            row = json.loads(ledger.read_text(encoding="utf-8").strip())
            self.assertEqual(len(row["content_hash"]), 16)
            validate_evidence_ledger_provenance(ledger)

    def test_repo_hygiene_detects_orphan_repair_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "fix_claims.py").write_text("print('temp')", encoding="utf-8")
            issues = find_repo_hygiene_issues(root)
        self.assertTrue(any("fix_claims.py" in issue for issue in issues))

    def test_final_publish_blocks_root_orphan_scripts(self):
        state = ReportState.new("publish", [], "out")
        state.qa["qa_decision"] = "pass"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docx = root / "report.docx"
            doc = Document()
            doc.add_paragraph("Report")
            doc.save(docx)
            (root / "strip_figures.py").write_text("print('temp')", encoding="utf-8")
            state.output["final_docx_path"] = str(docx)
            state.output["output_dir"] = str(root / "out")
            with patch("report_workflow.nodes.final_publish.find_repo_hygiene_issues", return_value=[str(root / "strip_figures.py")]):
                with self.assertRaises(QAHardBlockError):
                    run_final_publish(state)

    def test_admissions_project_report_inference_and_reference_policy(self):
        profile = infer_report_profile(
            "Write an admissions-facing academic project report from internal architecture docs."
        )
        self.assertEqual(profile, "admissions_project_report")

    def test_report_profile_alias_normalizes_to_admissions_project(self):
        profile = normalize_profile_id("admissions project report")
        self.assertEqual(profile, "admissions_project_report")

    def test_reference_relevance_allows_internal_only_for_admissions_project_report(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_project_report"
        state.spec["task_intent"] = "new_draft"
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "reference_verify_report.json"
            report.write_text(json.dumps({
                "references": [{
                    "ref_id": "Tsai, C.-C. (2026). *LLM Debate Architecture* (Architecture Documentation, Version 2026-04-13).",
                    "raw": "Tsai, C.-C. (2026). *LLM Debate Architecture* (Architecture Documentation, Version 2026-04-13).",
                    "status": "project_source",
                    "checks": [{"type": "project_source"}],
                }]
            }), encoding="utf-8")
            state.runtime["reference_verify_report_path"] = str(report)
            result = run_reference_relevance_gate(state)
        self.assertTrue(result.runtime["reference_relevance_report_path"])

    def test_submit_and_publish_report_returns_rendered_but_not_publishable(self):
        state = ReportState.new("report", [], "out")
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        doc = Document()
        doc.add_paragraph("Rendered but not published")
        rendered = run_dir / "rendered_report.docx"
        doc.save(rendered)
        result = submit_and_publish_report(state.job_id)
        self.assertTrue(result["rendered_but_not_publishable"])
        self.assertTrue(result["not_final_deliverable"])

    def test_project_identity_gate_blocks_topic_drift(self):
        state = ReportState.new("write admissions report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "new_draft"
        state.spec["project_identity"] = _strategy_project_identity()
        state.plan["front_matter"] = {
            "title": "A Trustworthy Verification Framework for LLM-Assisted Quantitative Strategy Generation in U.S. Equity Markets"
        }
        state.plan["thesis_statement"] = "StrategySpec JSON with JSON Schema validation supports a seven-phase pipeline."
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Abstract\n\nA StrategySpec JSON framework for U.S. equity markets is described.\n\n"
                "# Introduction\n\nThe report focuses on U.S. equity markets and JSON Schema validation.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(draft)
            with self.assertRaises(QAHardBlockError):
                run_project_identity_gate(state)

    def test_project_identity_gate_passes_project_spine(self):
        state = ReportState.new("write admissions report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "new_draft"
        state.spec["project_identity"] = _strategy_project_identity()
        state.plan["front_matter"] = {
            "title": "Deterministic Compilation Architecture for StrategyIR Trading Systems"
        }
        state.plan["thesis_statement"] = (
            "Deterministic compilation with StrategyIR and AST construction supports "
            "auditable Taiwan equities strategy generation."
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Abstract\n\nDeterministic compilation uses StrategyIR and AST construction for Taiwan equities.\n\n"
                "# Introduction\n\nThe project centers on compiler architecture, StrategyIR, and Taiwan equities verification.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(draft)
            result = run_project_identity_gate(state)
        self.assertTrue(result.runtime["project_identity_report_path"])

    def test_project_identity_gate_uses_outline_thesis_when_scope_freeze_does_not_set_one(self):
        state = ReportState.new("write admissions project report", [], "out")
        state.spec["report_profile"] = "admissions_project_report"
        state.spec["task_intent"] = "new_draft"
        state.spec["project_identity"] = {
            "required_terms": ["structured workflow", "evidence handling", "QA thinking"],
            "required_context_terms": ["auditable artifacts"],
            "forbidden_terms": [],
            "canonical_title_terms": ["workflow"],
            "domain_context": "structured workflow",
            "author_metadata": {},
        }
        state.plan["front_matter"] = {"title": "Structured Workflow Evidence Project"}
        state.plan["outline"] = {
            "thesis_statement": (
                "The structured workflow demonstrates evidence handling and QA thinking "
                "through auditable artifacts."
            )
        }
        state.plan["primary_contribution"] = "A measured outcome claim without the identity spine."
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Abstract\n\nThe structured workflow turns evidence handling and QA thinking into auditable artifacts.\n\n"
                "# Introduction\n\nThe structured workflow project centers evidence handling, QA thinking, and auditable artifacts.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(draft)
            result = run_project_identity_gate(state)
        self.assertTrue(result.runtime["project_identity_report_path"])

    def test_project_identity_gate_accepts_distributed_domain_context(self):
        state = ReportState.new("write admissions report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        state.spec["report_profile"] = "admissions_project_report"
        state.plan["front_matter"] = {
            "title": "Quant: Taiwan Equity Strategy Validation"
        }
        state.plan["thesis_statement"] = (
            "Quant supports Taiwan equities, LLM validation, and historical replay "
            "for a graduate admissions project."
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            identity_path = run_dir / "project_identity.json"
            identity_path.write_text(json.dumps({
                "required_terms": ["Quant", "Taiwan equities", "historical replay"],
                "required_context_terms": ["validation"],
                "forbidden_terms": [],
                "canonical_title_terms": ["Quant"],
                "domain_context": "Taiwan equities and graduate admissions project introduction",
                "author_metadata": {},
            }), encoding="utf-8")
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Abstract\n\nQuant is a validation platform for Taiwan equities and historical replay.\n\n"
                "# Introduction\n\nThe project introduces a graduate admissions report about Taiwan equities, "
                "validation, and historical replay.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(draft)
            result = run_project_identity_gate(state)
        self.assertTrue(result.runtime["project_identity_report_path"])

    def test_figure_quality_blocks_undeclared_prose_reference(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nThe architecture is summarized in Figure 3.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            with self.assertRaises(QAHardBlockError):
                run_figure_quality(state)

    def test_admissions_tone_gate_blocks_meta_reader_phrase(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_report"
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Discussion\n\nFor an admissions committee, the relevant evidence is clear.\n",
                encoding="utf-8",
            )
            state.drafts["publication_style_draft"] = str(draft)
            with self.assertRaises(QAHardBlockError):
                run_admissions_tone_gate(state)

    def test_admissions_tone_gate_uses_project_identity_instead_of_hardcoded_project_terms(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "new_draft"
        state.plan["project_identity"] = {
            "required_terms": ["structured workflow", "evidence handling", "QA thinking"],
            "required_context_terms": ["auditable artifacts"],
            "canonical_title_terms": ["workflow"],
            "domain_context": "technical communication project",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = Path(tmpdir) / "draft.md"
            draft.write_text(
                "# Conclusion\n\nThe project demonstrates evidence handling, QA thinking, "
                "and structured workflow judgment through auditable artifacts.\n",
                encoding="utf-8",
            )
            state.drafts["publication_style_draft"] = str(draft)
            result = run_admissions_tone_gate(state)
        self.assertTrue(result.runtime["admissions_tone_report_path"])

    def test_reference_relevance_gate_blocks_generic_reference(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_report"
        state.plan["project_identity"] = {
            "required_terms": ["deterministic compilation", "StrategyIR"],
            "required_context_terms": ["compiler architecture"],
            "canonical_title_terms": ["compiler"],
            "forbidden_terms": [],
            "domain_context": "Taiwan equities",
            "author_metadata": {},
        }
        state.plan["claim_matrix"] = {
            "claims": [{
                "claim_id": "c1",
                "claim_text": "StrategyIR supports deterministic compiler architecture.",
                "topic_tags": ["compiler architecture"],
            }]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "reference_verify_report.json"
            report.write_text(json.dumps({
                "references": [{
                    "ref_id": "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine.",
                    "status": "verified",
                    "checks": [{"type": "doi", "verified": True}],
                }]
            }), encoding="utf-8")
            state.runtime["reference_verify_report_path"] = str(report)
            with self.assertRaises(QAHardBlockError):
                run_reference_relevance_gate(state)

    def test_reference_relevance_gate_accepts_role_supported_reference(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_report"
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "reference_verify_report.json"
            report.write_text(json.dumps({
                "references": [{
                    "ref_id": "Cytron, R. (1991). Efficiently computing static single assignment form.",
                    "status": "verified",
                    "reference_role": "compiler_foundation",
                    "supports_claim_ids": ["c1"],
                    "checks": [{"type": "doi", "verified": True}],
                }]
            }), encoding="utf-8")
            state.runtime["reference_verify_report_path"] = str(report)
            result = run_reference_relevance_gate(state)
        self.assertTrue(result.runtime["reference_relevance_report_path"])

    def test_reference_relevance_gate_blocks_internal_only_admissions_without_name_error(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "admissions_report"
        state.spec["task_intent"] = "new_draft"
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "reference_verify_report.json"
            report.write_text(json.dumps({
                "references": [{
                    "ref_id": "Internal project note.",
                    "raw": "Internal project note.",
                    "status": "excluded",
                    "checks": [{"type": "internal"}],
                }]
            }), encoding="utf-8")
            state.runtime["reference_verify_report_path"] = str(report)
            with self.assertRaises(QAHardBlockError) as raised:
                run_reference_relevance_gate(state)
        self.assertIn("bibliography is not publication-bearing", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
