import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.artifacts import run_artifacts
from report_workflow.nodes.citation_bind import (
    default_gbt7714_standard,
    resolve_citations_publication,
)
from report_workflow.nodes.qa_gate import run_qa_gate
from report_workflow.nodes.reference_verify import run_reference_verify
from report_workflow.nodes.scholarly_quality import run_scholarly_quality
from report_workflow.state import ReportState, run_dir_for


def _write_section(run_dir: Path, section_id: str, text: str) -> str:
    section_dir = run_dir / "section_drafts"
    section_dir.mkdir(parents=True, exist_ok=True)
    path = section_dir / f"{section_id}.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _academic_state(tmpdir: str) -> ReportState:
    state = ReportState.new("write academic paper", [], str(Path(tmpdir) / "out"))
    state.spec["report_profile"] = "academic_paper"
    state.plan["front_matter"] = {
        "title": "Deterministic Validation for Evidence Backed Report Generation",
    }
    state.plan["outline"] = {
        "paper_spine": {
            "problem": "Evidence-backed reports need stronger scholarly structure.",
            "gap": "Existing drafts often lack explicit method and limitation framing.",
            "objective": "Assess deterministic QA signals for report generation.",
            "contribution": "A review-grade audit identifies missing scholarly cues.",
            "method_basis": "Static source and artifact inspection.",
            "main_limitation": "The audit cannot judge novelty by itself.",
        },
        "sections": {
            "abstract": {"claim_ids": []},
            "introduction": {"claim_ids": ["c1"], "figure_ids": ["1"]},
            "methods": {"claim_ids": ["c1"]},
            "results": {"claim_ids": ["c1"], "figure_ids": ["1"]},
            "discussion": {"claim_ids": ["c1"]},
            "limitations": {"claim_ids": []},
            "conclusion": {"claim_ids": []},
            "references": {"claim_ids": []},
        },
    }
    return state


class ScholarlyQualityNodeTests(unittest.TestCase):
    def test_passes_strong_academic_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _academic_state(tmpdir)
            run_dir = run_dir_for(state)
            state.drafts["section_drafts"] = {
                "abstract": _write_section(
                    run_dir,
                    "abstract",
                    "# Abstract\n\nBackground and objective are summarized with methods, principal findings, significance, and limitation.",
                ),
                "introduction": _write_section(
                    run_dir,
                    "introduction",
                    "# Introduction\n\nThe problem is that evidence-backed reports need stronger scholarly structure. However, the gap is that drafts often lack a stable objective and contribution. This paper evaluates deterministic audit signals and contributes a review-grade quality layer.",
                ),
                "methods": _write_section(
                    run_dir,
                    "methods",
                    "# Methods\n\nWe used source data from parsed artifacts, followed a documented procedure, recorded software version and parameter settings, and filtered transformed table evidence before analysis.",
                ),
                "results": _write_section(
                    run_dir,
                    "results",
                    "# Results\n\nFigure 1 summarizes the supported comparison. [FIGURE:1]\n\nFigure 1: Supported evidence coverage by section.",
                ),
                "discussion": _write_section(
                    run_dir,
                    "discussion",
                    "# Discussion\n\nThe result indicates where review attention should be focused.",
                ),
            }
            merged = run_dir / "merged_draft.md"
            merged.write_text(
                "\n\n".join(Path(path).read_text(encoding="utf-8") for path in state.drafts["section_drafts"].values()),
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            (run_dir / "section_drafts" / "figure_plan.json").write_text(json.dumps({
                "figures": [{
                    "figure_id": "1",
                    "figure_type": "bar",
                    "title": "Supported Evidence Coverage",
                    "xlabel": "Section",
                    "ylabel": "Evidence count",
                    "data": {"labels": ["Methods", "Results"], "series": [{"name": "Evidence", "values": [2, 3]}]},
                }]
            }), encoding="utf-8")

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["issues"], [])

    def test_flags_missing_gap_objective_and_spine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _academic_state(tmpdir)
            state.plan["outline"].pop("paper_spine")
            run_dir = run_dir_for(state)
            state.drafts["section_drafts"] = {
                "introduction": _write_section(
                    run_dir,
                    "introduction",
                    "# Introduction\n\nReports are important. The system is described in general terms.",
                ),
                "methods": _write_section(
                    run_dir,
                    "methods",
                    "# Methods\n\nSource data were parsed with a documented procedure, parameter settings, and filtering rules.",
                ),
            }

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))
            issue_types = {issue["type"] for issue in report["issues"]}

            self.assertIn("paper_spine_missing", issue_types)
            self.assertIn("introduction_spine_weak", issue_types)
            self.assertEqual(report["status"], "review")

    def test_flags_template_text_left_in_paper_spine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _academic_state(tmpdir)
            state.plan["outline"]["paper_spine"]["problem"] = "For academic_paper: the concrete problem or phenomenon."

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))
            issue_types = {issue["type"] for issue in report["issues"]}

            self.assertIn("paper_spine_template_text", issue_types)
            self.assertEqual(report["checks"]["spine"], "review")

    def test_flags_methods_that_contain_findings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _academic_state(tmpdir)
            run_dir = run_dir_for(state)
            state.drafts["section_drafts"] = {
                "introduction": _write_section(
                    run_dir,
                    "introduction",
                    "# Introduction\n\nThe problem and gap motivate the objective. This paper contributes an audit layer.",
                ),
                "methods": _write_section(
                    run_dir,
                    "methods",
                    "# Methods\n\nWe used source data and a documented procedure. The results show that the method is superior.",
                ),
            }

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))

            self.assertIn("methods_contains_findings", {issue["type"] for issue in report["issues"]})

    def test_flags_figure_caption_units_and_error_definition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _academic_state(tmpdir)
            run_dir = run_dir_for(state)
            state.drafts["section_drafts"] = {
                "introduction": _write_section(
                    run_dir,
                    "introduction",
                    "# Introduction\n\nThe problem and gap motivate the objective. This paper contributes an audit layer.",
                ),
                "methods": _write_section(
                    run_dir,
                    "methods",
                    "# Methods\n\nWe used source data, procedure settings, software version, and filtering parameters.",
                ),
                "results": _write_section(
                    run_dir,
                    "results",
                    "# Results\n\nFigure 2 summarizes uncertainty. [FIGURE:2]",
                ),
            }
            (run_dir / "section_drafts" / "figure_plan.json").write_text(json.dumps({
                "figures": [{
                    "figure_id": "2",
                    "figure_type": "error_bar",
                    "title": "Uncertainty",
                    "xlabel": "Sample",
                    "ylabel": "Value",
                    "data": {"labels": ["A", "B"], "series": [{"name": "Mean", "values": [1, 2], "errors": [0.1, 0.2]}]},
                }]
            }), encoding="utf-8")

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))
            issue_types = {issue["type"] for issue in report["issues"]}

            self.assertIn("figure_axis_unit_missing", issue_types)
            self.assertIn("error_bar_uncertainty_undefined", issue_types)
            self.assertIn("figure_caption_missing", issue_types)

    def test_flags_chinese_engineering_jargon_and_missing_lab_spine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("write engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            state.plan["outline"] = {"sections": {"procedure": {"claim_ids": ["c1"]}}}
            run_dir = run_dir_for(state)
            procedure = _write_section(
                run_dir,
                "procedure",
                "# 實驗步驟\n\n本 workflow 的 claim_matrix 洩漏到正文。",
            )
            state.drafts["section_drafts"] = {"procedure": procedure}
            state.drafts["merged_draft_md"] = procedure

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))
            issue_types = {issue["type"] for issue in report["issues"]}

            self.assertIn("lab_spine_missing", issue_types)
            self.assertIn("workflow_jargon_in_body", issue_types)
            self.assertEqual(report["status"], "failed")

    def test_agent_and_tool_terms_are_not_hard_blocked_when_legitimate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("write engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            state.plan["outline"] = {
                "lab_spine": {
                    "experiment_purpose": "Measure tool wear after reagent exposure.",
                    "variables": "Exposure time and tool wear depth in mm.",
                    "apparatus_procedure_basis": "Calibrated microscope procedure.",
                    "measurement_basis": "Recorded measurement table.",
                    "uncertainty_limitations": "Instrument resolution limits.",
                },
                "sections": {"procedure": {"claim_ids": ["c1"]}},
            }
            run_dir = run_dir_for(state)
            procedure = _write_section(
                run_dir,
                "procedure",
                "# Procedure\n\nThe reagent was applied before measuring tool wear with a calibrated software tool.",
            )
            state.drafts["section_drafts"] = {"procedure": procedure}
            state.drafts["merged_draft_md"] = procedure

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))

            self.assertNotIn("workflow_jargon_in_body", {issue["type"] for issue in report["issues"]})
            self.assertEqual(report["hard_issue_count"], 0)

    def test_publication_draft_is_audited_before_pre_citation_merged_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("write engineering report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "engineering_lab_report"
            state.plan["outline"] = {
                "lab_spine": {
                    "experiment_purpose": "Measure output voltage.",
                    "variables": "Input setting and voltage in V.",
                    "apparatus_procedure_basis": "Bench procedure.",
                    "measurement_basis": "Recorded instrument readings.",
                    "uncertainty_limitations": "Meter uncertainty.",
                },
                "sections": {"procedure": {"claim_ids": ["c1"]}},
            }
            run_dir = run_dir_for(state)
            merged = run_dir / "merged_draft.md"
            publication = run_dir / "merged_draft_cited.md"
            merged.write_text("# Procedure\n\nThe claim_matrix artifact should not be audited here.", encoding="utf-8")
            publication.write_text("# Procedure\n\nThe voltage was measured with a calibrated meter.", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["publication_draft_md"] = str(publication)

            result = run_scholarly_quality(state)
            report = json.loads(Path(result.qa["scholarly_quality_report_path"]).read_text(encoding="utf-8"))

            self.assertNotIn("workflow_jargon_in_body", {issue["type"] for issue in report["issues"]})
            self.assertEqual(report["hard_issue_count"], 0)


class ScholarlyCitationTests(unittest.TestCase):
    def test_engineering_report_uses_gbt_7714_2015_numeric_references(self):
        evidence = [{
            "evidence_id": "E001",
            "source_id": "S001",
            "source_role": "primary_source",
            "source_file_name": "experiment_notes.pdf",
            "file_type": "pdf",
            "author": "Lab Team",
            "title": "Experiment Notes",
            "year": "2026",
        }]

        resolved, audit, refs, _, _ = resolve_citations_publication(
            "測試結果來自量測資料 [CITE:E001]。",
            evidence,
            [],
            citation_style="gb_t_7714_2015",
            gbt7714_as_of=date(2026, 5, 11),
        )

        self.assertIn("[1]", resolved)
        self.assertTrue(all(item["resolved"] for item in audit))
        self.assertTrue(refs[0].startswith("[1] Lab Team. Experiment Notes[Z]. 2026."))
        self.assertIn("GB/T 7714-2015", refs[0])

    def test_academic_paper_citation_remains_apa_by_default(self):
        evidence = [{
            "evidence_id": "E001",
            "source_id": "S001",
            "source_role": "primary_source",
            "source_file_name": "source_paper.pdf",
            "file_type": "pdf",
        }]

        resolved, _audit, refs, _, _ = resolve_citations_publication(
            "The claim is supported [CITE:E001].",
            evidence,
            [],
        )

        self.assertNotIn("[1]", resolved)
        # Author-year form rather than numeric, which is what this test is
        # about. It used to expect "source & paper" — the file name split on
        # its underscore and joined as two surnames, which credited "paper"
        # as a co-author of "source". A file name says nothing about who
        # wrote a work or how many did, so the tag no longer claims to.
        self.assertIn("(source (n.d.))", resolved.lower())
        self.assertTrue(refs[0].startswith("source."))
        # The file name is still shown in full, in the title position, where
        # it states what the file is called and claims nothing more.
        self.assertIn("*source_paper*", refs[0])

    def test_the_banned_phrase_list_speaks_chinese_too(self):
        """One hundred and thirty-five phrases, none of them Chinese.

        The matching is language-neutral; the vocabulary was not. A report in
        Chinese — the ordinary case here — got no prose-quality enforcement
        at all. Every entry added is the direct equivalent of one already on
        the same list, so this widens the rule's reach without widening the
        rule: "不言而喻" for "it goes without saying", "顯而易見" for
        "obviously", "如前所述" for "as previously mentioned".
        """
        from report_workflow.policies.policy_pack import get_policy

        for profile in ("engineering_lab_report", "business_report"):
            banned = get_policy(profile).banned_phrases
            chinese = [p for p in banned if any("一" <= c <= "鿿" for c in p)]
            self.assertTrue(chinese, profile)

    def test_an_appeal_to_the_obvious_is_caught_in_chinese(self):
        from report_workflow.policies.policy_pack import get_policy

        banned = set(get_policy("engineering_lab_report").banned_phrases)
        self.assertTrue(any(p in "眾所周知，有效度會隨流量上升。" for p in banned))

    def test_ordinary_chinese_prose_is_not_flagged(self):
        """A measured sentence must survive: the cost of a filler list is
        false positives, and a report that states its numbers is the thing
        this tool exists to produce."""
        from report_workflow.policies.policy_pack import get_policy

        banned = set(get_policy("engineering_lab_report").banned_phrases)
        for sentence in ("量測顯示有效度隨流量上升，斜率為 2.12。",
                         "由最小平方法擬合得到 R² 為 0.9645。",
                         "明顯的趨勢需要更多試驗才能確認。"):
            self.assertFalse(any(p in sentence for p in banned), sentence)

    def test_gbt_7714_2025_is_not_default_before_effective_date(self):
        self.assertEqual(default_gbt7714_standard(date(2026, 5, 11)), "GB/T 7714-2015")
        self.assertEqual(default_gbt7714_standard(date(2026, 7, 1)), "GB/T 7714-2025")

    def _curate_gbt(self, tmpdir, entries):
        state = ReportState.new("publish engineering report", [], str(Path(tmpdir) / "out"))
        state.spec["report_profile"] = "engineering_lab_report"
        run_dir = run_dir_for(state)
        ref_path = run_dir / "publication_reference_list.md"
        body = "\n".join(f"[{n}] {e}" for n, e in enumerate(entries, start=1))
        ref_path.write_text(f"## References\n\n{body}\n", encoding="utf-8")
        state.citations["publication_reference_list_path"] = str(ref_path)
        state.citations["publication_citation_style"] = "gb_t_7714_2015"
        run_reference_verify(state)
        return ref_path.read_text(encoding="utf-8")

    def test_gbt_7714_publications_survive_reference_verify_curation(self):
        """Real GB/T references must not be curated away.

        The type marker carries the distinction: [J], [M], [D], [S] are
        publications. The APA-shaped candidate test matches none of these
        notations, so a GB/T journal article once read as non-publication —
        which is why curation used to be skipped wholesale for this style.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._curate_gbt(tmpdir, [
                "王小明. 板式熱交換器結垢對熱傳效能之影響[J]. 機械工程學報, 2024, 60(3): 45-52.",
                "Incropera F P. Fundamentals of Heat and Mass Transfer[M]. New York: Wiley, 2007.",
            ])
            self.assertIn("機械工程學報", content)
            self.assertIn("Fundamentals of Heat and Mass Transfer[M]", content)

    def test_gbt_7714_local_artifacts_are_curated_out(self):
        """A source file is not a publication in either notation.

        Skipping curation for GB/T meant every Chinese-language report shipped
        its own CSV in the reference list — the APA path had excluded these
        since 4.24.0, and the two notations disagreed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._curate_gbt(tmpdir, [
                "data[DS]. (GB/T 7714-2025)",
                "Lab Team. Experiment Notes[Z]. 2026.",
                "王小明. 板式熱交換器結垢[J]. 機械工程學報, 2024, 60(3): 45-52.",
            ])
            self.assertNotIn("[DS]", content)
            self.assertNotIn("[Z]", content)
            self.assertIn("機械工程學報", content)
            # Renumbered from one, not left with the gap the drops would make.
            self.assertIn("[1] 王小明", content)

    def test_gbt_7714_unknown_type_marker_is_kept(self):
        """Fail open: an unfamiliar type code must not silently delete a
        reference. Dropping a real citation is worse than keeping a doubtful
        one, because only the first is invisible to the author."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content = self._curate_gbt(tmpdir, ["某作者. 新型式資料[XX]. 2026."])
            self.assertIn("[XX]", content)


class ScholarlyPackagingTests(unittest.TestCase):
    def test_qa_gate_blocks_scholarly_hard_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("validate academic paper", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "academic_paper"
            run_dir = run_dir_for(state)
            section_path = _write_section(
                run_dir,
                "introduction",
                "# Introduction\n\nThe supported claim is stated [CITE:E001].\n",
            )
            ledger = run_dir / "evidence_ledger.jsonl"
            ledger.write_text(json.dumps({"evidence_id": "E001", "quote": "supported claim"}) + "\n", encoding="utf-8")
            sentence_map = run_dir / "sentence_map.jsonl"
            sentence_map.write_text(
                json.dumps({"sentence_id": "S001", "section_id": "introduction", "evidence_ids": ["E001"]}) + "\n",
                encoding="utf-8",
            )
            factuality = run_dir / "factuality_report.json"
            factuality.write_text(
                json.dumps({"verified_count": 1, "blocked_count": 0, "disputed_count": 0, "claims": []}),
                encoding="utf-8",
            )
            scholarly = run_dir / "scholarly_quality_report.json"
            scholarly.write_text(
                json.dumps({
                    "status": "failed",
                    "hard_issue_count": 1,
                    "issue_count": 1,
                    "issues": [{
                        "type": "workflow_jargon_in_body",
                        "severity": "hard",
                        "detail": "Workflow jargon leaked into publication prose.",
                    }],
                }),
                encoding="utf-8",
            )

            state.sources["source_registry"] = [{"parse_status": "parsed", "parsed_content": "supported claim"}]
            state.sources["evidence_ledger_path"] = str(ledger)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "C001"}]}
            state.plan["outline"] = {"sections": {"introduction": {}}}
            state.drafts["section_drafts"] = {"introduction": section_path}
            state.drafts["sentence_map_path"] = str(sentence_map)
            state.drafts["merged_draft_md"] = section_path
            state.qa["factuality_report_path"] = str(factuality)
            state.qa["scholarly_quality_report_path"] = str(scholarly)

            with self.assertRaises(QAHardBlockError) as raised:
                run_qa_gate(state)

            self.assertIn("scholarly quality hard issues", str(raised.exception))

    def test_artifacts_package_scholarly_quality_reports_and_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("publish report", [], str(Path(tmpdir) / "out"))
            state.status = "completed"
            state.spec["report_profile"] = "academic_paper"
            state.qa["qa_decision"] = "pass"
            state.qa["artifact_completeness_status"] = "pass"
            state.output["workflow_success"] = True
            run_dir = run_dir_for(state)
            docx = run_dir / "report.docx"
            docx.write_bytes(b"docx")
            state.output["final_docx_path"] = str(docx)
            state.output["published_report_path"] = str(docx)

            qa_summary = run_dir / "qa_summary.json"
            qa_summary.write_text(json.dumps({"qa_decision": "pass", "artifact_completeness_status": "pass"}), encoding="utf-8")
            state.qa["qa_summary_path"] = str(qa_summary)
            factuality = run_dir / "factuality_report.json"
            factuality.write_text(json.dumps({"verified_count": 1, "blocked_count": 0, "claims": []}), encoding="utf-8")
            state.qa["factuality_report_path"] = str(factuality)
            scholarly_json = run_dir / "scholarly_quality_report.json"
            scholarly_json.write_text(json.dumps({
                "status": "review",
                "issue_count": 1,
                "hard_issue_count": 0,
                "review_issue_count": 1,
                "issues": [{"type": "paper_spine_missing"}],
            }), encoding="utf-8")
            scholarly_md = run_dir / "scholarly_quality_report.md"
            scholarly_md.write_text("# Scholarly Quality Report\n", encoding="utf-8")
            state.qa["scholarly_quality_report_path"] = str(scholarly_json)
            state.qa["scholarly_quality_report_md_path"] = str(scholarly_md)

            packaged = run_artifacts(state)
            summary = json.loads(Path(packaged.qa["final_qa_summary_path"]).read_text(encoding="utf-8"))
            roles = {
                item["role"]
                for item in json.loads(Path(packaged.output["artifacts_manifest_path"]).read_text(encoding="utf-8"))["files"]
            }

            self.assertEqual(summary["scholarly_quality"]["status"], "review")
            self.assertEqual(summary["overall_status"], "review")
            self.assertIn("qa_scholarly_quality_report", roles)
            self.assertIn("qa_scholarly_quality_report_markdown", roles)


if __name__ == "__main__":
    unittest.main()
