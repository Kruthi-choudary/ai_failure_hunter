import unittest

from failure_hunter.models import HuntRequest
from failure_hunter.reporting import regression_test_source, report_json
from failure_hunter.service import run_hunt


class StageThreeTests(unittest.TestCase):
    def test_minimizes_duplicate_sort_failure(self):
        source = "def buggy_sort(values):\n    return sorted(set(values))\n"
        report = run_hunt(
            HuntRequest(
                source=source,
                function_name="buggy_sort",
                parameter_types={"values": "list[int]"},
                oracle="sorted",
                num_tests=8,
            )
        )
        larger = next(f for f in report.failures if f.original_input["values"] == [2, 2, 1])
        self.assertIsNotNone(larger.minimized_input)
        self.assertEqual(len(larger.minimized_input["values"]), 2)

    def test_exports_reproducible_regression(self):
        source = "def buggy_abs(value):\n    return value\n"
        request = HuntRequest(
            source=source,
            function_name="buggy_abs",
            parameter_types={"value": "int"},
            oracle="non_negative",
            num_tests=5,
        )
        report = run_hunt(request)
        generated = regression_test_source(request, report)
        self.assertIn("assert buggy_abs", generated)
        compile(generated, "regression_test.py", "exec")
        self.assertIn('"failures"', report_json(report))


if __name__ == "__main__":
    unittest.main()
