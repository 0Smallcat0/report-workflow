"""A source file's own citations have to reach the deliverable.

Ingestion counted one file as one source. A market report citing thirty-nine
outside houses therefore entered as a single entry named after itself, and
every consumer downstream agreed with it: `publication_reference_list.md`,
`publication_references.bib` and `internal_source_appendix.md` were all zero
bytes, and the delivered document told its reader nothing about where any
figure came from. No code was wrong — the path did not exist.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.nodes.cited_sources import (
    extract_cited_sources,
    format_bibtex_entry,
    format_reference_entry,
)
from report_workflow.nodes.reference_verify import (
    _check_reference_curation,
    _is_publication_reference_candidate,
)
from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR


#: Six distinct outside sources, cited eight times, in all three shapes:
#: two Markdown links, two bare URLs, two attributions with no URL. One link
#: and one attribution repeat, so a correct extractor reports six, not eight.
CITING_REPORT = """# 回收利用經濟性

## 電池

黑粉價格見 [Black mass prices](https://www.fastmarkets.com/metals-and-mining/black-mass-prices/)。
濕法冶金回收率可達 95%（來源：IMARC，2026），實際良率視前處理而定。

LFP 回收的討論見 https://www.crugroup.com/en/communities/thought-leadership/2025/lfp-recycling
其中提到毛利長期為負。

## 塑膠

再生料與原生料價差見 [Global Plastics Outlook](https://www.oecd.org/environment/plastics/outlook.pdf)。
分選瓶頸的討論見 https://ellenmacarthurfoundation.org/topics/circular-economy

## 紙張

到廠價格由區域供需決定（來源：Fastmarkets RISI，2026）。
黑粉價格再次參考 https://www.fastmarkets.com/metals-and-mining/black-mass-prices/，
回收率數字同樣引自（來源：IMARC，2026）。
"""

#: The same report with every citation removed. Its empty source list is
#: correct, not a defect, and the two cases must be distinguishable.
UNCITED_REPORT = """# 回收利用經濟性

## 電池

濕法冶金回收率可達 95%，實際良率視前處理環節的雜質控制而定，各廠差距不小。

## 紙張

到廠價格由區域供需決定，出口導向的港口城市與內陸城市之間常年存在價差。
"""

EXPECTED_UNIQUE_SOURCES = 6


def _all_packages_present(name: str, *args, **kwargs):
    return object()


def _prepare(tmpdir: str, text: str) -> ReportState:
    src = Path(tmpdir) / "recycling.md"
    src.write_text(text, encoding="utf-8")
    with patch(
        "report_workflow.preflight.importlib.util.find_spec",
        side_effect=_all_packages_present,
    ):
        return prepare_workflow(
            "analyse recycling economics",
            [str(src)],
            str(Path(tmpdir) / "out"),
            report_profile="business_report",
        )


def _cited(state: ReportState) -> list[dict]:
    path = Path(state.sources["cited_sources_path"])
    return json.loads(path.read_text(encoding="utf-8"))["cited_sources"]


class ExtractionTests(unittest.TestCase):
    def _rows(self, content: str) -> list[dict]:
        registry = [{
            "source_id": "s1",
            "file_name": "recycling.md",
            "parsed_content": [
                {"block_id": "md_1", "line_start": 1, "line_end": 2, "content": content}
            ],
        }]
        return extract_cited_sources(registry)

    def test_a_markdown_link_keeps_its_title(self):
        rows = self._rows("見 [Black mass prices](https://example.org/black-mass)。")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "link")
        self.assertEqual(rows[0]["title"], "Black mass prices")
        self.assertEqual(rows[0]["url"], "https://example.org/black-mass")

    def test_a_bare_url_is_a_source_too(self):
        rows = self._rows("討論見 https://example.org/report 其中提到毛利為負。")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "url")

    def test_a_url_does_not_swallow_the_sentence_punctuation(self):
        rows = self._rows("參考 https://example.org/report，其後續分析另見他處。")
        self.assertEqual(rows[0]["url"], "https://example.org/report")

    def test_an_attribution_without_a_url_is_kept(self):
        """A named house and a year is still somewhere a reader can go."""
        rows = self._rows("回收率可達 95%（來源：IMARC，2026）。")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "attribution")
        self.assertEqual(rows[0]["publisher"], "IMARC")
        self.assertEqual(rows[0]["year"], "2026")
        self.assertEqual(rows[0]["url"], "")

    def test_one_source_cited_twice_is_listed_once(self):
        rows = self._rows(
            "見 https://example.org/x 與（來源：IMARC，2026）。"
            "又見 https://example.org/x 與（來源：IMARC，2026）。"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["occurrences"] for row in rows}, {2})

    def test_a_link_and_a_bare_mention_of_one_address_are_one_source(self):
        rows = self._rows(
            "見 [Prices](https://example.org/x) 以及 https://example.org/x 的原文。"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Prices")

    def test_every_row_says_where_it_came_from(self):
        """Without this a reference cannot be walked back to its sentence."""
        rows = self._rows("見 https://example.org/x。")
        self.assertEqual(rows[0]["source_file_name"], "recycling.md")
        self.assertEqual(rows[0]["block_id"], "md_1")
        self.assertEqual(rows[0]["line_start"], 1)


class RegistryTests(unittest.TestCase):
    def test_a_citing_source_yields_one_row_per_distinct_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, CITING_REPORT)
            rows = _cited(state)
            self.assertEqual(len(rows), EXPECTED_UNIQUE_SOURCES)
            self.assertEqual(state.sources["cited_source_count"], EXPECTED_UNIQUE_SOURCES)

    def test_an_uncited_source_yields_an_empty_registry(self):
        """Empty is the right answer here, and must not read as a failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, UNCITED_REPORT)
            self.assertEqual(_cited(state), [])
            self.assertEqual(state.sources["cited_source_count"], 0)


class CurationTests(unittest.TestCase):
    """An entry the curation filter deletes is a citation the reader loses."""

    def test_every_formatted_entry_survives_reference_curation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, CITING_REPORT)
            for row in _cited(state):
                entry = format_reference_entry(row)
                with self.subTest(entry=entry):
                    ok, reason = _check_reference_curation(entry)
                    self.assertTrue(ok, reason)
                    self.assertTrue(_is_publication_reference_candidate(entry))

    def test_a_pdf_url_is_not_mistaken_for_a_local_file(self):
        """Published reports are served as .pdf; that is not a local artifact."""
        entry = "OECD. (2026). *Global Plastics Outlook*. https://www.oecd.org/env/outlook.pdf"
        ok, reason = _check_reference_curation(entry)
        self.assertTrue(ok, reason)

    def test_a_bibtex_entry_carries_what_the_source_stated(self):
        row = {
            "cited_source_id": "CS_abc123",
            "publisher": "IMARC",
            "title": "",
            "year": "2026",
            "url": "",
        }
        entry = format_bibtex_entry(row, 1)
        self.assertIn("@misc{CS_abc123,", entry)
        self.assertIn("author = {IMARC}", entry)
        self.assertIn("year = {2026}", entry)

    def test_no_year_becomes_n_d_rather_than_this_year(self):
        row = {"cited_source_id": "CS_x", "publisher": "", "title": "", "url": "https://a.org/b"}
        self.assertIn("(n.d.)", format_reference_entry(row))


class DeliveredDocumentTests(unittest.TestCase):
    """The point of all of it: the reader gets the list."""

    def _publish(self, tmpdir: str, text: str):
        from docx import Document
        from report_workflow.run_workflow import render_workflow, validate_workflow

        state = _prepare(tmpdir, text)
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        ledger = [
            json.loads(line)
            for line in (run_dir / "evidence_ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        picked = [row for row in ledger if len(row.get("content", "")) > 30][:3]
        claims = [
            {
                "claim_id": f"c{index}",
                "claim_text": row["content"][:120],
                "claim_type": (
                    "statistical" if "statistical" in row["allowed_claim_types"] else "factual"
                ),
                "risk_level": "low",
                "status": "supported",
                "evidence_ids": [row["evidence_id"]],
                "requires_hedged_wording": True,
                "claim_role": "primary",
            }
            for index, row in enumerate(picked, start=1)
        ]
        # business_report requires a section stating what would weaken the
        # conclusions, and requires it to name conclusions it does not itself
        # carry. Give it claims of its own rather than sharing the body's.
        body_claim_ids = [claim["claim_id"] for claim in claims]
        counter_claims = [
            {**claims[-1], "claim_id": f"c_limit_{index}", "claim_role": "supporting"}
            for index in (1, 2)
        ]
        claims.extend(counter_claims)
        counter_claim_ids = [claim["claim_id"] for claim in counter_claims]
        (run_dir / "claim_matrix.json").write_text(
            json.dumps({"claims": claims}, ensure_ascii=False), encoding="utf-8"
        )
        plan_path = run_dir / "section_drafts" / "figure_plan.json"
        if plan_path.exists():
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            payload["figures"] = []
            plan_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        order = state.plan["blueprint"]["section_order"]
        claimless = {"references", "appendix"}

        def _section_claim_ids(section_id: str) -> list[str]:
            if section_id in claimless:
                return []
            return counter_claim_ids if section_id == "limitations" else body_claim_ids

        sections = {
            section_id: {
                "section_id": section_id,
                "goals": f"cover {section_id}",
                "claim_ids": _section_claim_ids(section_id),
                "paragraph_order": ["context", "content", "conclusion"],
                "figure_ids": [],
            }
            for section_id in order
        }
        if "limitations" in sections:
            sections["limitations"]["undermines"] = body_claim_ids[:1]
        (run_dir / "outline.json").write_text(
            json.dumps({"sections": sections}, ensure_ascii=False), encoding="utf-8"
        )

        section_dir = run_dir / "section_drafts"
        section_dir.mkdir(exist_ok=True)
        rows = []
        for section_id in order:
            if section_id in claimless:
                (section_dir / f"{section_id}.md").write_text(
                    f"# {section_id}\n\n本節由流程自動產生。\n", encoding="utf-8"
                )
                continue
            lines = [f"# {section_id}", ""]
            wanted = set(_section_claim_ids(section_id))
            for claim in (c for c in claims if c["claim_id"] in wanted):
                marker = " ".join(f"[CITE:{eid}]" for eid in claim["evidence_ids"])
                # Not a prefix: FS blocks a sentence omitting a figure its claim
                # asserts, which a truncated restatement would do.
                lines.extend([f"就本節而言，{claim['claim_text']} {marker}。", ""])
                rows.append({
                    "sentence_id": f"s_{section_id}_{claim['claim_id']}",
                    "section_id": section_id,
                    "claim_ids": [claim["claim_id"]],
                    "evidence_ids": claim["evidence_ids"],
                    "citation_ids": claim["evidence_ids"],
                    "wording_strength": "hedged",
                    "draft_origin": "agent_draft",
                })
            (section_dir / f"{section_id}.md").write_text("\n".join(lines), encoding="utf-8")
        with open(run_dir / "sentence_map.jsonl", "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        validated = validate_workflow(state.job_id)
        self.assertEqual((validated.qa or {}).get("qa_decision"), "pass")
        rendered = render_workflow(state.job_id)
        docx_path = (
            rendered.output.get("published_report_path")
            or rendered.output.get("final_docx_path")
            or rendered.output.get("rendered_docx_path")
        )
        document = Document(docx_path)
        text_out = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return state, rendered, text_out

    def test_all_cited_sources_reach_the_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state, _rendered, text = self._publish(tmpdir, CITING_REPORT)
            for row in _cited(state):
                needle = row["url"] or row["publisher"]
                with self.subTest(source=needle):
                    self.assertIn(needle, text)

    def test_the_bibliography_is_not_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _state, rendered, _text = self._publish(tmpdir, CITING_REPORT)
            bib = Path(rendered.citations["publication_references_bib_path"]).read_text(
                encoding="utf-8"
            )
            self.assertGreaterEqual(bib.count("@misc{"), EXPECTED_UNIQUE_SOURCES)

    def test_an_uncited_source_publishes_without_complaint(self):
        """The counterpart case: empty is normal and raises no warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state, rendered, _text = self._publish(tmpdir, UNCITED_REPORT)
            self.assertEqual(state.sources["cited_source_count"], 0)
            warnings = " ".join(rendered.runtime.get("warnings", []))
            self.assertNotIn("cited source", warnings)


if __name__ == "__main__":
    unittest.main()
