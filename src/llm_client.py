"""Structured, budget-guarded outreach generation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from config.settings import Settings, settings
from src.scoring import AccountScore, load_rules
from src.tracer import current_day_decision_count, current_month_cost, write_trace

PROMPT_VERSION = "outreach_draft_v1"
SKILL_NAME = "outreach-draft"
INPUT_PRICE_PER_MILLION = 0.150
OUTPUT_PRICE_PER_MILLION = 0.600


class OutreachDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=80)
    opening: str = Field(max_length=280)
    evidence: list[str] = Field(min_length=1, max_length=3)
    call_to_action: str = Field(max_length=180)
    confidence: str = Field(pattern="^(low|medium|high)$")


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1_000_000 * INPUT_PRICE_PER_MILLION
        + completion_tokens / 1_000_000 * OUTPUT_PRICE_PER_MILLION
    )


def _safe_payload(account: AccountScore) -> dict[str, object]:
    return {
        "account_name": account.account_name,
        "country_code": account.country_code,
        "icp_score": account.icp_score,
        "ports": list(account.ports),
        "signals": [
            {"code": signal.code, "detail": signal.detail}
            for signal in account.signals
            if signal.weight > 0
        ],
    }


def generate_outreach(
    account: AccountScore,
    prompt_path: Path = Path("prompts/outreach_draft_v1.md"),
    app_settings: Settings = settings,
) -> OutreachDraft:
    """Generate and trace one draft; raw banner data never reaches the model."""
    if not account.is_addressable:
        raise ValueError("outreach requires an addressable company domain")
    spent_this_month = current_month_cost(app_settings.trace_path)
    if spent_this_month >= app_settings.llm_monthly_budget_usd:
        raise RuntimeError("monthly LLM budget exhausted")
    rules = load_rules(vertical=account.vertical)
    daily_cap = int(rules["daily_draft_cap"])
    prompt_file = Path(rules.get("prompt_path", prompt_path))
    drafts_today = current_day_decision_count(app_settings.trace_path, "draft_outreach")
    if drafts_today >= daily_cap:
        raise RuntimeError("daily outreach draft cap exhausted")
    if not app_settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = prompt_file.read_text(encoding="utf-8")
    payload = _safe_payload(account)
    client = OpenAI(api_key=app_settings.openai_api_key)
    started_at = time.perf_counter()
    status = "error"
    validation_passed = False
    prompt_tokens = 0
    completion_tokens = 0
    response_payload: dict[str, object] | None = None

    try:
        response = client.responses.parse(
            model=app_settings.llm_model,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            text_format=OutreachDraft,
        )
        draft = response.output_parsed
        if draft is None:
            raise RuntimeError("model returned no parsed outreach draft")
        usage = response.usage
        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0
        status = "success"
        validation_passed = True
        response_payload = draft.model_dump()
        return draft
    finally:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        write_trace(
            app_settings.trace_path,
            {
                "account_id": account.account_id,
                "completion_tokens": completion_tokens,
                "decision": "draft_outreach",
                "icp_score": account.icp_score,
                "latency_ms": latency_ms,
                "model": app_settings.llm_model,
                "output_status": status,
                "prompt_tokens": prompt_tokens,
                "prompt_version": PROMPT_VERSION,
                "request": payload,
                "response": response_payload,
                "signals": [signal.code for signal in account.signals],
                "skill_name": SKILL_NAME,
                "total_cost_usd": estimate_cost(prompt_tokens, completion_tokens),
                "validation_passed": validation_passed,
                "vertical": account.vertical,
            },
        )
