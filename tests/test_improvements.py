"""Tests for workflow improvements: sanity gate, table styling, facts freeze, query evidence."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Test pre-render sanity gate
from report_workflow.nodes.docx_render import _pre_render_sanity_check
from report_workflow.nodes.intake import infer_report_family_detail
from report_workflow.nodes.reference_verify import _is_publication_reference_candidate

# Test query_evidence
from report_workflow.agent_wrapper import query_evidence

# Test policy subtype
from report_workflow.policies.policy_pack import get_policy, _POLICY_CACHE


class PreRenderSanityGateTests(unittest.TestCase):
    """Test _pre_render_sanity_check function."""

    def test_clean_document_passes(self):
        md = "# Title\n\n## Abstract\n\nSome text here.\n\n## Introduction\n\nMore text.\n"
        issues = _pre_render_sanity_check(md)
        self.assertEqual(issues, [])

    def test_duplicated_heading_detected(self):
        md = "# Title\n\n## Abstract\n\nText.\n\n## Abstract\n\nDuplicate.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Duplicated heading" in i for i in issues))

    def test_duplicated_references_detected(self):
        md = "## References\n\nRef1.\n\n## References\n\nRef2.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Multiple References" in i for i in issues))

    def test_placeholder_metadata_detected(self):
        md = "Author: [Author Name]\nUniversity: [University]\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Placeholder metadata" in i for i in issues))

    def test_unresolved_cite_detected(self):
        md = "This claim [CITE:E001] is unresolved.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("[CITE:]" in i for i in issues))

    def test_prompt_and_metadata_leakage_detected(self):
        md = (
            "# {.Title} Revise the base document as an academic report\n\n"
            "Author\n\nIndependent Researcher\n\n"
            "Correspondence: author@example.com\n\n"
            "Keywords: Corpus, Backtrader, Pydantic, Kelly, Bayesian, Ollama\n"
        )
        issues = _pre_render_sanity_check(md)
        joined = "; ".join(issues)
        self.assertIn("Pandoc title marker", joined)
        self.assertIn("raw task instruction", joined)
        self.assertIn("generic template", joined)
        self.assertIn("implementation-noise", joined)

    def test_prompt_fragment_detected(self):
        prompt = "Write an admissions-facing academic project report on deterministic compilation architecture."
        md = f"# Title\n\n{prompt}\n"
        issues = _pre_render_sanity_check(md, forbidden_fragments=[prompt])
        self.assertTrue(any("Raw prompt fragment" in i for i in issues))

    def test_internal_pseudo_citation_detected(self):
        md = "The system is deterministic (source & corpus (n.d.)).\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("pseudo-citation" in i for i in issues))

    def test_internal_source_corpus_detected(self):
        md = "## References\n\n- source & corpus. (2026). *source_corpus* [Text file].\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("source_corpus" in i for i in issues))

    def test_internal_markers_detected(self):
        md = "Some text [Source: internal file] here.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Internal markers" in i for i in issues))

    def test_end_of_report_sentinel_detected(self):
        md = "## End of Main Report\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("sentinel" in i.lower() for i in issues))

    def test_facts_freeze_pass(self):
        md = "We analyzed 388 files with 5,171 nodes.\n"
        freeze = {"total_files": "388", "graph_nodes": "5,171"}
        issues = _pre_render_sanity_check(md, freeze)
        self.assertEqual(issues, [])

    def test_facts_freeze_violation(self):
        md = "We analyzed 386 files.\n"
        freeze = {"total_files": "388"}
        issues = _pre_render_sanity_check(md, freeze)
        self.assertTrue(any("Facts freeze violation" in i for i in issues))

    def test_ascii_art_detected(self):
        md = "```\n┌──────┐\n│ Box  │\n└──────┘\n```\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("ASCII art" in i for i in issues))

    def test_traceability_appendix_detected(self):
        md = "See traceability_appendix for details.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Traceability appendix" in i for i in issues))


class QueryEvidenceTests(unittest.TestCase):
    """Test query_evidence agent tool."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.job_id = "test_query_job"
        self.run_dir = Path(os.path.expanduser("~")) / ".hermes" / "workflow_runs" / self.job_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Write test evidence ledger
        entries = []
        for i in range(1, 26):
            entries.append(json.dumps({
                "evidence_id": f"E{i:03d}",
                "source_file_name": f"file_{i}.py",
                "evidence_type": "code_artifact",
                "quote": f"Evidence text for entry {i}",
            }))
        (self.run_dir / "evidence_ledger.jsonl").write_text(
            "\n".join(entries), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_query_by_ids(self):
        result = query_evidence(self.job_id, evidence_ids=["E001", "E005"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returned"], 2)
        self.assertEqual(result["total_entries"], 25)
        ids = {e["evidence_id"] for e in result["entries"]}
        self.assertEqual(ids, {"E001", "E005"})

    def test_query_missing_ids(self):
        result = query_evidence(self.job_id, evidence_ids=["E001", "E999"])
        self.assertEqual(result["returned"], 1)
        self.assertIn("E999", result["missing_ids"])

    def test_paginated_browsing(self):
        result = query_evidence(self.job_id, offset=0, limit=10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returned"], 10)
        self.assertTrue(result["has_more"])

    def test_paginated_last_page(self):
        result = query_evidence(self.job_id, offset=20, limit=10)
        self.assertEqual(result["returned"], 5)
        self.assertFalse(result["has_more"])

    def test_limit_capped_at_50(self):
        result = query_evidence(self.job_id, offset=0, limit=100)
        # Should be capped internally but return all 25 since total < 50
        self.assertEqual(result["returned"], 25)

    def test_missing_ledger(self):
        result = query_evidence("nonexistent_job_id")
        self.assertEqual(result["status"], "error")


class PolicySubtypeTests(unittest.TestCase):
    """Test policy subtype overrides."""

    def setUp(self):
        _POLICY_CACHE.clear()

    def test_default_academic_requires_structure(self):
        policy = get_policy("academic_report")
        self.assertTrue(policy.abstract.structure_required)
        self.assertEqual(policy.abstract.word_count_min, 180)

    def test_admissions_subtype_relaxes_abstract(self):
        policy = get_policy("academic_report", subtype="admissions_report")
        self.assertFalse(policy.abstract.structure_required)
        self.assertTrue(policy.abstract.allow_plain_paragraph)
        self.assertEqual(policy.abstract.word_count_min, 150)
        self.assertEqual(policy.abstract.word_count_max, 250)

    def test_subtype_preserves_other_policies(self):
        policy = get_policy("academic_report", subtype="admissions_report")
        # Other policies should remain unchanged
        self.assertTrue(policy.front_matter.required)
        self.assertTrue(policy.claim.thesis_required)
        self.assertEqual(policy.citation.style, "APA")

    def test_unknown_subtype_returns_base(self):
        policy = get_policy("academic_report", subtype="unknown_type")
        # Should fall back to base academic policy
        self.assertTrue(policy.abstract.structure_required)

    def test_intake_infers_admissions_detail(self):
        detail = infer_report_family_detail(
            "Write an admissions-facing academic project report for graduate school admissions.",
            "academic_report",
        )
        self.assertEqual(detail, "admissions_project_report")


class ReferenceCurationTests(unittest.TestCase):
    def test_internal_text_reference_is_not_publication_candidate(self):
        self.assertFalse(
            _is_publication_reference_candidate("source & corpus. (2026). source_corpus [Text file].")
        )

    def test_book_reference_is_publication_candidate(self):
        self.assertTrue(
            _is_publication_reference_candidate("Lopez-de Prado, M. (2018). *Advances in financial machine learning*. John Wiley & Sons.")
        )

    def tearDown(self):
        _POLICY_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
