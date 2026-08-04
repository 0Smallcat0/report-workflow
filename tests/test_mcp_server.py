"""Tests for the MCP server surface over the deterministic gates.

The payload functions are pure and importable without the optional ``mcp``
dependency; server construction itself is exercised only when the extra is
installed.
"""
import importlib.util
import unittest

from report_workflow.mcp_server import (
    list_profiles_payload,
    verify_claims_payload,
    workflow_status_payload,
)

def _mcp_available() -> bool:
    """Whether the module the server actually imports can be imported.

    Probing "mcp" alone found the top-level package on a runner where
    mcp.server.fastmcp does not exist, so the guard let the test through and it
    errored instead of skipping. Probe what is used, not what it starts with.
    """
    try:
        return importlib.util.find_spec("mcp.server.fastmcp") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


MCP_AVAILABLE = _mcp_available()

EVIDENCE = [
    {
        "evidence_id": "ev_error",
        "content": "The error rate fell to 3.5% under the structured workflow, "
        "down from 9.0% for the manual baseline.",
        "evidence_type": "quantitative",
        "source_role": "primary_source",
        "evidence_grade": "high",
    },
]


def _claim(claim_id, text, evidence_ids, claim_type="factual", status="supported"):
    return {
        "claim_id": claim_id,
        "claim_text": text,
        "claim_type": claim_type,
        "status": status,
        "evidence_ids": evidence_ids,
    }


class VerifyClaimsPayloadTests(unittest.TestCase):
    def test_honest_claim_is_publishable(self):
        payload = verify_claims_payload(
            [_claim("c1", "The error rate fell to 3.5% under the structured workflow.", ["ev_error"])],
            EVIDENCE,
        )

        self.assertTrue(payload["publishable"])
        self.assertEqual(payload["verified_count"], 1)
        self.assertEqual(payload["blocked_count"], 0)

    def test_invented_statistic_is_blocked_by_deep_audit(self):
        payload = verify_claims_payload(
            [_claim("c1", "The error rate fell to 0.2% under the structured workflow.", ["ev_error"])],
            EVIDENCE,
        )

        self.assertFalse(payload["publishable"])
        blocked = payload["claim_results"][0]
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["checker"], "FE")

    def test_fabricated_citation_is_blocked(self):
        payload = verify_claims_payload(
            [_claim("c1", "An external audit certified the results.", ["ev_ghost"])],
            EVIDENCE,
        )

        self.assertFalse(payload["publishable"])
        self.assertEqual(payload["claim_results"][0]["checker"], "FA")

    def test_sentences_are_synthesized_when_missing(self):
        # Without explicit sentences the claim must still be anchored, so FA
        # cannot fail with "claim does not appear in sentence_map".
        payload = verify_claims_payload(
            [_claim("c1", "The error rate fell to 3.5% under the structured workflow.", ["ev_error"])],
            EVIDENCE,
            sentences=None,
        )

        self.assertTrue(payload["publishable"])

    def test_wording_strength_flags_overclaiming(self):
        claim = _claim("c1", "The error rate fell to 3.5% under the structured workflow.", ["ev_error"])
        claim["wording_strength"] = "measured"
        evidence = [dict(EVIDENCE[0], evidence_grade="low")]

        payload = verify_claims_payload([claim], evidence)

        self.assertFalse(payload["publishable"])
        self.assertEqual(payload["wording_flags"][0]["checker"], "FD")

    def test_empty_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_claims_payload([], EVIDENCE)
        with self.assertRaises(ValueError):
            verify_claims_payload([_claim("c1", "x", [])], [])


class ProfileAndStatusPayloadTests(unittest.TestCase):
    def test_profiles_payload_uses_report_profile_selector_only(self):
        payload = list_profiles_payload()

        self.assertEqual(payload["selector"], "report_profile")
        profile_ids = {profile["profile_id"] for profile in payload["profiles"]}
        self.assertIn("engineering_lab_report", profile_ids)
        self.assertIn("custom", profile_ids)
        self.assertEqual(len(profile_ids), 7)

    def test_unknown_job_id_raises_value_error(self):
        with self.assertRaises(ValueError):
            workflow_status_payload("job_that_does_not_exist_anywhere")


@unittest.skipUnless(MCP_AVAILABLE, "optional mcp extra not installed")
class ServerConstructionTests(unittest.TestCase):
    def test_build_server_exposes_the_whole_pipeline_not_just_the_gate(self):
        """MCP is the only surface every target agent speaks.

        The server used to expose three tools, none of which can produce a
        report, so an agent that installed it still had to clone this
        repository and copy the skill to get anywhere. The pipeline functions
        already existed in agent_wrapper; they were simply never registered.

        Each pipeline tool is checked against the function it delegates to, so
        renaming one in agent_wrapper fails here rather than at a caller's
        first invocation.
        """
        import asyncio

        from report_workflow import agent_wrapper
        from report_workflow.mcp_server import build_server

        server = build_server()
        tool_names = {tool.name for tool in asyncio.run(server.list_tools())}

        gate_tools = {"verify_claims", "list_report_profiles", "get_workflow_status"}
        pipeline_tools = {
            "check_environment": "check_setup",
            "start_report": "start_report_task",
            "get_next_action": "get_controlled_next_action",
            "submit_action": "submit_controlled_action",
            "query_evidence": "query_evidence",
            "lint_artifacts": "lint_agent_artifacts",
            "audit_engineering_report": "run_engineering_audit",
            "publish_report": "submit_and_publish_report",
            "submit_revision_plan": "submit_revision_plan",
            "preview_revision_diff": "preview_revision_diff",
        }

        self.assertEqual(tool_names, gate_tools | set(pipeline_tools))
        for tool_name, wrapper_name in pipeline_tools.items():
            with self.subTest(tool=tool_name):
                self.assertTrue(
                    callable(getattr(agent_wrapper, wrapper_name, None)),
                    f"{tool_name} delegates to agent_wrapper.{wrapper_name}, which is gone",
                )


if __name__ == "__main__":
    unittest.main()
