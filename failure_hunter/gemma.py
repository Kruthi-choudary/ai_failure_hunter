from __future__ import annotations

import ast
import json
import os
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import HuntRequest, TestCase


DEFAULT_MODEL = "gemma-4-26b-a4b-it"


class GemmaError(RuntimeError):
    pass


class AICandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    args: dict[str, Any]
    rationale: str = Field(min_length=1, max_length=500)


class AITestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypotheses: list[str] = Field(default_factory=list, max_length=10)
    tests: list[AICandidate] = Field(max_length=100)


class AIAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1, max_length=2_000)
    suggested_fix: str = Field(default="", max_length=2_000)


def relevant_function_source(source: str, function_name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])[:6_000]
    return ""


def _type_ok(value: Any, kind: str) -> bool:
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool) and -(2**53) <= value <= 2**53
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) <= 1e100
    if kind == "str":
        return isinstance(value, str) and len(value) <= 1_000
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "list[int]":
        return isinstance(value, list) and len(value) <= 200 and all(_type_ok(v, "int") for v in value)
    if kind == "list[str]":
        return isinstance(value, list) and len(value) <= 200 and all(_type_ok(v, "str") for v in value)
    return False


def parse_test_response(text: str, parameter_types: dict[str, str]) -> tuple[list[TestCase], list[str]]:
    try:
        batch = AITestBatch.model_validate_json(text)
    except ValidationError as exc:
        raise GemmaError(f"Gemma returned invalid test JSON: {exc.errors()[0]['msg']}") from exc
    expected_names = set(parameter_types)
    cases: list[TestCase] = []
    seen: set[str] = set()
    for candidate in batch.tests:
        if set(candidate.args) != expected_names:
            continue
        if not all(_type_ok(candidate.args[name], kind) for name, kind in parameter_types.items()):
            continue
        key = json.dumps(candidate.args, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            cases.append(TestCase(args=candidate.args, strategy="ai", rationale=candidate.rationale))
    if not cases:
        raise GemmaError("Gemma returned no inputs matching the declared parameter schema")
    return cases, batch.hypotheses


class GemmaClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, client: Any = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMMA_MODEL", DEFAULT_MODEL)
        if client is not None:
            self.client = client
            return
        if not self.api_key:
            raise GemmaError("Gemma is not configured. Set GEMINI_API_KEY; deterministic boundary tests still work.")
        try:
            from google import genai
        except ImportError as exc:
            raise GemmaError("The google-genai package is not installed; deterministic boundary tests still work.") from exc
        self.client = genai.Client(api_key=self.api_key)

    def _generate(self, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(model=self.model, contents=prompt)
                if not getattr(response, "text", None):
                    raise GemmaError("Gemma returned an empty response")
                return response.text
            except GemmaError:
                raise
            except Exception as exc:
                last_error = exc
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                retryable = status in {429, 500, 502, 503, 504} or any(
                    marker in str(exc).lower() for marker in ("rate", "timeout", "tempor", "unavailable", "network")
                )
                if not retryable or attempt == 2:
                    break
                time.sleep(0.5 * (2**attempt))
        message = str(last_error) if last_error else "unknown API error"
        raise GemmaError(f"Gemma request failed for model {self.model}: {message}") from last_error

    def generate_tests(self, request: HuntRequest, count: int) -> tuple[list[TestCase], list[str]]:
        snippet = relevant_function_source(request.source, request.function_name)
        schema_example = {
            "hypotheses": ["short likely failure condition"],
            "tests": [{"args": {name: f"<{kind}>" for name, kind in request.parameter_types.items()}, "rationale": "why this edge case matters"}],
        }
        prompt = f"""You generate edge-case TEST DATA, never Python expressions or code.
Return exactly one JSON object and no Markdown. Use this shape:
{json.dumps(schema_example)}
Produce at most {count} diverse tests. Every args object must have exactly these typed fields:
{json.dumps(request.parameter_types)}
Keep strings under 1000 characters and lists under 200 items. JSON numbers must be finite.

Function:
{snippet}
Description: {request.description}
Expected behavior: {request.expected_behavior}
Executable oracle: {request.oracle}
"""
        return parse_test_response(self._generate(prompt), request.parameter_types)

    def analyze_failure(self, request: HuntRequest, evidence: dict[str, Any]) -> AIAnalysis:
        prompt = f"""Analyze only the supplied failure evidence. Do not claim certainty beyond it.
Return exactly one JSON object and no Markdown with keys "explanation" and "suggested_fix", both strings.
Function:
{relevant_function_source(request.source, request.function_name)}
Developer expectation: {request.expected_behavior}
Evidence: {json.dumps(evidence, ensure_ascii=False, default=str)[:8_000]}
If the evidence is only suspected, say human review is required. Never include executable test inputs.
"""
        try:
            return AIAnalysis.model_validate_json(self._generate(prompt))
        except ValidationError as exc:
            raise GemmaError(f"Gemma returned invalid analysis JSON: {exc.errors()[0]['msg']}") from exc

