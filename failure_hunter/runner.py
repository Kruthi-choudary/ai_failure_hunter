from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from .models import ExecutionResult


def _bounded(value: Any, depth: int = 0) -> bool:
    if depth > 4:
        return False
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= 1_000
    if isinstance(value, list):
        return len(value) <= 200 and all(_bounded(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return len(value) <= 20 and all(isinstance(k, str) and _bounded(v, depth + 1) for k, v in value.items())
    return False


def execute_case(source: str, function_name: str, args: dict[str, Any], timeout: float) -> ExecutionResult:
    if not _bounded(args):
        raise ValueError("Input exceeds the supported JSON size or nesting limits")
    payload = json.dumps({"source": source, "function_name": function_name, "args": args}, allow_nan=False)
    env = dict(os.environ)
    project_root = os.path.dirname(os.path.dirname(__file__))
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="failure-hunter-") as workdir:
        process = subprocess.Popen(
            [sys.executable, "-m", "failure_hunter.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=workdir,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.kill()
            process.communicate()
            return ExecutionResult(status="timeout", duration_ms=round((time.perf_counter() - started) * 1_000, 3))
    try:
        raw = json.loads(stdout)
        return ExecutionResult.model_validate(raw)
    except Exception:
        message = (stderr or stdout or f"worker exited {process.returncode}")[-1_000:]
        return ExecutionResult(
            status="worker_error",
            exception_type="WorkerProtocolError",
            exception_message=message,
            duration_ms=round((time.perf_counter() - started) * 1_000, 3),
        )
