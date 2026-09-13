"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    product_name: str = os.getenv("PRODUCT_NAME", "SignalPath")
    vertical: str = os.getenv("VERTICAL", "cybersecurity")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_monthly_budget_usd: float = float(os.getenv("LLM_MONTHLY_BUDGET_USD", "25"))
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    trace_path: Path = Path(os.getenv("TRACE_PATH", "logs/traces.jsonl"))
    database_path: Path = Path(
        os.getenv("DATABASE_PATH", "data/signal_path.duckdb")
    )


settings = Settings()
