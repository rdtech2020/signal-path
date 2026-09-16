"""Streamlit prospect queue backed by the DuckDB account store."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import settings
from src.brief import evidence_ports
from src.duckdb_store import (
    account_from_row,
    count_ranked_accounts,
    query_country_codes,
    query_database_summary,
    query_qualified_accounts,
    query_ranked_accounts,
)
from src.llm_client import generate_outreach
from src.scoring import AccountScore, load_rules
from src.store_fetch import ensure_database


def database_accounts(rows: list[dict[str, object]]) -> list[AccountScore]:
    """Convert bounded query results to the app's existing account contract."""
    return [account_from_row(row, rules) for row in rows]


def port_label(account: AccountScore) -> str:
    shown, withheld = evidence_ports(account.ports, account.signals)
    label = ", ".join(map(str, shown))
    return f"{label} (+{withheld})" if withheld else label


def account_rows(accounts: list[AccountScore]) -> list[dict[str, object]]:
    return [
        {
            "account": account.account_name,
            "score": account.icp_score,
            "addressable": account.is_addressable,
            "country": account.country_code,
            "org": account.org,
            "ports": port_label(account),
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


@st.cache_resource(show_spinner=False)
def prepared_database(path_text: str, url: str | None) -> str:
    """Download the store once per container; local runs use the built file."""
    target = Path(path_text)
    if target.exists() or not url:
        return str(ensure_database(target, url))

    status = st.status("Downloading the account store…", expanded=True)
    progress = status.progress(0.0)

    def report(received: int, total: int) -> None:
        received_mib = received / 1024**2
        if total:
            progress.progress(min(received / total, 1.0))
            status.write(f"{received_mib:,.0f} of {total / 1024**2:,.0f} MiB")
        else:
            status.write(f"{received_mib:,.0f} MiB")

    resolved = ensure_database(target, url, on_progress=report)
    status.update(label="Account store ready", state="complete", expanded=False)
    return str(resolved)


try:
    database_path = Path(
        prepared_database(
            os.getenv("DATABASE_PATH", str(settings.database_path)),
            os.getenv("DATABASE_URL", settings.database_url),
        )
    )
except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

score_floor = st.sidebar.slider("Minimum score", 0, 100, 0, 5)
addressable_only = st.sidebar.checkbox("Addressable accounts only", value=True)
country_options = query_country_codes(database_path)
countries = st.sidebar.multiselect("Countries", country_options)
page_size = st.sidebar.selectbox("Rows per page", (50, 100, 250, 500), index=1)

summary = query_database_summary(database_path, gate)
matching_accounts = count_ranked_accounts(
    database_path,
    minimum_score=score_floor,
    addressable_only=addressable_only,
    country_codes=tuple(countries),
)
total_pages = max(1, -(-matching_accounts // page_size))
# Keying the widget by filter state resets paging whenever the result set does.
page = st.sidebar.number_input(
    f"Page (of {total_pages:,})",
    min_value=1,
    max_value=total_pages,
    value=1,
    step=1,
    key=f"page_{score_floor}_{addressable_only}_{page_size}_{'+'.join(countries)}",
)
offset = (int(page) - 1) * page_size

filtered = database_accounts(
    query_ranked_accounts(
        database_path,
        minimum_score=score_floor,
        addressable_only=addressable_only,
        country_codes=tuple(countries),
        limit=page_size,
        offset=offset,
    )
)
qualified = database_accounts(
    query_qualified_accounts(
        database_path,
        minimum_score=gate,
        limit=int(rules["daily_draft_cap"]),
    )
)

metric_columns = st.columns(4)
metric_columns[0].metric("Banners", f"{summary['banners']:,}")
metric_columns[1].metric("Accounts", f"{summary['accounts']:,}")
metric_columns[2].metric("Addressable", f"{summary['addressable']:,}")
metric_columns[3].metric(f"Qualified (≥ {gate})", f"{summary['qualified']:,}")

st.subheader("Ranked account queue")
if filtered:
    st.caption(
        f"Showing {offset + 1:,}–{offset + len(filtered):,} "
        f"of {matching_accounts:,} matching accounts. "
        "Each page is one bounded query; raw banner facts stay outside Python."
    )
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
            "ports": port_label(selected),
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
