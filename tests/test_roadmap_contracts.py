import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml
from docx import Document

from report_workflow.agent_wrapper import (
    _normalize_source_files,
    lint_agent_artifacts,
    query_evidence,
    run_engineering_audit,
)
from report_workflow.nodes.artifacts import run_artifacts
from report_workflow.nodes.corpus_build import run_corpus_build
from report_workflow.nodes.citation_bind import audit_sentence_citations, resolve_citations_publication
from report_workflow.nodes.factuality_check import (
    _check_content_overlap,
    _extract_numbers_with_unit,
)
from report_workflow.nodes.front_matter_build import run_front_matter_build
from report_workflow.nodes.evidence_normalize import _determine_source_role
from report_workflow.nodes.post_render_validate import run_post_render_validate
from report_workflow.nodes.section_draft import run_section_draft
from report_workflow.artifact_contract import load_jsonl_without_contract
from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR


class SourceRoleContractTests(unittest.TestCase):
    def test_agent_wrapper_accepts_structured_source_roles(self):
        files, role_map = _normalize_source_files([
            {"path": "old_report.docx", "role": "base_document"},
            "measurements.csv:source_data",
        ])

        self.assertEqual(files, ["old_report.docx", "measurements.csv"])
        self.assertEqual(role_map["old_report.docx"], "base_document")
        self.assertEqual(role_map["measurements.csv"], "source_data")

    def test_source_data_markdown_notes_are_project_sources(self):
        role = _determine_source_role(
            {
                "artifact_role": "source_data",
                "file_name": "source_notes.md",
                "file_type": "md",
            },
            {"content": "Transcribed measurements from scanned lab handout."},
        )

        self.assertEqual(role, "internal_project_source")

    def test_corpus_build_resolves_roles_by_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "base.md"
            base.write_text("# Report\n\nBody", encoding="utf-8")
            source = Path(tmpdir) / "source.txt"
            source.write_text("Measurement source.", encoding="utf-8")

            state = ReportState.new(
                "revise report",
                [str(base), str(source)],
                str(Path(tmpdir) / "out"),
            )
            state.spec["artifact_role_map"] = {
                str(base.resolve()): "base_document",
                str(source.resolve()): "source_data",
            }

            result = run_corpus_build(state)
            roles = {
                entry["file_name"]: entry["artifact_role"]
                for entry in result.sources["source_registry"]
            }

        self.assertEqual(roles["base.md"], "base_document")
        self.assertEqual(roles["source.txt"], "source_data")


class EvidenceQueryContractTests(unittest.TestCase):
    def test_query_evidence_ranks_by_query(self):
        state = ReportState.new("report", [], "out")
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        rows = [
            {
                "evidence_id": "E001",
                "content": "The voltage measurement stayed stable during the trial.",
            },
            {
                "evidence_id": "E002",
                "content": "A separate table describes unrelated attendance data.",
            },
        ]
        (run_dir / "evidence_ledger.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

        result = query_evidence(state.job_id, query="voltage stable")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["entries"][0]["evidence_id"], "E001")
        self.assertEqual(result["total_matches"], 1)


class ChineseFactualityContractTests(unittest.TestCase):
    def test_numeric_overlap_matches_compact_and_chinese_units(self):
        self.assertIn(("5", "cm"), _extract_numbers_with_unit("length is 5cm"))

        reasons = _check_content_overlap(
            {"claim_text": "試片長度為 5 cm 且電壓量測穩定。"},
            {"content": "電壓量測結果穩定，試片長度為5公分。"},
        )

        self.assertEqual(reasons, [])

    def test_chinese_overlap_blocks_unrelated_evidence(self):
        reasons = _check_content_overlap(
            {"claim_text": "試片溫度快速上升。"},
            {"content": "電壓量測結果穩定，試片長度為5公分。"},
        )

        self.assertTrue(any("Chinese claim terms not in evidence" in reason for reason in reasons))


class StructuredDraftContractTests(unittest.TestCase):
    def test_structured_drafts_generate_markdown_and_sentence_map(self):
        state = ReportState.new("write report", [], "out")
        state.plan["blueprint"] = {
            "section_order": ["results"],
            "sections": {"results": {"required": True}},
        }
        state.plan["outline"] = {
            "sections": {
                "results": {
                    "section_id": "results",
                    "claim_ids": ["c1"],
                }
            }
        }
        state.plan["claim_matrix"] = {
            "claims": [{
                "claim_id": "c1",
                "claim_text": "The pilot program enrolled 42 participants.",
                "evidence_ids": ["E001"],
            }]
        }
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        (run_dir / "structured_drafts.json").write_text(json.dumps({
            "sections": {
                "results": {
                    "title": "Results",
                    "sentences": [{
                        "text": "The pilot program enrolled 42 participants.",
                        "claim_ids": ["c1"],
                        "evidence_ids": ["E001"],
                        "wording_strength": "hedged",
                    }],
                }
            }
        }), encoding="utf-8")

        result = run_section_draft(state)

        section_path = Path(result.drafts["section_drafts"]["results"])
        self.assertIn(
            "The pilot program enrolled 42 participants [CITE:E001].",
            section_path.read_text(encoding="utf-8"),
        )
        rows = load_jsonl_without_contract(result.drafts["sentence_map_path"])
        self.assertEqual(rows[0]["section_id"], "results")
        self.assertEqual(rows[0]["claim_ids"], ["c1"])
        self.assertEqual(rows[0]["evidence_ids"], ["E001"])
        self.assertEqual(rows[0]["citation_ids"], ["E001"])
        self.assertEqual(rows[0]["draft_origin"], "structured_draft")

    def test_structured_drafts_emit_separate_markers_for_multiple_citations(self):
        state = ReportState.new("write report", [], "out")
        state.plan["blueprint"] = {
            "section_order": ["results"],
            "sections": {"results": {"required": True}},
        }
        state.plan["outline"] = {
            "sections": {
                "results": {
                    "section_id": "results",
                    "claim_ids": ["c1"],
                }
            }
        }
        state.plan["claim_matrix"] = {
            "claims": [{
                "claim_id": "c1",
                "claim_text": "The table and notes both support the result.",
                "evidence_ids": ["E001", "E002"],
            }]
        }
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        (run_dir / "structured_drafts.json").write_text(json.dumps({
            "sections": {
                "results": {
                    "title": "Results",
                    "sentences": [{
                        "text": "The table and notes both support the result.",
                        "claim_ids": ["c1"],
                        "evidence_ids": ["E001", "E002"],
                    }],
                }
            }
        }), encoding="utf-8")

        result = run_section_draft(state)

        section_text = Path(result.drafts["section_drafts"]["results"]).read_text(encoding="utf-8")
        self.assertIn("[CITE:E001] [CITE:E002]", section_text)
        self.assertNotIn("[CITE:E001,E002]", section_text)
        rows = load_jsonl_without_contract(result.drafts["sentence_map_path"])
        self.assertEqual(rows[0]["citation_ids"], ["E001", "E002"])

    def test_citation_bind_accepts_comma_delimited_legacy_markers(self):
        evidence = [
            {
                "evidence_id": "E001",
                "source_id": "S1",
                "source_role": "internal_project_source",
                "source_file_name": "source_data.md",
            },
            {
                "evidence_id": "E002",
                "source_id": "S1",
                "source_role": "internal_project_source",
                "source_file_name": "source_data.md",
            },
        ]
        sentence_map = [{
            "sentence_id": "s1",
            "section_id": "results",
            "evidence_ids": ["E001", "E002"],
            "citation_ids": ["E001", "E002"],
        }]

        audit = audit_sentence_citations("Result [CITE:E001,E002].", sentence_map, evidence)
        resolved, resolved_audit, _, _ = resolve_citations_publication(
            "Result [CITE:E001,E002].",
            evidence,
            [],
        )

        self.assertEqual(audit, [])
        self.assertNotIn("[CITE:", resolved)
        self.assertTrue(all(item["resolved"] for item in resolved_audit))


class PostRenderLayoutManifestTests(unittest.TestCase):
    def test_post_render_validate_writes_layout_manifest_and_packages_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("render report", [], str(Path(tmpdir) / "out"))
            state.output["renderer_used"] = "python-docx (fallback)"

            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            docx_path = run_dir / "rendered_report.docx"
            doc = Document()
            doc.add_heading("Results", level=1)
            doc.add_paragraph("The rendered report contains final prose without internal markers.")
            table = doc.add_table(rows=2, cols=2)
            table.rows[0].cells[0].text = "Metric"
            table.rows[0].cells[1].text = "Value"
            table.rows[1].cells[0].text = "Participants"
            table.rows[1].cells[1].text = "42"
            doc.save(docx_path)
            state.output["final_docx_path"] = str(docx_path)

            validated = run_post_render_validate(state)
            manifest_path = Path(validated.runtime["post_render_layout_manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["renderer_used"], "python-docx (fallback)")
            self.assertEqual(manifest["counts"]["tables"], 1)
            self.assertEqual(manifest["counts"]["paragraphs"], 2)
            self.assertGreater(manifest["docx"]["file_size_bytes"], 0)
            self.assertEqual(manifest["headings"][0]["text"], "Results")
            self.assertEqual(manifest["tables"][0]["rows"], 2)
            self.assertEqual(manifest["tables"][0]["first_row_preview"], ["Metric", "Value"])

            packaged = run_artifacts(validated)
            roles = {
                item["role"]
                for item in json.loads(
                    Path(packaged.output["artifacts_manifest_path"]).read_text(encoding="utf-8")
                )["files"]
            }
            self.assertIn("qa_post_render_layout_manifest", roles)


class FinalQASummaryContractTests(unittest.TestCase):
    def test_artifacts_write_final_qa_summary_and_package_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("publish report", [], str(Path(tmpdir) / "out"))
            state.status = "completed"
            state.spec["report_profile"] = "engineering_lab_report"
            state.qa["qa_decision"] = "pass"
            state.qa["artifact_completeness_status"] = "pass"
            state.output["workflow_success"] = True
            state.output["renderer_used"] = "pandoc"

            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            docx_path = run_dir / "final.docx"
            docx_path.write_bytes(b"docx placeholder")
            state.output["final_docx_path"] = str(docx_path)
            state.output["published_report_path"] = str(docx_path)

            qa_summary_path = run_dir / "qa_summary.json"
            qa_summary_path.write_text(json.dumps({
                "qa_decision": "pass",
                "artifact_completeness_status": "pass",
            }), encoding="utf-8")
            state.qa["qa_summary_path"] = str(qa_summary_path)

            factuality_path = run_dir / "factuality_report.json"
            factuality_path.write_text(json.dumps({
                "verified_count": 2,
                "blocked_count": 0,
                "claims": [{"claim_id": "C001", "status": "verified"}],
            }), encoding="utf-8")
            state.qa["factuality_report_path"] = str(factuality_path)

            engineering_path = run_dir / "engineering_audit_report.json"
            engineering_path.write_text(json.dumps({
                "status": "review_recommended",
                "warning_count": 1,
                "issue_count": 1,
                "info_count": 0,
                "measurement_count": 3,
                "table_evidence_count": 1,
                "calculation_count": 1,
                "issues": [{"severity": "warning", "check": "claim_table_value_support"}],
            }), encoding="utf-8")
            state.qa["engineering_audit_report_path"] = str(engineering_path)

            (run_dir / "artifact_lint_report.json").write_text(json.dumps({
                "status": "ok",
                "error_count": 0,
                "warning_count": 0,
                "issues": [],
            }), encoding="utf-8")

            post_render_path = run_dir / "post_render_validate_report.json"
            post_render_path.write_text(json.dumps({
                "status": "passed",
                "paragraph_count": 4,
                "table_count": 1,
                "inline_shape_count": 0,
                "issues": [],
            }), encoding="utf-8")
            state.runtime["post_render_validate_report_path"] = str(post_render_path)

            layout_path = run_dir / "post_render_layout_manifest.json"
            layout_path.write_text(json.dumps({
                "status": "passed",
                "counts": {
                    "paragraphs": 4,
                    "tables": 1,
                    "inline_shapes": 0,
                },
                "issues": [],
            }), encoding="utf-8")
            state.runtime["post_render_layout_manifest_path"] = str(layout_path)

            figure_visual_path = run_dir / "figure_visual_quality_report.json"
            figure_visual_path.write_text(json.dumps({
                "status": "review",
                "issue_count": 1,
                "issues": [{"type": "tick_label_overlap", "figure_id": "fig1"}],
                "figures": [{"figure_id": "fig1", "status": "review"}],
            }), encoding="utf-8")
            state.qa["figure_visual_quality_report_path"] = str(figure_visual_path)

            packaged = run_artifacts(state)

            summary_path = Path(packaged.qa["final_qa_summary_path"])
            markdown_path = Path(packaged.qa["final_qa_summary_md_path"])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            manifest = json.loads(
                Path(packaged.output["artifacts_manifest_path"]).read_text(encoding="utf-8")
            )
            roles = {item["role"] for item in manifest["files"]}

            self.assertEqual(summary["overall_status"], "review")
            self.assertEqual(summary["factuality"]["verified_count"], 2)
            self.assertEqual(summary["engineering_audit"]["warning_count"], 1)
            self.assertEqual(summary["engineering_audit"]["table_evidence_count"], 1)
            self.assertEqual(summary["figure_visual_quality"]["issue_count"], 1)
            self.assertEqual(summary["render"]["table_count"], 1)
            self.assertTrue(markdown_path.exists())
            self.assertIn("Engineering audit: review", markdown_path.read_text(encoding="utf-8"))
            self.assertIn("Figure visual quality: review", markdown_path.read_text(encoding="utf-8"))
            self.assertIn("qa_final_qa_summary", roles)
            self.assertIn("qa_final_qa_summary_markdown", roles)
            self.assertIn("qa_figure_visual_quality_report", roles)
            self.assertTrue((Path(packaged.output["published_dir"]) / "qa" / "final_qa_summary.json").exists())
            self.assertTrue((Path(packaged.output["published_dir"]) / "qa" / "figure_visual_quality_report.json").exists())


class TemplateStyleMapContractTests(unittest.TestCase):
    def test_artifacts_write_template_style_map_from_reference_and_rendered_docx(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("publish styled report", [], str(Path(tmpdir) / "out"))
            state.status = "completed"
            state.spec["report_profile"] = "academic_paper"
            state.spec["reference_template_mode"] = "style_reference"
            state.qa["qa_decision"] = "pass"
            state.qa["artifact_completeness_status"] = "pass"
            state.output["workflow_success"] = True
            state.output["renderer_used"] = "pandoc"

            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            reference_path = run_dir / "reference.docx"
            reference = Document()
            reference.add_heading("Reference Heading", level=1)
            reference.add_paragraph("Reference body text.")
            reference.save(reference_path)

            rendered_path = run_dir / "rendered_report.docx"
            rendered = Document()
            rendered.add_heading("Rendered Heading", level=1)
            rendered.add_paragraph("Rendered body text.")
            rendered.save(rendered_path)

            state.output["reference_docx_path"] = str(reference_path)
            state.output["reference_docx_applied"] = True
            state.output["final_docx_path"] = str(rendered_path)
            state.output["published_report_path"] = str(rendered_path)

            packaged = run_artifacts(state)
            style_map_path = Path(packaged.output["template_style_map_path"])
            style_map = json.loads(style_map_path.read_text(encoding="utf-8"))
            manifest = json.loads(
                Path(packaged.output["artifacts_manifest_path"]).read_text(encoding="utf-8")
            )
            roles = {item["role"] for item in manifest["files"]}

            self.assertEqual(style_map["status"], "pass")
            self.assertTrue(style_map["reference_docx_applied"])
            self.assertEqual(style_map["reference_template_mode"], "style_reference")
            self.assertIn("Heading 1", style_map["rendered_docx"]["paragraph_style_counts"])
            self.assertIn("Heading 1", style_map["style_comparison"]["rendered_styles_defined_in_reference"])
            self.assertIn("qa_template_style_map", roles)
            self.assertIn("qa_template_style_map_markdown", roles)
            self.assertTrue((Path(packaged.output["published_dir"]) / "qa" / "template_style_map.md").exists())


class TemplateFieldFillContractTests(unittest.TestCase):
    def test_template_fields_are_rendered_in_front_matter(self):
        state = ReportState.new("write fixed template report", [], "out")
        state.spec["report_profile"] = "custom"
        state.spec["front_matter"] = {
            "title": "Capstone Lab Report",
            "template_fields": {
                "course_name": "Control Systems",
                "student_id": "S12345",
            },
        }
        state.plan["blueprint"] = {"front_matter": {}}

        result = run_front_matter_build(state)

        self.assertIn("**Course Name:** Control Systems", result.plan["front_matter_md"])
        self.assertIn("**Student Id:** S12345", result.plan["front_matter_md"])
        self.assertEqual(result.plan["front_matter"]["template_fields"]["course_name"], "Control Systems")

    def test_artifacts_write_template_field_fill_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("publish fixed template report", [], str(Path(tmpdir) / "out"))
            state.status = "completed"
            state.spec["report_profile"] = "engineering_lab_report"
            state.spec["reference_template_mode"] = "fixed_template"
            state.qa["qa_decision"] = "pass"
            state.qa["artifact_completeness_status"] = "pass"
            state.output["workflow_success"] = True
            state.output["renderer_used"] = "pandoc"
            state.plan["front_matter"] = {
                "title": "Capstone Lab Report",
                "author_block": "Example Student",
                "template_fields": {
                    "course_name": "Control Systems",
                    "student_id": "S12345",
                },
            }

            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            reference_path = run_dir / "reference.docx"
            reference = Document()
            reference.add_paragraph("[Course Name]")
            reference.add_paragraph("[Student Id]")
            reference.save(reference_path)

            rendered_path = run_dir / "rendered_report.docx"
            rendered = Document()
            rendered.add_heading("Capstone Lab Report", level=1)
            rendered.add_paragraph("Example Student")
            rendered.add_paragraph("Course Name: Control Systems")
            rendered.add_paragraph("Student Id: S12345")
            rendered.save(rendered_path)

            state.output["reference_docx_path"] = str(reference_path)
            state.output["reference_docx_applied"] = True
            state.output["final_docx_path"] = str(rendered_path)
            state.output["published_report_path"] = str(rendered_path)

            packaged = run_artifacts(state)
            report_path = Path(packaged.output["template_field_fill_report_path"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            final_summary = json.loads(Path(packaged.output["final_qa_summary_path"]).read_text(encoding="utf-8"))
            manifest = json.loads(
                Path(packaged.output["artifacts_manifest_path"]).read_text(encoding="utf-8")
            )
            roles = {item["role"] for item in manifest["files"]}
            statuses = {field["key"]: field["status"] for field in report["fields"]}

            self.assertEqual(report["status"], "pass")
            self.assertEqual(statuses["course_name"], "filled")
            self.assertEqual(statuses["student_id"], "filled")
            self.assertEqual(final_summary["template_field_fill"]["filled_count"], report["filled_count"])
            self.assertIn("qa_template_field_fill_report", roles)
            self.assertIn("qa_template_field_fill_report_markdown", roles)
            self.assertTrue((Path(packaged.output["published_dir"]) / "qa" / "template_field_fill_report.md").exists())


class ArtifactLintContractTests(unittest.TestCase):
    def test_lint_agent_artifacts_reports_json_paths_and_hints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("lint report", [], str(Path(tmpdir) / "out"))
            state.plan["blueprint"] = {
                "section_order": ["results"],
                "sections": {"results": {"required": True}},
            }
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({"evidence_id": "E001", "content": "Supported measurement."}) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "The report cites an out-of-run evidence ID.",
                    "evidence_ids": ["E999"],
                }]
            }), encoding="utf-8")
            (run_dir / "outline.json").write_text(json.dumps({
                "sections": {"results": {"claim_ids": ["C404"]}}
            }), encoding="utf-8")
            state.checkpoint("AGENT_TASKS")

            result = lint_agent_artifacts(state.job_id)

            self.assertEqual(result["status"], "issues_found")
            self.assertGreater(result["error_count"], 0)
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            json_paths = {issue["json_path"] for issue in report["issues"]}
            self.assertIn("$.claims[0].evidence_ids", json_paths)
            self.assertIn("$.sections.results.claim_ids", json_paths)
            self.assertTrue(all(issue["hint"] for issue in report["issues"]))

    def test_lint_agent_artifacts_accepts_structured_drafts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("lint report", [], str(Path(tmpdir) / "out"))
            state.plan["blueprint"] = {
                "section_order": ["results"],
                "sections": {"results": {"required": True}},
            }
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({"evidence_id": "E001", "content": "The pilot enrolled 42 participants."}) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "The pilot enrolled 42 participants.",
                    "evidence_ids": ["E001"],
                }]
            }), encoding="utf-8")
            (run_dir / "outline.json").write_text(json.dumps({
                "sections": {"results": {"claim_ids": ["C001"]}}
            }), encoding="utf-8")
            (run_dir / "structured_drafts.json").write_text(json.dumps({
                "sections": {
                    "results": {
                        "sentences": [{
                            "text": "The pilot enrolled 42 participants.",
                            "claim_ids": ["C001"],
                            "evidence_ids": ["E001"],
                        }]
                    }
                }
            }), encoding="utf-8")
            state.checkpoint("AGENT_TASKS")

            result = lint_agent_artifacts(state.job_id)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["error_count"], 0)
            self.assertTrue(Path(result["report_path"]).exists())


class EngineeringAuditContractTests(unittest.TestCase):
    def test_engineering_audit_flags_unit_support_and_bad_calculation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({"evidence_id": "E001", "content": "Measured length was 5 cm."}) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "Measured length was 5 mm.",
                    "evidence_ids": ["E001"],
                }]
            }), encoding="utf-8")
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir()
            (draft_dir / "calculations.md").write_text(
                "# Calculations\n\nThe reported length is 5 mm.\n\n5 + 5 = 11 cm\n",
                encoding="utf-8",
            )
            state.checkpoint("AGENT_TASKS")

            result = run_engineering_audit(state.job_id)

            self.assertEqual(result["status"], "review_recommended")
            checks = {issue["check"] for issue in result["issues"]}
            self.assertIn("claim_unit_support", checks)
            self.assertIn("calculation_result", checks)
            self.assertTrue(Path(result["report_path"]).exists())

    def test_engineering_audit_accepts_supported_measurement_and_calculation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({"evidence_id": "E001", "content": "Measured length was 5 cm."}) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "Measured length was 5 cm.",
                    "evidence_ids": ["E001"],
                }]
            }), encoding="utf-8")
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir()
            (draft_dir / "calculations.md").write_text(
                "# Calculations\n\nThe measured length is 5 cm.\n\n5 + 5 = 10 cm\n",
                encoding="utf-8",
            )
            state.checkpoint("AGENT_TASKS")

            result = run_engineering_audit(state.job_id)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["warning_count"], 0)
            self.assertEqual(result["calculation_count"], 1)
            self.assertGreaterEqual(result["measurement_count"], 2)

    def test_engineering_audit_checks_claim_values_against_table_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({
                    "evidence_id": "E001",
                    "source_file_name": "measurements.csv",
                    "file_type": "csv",
                    "granularity": "table_row",
                    "content": json.dumps({
                        "metric": "participants",
                        "value": "42",
                        "unit": "count",
                    }),
                    "table_data": [
                        ["metric", "value", "unit"],
                        ["participants", "42", "count"],
                    ],
                }) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "The participant table reports 41 participants.",
                    "evidence_ids": ["E001"],
                }]
            }), encoding="utf-8")
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir()
            (draft_dir / "data.md").write_text("# Data\n\nThe table reports participants.\n", encoding="utf-8")
            state.checkpoint("AGENT_TASKS")

            result = run_engineering_audit(state.job_id)

            self.assertEqual(result["status"], "review_recommended")
            self.assertEqual(result["table_evidence_count"], 1)
            checks = {issue["check"] for issue in result["issues"]}
            self.assertIn("claim_table_value_support", checks)
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["tables"][0]["row_count"], 2)

    def test_engineering_audit_accepts_matching_table_claim_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                json.dumps({
                    "evidence_id": "E001",
                    "source_file_name": "measurements.csv",
                    "file_type": "csv",
                    "granularity": "table_row",
                    "content": json.dumps({"metric": "participants", "value": "42"}),
                    "table_data": [["metric", "value"], ["participants", "42"]],
                }) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "The participant table reports 42 participants.",
                    "evidence_ids": ["E001"],
                }]
            }), encoding="utf-8")
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir()
            (draft_dir / "data.md").write_text("# Data\n\nParticipant count is listed in the source table.\n", encoding="utf-8")
            state.checkpoint("AGENT_TASKS")

            result = run_engineering_audit(state.job_id)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["table_evidence_count"], 1)
            self.assertNotIn("claim_table_value_support", {issue["check"] for issue in result["issues"]})

    def test_engineering_audit_accepts_rounded_table_claim_values_and_page_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(
                "\n".join([
                    json.dumps({
                        "evidence_id": "E001",
                        "source_file_name": "measurements.md",
                        "file_type": "md",
                        "content": "PDF page 12 records airflow 6.0 m/s.",
                    }),
                    json.dumps({
                        "evidence_id": "E002",
                        "source_file_name": "measurements.md",
                        "file_type": "md",
                        "content": "| metric | value |\n|---|---:|\n| COP initial | 1.587793 |\n| COP final | 5.722860 |",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "C001",
                    "claim_text": "PDF page 12 shows airflow 6.0 m/s and COP rises from 1.588 to 5.723.",
                    "evidence_ids": ["E001", "E002"],
                }]
            }), encoding="utf-8")
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir()
            (draft_dir / "data.md").write_text(
                "# Data\n\nPDF page 12 shows airflow 6.0 m/s and rounded COP values.\n",
                encoding="utf-8",
            )
            state.checkpoint("AGENT_TASKS")

            result = run_engineering_audit(state.job_id)

            self.assertNotIn("claim_table_value_support", {issue["check"] for issue in result["issues"]})
            self.assertNotIn("number_without_unit", {issue["check"] for issue in result["issues"]})


class DocumentationContractTests(unittest.TestCase):
    def test_agents_doc_does_not_show_removed_family_cli(self):
        text = Path("AGENTS.md").read_text(encoding="utf-8")

        self.assertNotIn("--family", text)
        self.assertNotIn("state.spec." + "report_family", text)
        legacy_triplet = "|".join(["academic_report", "work_report", "hybrid_report"])
        self.assertNotIn(legacy_triplet, text)

    def test_pillow_dependency_is_consistent(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        requirements = Path("requirements.txt").read_text(encoding="utf-8")

        self.assertIn("Pillow>=10.0.0", pyproject)
        self.assertIn("Pillow>=10.0.0", requirements)

    def test_short_skill_documents_yaml_tool_surface(self):
        skill_text = Path("agent_skill/SKILL.md").read_text(encoding="utf-8")
        skill_yaml = yaml.safe_load(Path("agent_skill/skill.yaml").read_text(encoding="utf-8"))

        tool_names = [tool["name"] for tool in skill_yaml["tools"]]
        for tool_name in tool_names:
            with self.subTest(tool=tool_name):
                self.assertIn(f"`{tool_name}`", skill_text)

    def test_short_skill_points_to_reference_library(self):
        skill_text = Path("agent_skill/SKILL.md").read_text(encoding="utf-8")

        # SKILL.md stays a lean hub that links every reference file one level deep.
        skill_pointers = [
            "## Reference Library",
            "reference/setup-and-preflight.md",
            "reference/profiles.md",
            "reference/tools.md",
            "reference/authoring.md",
            "reference/figures.md",
            "reference/engineering-lab.md",
            "reference/revision.md",
            "reference/benchmarking.md",
            "python scripts/render_skill_docs.py --check",
            "python scripts/sync_codex_skill.py --write",
        ]
        for pointer in skill_pointers:
            with self.subTest(pointer=pointer):
                self.assertIn(pointer, skill_text)

    def test_reference_files_document_operational_guardrails(self):
        reference = Path("agent_skill/reference")

        # Detailed guardrails live in one-level-deep reference files, not SKILL.md.
        expected = {
            "setup-and-preflight.md": [
                "## Preflight Decision Examples",
                "allow_degraded_render=True",
                '"pandoc": "accept_degraded"',
                "enable_research=True",
                'notebooklm_notebook_id="notebook-id-from-user"',
            ],
            "authoring.md": [
                "`structured_drafts.json`",
                "remap_agent_artifacts(job_id=..., previous_job_id=...)",
                "Validation Failure Repair",
            ],
            "revision.md": [
                "`preview_revision_diff`",
                "`submit_revision_plan`",
            ],
            "engineering-lab.md": [
                "Chinese Engineering Publish Checklist",
                "`template_field_fill_report_path`",
                "`final_qa_summary_path`",
            ],
        }
        for file_name, phrases in expected.items():
            text = (reference / file_name).read_text(encoding="utf-8")
            for phrase in phrases:
                with self.subTest(file=file_name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_generated_skill_doc_blocks_are_current(self):
        script_path = Path("scripts/render_skill_docs.py")
        spec = importlib.util.spec_from_file_location("render_skill_docs", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        results = module.render_docs(Path("."), write=False)
        self.assertTrue(results)
        for result in results:
            with self.subTest(path=str(result["path"])):
                self.assertFalse(result["changed"])

    def test_sync_codex_skill_script_copies_skill_files(self):
        script_path = Path("scripts/sync_codex_skill.py")
        spec = importlib.util.spec_from_file_location("sync_codex_skill", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir) / "report-workflow"

            dry_run_ops = module.sync_skill(Path("agent_skill"), dest_dir, write=False)
            # SKILL.md + skill.yaml + every reference/ file.
            self.assertGreaterEqual(len(dry_run_ops), 3)
            self.assertFalse(dest_dir.exists())

            write_ops = module.sync_skill(Path("agent_skill"), dest_dir, write=True)
            self.assertEqual(len(write_ops), len(dry_run_ops))
            for source, dest in write_ops:
                self.assertTrue(dest.exists())
                self.assertEqual(
                    source.read_text(encoding="utf-8"),
                    dest.read_text(encoding="utf-8"),
                )

            synced_names = {dest.name for _, dest in write_ops}
            self.assertIn("SKILL.md", synced_names)
            self.assertIn("skill.yaml", synced_names)
            self.assertIn("tools.md", synced_names)
            self.assertTrue((dest_dir / "reference" / "tools.md").exists())
            self.assertFalse((dest_dir / "agent_instructions.md").exists())


if __name__ == "__main__":
    unittest.main()
