from __future__ import annotations

import ast


class SourceError(ValueError):
    pass


def discover_functions(source: str) -> list[dict[str, object]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SourceError(f"Invalid Python: {exc.msg} at line {exc.lineno}") from exc

    functions: list[dict[str, object]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params = []
            for arg in node.args.args:
                annotation = ast.unparse(arg.annotation) if arg.annotation else "unknown"
                params.append({"name": arg.arg, "annotation": annotation})
            functions.append({"name": node.name, "parameters": params, "async": isinstance(node, ast.AsyncFunctionDef)})
    return functions


def validate_target(source: str, function_name: str, parameter_names: set[str]) -> None:
    functions = discover_functions(source)
    target = next((f for f in functions if f["name"] == function_name), None)
    if target is None:
        raise SourceError(f"Function {function_name!r} was not found at module level")
    if target["async"]:
        raise SourceError("async functions are not supported in this version")
    actual = {p["name"] for p in target["parameters"]}  # type: ignore[index]
    if actual != parameter_names:
        raise SourceError(f"Parameter schema must match the function parameters: {sorted(actual)}")

