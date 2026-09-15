"""A structured draft can write a paragraph of more than one sentence.

structured_drafts.json compiled every sentence into a paragraph of its own, so
the preferred authoring path could only produce a column of one-sentence
paragraphs — the shape the brief's own paragraph rule (context, content,
conclusion) forbids. ``paragraphs`` groups sentences; each keeps its claims,
citations and sentence-map row.
"""
import json
import unittest
from pathlib import Path

from report_workflow.artifact_contract import load_jsonl_without_contract
from report_workflow.artifact_lint import _lint_structured_drafts
from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.section_draft import run_section_draft
from report_workflow.state import WORKFLOW_RUNS_DIR, ReportState


def _state() -> ReportState:
    state = ReportState.new("write report", [], "out")
    state.plan["blueprint"] = {"section_order": ["results"], "sections": {"results": {"required": True}}}
    state.plan["outline"] = {"sections": {"results": {"section_id": "results", "claim_ids": ["c1", "c2"]}}}
    state.plan["claim_matrix"] = {"claims": [
        {"claim_id": "c1", "claim_text": "製造排放多 3.6 t。", "evidence_ids": ["E001"]},
        {"claim_id": "c2", "claim_text": "約 44,200 公里追平。", "evidence_ids": ["E002"]},
    ]}
    return state


def _write(state: ReportState, results: dict) -> Path:
    path = WORKFLOW_RUNS_DIR / state.job_id / "structured_drafts.json"
    path.write_text(json.dumps({"sections": {"results": {"title": "結果", **results}}}, ensure_ascii=False), encoding="utf-8")
    return path


class StructuredDraftParagraphTests(unittest.TestCase):
    def test_sentences_grouped_into_one_paragraph_render_as_one(self):
        state = _state()
        _write(state, {"paragraphs": [
            {"sentences": [
                {"text": "電動車出廠時多排 3.6 t。", "claim_ids": ["c1"], "evidence_ids": ["E001"]},
                {"text": "約行駛 44,200 公里後追平。", "claim_ids": ["c2"], "evidence_ids": ["E002"]},
            ]},
            {"sentences": [{"text": "[TABLE:E002 表 1 碳平衡點]"}]},
        ]})
        result = run_section_draft(state)
        text = Path(result.drafts["section_drafts"]["results"]).read_text(encoding="utf-8")
        self.assertIn("電動車出廠時多排 3.6 t [CITE:E001]。約行駛 44,200 公里後追平 [CITE:E002]。\n", text)
        self.assertIn("\n[TABLE:E002 表 1 碳平衡點]\n", text)
        rows = load_jsonl_without_contract(result.drafts["sentence_map_path"])
        self.assertEqual([(row["sentence_id"], row["claim_ids"]) for row in rows], [("results_1", ["c1"]), ("results_2", ["c2"])])

    def test_english_sentences_are_joined_with_a_space_and_a_block_cannot_share_a_paragraph(self):
        state = _state()
        _write(state, {"paragraphs": [{"sentences": [
            {"text": "Production adds 3.6 t.", "claim_ids": ["c1"], "evidence_ids": ["E001"]},
            {"text": "[FIGURE:1]"},
        ]}]})
        with self.assertRaises(QAHardBlockError) as caught:
            run_section_draft(state)
        self.assertIn("results.paragraphs[0].sentences[1]", str(caught.exception))

        state = _state()
        _write(state, {"paragraphs": [{"sentences": [
            {"text": "Production adds 3.6 t.", "claim_ids": ["c1"], "evidence_ids": ["E001"]},
            {"text": "Parity comes at 44,200 km.", "claim_ids": ["c2"], "evidence_ids": ["E002"]},
        ]}]})
        text = Path(run_section_draft(state).drafts["section_drafts"]["results"]).read_text(encoding="utf-8")
        self.assertIn("Production adds 3.6 t [CITE:E001]. Parity comes at 44,200 km [CITE:E002].", text)

    def test_lint_reads_sentences_inside_paragraphs(self):
        state = _state()
        path = _write(state, {"paragraphs": [{"sentences": [
            {"text": "電動車出廠時多排 3.6 t。", "claim_ids": ["c9"], "evidence_ids": ["E001"]},
        ]}]})
        issues: list = []
        _lint_structured_drafts(state, path.parent, issues, {"c1", "c2"}, {"E001", "E002"}, {"results"})
        self.assertEqual(
            [(issue.json_path, issue.message) for issue in issues],
            [("$.sections.results.paragraphs[0].sentences[0].claim_ids", "Unknown claim_id: c9")],
        )


if __name__ == "__main__":
    unittest.main()
