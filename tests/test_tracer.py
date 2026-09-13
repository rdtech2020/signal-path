import json
from datetime import UTC, datetime

from src.tracer import current_day_decision_count, current_month_cost, write_trace


def test_trace_is_allowlisted_and_aggregated(tmp_path):
    trace_path = tmp_path / "traces.jsonl"
    trace = write_trace(
        trace_path,
        {
            "decision": "draft_outreach",
            "output_status": "success",
            "total_cost_usd": 0.25,
            "request": {"account_name": "example.com"},
            "raw_banner": "must not be written",
        },
    )

    saved = json.loads(trace_path.read_text())
    assert saved == trace
    assert "raw_banner" not in saved
    assert saved["timestamp"].startswith(datetime.now(UTC).strftime("%Y-%m-%d"))
    assert current_month_cost(trace_path) == 0.25
    assert current_day_decision_count(trace_path, "draft_outreach") == 1
