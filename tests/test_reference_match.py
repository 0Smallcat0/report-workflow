"""A DOI that resolves is not a reference that checks out.

``_verify_doi`` passed any DOI doi.org would redirect, so a reference with
invented authors and a real DOI pasted in -- "DOIs were either fabricated or
they linked to another article", the commonest complaint about AI-written
references -- was reported as verified. These tests pin the comparison that
replaced it, against canned registry answers so no test touches the network.
"""
import json
import unittest

from report_workflow import reference_match as rm

LLAMA_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2302.13971v1</id>
    <published>2023-02-27T17:11:15Z</published>
    <updated>2023-02-27T17:11:15Z</updated>
    <title>LLaMA: Open and Efficient Foundation Language Models</title>
    <author><name>Hugo Touvron</name></author>
    <author><name>Thibaut Lavril</name></author>
    <author><name>Gautier Izacard</name></author>
    <author><name>Xavier Martinet</name></author>
    <author><name>Marie-Anne Lachaux</name></author>
    <author><name>Timothée Lacroix</name></author>
    <author><name>Guillaume Lample</name></author>
  </entry>
</feed>"""

WAKEFIELD_CSL = {
    "title": "RETRACTED: Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and "
    "pervasive developmental disorder in children",
    "author": [
        {"given": "AJ", "family": "Wakefield"},
        {"given": "SH", "family": "Murch"},
        {"given": "A", "family": "Anthony"},
    ],
    "issued": {"date-parts": [[1998, 2]]},
    "updated-by": [
        {
            "DOI": "10.1016/s0140-6736(10)60175-4",
            "type": "retraction",
            "label": "Retraction",
            "source": "retraction-watch",
            "updated": {"date-parts": [[2010, 2, 6]]},
        }
    ],
}

SSA_CSL = {
    "title": "Efficiently computing static single assignment form and the control dependence graph",
    "author": [
        {"given": "Ron", "family": "Cytron"},
        {"given": "Jeanne", "family": "Ferrante"},
        {"given": "Barry K.", "family": "Rosen"},
        {"given": "Mark N.", "family": "Wegman"},
        {"given": "F. Kenneth", "family": "Zadeck"},
    ],
    "issued": {"date-parts": [[1991, 10]]},
}


def registry(answers):
    """A fake HTTP GET that answers from a {url-substring: (status, body)} table."""

    calls = []

    def get(url, headers):
        calls.append(url)
        for key, (status, body) in answers.items():
            if key in url:
                return status, body if isinstance(body, str) else json.dumps(body)
        raise AssertionError(f"unexpected request {url}")

    get.calls = calls
    return get


class DoiComparisonTest(unittest.TestCase):
    def test_a_reference_that_names_its_doi_record_is_verified(self):
        get = registry({"doi.org/10.1145/115372.115320": (200, SSA_CSL)})
        check = rm.check_reference(
            "Cytron, R., Ferrante, J., Rosen, B. K., Wegman, M. N., & Zadeck, F. K. (1991). "
            "Efficiently computing static single assignment form and the control dependence "
            "graph. ACM TOPLAS, 13(4), 451-490. https://doi.org/10.1145/115372.115320",
            get=get,
        )
        self.assertEqual(check.status, rm.VERIFIED, check.message)
        self.assertEqual(check.identifier, "doi:10.1145/115372.115320")

    def test_a_real_doi_under_another_title_is_a_mismatch(self):
        """The case resolve-only checking passed: the DOI exists, the work does not."""

        get = registry({"doi.org/10.1145/115372.115320": (200, SSA_CSL)})
        check = rm.check_reference(
            "Nguyen, T., & Patel, R. (2021). Adaptive caching for serverless inference "
            "pipelines. ACM TOPLAS, 13(4), 451-490. https://doi.org/10.1145/115372.115320",
            get=get,
        )
        self.assertEqual(check.status, rm.MISMATCH)
        self.assertIn("Efficiently computing static single assignment form", check.message)
        self.assertIn("not the work this reference names", check.message)

    def test_an_unregistered_doi_is_not_found(self):
        get = registry({"doi.org/": (404, "")})
        check = rm.check_reference("Smith, J. (2020). A title. doi: 10.9999/does-not-exist", get=get)
        self.assertEqual(check.status, rm.NOT_FOUND)

    def test_a_retraction_the_reference_does_not_mention_is_reported(self):
        get = registry({"doi.org/": (200, WAKEFIELD_CSL)})
        reference = (
            "Wakefield, A. J., Murch, S. H., & Anthony, A. (1998). Ileal-lymphoid-nodular "
            "hyperplasia, non-specific colitis, and pervasive developmental disorder in "
            "children. The Lancet, 351(9103), 637-641. https://doi.org/10.1016/S0140-6736(97)11096-0"
        )
        check = rm.check_reference(reference, get=get)
        self.assertEqual(check.status, rm.RETRACTED)
        self.assertIn("10.1016/s0140-6736(10)60175-4", check.message)

        acknowledged = rm.check_reference(reference + " (Retracted 2010)", get=get)
        self.assertEqual(acknowledged.status, rm.VERIFIED)

    def test_a_registry_that_cannot_be_reached_is_not_a_verdict(self):
        def offline(url, headers):
            raise rm.LookupUnavailable("network down")

        check = rm.check_reference("Smith, J. (2020). A title. doi: 10.1000/xyz", get=offline)
        self.assertEqual(check.status, rm.UNREACHABLE)
        self.assertEqual(check.identifier, "doi:10.1000/xyz")
        self.assertIn("could not be checked", check.message)


class ArxivComparisonTest(unittest.TestCase):
    def test_invented_coauthors_on_a_real_preprint_are_a_mismatch(self):
        """A reference from the Badalova & Mayr dataset: real title, real ID, wrong authors."""

        get = registry({"export.arxiv.org": (200, LLAMA_ATOM)})
        check = rm.check_reference(
            "Hugo Touvron, Thibaut Martin, Kevin Stone, Marie-Anne Lachaux, Timothee Albert, "
            "et al. Llama: Open and efficient foundation language models. arXiv preprint "
            "arXiv:2302.13971, 2023",
            get=get,
        )
        self.assertEqual(check.status, rm.MISMATCH)
        self.assertIn("Stone", check.unmatched_authors)
        self.assertIn("Albert", check.unmatched_authors)
        self.assertNotIn("Touvron", check.unmatched_authors)

    def test_the_same_preprint_cited_correctly_is_verified(self):
        get = registry({"export.arxiv.org": (200, LLAMA_ATOM)})
        check = rm.check_reference(
            "Touvron, H., Lavril, T., Izacard, G., et al. (2023). LLaMA: Open and efficient "
            "foundation language models. arXiv:2302.13971",
            get=get,
        )
        self.assertEqual(check.status, rm.VERIFIED, check.message)

    def test_a_placeholder_identifier_is_not_an_identifier(self):
        get = registry({})
        check = rm.check_reference(
            "Nuo Lou and et al. Dsp: Diffusion-based span prediction for masked text modeling. "
            "arXiv preprint arXiv:2305.XXXX, 2023",
            get=get,
        )
        self.assertEqual(check.status, rm.NOT_FOUND)
        self.assertEqual(get.calls, [])


class SearchTest(unittest.TestCase):
    def test_absence_from_the_indexes_is_not_called_fabrication(self):
        get = registry({
            "api.crossref.org": (200, {"message": {"items": []}}),
            "api.openalex.org": (200, {"results": []}),
        })
        check = rm.check_reference(
            "European Commission. (2025). Open Research Europe: Full article corpus. "
            "https://open-research-europe.ec.europa.eu",
            get=get,
        )
        self.assertEqual(check.status, rm.NEEDS_REVIEW)
        self.assertIn("no Crossref or OpenAlex record carries its title", check.message)

    def test_a_search_hit_must_carry_the_title_not_just_resemble_it(self):
        crossref = {"message": {"items": [{
            "DOI": "10.1000/other",
            "title": ["Semantic similarity measures in ontologies"],
            "author": [{"given": "A", "family": "Other"}],
            "issued": {"date-parts": [[2008]]},
        }]}}
        get = registry({
            "api.crossref.org": (200, crossref),
            "api.openalex.org": (200, {"results": []}),
        })
        check = rm.check_reference(
            "Shyam Fernando and Mark Stevenson. Semantic similarity based on lexical "
            "substitution. In Proceedings of ACL-08: HLT, pp. 756-764, 2008",
            get=get,
        )
        self.assertEqual(check.status, rm.NEEDS_REVIEW)

    def test_a_found_title_under_other_authors_is_a_mismatch(self):
        openalex = {"results": [{
            "title": "Semantically Diverse Language Generation for Uncertainty Estimation in Language Models",
            "authorships": [
                {"author": {"display_name": "Lukas Aichberger"}},
                {"author": {"display_name": "Kajetan Schweighofer"}},
                {"author": {"display_name": "Sepp Hochreiter"}},
            ],
            "publication_year": 2024,
            "doi": "https://doi.org/10.48550/arxiv.2406.04306",
        }]}
        get = registry({
            "api.crossref.org": (200, {"message": {"items": []}}),
            "api.openalex.org": (200, openalex),
        })
        check = rm.check_reference(
            "Franz Aichberger, Lily Chen, and John Smith. Semantically diverse language "
            "generation for uncertainty estimation in language models. In International "
            "Conference on Learning Representations (ICLR), 2025",
            get=get,
        )
        self.assertEqual(check.status, rm.MISMATCH)
        self.assertEqual(set(check.unmatched_authors), {"Chen", "Smith"})


class NameParsingTest(unittest.TestCase):
    def test_surnames_come_out_of_every_common_style(self):
        self.assertEqual(
            rm.cited_surnames("Atanassova, I., Bertin, M., & Mayr, P. (2020)."),
            ["Atanassova", "Bertin", "Mayr"],
        )
        self.assertEqual(
            rm.cited_surnames("Daniel Schindler, Benjamin Zapilko, and Frank Krüger."),
            ["Schindler", "Zapilko", "Krüger"],
        )
        self.assertEqual(rm.cited_surnames("S. Zhang, S. Roller, N. Goyal, et al."), ["Zhang", "Roller", "Goyal"])

    def test_accents_and_mis_encoding_do_not_make_a_stranger(self):
        missing, cited = rm.unmatched_surnames(
            "Elif Aky?rek and Ondrej Dusek.", ("Ekin Akyürek", "Ondřej Dušek")
        )
        self.assertEqual((missing, cited), ([], 2))


if __name__ == "__main__":
    unittest.main()
