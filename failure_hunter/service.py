from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .boundaries import generate_boundary_cases
from .gemma import DEFAULT_MODEL, GemmaClient, GemmaError
from .minimizer import minimize_failure
from .models import Failure, HuntReport, HuntRequest, TestCase
from .oracles import ORACLE_LABELS, check_oracle
from .runner import execute_case
from .source import validate_target


def _actual(result: dict[str, Any]) -> Any:
    if result["status"] == "ok":
        if result["output"] is None and result["output_repr"] != "None":
            return result["output_repr"]
        return result["output"]
    if result["status"] == "timeout":
        return "Execution timed out"
    return f'{result.get("exception_type")}: {result.get("exception_message")}'


def _failure_for(request: HuntRequest, case: TestCase, result: dict[str, Any], index: int) -> Failure | None:
    explicit_expectation = request.oracle != "review"
    expected = ORACLE_LABELS[request.oracle]
    if result["status"] != "ok":
        confirmed = explicit_expectation
        classification = result["status"] if confirmed else "suspicious"
        return Failure(
            failure_id=f"F-{index:03d}",
            function_name=request.function_name,
            strategy=case.strategy,
            original_input=case.args,
            expected=expected,
            actual=_actual(result),
            classification=classification,
            verification_status="confirmed" if confirmed else "suspected",
            reproduction_steps=f"Call {request.function_name}(**{case.args!r}) with a {request.timeout_seconds:g}s timeout.",
        )
    passed, expected = check_oracle(request.oracle, case.args, result["output"])
    if passed is False:
        return Failure(
            failure_id=f"F-{index:03d}",
            function_name=request.function_name,
            strategy=case.strategy,
            original_input=case.args,
            expected=expected,
            actual=_actual(result),
            classification="wrong_result",
            verification_status="confirmed",
            reproduction_steps=f"Call {request.function_name}(**{case.args!r}) and check: {expected}.",
        )
    return None


def run_cases(request: HuntRequest, cases: list[TestCase], *, model_identifier: str | None = None, ai_status: str = "not requested") -> HuntReport:
    validate_target(request.source, request.function_name, set(request.parameter_types))
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    failures: list[Failure] = []
    for index, case in enumerate(cases[: request.num_tests], 1):
        result = execute_case(request.source, request.function_name, case.args, request.timeout_seconds)
        row = {"input": case.args, "strategy": case.strategy, "rationale": case.rationale, **result.model_dump()}
        failure = _failure_for(request, case, row, index)
        row["verdict"] = failure.verification_status if failure else ("review" if request.oracle == "review" else "passed")
        rows.append(row)
        if failure:
            failures.append(failure)
    return HuntReport(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(),
        function_name=request.function_name,
        strategy=request.strategy,
        model_identifier=model_identifier,
        ai_status=ai_status,
        tests_executed=len(rows),
        duration_ms=round((time.perf_counter() - started) * 1_000, 3),
        results=rows,
        failures=failures,
    )


def run_hunt(request: HuntRequest, gemma: GemmaClient | None = None) -> HuntReport:
    wants_ai = request.strategy in {"ai", "both"}
    boundary_count = request.num_tests if request.strategy == "boundary" else (request.num_tests + 1) // 2
    if request.strategy == "ai":
        boundary_count = 0
    cases = generate_boundary_cases(request.parameter_types, boundary_count) if boundary_count else []
    ai_status = "not requested"
    model_identifier: str | None = None
    active_gemma: GemmaClient | None = None
    if wants_ai:
        ai_count = request.num_tests - len(cases)
        if ai_count <= 0:
            ai_status = "no AI cases fit within this test budget"
        else:
            try:
                gemma = gemma or GemmaClient()
                active_gemma = gemma
                model_identifier = gemma.model
                ai_cases, hypotheses = gemma.generate_tests(request, ai_count)
                cases.extend(ai_cases[:ai_count])
                ai_status = f"generated {min(len(ai_cases), ai_count)} tests; {len(hypotheses)} hypotheses"
            except GemmaError as exc:
                ai_status = str(exc)
                model_identifier = getattr(gemma, "model", os.getenv("GEMMA_MODEL", DEFAULT_MODEL)) if gemma else os.getenv("GEMMA_MODEL", DEFAULT_MODEL)
                # AI failure never disables the useful deterministic path.
                if not cases:
                    cases = generate_boundary_cases(request.parameter_types, request.num_tests)
    report = run_cases(request, cases, model_identifier=model_identifier, ai_status=ai_status)
    for failure in report.failures:
        failure.minimized_input = minimize_failure(request, failure)
    if active_gemma:
        analysis_errors: list[str] = []
        for failure in report.failures[:5]:
            try:
                analysis = active_gemma.analyze_failure(request, failure.model_dump())
                failure.explanation = analysis.explanation
                failure.suggested_fix = analysis.suggested_fix
            except GemmaError as exc:
                analysis_errors.append(str(exc))
        if analysis_errors:
            report.ai_status += f"; analysis unavailable: {analysis_errors[0]}"
    return report

