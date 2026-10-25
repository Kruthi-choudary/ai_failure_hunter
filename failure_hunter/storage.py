from __future__ import annotations

import json
from pathlib import Path

from .models import HuntReport, HuntRequest


class RunStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).resolve().parent.parent / "runs"
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, request: HuntRequest, report: HuntReport) -> Path:
        path = self.directory / f"{report.run_id}.json"
        payload = {"request": request.model_dump(), "report": report.model_dump()}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def list(self, limit: int = 20) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))["report"]
                entries.append(
                    {
                        "run_id": report["run_id"],
                        "created_at": report["created_at"],
                        "function_name": report["function_name"],
                        "strategy": report["strategy"],
                        "tests_executed": report["tests_executed"],
                        "confirmed": sum(f["verification_status"] == "confirmed" for f in report["failures"]),
                        "suspected": sum(f["verification_status"] == "suspected" for f in report["failures"]),
                    }
                )
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return entries

    def load(self, run_id: str) -> dict[str, object]:
        if not run_id.isalnum():
            raise ValueError("Invalid run ID")
        path = self.directory / f"{run_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

