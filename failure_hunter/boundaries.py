from __future__ import annotations

from itertools import islice

from .models import TestCase


VALUES: dict[str, list[object]] = {
    "int": [0, 1, -1, 2, -2, 2**31 - 1, -(2**31)],
    "float": [0.0, 1.0, -1.0, 0.5, -0.5, 1e-9, 1e9],
    "str": ["", "a", " ", "aa", "A", "0", "🙂"],
    "bool": [False, True],
    "list[int]": [[], [0], [1], [-1], [1, 1], [2, 1], [0, -1, 1], [2, 2, 1]],
    "list[str]": [[], [""], ["a"], ["a", "a"], ["b", "a"], ["", "a"]],
}


def generate_boundary_cases(parameter_types: dict[str, str], limit: int) -> list[TestCase]:
    if not parameter_types:
        return [TestCase(args={}, rationale="zero-argument call")]
    names = list(parameter_types)
    baseline = {name: VALUES[kind][0] for name, kind in parameter_types.items()}
    candidates: list[TestCase] = []
    seen: set[str] = set()
    for name in names:
        for value in VALUES[parameter_types[name]]:
            args = dict(baseline)
            args[name] = value
            key = repr(args)
            if key not in seen:
                seen.add(key)
                candidates.append(TestCase(args=args, rationale=f"boundary value for {name}"))
    # A few aligned multi-parameter cases catch comparisons such as low/high bounds.
    for index in range(1, 5):
        args = {name: VALUES[kind][min(index, len(VALUES[kind]) - 1)] for name, kind in parameter_types.items()}
        key = repr(args)
        if key not in seen:
            candidates.append(TestCase(args=args, rationale="combined boundary values"))
            seen.add(key)
    return list(islice(candidates, limit))

