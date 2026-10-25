from __future__ import annotations

import contextlib
import io
import json
import resource
import sys
import time
import traceback


def _limits() -> None:
    limits = [
        (resource.RLIMIT_CPU, (2, 2)),
        (resource.RLIMIT_FSIZE, (1_000_000, 1_000_000)),
    ]
    # RLIMIT_AS is unreliable on macOS but useful on Linux.
    if sys.platform.startswith("linux"):
        limits.append((resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024)))
    for kind, value in limits:
        try:
            resource.setrlimit(kind, value)
        except (ValueError, OSError):
            pass


def _json_value(value: object) -> tuple[object | None, str]:
    representation = repr(value)[:2_000]
    try:
        json.dumps(value, allow_nan=False)
        return value, representation
    except (TypeError, ValueError):
        return None, representation


def main() -> None:
    _limits()
    request = json.load(sys.stdin)
    namespace: dict[str, object] = {"__builtins__": __builtins__, "__name__": "submitted_code"}
    stdout, stderr = io.StringIO(), io.StringIO()
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(request["source"], "<submitted>", "exec"), namespace, namespace)
            function = namespace[request["function_name"]]
            output = function(**request["args"])  # type: ignore[operator]
        json_output, output_repr = _json_value(output)
        result = {"status": "ok", "output": json_output, "output_repr": output_repr}
    except BaseException as exc:
        result = {
            "status": "exception",
            "output": None,
            "output_repr": "",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)[:1_000],
            "traceback": traceback.format_exc(limit=8)[-4_000:],
        }
    result["duration_ms"] = round((time.perf_counter() - started) * 1_000, 3)
    result["stdout"] = stdout.getvalue()[-2_000:]
    result["stderr"] = stderr.getvalue()[-2_000:]
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()

