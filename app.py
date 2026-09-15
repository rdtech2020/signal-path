"""Streamlit prospect queue backed by the DuckDB account store."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import settings
from src.duckdb_store import (
    query_country_codes,
    query_database_summary,
    query_qualified_accounts,
    query_ranked_accounts,
)
from src.llm_client import generate_outreach
from src.scoring import AccountScore, Signal, load_rules


def database_accounts(rows: list[dict[str, object]]) -> list[AccountScore]:
    """Convert bounded query results to the app's existing account contract."""
    weights = rules["weights"]
    return [
        AccountScore(
            account_id=str(row["account_id"]),
            account_name=str(row["account_name"]),
            is_named=bool(row["is_named"]),
            is_addressable=bool(row["is_addressable"]),
            icp_score=int(row["icp_score"]),
            country_code=(
                str(row["country_code"]) if row["country_code"] else None
            ),
            org=str(row["org"]) if row["org"] else None,
            ports=tuple(int(port) for port in row["ports"]),
            ip_addresses=tuple(str(ip) for ip in row["ip_addresses"]),
            banner_count=int(row["banner_count"]),
            signals=tuple(
                Signal(
                    code=str(code),
                    weight=int(weights[str(code)]),
                    detail=f"Detected by deterministic rule: {code}",
                )
                for code in row["signal_codes"]
            ),
            vertical=str(row["vertical"]),
        )
        for row in rows
    ]


def account_rows(accounts: list[AccountScore]) -> list[dict[str, object]]:
    return [
        {
            "account": account.account_name,
            "score": account.icp_score,
            "addressable": account.is_addressable,
            "country": account.country_code,
            "org": account.org,
            "ports": ", ".join(map(str, account.ports)),
            "signals": ", ".join(signal.code for signal in account.signals),
            "banners": account.banner_count,
        }
        for account in accounts
    ]


rules = load_rules()
vertical_label = str(rules.get("label") or rules.get("id") or settings.vertical)

st.set_page_config(page_title=settings.product_name, layout="wide")
st.title(settings.product_name)
st.caption(
    f"{vertical_label} queue from observational data. "
    "Scores are deterministic; outreach is optional and budget-gated."
)

gate = int(rules["llm_gate_score"])
database_path = Path(os.getenv("DATABASE_PATH", str(settings.database_path)))
if not database_path.exists():
    st.error(
        f"DuckDB not found at {database_path}. "
        "Build it with `python scripts/build_duckdb.py`."
    )
    st.stop()

score_floor = st.sidebar.slider("Minimum score", 0, 100, 0, 5)
addressable_only = st.sidebar.checkbox("Addressable accounts only", value=True)
country_options = query_country_codes(database_path)
countries = st.sidebar.multiselect("Countries", country_options)

summary = query_database_summary(database_path, gate)
filtered = database_accounts(
    query_ranked_accounts(
        database_path,
        minimum_score=score_floor,
        addressable_only=addressable_only,
        country_codes=tuple(countries),
        limit=100,
    )
)
qualified = database_accounts(
    query_qualified_accounts(
        database_path,
        minimum_score=gate,
        limit=int(rules["daily_draft_cap"]),
    )
)
st.caption(
    "Showing at most 100 qualified and ranked rows. "
    "Raw banner facts stay outside Python."
)

metric_columns = st.columns(4)
metric_columns[0].metric("Banners", f"{summary['banners']:,}")
metric_columns[1].metric("Accounts", f"{summary['accounts']:,}")
metric_columns[2].metric("Addressable", f"{summary['addressable']:,}")
metric_columns[3].metric(f"Qualified (≥ {gate})", f"{summary['qualified']:,}")

st.subheader("Ranked account queue")
if filtered:
    st.dataframe(
        pd.DataFrame(account_rows(filtered)),
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No accounts match these filters.")

st.subheader("Evidence-grounded outreach")
if not qualified:
    st.info("No accounts pass the current outreach gate.")
else:
    selected_id = st.selectbox(
        "Qualified account",
        [account.account_id for account in qualified],
        format_func=lambda value: next(
            account.account_name for account in qualified if account.account_id == value
        ),
    )
    selected = next(
        account for account in qualified if account.account_id == selected_id
    )
    st.json(
        {
            "score": selected.icp_score,
            "ports": list(selected.ports),
            "signals": [
                {"code": signal.code, "detail": signal.detail}
                for signal in selected.signals
                if signal.weight > 0
            ],
        }
    )
    if st.button("Generate outreach draft"):
        try:
            draft = generate_outreach(selected)
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.json(draft.model_dump())
