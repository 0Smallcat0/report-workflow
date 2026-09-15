"""A source whose publication the author declared is cited like literature.

A Markdown transcription of a government report, or of an ICCT white paper,
entered the pipeline as a project file: in-text it became an ``[S3]`` marker,
and the reference list never carried it, because a file name says nothing about
who published the content and the pipeline refuses to invent that. The refusal
is right. What was missing was a place for an author who does know the details
to state them — so a course report could not produce ``(Negri & Bieker, 2025)``
and an APA entry however completely its author knew the citation.
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from report_workflow.agent_wrapper import _source_citation_map
from report_workflow.cli import _load_source_manifest
from report_workflow.nodes.citation_bind import _build_bibtex, resolve_citations_publication
from report_workflow.nodes.reference_verify import (
    _check_reference_curation,
    _is_publication_reference_candidate,
)
from report_workflow.run_workflow import prepare_workflow
from report_workflow.source_citation import (
    CitationMetadataError,
    format_in_text,
    format_reference,
    merge_adjacent_parentheticals,
    normalize_citation,
)
from report_workflow.state import WORKFLOW_RUNS_DIR

ICCT = {
    "author": "Negri, M., & Bieker, G.",
    "year": "2025",
    "title": "Life-cycle greenhouse gas emissions from passenger cars in the European Union",
    "publisher": "International Council on Clean Transportation",
    "url": "https://theicct.org/publication/electric-cars-life-cycle-analysis-emissions-europe-jul25/",
}
MOEAEA = {
    "author": "經濟部能源署",
    "year": "2026",
    "title": "114年度電力排碳係數",
    "url": "https://www.moeaea.gov.tw/ecw/populace/content/ContentDesc.aspx?menu_id=27028",
}

TRANSCRIPTION = """# ICCT 2025 摘錄

The life-cycle emissions of BEVs registered in 2025 are estimated at 63 g CO2e/km, 73% lower than gasoline cars at 235 g CO2e/km.

Battery electric cars were estimated to have about 40% higher production emissions than combustion cars.
"""

PROJECT_NOTE = """# 課堂筆記

老師提到電動車在中低速市區行駛的效率最好，高速公路上反而比較耗電。
"""


def _all_packages_present(name: str, *args, **kwargs):
    return object()


class FormatterTests(unittest.TestCase):
    def test_two_authors_cite_by_both_surnames(self):
        citation = normalize_citation(ICCT)
        self.assertEqual(format_in_text(citation), "(Negri & Bieker, 2025)")
        self.assertTrue(format_reference(citation).startswith("Negri, M., & Bieker, G. (2025). *Life-cycle"))

    def test_three_or_more_authors_cite_et_al(self):
        citation = normalize_citation({
            "author": "Machala, M. L., Chen, X., Bunke, S. P., & Tarpeh, W. A.",
            "year": "2025",
            "title": "Life cycle comparison of battery recycling and mining supply chains",
            "container": "Nature Communications",
            "volume": "16",
            "pages": "Article 988",
            "doi": "https://doi.org/10.1038/s41467-025-56063-x",
        })
        self.assertEqual(format_in_text(citation), "(Machala et al., 2025)")
        reference = format_reference(citation)
        self.assertIn("*Nature Communications, 16*, Article 988.", reference)
        self.assertTrue(reference.endswith("https://doi.org/10.1038/s41467-025-56063-x"))

    def test_a_group_author_gets_the_period_apa_requires(self):
        citation = normalize_citation({"author": "International Energy Agency", "year": "2021", "title": "Critical minerals"})
        self.assertEqual(format_in_text(citation), "(International Energy Agency, 2021)")
        self.assertTrue(format_reference(citation).startswith("International Energy Agency. (2021)."))

    def test_a_chinese_author_uses_full_width_punctuation(self):
        citation = normalize_citation(MOEAEA)
        self.assertEqual(format_in_text(citation), "（經濟部能源署，2026）")
        self.assertTrue(format_reference(citation).startswith("經濟部能源署（2026）。*114年度電力排碳係數*。"))

    def test_a_missing_year_is_stated_as_missing_not_invented(self):
        citation = normalize_citation({"author": "林心恬", "title": "從生命週期角度淺談電動車是否環保"})
        self.assertEqual(format_in_text(citation), "（林心恬，無日期）")
        english = normalize_citation({"author": "Gogoro", "title": "Battery notes"})
        self.assertEqual(format_in_text(english), "(Gogoro, n.d.)")

    def test_an_element_that_already_ends_in_punctuation_takes_no_second_mark(self):
        # The delivered reference list printed "cleaner than gasoline cars?.",
        # "VDI e.V.." and "開電動車減碳足跡？。".
        article = format_reference(normalize_citation({
            "author": "Lienert, P.", "year": "2021", "container": "Reuters",
            "title": "When do electric vehicles become cleaner than gasoline cars?",
        }))
        self.assertIn("gasoline cars? *Reuters*.", article)
        factsheet = format_reference(normalize_citation({
            "author": "VDI-Gesellschaft Fahrzeug- und Verkehrstechnik", "year": "2023",
            "title": "VDI-Analyse der CO2äq-Emissionen", "publisher": "VDI e.V.",
        }))
        self.assertTrue(factsheet.endswith("VDI e.V."), factsheet)
        chinese = format_reference(normalize_citation({
            "author": "消費者委員會", "year": "2023", "container": "選擇月刊", "issue": "557",
            "title": "315 消費者權益日：開電動車減碳足跡？",
        }))
        self.assertIn("開電動車減碳足跡？*選擇月刊*（557）。", chinese)

    def test_a_verbatim_reference_is_used_as_written(self):
        verbatim = "Tesla, Inc. (2023, March 1). *2023 Investor Day* [Presentation slides]."
        citation = normalize_citation({"author": "Tesla, Inc.", "in_text": "Tesla", "year": "2023", "reference": verbatim})
        self.assertEqual(format_reference(citation), verbatim)
        self.assertEqual(format_in_text(citation), "(Tesla, 2023)")

    def test_an_author_that_cannot_be_split_asks_for_in_text(self):
        with self.assertRaises(CitationMetadataError) as caught:
            normalize_citation({"author": "Tesla, Inc.", "year": "2023", "title": "Investor Day"}, "sources[3].citation")
        self.assertIn("in_text", str(caught.exception))
        self.assertIn("sources[3].citation", str(caught.exception))

    def test_a_misspelled_field_is_refused_rather_than_dropped(self):
        with self.assertRaises(CitationMetadataError) as caught:
            normalize_citation({"auther": "Negri, M.", "year": "2025"})
        self.assertIn("auther", str(caught.exception))

    def test_declared_entries_survive_reference_curation(self):
        for raw in (ICCT, MOEAEA):
            entry = format_reference(normalize_citation(raw))
            with self.subTest(entry=entry):
                self.assertTrue(_is_publication_reference_candidate(entry))
                self.assertTrue(_check_reference_curation(entry)[0])

    def test_adjacent_parentheticals_merge_the_way_apa_writes_them(self):
        self.assertEqual(
            merge_adjacent_parentheticals("低 73% (Negri & Bieker, 2025) (Bieker, 2021) (Negri & Bieker, 2025)。"),
            "低 73% (Negri & Bieker, 2025; Bieker, 2021)。",
        )
        self.assertEqual(
            merge_adjacent_parentheticals("0.467（經濟部能源署，2026）; （經濟部，2026a）。"),
            "0.467（經濟部能源署，2026；經濟部，2026a）。",
        )


class InputSurfaceTests(unittest.TestCase):
    def test_the_agent_surface_keys_citations_like_roles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "icct.md"
            path.write_text(TRANSCRIPTION, encoding="utf-8")
            mapping = _source_citation_map([
                {"path": str(path), "role": "source_data", "citation": ICCT},
                str(path.with_name("notes.md")),
            ])
            self.assertEqual(mapping["icct.md"]["year"], "2025")
            self.assertEqual(mapping[str(path.resolve())]["author"], ICCT["author"])
            self.assertNotIn("notes.md", mapping)

    def test_one_file_cannot_carry_two_publication_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "icct.md")
            with self.assertRaises(ValueError):
                _source_citation_map([
                    {"path": path, "citation": ICCT},
                    {"path": path, "citation": {**ICCT, "year": "2024"}},
                ])

    def test_a_manifest_resolves_paths_against_its_own_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "sources"
            folder.mkdir()
            (folder / "icct.md").write_text(TRANSCRIPTION, encoding="utf-8")
            manifest = folder / "sources.json"
            manifest.write_text(json.dumps([
                {"path": "icct.md", "role": "source_data", "citation": ICCT},
                {"path": "notes.md"},
            ]), encoding="utf-8")
            files, roles, citations, _selections = _load_source_manifest(str(manifest))
            self.assertEqual(Path(files[0]).resolve(), (folder / "icct.md").resolve())
            self.assertEqual(roles["notes.md"], "source_data")
            self.assertEqual(citations["icct.md"]["author"], ICCT["author"])


class LedgerAndBindingTests(unittest.TestCase):
    def _prepare(self, tmpdir: str):
        icct = Path(tmpdir) / "icct_excerpt.md"
        icct.write_text(TRANSCRIPTION, encoding="utf-8")
        note = Path(tmpdir) / "class_notes.md"
        note.write_text(PROJECT_NOTE, encoding="utf-8")
        with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
            state = prepare_workflow(
                "compare electric and combustion cars",
                [str(icct), str(note)],
                str(Path(tmpdir) / "out"),
                report_profile="custom",
                source_citations={"icct_excerpt.md": normalize_citation(ICCT)},
            )
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        ledger = [
            json.loads(line)
            for line in (run_dir / "evidence_ledger.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return state, ledger

    def test_declared_rows_carry_the_record_and_count_as_literature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _state, ledger = self._prepare(tmpdir)
            declared = [row for row in ledger if row["source_file_name"] == "icct_excerpt.md"]
            undeclared = [row for row in ledger if row["source_file_name"] == "class_notes.md"]
            self.assertTrue(declared and undeclared)
            for row in declared:
                self.assertEqual(row["citation"]["author"], ICCT["author"])
                self.assertEqual(row["source_role"], "research_document")
            for row in undeclared:
                self.assertNotIn("citation", row)
                self.assertEqual(row["source_role"], "internal_project_source")

    def test_declared_rows_resolve_author_year_and_undeclared_keep_their_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _state, ledger = self._prepare(tmpdir)
            declared = next(row for row in ledger if row["source_file_name"] == "icct_excerpt.md" and "63" in row["content"])
            second = next(row for row in ledger if row["source_file_name"] == "icct_excerpt.md" and "40%" in row["content"])
            note = next(row for row in ledger if row["source_file_name"] == "class_notes.md" and "效率" in row["content"])
            draft = (
                f"電動車排放低 73% [CITE:{declared['evidence_id']}] [CITE:{second['evidence_id']}]。\n"
                f"市區行駛較省電 [CITE:{note['evidence_id']}]。\n"
            )
            resolved, _audit, refs, _internal, sources = resolve_citations_publication(draft, ledger, [])
            self.assertIn("電動車排放低 73% (Negri & Bieker, 2025)。", resolved)
            self.assertIn("市區行駛較省電（本研究整理，計算附件 C1）。", resolved)
            self.assertEqual(len(refs), 1)
            self.assertTrue(refs[0].startswith("Negri, M., & Bieker, G. (2025)."))
            self.assertEqual(len(sources), 1)
            self.assertIn("class_notes.md", sources[0])

    def test_bibtex_uses_the_record_and_never_the_current_year(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _state, ledger = self._prepare(tmpdir)
            bib = _build_bibtex(ledger, [])
            self.assertIn("author = {Negri, M., & Bieker, G.}", bib)
            self.assertIn("year = {2025}", bib)
            file_derived = [
                {"source_role": "primary_source", "source_file_name": "measurements.csv", "file_type": "csv"}
            ]
            self.assertNotIn(str(date.today().year), _build_bibtex(file_derived, []))
            self.assertIn("year = {n.d.}", _build_bibtex(file_derived, []))


if __name__ == "__main__":
    unittest.main()
