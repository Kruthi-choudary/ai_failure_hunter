from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from failure_hunter.models import HuntRequest  # noqa: E402
from failure_hunter.service import run_hunt  # noqa: E402


TARGETS = [
    {
        "name": "buggy_sort",
        "source": "def buggy_sort(values):\n    return sorted(set(values))\n",
        "types": {"values": "list[int]"},
        "oracle": "sorted",
        "seeded_bug": True,
        "description": "Sort ascending while preserving duplicates.",
    },
    {
        "name": "buggy_absolute",
        "source": "def buggy_absolute(value):\n    return value if value >= 0 else value\n",
        "types": {"value": "int"},
        "oracle": "non_negative",
        "seeded_bug": True,
        "description": "Return the non-negative magnitude.",
    },
    {
        "name": "correct_sort",
        "source": "def correct_sort(values):\n    return sorted(values)\n",
        "types": {"values": "list[int]"},
        "oracle": "sorted",
        "seeded_bug": False,
        "description": "Correct control function.",
    },
]


def benchmark_strategy(strategy: str, budget: int) -> dict[str, object]:
    details = []
    started = time.perf_counter()
    for target in TARGETS:
        report = run_hunt(
            HuntRequest(
                source=target["source"],
                function_name=target["name"],
                parameter_types=target["types"],
                description=target["description"],
                expected_behavior=target["description"],
                oracle=target["oracle"],
                strategy=strategy,
                num_tests=budget,
            )
        )
        confirmed = [failure for failure in report.failures if failure.verification_status == "confirmed"]
        first_index = int(confirmed[0].failure_id.split("-")[1]) if confirmed else None
        details.append(
            {
                "target": target["name"],
                "seeded_bug": target["seeded_bug"],
                "discovered": bool(confirmed),
                "confirmed_failures": len(confirmed),
                "tests_executed": report.tests_executed,
                "test_index_to_first_failure": first_index,
                "minimized_failures": sum(f.minimized_input is not None for f in confirmed),
                "duration_ms": report.duration_ms,
                "ai_status": report.ai_status,
                "model_identifier": report.model_identifier,
            }
        )
    seeded = [row for row in details if row["seeded_bug"]]
    controls = [row for row in details if not row["seeded_bug"]]
    false_positives = sum(bool(row["discovered"]) for row in controls)
    return {
        "strategy": strategy,
        "budget_per_target": budget,
        "seeded_bugs_discovered": sum(bool(row["discovered"]) for row in seeded),
        "seeded_bugs_total": len(seeded),
        "confirmed_failures": sum(int(row["confirmed_failures"]) for row in details),
        "false_positive_rate": false_positives / len(controls) if controls else None,
        "tests_executed": sum(int(row["tests_executed"]) for row in details),
        "minimization_success_rate": (
            sum(int(row["minimized_failures"]) for row in details)
            / max(1, sum(int(row["confirmed_failures"]) for row in details))
        ),
        "wall_time_ms": round((time.perf_counter() - started) * 1_000, 3),
        "targets": details,
    }


def main() -> None:
    output = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "method": "Same three targets and 8-test budget per strategy. A failure counts only when the explicit oracle is violated.",
        "results": [benchmark_strategy("boundary", 8)],
    }
    if os.getenv("GEMINI_API_KEY"):
        output["results"].append(benchmark_strategy("ai", 8))
    else:
        output["results"].append(
            {
                "strategy": "ai",
                "status": "not measured: GEMINI_API_KEY was not configured",
                "model_identifier": os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it"),
            }
        )
    destination = ROOT / "benchmark" / "results" / "latest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
