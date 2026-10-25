from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .models import HuntReport, HuntRequest
from .service import run_hunt
from .source import SourceError, discover_functions
from .storage import RunStore


app = FastAPI(title="AI Failure Hunter", version="0.1.0")
store = RunStore()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/functions")
def functions(payload: dict[str, str]) -> list[dict[str, object]]:
    try:
        return discover_functions(payload.get("source", ""))
    except SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/runs", response_model=HuntReport)
def create_run(request: HuntRequest) -> HuntReport:
    try:
        report = run_hunt(request)
        store.save(request, report)
        return report
    except (SourceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/runs")
def runs() -> list[dict[str, object]]:
    return store.list()

