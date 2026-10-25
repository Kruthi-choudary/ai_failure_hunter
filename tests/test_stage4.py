import json
import tempfile
import unittest
from pathlib import Path

from failure_hunter.gemma import GemmaClient
from failure_hunter.models import HuntRequest
from failure_hunter.service import run_hunt
from failure_hunter.storage import RunStore


class _Response:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, responses):
        self.responses = iter(responses)

    def generate_content(self, **kwargs):
        return _Response(next(self.responses))


class _Client:
    def __init__(self, responses):
        self.models = _Models(responses)


class StageFourTests(unittest.TestCase):
    def test_ai_analysis_is_labeled_and_stored(self):
        responses = [
            '{"hypotheses":["duplicates"],"tests":[{"args":{"values":[3,3]},"rationale":"duplicate"}]}',
            '{"explanation":"The observed output loses one duplicate.","suggested_fix":"Return sorted(values)."}',
        ]
        gemma = GemmaClient(model="gemma-test", client=_Client(responses))
        request = HuntRequest(
            source="def buggy(values):\n    return sorted(set(values))\n",
            function_name="buggy",
            parameter_types={"values": "list[int]"},
            oracle="sorted",
            strategy="ai",
            num_tests=1,
        )
        report = run_hunt(request, gemma=gemma)
        self.assertIn("loses one duplicate", report.failures[0].explanation)
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory))
            path = store.save(request, report)
            self.assertTrue(path.exists())
            self.assertEqual(store.list()[0]["confirmed"], 1)
            self.assertEqual(json.loads(path.read_text())["report"]["model_identifier"], "gemma-test")


if __name__ == "__main__":
    unittest.main()
