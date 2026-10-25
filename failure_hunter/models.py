from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


JsonScalar = None | bool | int | float | str
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    args: dict[str, JsonValue]
    strategy: Literal["boundary", "ai", "regression"] = "boundary"
    rationale: str = ""


class HuntRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=30_000)
    function_name: str = Field(pattern=r"^[A-Za-z_]\w*$")
    parameter_types: dict[str, Literal["int", "float", "str", "bool", "list[int]", "list[str]"]]
    description: str = Field(default="", max_length=2_000)
    expected_behavior: str = Field(default="", max_length=2_000)
    oracle: Literal["review", "no_exception", "sorted", "sum", "identity", "non_negative"] = "review"
    strategy: Literal["boundary", "ai", "both"] = "boundary"
    num_tests: int = Field(default=20, ge=1, le=100)
    timeout_seconds: float = Field(default=1.0, ge=0.1, le=5.0)

    @field_validator("parameter_types")
    @classmethod
    def require_parameters(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 8:
            raise ValueError("at most 8 parameters are supported")
        return value


class ExecutionResult(BaseModel):
    status: Literal["ok", "exception", "timeout", "worker_error"]
    output: JsonValue = None
    output_repr: str = ""
    exception_type: str | None = None
    exception_message: str | None = None
    duration_ms: float


class Failure(BaseModel):
    failure_id: str
    function_name: str
    strategy: str
    original_input: dict[str, JsonValue]
    minimized_input: dict[str, JsonValue] | None = None
    expected: str
    actual: JsonValue | str | None
    classification: Literal["wrong_result", "exception", "timeout", "worker_error", "suspicious"]
    verification_status: Literal["confirmed", "suspected"]
    reproduction_steps: str = ""
    explanation: str = ""
    suggested_fix: str = ""


class HuntReport(BaseModel):
    run_id: str
    created_at: str
    function_name: str
    strategy: str
    model_identifier: str | None = None
    ai_status: str = "not requested"
    tests_executed: int
    duration_ms: float
    results: list[dict[str, Any]]
    failures: list[Failure]

