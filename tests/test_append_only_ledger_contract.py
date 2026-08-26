"""A run's ledger grows while the run is in progress; that must not deadlock it.

The pipeline appends derived rows to the evidence ledger on its own — the
grouped table built during outline planning does it. That moves the ledger
hash, and the artifacts accepted before the append still carry the old stamp.

Publishing then refused on the hash, routing the failure handed back an empty
repair scope, and the prescribed cure (call register_derived_evidence again)
had nothing to re-register when the author never registered anything. The run
had no way forward.

An append does not invalidate an artifact. Only a disappearance does. These
tests pin that distinction.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from report_workflow.artifact_contract import (
    load_artifact_contract,
    make_artifact_contract,
    validate_artifact_contract,
    write_artifact_contract,
)
from report_workflow.errors import QAHardBlockError
from report_workflow.state import ReportState


def _row(evidence_id: str) -> str:
    return json.dumps({"evidence_id": evidence_id, "content": "x",
                       "evidence_type": "quantitative"}, ensure_ascii=False)


class AppendOnlyLedgerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ledger = self.root / "evidence_ledger.jsonl"
        self.ledger.write_text(_row("E_a") + "\n" + _row("E_b") + "\n", encoding="utf-8")
        self.state = ReportState(job_id="run_test")
        self.state.sources["evidence_ledger_path"] = str(self.ledger)

        self.artifact = self.root / "claim_matrix.json"
        self.artifact.write_text(json.dumps({
            "claims": [{"claim_id": "c1", "evidence_ids": ["E_a"]}]
        }, ensure_ascii=False), encoding="utf-8")
        write_artifact_contract(self.artifact, make_artifact_contract(self.state))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _append(self, evidence_id: str) -> None:
        with open(self.ledger, "a", encoding="utf-8") as fh:
            fh.write(_row(evidence_id) + "\n")

    def test_append_re_stamps_instead_of_blocking(self) -> None:
        stamped = load_artifact_contract(self.artifact)["evidence_ledger_hash"]
        self._append("E_derived")
        validate_artifact_contract(self.state, self.artifact)
        current = load_artifact_contract(self.artifact)["evidence_ledger_hash"]
        self.assertNotEqual(stamped, current)
        self.assertEqual(current, make_artifact_contract(self.state)["evidence_ledger_hash"])

    def test_cited_row_disappearing_still_blocks(self) -> None:
        self.ledger.write_text(_row("E_b") + "\n", encoding="utf-8")   # E_a is gone
        with self.assertRaises(QAHardBlockError) as ctx:
            validate_artifact_contract(self.state, self.artifact)
        self.assertIn("E_a", str(ctx.exception))

    def test_other_job_still_gets_the_remap_message(self) -> None:
        contract = make_artifact_contract(self.state)
        contract["job_id"] = "run_somebody_else"
        write_artifact_contract(self.artifact, contract)
        with self.assertRaises(QAHardBlockError) as ctx:
            validate_artifact_contract(self.state, self.artifact)
        self.assertIn("remap-evidence", str(ctx.exception))

    def test_sentence_map_citations_count_as_cited(self) -> None:
        smap = self.root / "sentence_map.jsonl"
        smap.write_text(json.dumps({"sentence_id": "s0", "citation_ids": ["E_b"]},
                                   ensure_ascii=False) + "\n", encoding="utf-8")
        write_artifact_contract(smap, make_artifact_contract(self.state))
        self._append("E_derived")
        validate_artifact_contract(self.state, smap)
        self.assertEqual(load_artifact_contract(smap)["evidence_ledger_hash"],
                         make_artifact_contract(self.state)["evidence_ledger_hash"])


if __name__ == "__main__":
    unittest.main()


class EmptyFilterDerivationTest(unittest.TestCase):
    """A filter that names nothing must not mint a citable zero.

    `count` over an empty selection came back 0 and got an evidence id, so a
    typo in a row filter produced a figure a sentence could cite. The commonest
    typo is joining clauses with a comma: that parses as one equality against a
    value no row holds, selects nothing, and reads as a real answer.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        self.csv = root / "grid.csv"
        self.csv.write_text(
            "lag,hold,trades\n0,1,1140\n0,3,1135\n60,1,1129\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _dataset(self):
        import csv as _csv
        from report_workflow.derived_evidence import Dataset
        with open(self.csv, encoding="utf-8", newline="") as fh:
            rows = list(_csv.DictReader(fh))
        return Dataset({"source_id": "s1", "file_name": "grid.csv",
                        "file_path": str(self.csv), "file_type": "csv"}, rows)

    def test_comma_joined_filter_is_refused_and_names_the_separator(self) -> None:
        from report_workflow.derived_evidence import DerivationError, compute
        with self.assertRaises(DerivationError) as ctx:
            compute(self._dataset(), {"id": "d", "op": "count", "rows": "lag=0,hold=1"})
        message = str(ctx.exception)
        self.assertIn("selects no rows", message)
        self.assertIn("'&'", message)

    def test_intentional_emptiness_still_available(self) -> None:
        from report_workflow.derived_evidence import compute
        result = compute(
            self._dataset(), {"id": "d", "op": "count", "rows": "lag=999", "allow_empty": True}
        )
        self.assertEqual(result["value"], 0)

    def test_ampersand_filter_selects_the_row(self) -> None:
        from report_workflow.derived_evidence import compute
        result = compute(
            self._dataset(), {"id": "d", "op": "sum", "column": "trades", "rows": "lag=0&hold=1"}
        )
        self.assertEqual(result["value"], 1140)
