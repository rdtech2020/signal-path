"""Privacy-conscious JSONL tracing for LLM calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ALLOWED_TRACE_FIELDS = {
    "account_id",
    "completion_tokens",
    "decision",
    "icp_score",
    "latency_ms",
    "model",
    "output_status",
    "prompt_tokens",
    "prompt_version",
    "request",
    "response",
    "signals",
    "skill_name",
    "total_cost_usd",
    "validation_passed",
    "vertical",
}


def write_trace(path: Path, values: dict[str, Any]) -> dict[str, Any]:
    """Append a redacted trace. Unknown fields are intentionally discarded."""
    trace = {
        "trace_id": f"tr_{uuid4().hex}",
        "timestamp": datetime.now(UTC).isoformat(),
        **{key: values[key] for key in ALLOWED_TRACE_FIELDS if key in values},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return trace


def current_month_cost(path: Path) -> float:
    if not path.exists():
        return 0.0
    month_prefix = datetime.now(UTC).strftime("%Y-%m")
    total = 0.0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(trace.get("timestamp", "")).startswith(month_prefix):
                total += float(trace.get("total_cost_usd", 0))
    return total


def current_day_decision_count(path: Path, decision: str) -> int:
    if not path.exists():
        return 0
    day_prefix = datetime.now(UTC).strftime("%Y-%m-%d")
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                str(trace.get("timestamp", "")).startswith(day_prefix)
                and trace.get("decision") == decision
                and trace.get("output_status") == "success"
            ):
                count += 1
    return count
