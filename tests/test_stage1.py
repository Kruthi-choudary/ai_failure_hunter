import unittest

from failure_hunter.boundaries import generate_boundary_cases
from failure_hunter.models import HuntRequest
from failure_hunter.runner import execute_case
from failure_hunter.service import run_hunt
from failure_hunter.source import discover_functions


BUGGY_SORT = """
def buggy_sort(values: list[int]) -> list[int]:
    return sorted(set(values))
"""


class StageOneTests(unittest.TestCase):
    def test_discovers_function_signature(self):
        found = discover_functions(BUGGY_SORT)
        self.assertEqual(found[0]["name"], "buggy_sort")
        self.assertEqual(found[0]["parameters"], [{"name": "values", "annotation": "list[int]"}])

    def test_boundary_cases_include_duplicate_list(self):
        cases = generate_boundary_cases({"values": "list[int]"}, 20)
        self.assertTrue(any(case.args["values"] == [1, 1] for case in cases))

    def test_worker_captures_exception(self):
        result = execute_case("def boom(x):\n    return 1 / x\n", "boom", {"x": 0}, 1)
        self.assertEqual(result.status, "exception")
        self.assertEqual(result.exception_type, "ZeroDivisionError")

    def test_seeded_sort_bug_is_confirmed(self):
        report = run_hunt(
            HuntRequest(
                source=BUGGY_SORT,
                function_name="buggy_sort",
                parameter_types={"values": "list[int]"},
                oracle="sorted",
                num_tests=20,
            )
        )
        self.assertGreater(report.tests_executed, 0)
        self.assertTrue(
            any(f.verification_status == "confirmed" and f.original_input["values"] == [1, 1] for f in report.failures)
        )

    def test_review_only_exception_is_suspected(self):
        report = run_hunt(
            HuntRequest(
                source="def reciprocal(x):\n    return 1 / x\n",
                function_name="reciprocal",
                parameter_types={"x": "int"},
                oracle="review",
                num_tests=2,
            )
        )
        self.assertEqual(report.failures[0].classification, "suspicious")
        self.assertEqual(report.failures[0].verification_status, "suspected")

    def test_worker_times_out(self):
        result = execute_case("def spin():\n    while True: pass\n", "spin", {}, 0.1)
        self.assertEqual(result.status, "timeout")


if __name__ == "__main__":
    unittest.main()

