import os
import unittest
from unittest.mock import patch

from failure_hunter.gemma import GemmaClient, GemmaError, parse_test_response, relevant_function_source
from failure_hunter.models import HuntRequest
from failure_hunter.service import run_hunt


SOURCE = """
def helper():
    return 1

def buggy_sort(values: list[int]) -> list[int]:
    return sorted(set(values))
"""


class _Response:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, text):
        self.text = text

    def generate_content(self, **kwargs):
        return _Response(self.text)


class _Client:
    def __init__(self, text):
        self.models = _Models(text)


class StageTwoTests(unittest.TestCase):
    def test_extracts_only_selected_function(self):
        snippet = relevant_function_source(SOURCE, "buggy_sort")
        self.assertIn("def buggy_sort", snippet)
        self.assertNotIn("def helper", snippet)

    def test_validates_ai_json_and_types(self):
        cases, hypotheses = parse_test_response(
            '{"hypotheses":["duplicates"],"tests":['
            '{"args":{"values":[2,2]},"rationale":"duplicate values"},'
            '{"args":{"values":"not a list"},"rationale":"invalid"}]}' ,
            {"values": "list[int]"},
        )
        self.assertEqual(cases[0].args, {"values": [2, 2]})
        self.assertEqual(len(cases), 1)
        self.assertEqual(hypotheses, ["duplicates"])

    def test_rejects_non_json_model_output(self):
        with self.assertRaises(GemmaError):
            parse_test_response("```json\n{}\n```", {"x": "int"})

    def test_ai_case_discovers_seeded_bug(self):
        model_json = '{"hypotheses":["duplicates are lost"],"tests":[{"args":{"values":[2,2]},"rationale":"duplicate preservation"}]}'
        gemma = GemmaClient(model="gemma-test", client=_Client(model_json))
        report = run_hunt(
            HuntRequest(
                source=SOURCE,
                function_name="buggy_sort",
                parameter_types={"values": "list[int]"},
                oracle="sorted",
                strategy="ai",
                num_tests=1,
            ),
            gemma=gemma,
        )
        self.assertEqual(report.model_identifier, "gemma-test")
        self.assertEqual(report.failures[0].verification_status, "confirmed")

    def test_missing_key_falls_back_to_boundaries(self):
        with patch.dict(os.environ, {}, clear=True):
            report = run_hunt(
                HuntRequest(
                    source=SOURCE,
                    function_name="buggy_sort",
                    parameter_types={"values": "list[int]"},
                    oracle="sorted",
                    strategy="ai",
                    num_tests=8,
                )
            )
        self.assertIn("not configured", report.ai_status)
        self.assertGreater(report.tests_executed, 0)


if __name__ == "__main__":
    unittest.main()
