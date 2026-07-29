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
