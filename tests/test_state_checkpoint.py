"""Checkpointing a large state.

A run over 176,920 rows of block trade data stopped with MemoryError. The
traceback pointed at ``json.dumps(..., indent=2)`` inside ``checkpoint`` —
raised while writing the checkpoint for an *earlier* failure, so the error
reported to the user belonged to the checkpoint and not to the thing that
actually stopped the run. With ``indent`` set, ``dumps`` takes the
pure-Python encoder, and ``encode()`` finishes with ``chunks = list(chunks)``:
the whole document alive at once as millions of separate str objects, before
a single byte is written. The state was then serialised a second time, in
full, for ``checkpoint_latest.json``.
"""
import json
import tempfile
import tracemalloc
import unittest
import uuid
from pathlib import Path

from report_workflow.state import ReportState, run_dir_for


def _state_with_rows(row_count: int) -> ReportState:
    tmpdir = Path(tempfile.mkdtemp())
    state = ReportState.new("報告", [], str(tmpdir / "out"))
    state.job_id = f"test_checkpoint_{uuid.uuid4().hex}"
    state.sources["parsed_blocks"] = [
        {"id": f"S{i}", "file": "sample.csv", "field": "value", "value": i}
        for i in range(row_count)
    ]
    return state


class CheckpointMemoryTests(unittest.TestCase):
    def _serialisation_overhead(self, row_count: int) -> tuple[int, int]:
        """Bytes the write costs beyond the state dict it is handed.

        ``model_dump`` builds a copy of the state and that copy scales with
        the state; nothing here changes it. What is measured is the step
        after it — whether turning that dict into a file holds the document
        or streams it.
        """
        state = _state_with_rows(row_count)

        tracemalloc.start()
        state.model_dump(mode="json")
        _current, dump_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        tracemalloc.start()
        state.checkpoint("BIG")
        _current, checkpoint_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        run_dir = run_dir_for(state.job_id, workspace_root=state.output["workspace_root"])
        written = (run_dir / "checkpoint_BIG.json").stat().st_size
        return checkpoint_peak - dump_peak, written

    def test_writing_costs_a_constant_not_a_multiple_of_the_document(self):
        """Tripling the document must not triple what the write holds.

        The old path cost roughly seven times the document on top of the
        dict: 18.7 MB to write a 2.5 MB checkpoint, 57.0 MB to write a 7.5 MB
        one. Streaming costs about 1.07 MB for either, and for a 15 MB one.
        """
        small_overhead, small_doc = self._serialisation_overhead(20000)
        large_overhead, large_doc = self._serialisation_overhead(60000)

        self.assertGreater(large_doc, small_doc * 2, "sizes must actually differ")
        for overhead, doc in ((small_overhead, small_doc), (large_overhead, large_doc)):
            self.assertLess(
                overhead,
                2_000_000,
                f"writing a {doc:,} byte checkpoint held {overhead:,} extra bytes",
            )
        self.assertLess(
            large_overhead,
            small_overhead * 1.5,
            f"a 3x larger document cost {large_overhead:,} against {small_overhead:,} "
            "— the write is scaling with the document again",
        )

    def test_latest_matches_the_named_checkpoint_byte_for_byte(self):
        state = _state_with_rows(50)
        state.checkpoint("NODE")
        run_dir = run_dir_for(state.job_id, workspace_root=state.output["workspace_root"])

        named = (run_dir / "checkpoint_NODE.json").read_bytes()
        latest = (run_dir / "checkpoint_latest.json").read_bytes()
        self.assertEqual(named, latest)

    def test_the_written_checkpoint_is_still_indented_utf8_json(self):
        """Streaming changed how it is written, not what is written."""
        state = _state_with_rows(3)
        state.checkpoint("READABLE")
        run_dir = run_dir_for(state.job_id, workspace_root=state.output["workspace_root"])

        raw = (run_dir / "checkpoint_READABLE.json").read_text(encoding="utf-8")
        self.assertIn('\n  "job_id"', raw)
        self.assertIn("報告", raw)
        self.assertNotIn("\\u5831", raw)
        self.assertEqual(json.loads(raw)["runtime"]["current_node"], "READABLE")


if __name__ == "__main__":
    unittest.main()
