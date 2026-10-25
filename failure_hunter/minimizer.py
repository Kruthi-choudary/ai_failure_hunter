from __future__ import annotations

from typing import Any, Callable, Iterator

from .models import Failure, HuntRequest
from .oracles import check_oracle
from .runner import execute_case


def _simpler_values(value: Any) -> Iterator[Any]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        for candidate in (0, 1, -1, value // 2):
            if candidate != value:
                yield candidate
    elif isinstance(value, float):
        for candidate in (0.0, 1.0, -1.0, value / 2):
            if candidate != value:
                yield candidate
    elif isinstance(value, str):
        if value:
            yield ""
        size = len(value)
        while size > 1:
            size //= 2
            yield value[:size]
    elif isinstance(value, list):
        n = len(value)
        granularity = 2
        while n and granularity <= max(2, n * 2):
            chunk = max(1, (n + granularity - 1) // granularity)
            for start in range(0, n, chunk):
                yield value[:start] + value[start + chunk :]
            granularity *= 2
        for index, item in enumerate(value):
            for simpler in _simpler_values(item):
                candidate = list(value)
                candidate[index] = simpler
                yield candidate


def _same_failure(request: HuntRequest, args: dict[str, Any], original: Failure) -> bool:
    result = execute_case(request.source, request.function_name, args, request.timeout_seconds)
    if original.classification == "wrong_result":
        if result.status != "ok":
            return False
        passed, _ = check_oracle(request.oracle, args, result.output)
        return passed is False
    if original.classification in {"exception", "suspicious"}:
        return result.status == "exception" and str(original.actual).startswith(f"{result.exception_type}:")
    if original.classification == "worker_error":
        return result.status == "worker_error"
    return False  # Timeouts are deliberately not minimized; retries are costly and noisy.


def minimize_failure(request: HuntRequest, failure: Failure, budget: int = 15) -> dict[str, Any] | None:
    if failure.classification == "timeout":
        return None
    values = list(failure.original_input.values())
    if values and all(isinstance(value, list) and len(value) <= 2 for value in values):
        return None
    current = dict(failure.original_input)
    attempts = 0
    changed = True
    while changed and attempts < budget:
        changed = False
        for name, value in list(current.items()):
            for simpler in _simpler_values(value):
                attempts += 1
                candidate = dict(current)
                candidate[name] = simpler
                if _same_failure(request, candidate, failure):
                    current = candidate
                    changed = True
                    break
                if attempts >= budget:
                    break
            if changed or attempts >= budget:
                break
    return current if current != failure.original_input else None

