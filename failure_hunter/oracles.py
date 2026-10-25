from __future__ import annotations

from typing import Any


ORACLE_LABELS = {
    "review": "No executable oracle; unusual behavior requires human review",
    "no_exception": "The function returns without raising an exception",
    "sorted": "The result equals Python's sorted() of the first argument",
    "sum": "The result equals Python's sum() of the first argument",
    "identity": "The result equals the first argument",
    "non_negative": "The result is a number greater than or equal to zero",
}


def check_oracle(oracle: str, args: dict[str, Any], output: Any) -> tuple[bool | None, str]:
    expected = ORACLE_LABELS[oracle]
    if oracle == "review":
        return None, expected
    if oracle == "no_exception":
        return True, expected
    first = next(iter(args.values()), None)
    try:
        if oracle == "sorted":
            return output == sorted(first), expected
        if oracle == "sum":
            return output == sum(first), expected
        if oracle == "identity":
            return output == first, expected
        if oracle == "non_negative":
            return isinstance(output, (int, float)) and not isinstance(output, bool) and output >= 0, expected
    except (TypeError, ValueError):
        return False, expected
    raise ValueError(f"Unknown oracle: {oracle}")

