"""A backtest is not an academic paper, and the registry already knew the words.

Running the workflow on a real quantitative deliverable, `report_profile` was
inferred as `academic_paper`: abstract of 180–220 words, introduction, methods,
discussion, references — for a table of eleven exit rules and their per-trade
means. There was no profile for the thing being written, and the inference
cascade was hand-written token matching that never consulted the aliases every
profile already declares, so 回測報告 fell past all of it to the default.

Two things follow. The memo profile exists, and it requires the section a paper
does not have: robustness. A result that holds in one setting and reverses in
the next is not a result, and the only way a reader can tell is if the other
settings are in the document.
"""
import unittest

from report_workflow.profiles import (
    PROFILE_REGISTRY,
    get_profile,
    infer_report_profile,
    normalize_profile_id,
)
from report_workflow.nodes.blueprint_plan import BLUEPRINTS_DIR


class QuantResearchMemoProfileTests(unittest.TestCase):
    def test_the_profile_is_registered(self):
        profile = get_profile("quant_research_memo")
        self.assertEqual(profile.blueprint_file, "quant_research_memo.yaml")

    def test_a_backtest_prompt_no_longer_becomes_an_academic_paper(self):
        for prompt in (
            "用東財資料做一個回購事件的回測報告",
            "write a backtest report for buyback events",
            "整理成一份量化研究備忘",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(infer_report_profile(prompt), "quant_research_memo")

    def test_the_tuned_cascade_still_wins(self):
        # Alias matching runs last precisely so these keep their answers.
        self.assertEqual(infer_report_profile("engineering report"), "engineering_lab_report")
        self.assertEqual(infer_report_profile("graduate school application"), "admissions_report")
        self.assertEqual(infer_report_profile("a proposal for next quarter"), "proposal")

    def test_an_unrecognised_prompt_still_defaults(self):
        self.assertEqual(infer_report_profile("寫點東西"), "academic_paper")

    def test_every_profile_alias_resolves_to_its_own_profile(self):
        # The registry is now load-bearing for inference, so an alias that
        # belongs to two profiles would silently pick one of them.
        seen: dict[str, str] = {}
        for profile in PROFILE_REGISTRY.values():
            for alias in profile.aliases:
                key = alias.lower()
                self.assertNotIn(
                    key, seen,
                    f"{alias!r} is claimed by both {seen.get(key)} and {profile.profile_id}",
                )
                seen[key] = profile.profile_id

    def test_the_memo_requires_a_robustness_section(self):
        import yaml
        blueprint = yaml.safe_load(
            (BLUEPRINTS_DIR / "quant_research_memo.yaml").read_text(encoding="utf-8")
        )
        sections = blueprint.get("sections", {})
        self.assertIn("robustness", sections)
        self.assertTrue(sections["robustness"].get("required"))
        self.assertNotIn("introduction", sections, "a memo answers a question, it does not open one")


if __name__ == "__main__":
    unittest.main()
