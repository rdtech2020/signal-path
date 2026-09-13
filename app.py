"""Streamlit prospect queue for the 100-record development sample."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import settings
from src.ingester import load_records, normalize_banner
from src.llm_client import generate_outreach
from src.scoring import AccountScore, load_rules, qualified_accounts, score_accounts

SAMPLE_PATH = Path("data/readable/shodan_100.jsonl")


@st.cache_data
def load_scored_accounts() -> list[AccountScore]:
    records = [
        normalized
        for record in load_records(SAMPLE_PATH)
        if (normalized := normalize_banner(record)) is not None
    ]
    return score_accounts(records)


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

accounts = load_scored_accounts()
gate = int(rules["llm_gate_score"])
qualified = qualified_accounts(accounts, rules)

metric_columns = st.columns(4)
metric_columns[0].metric("Banners", 100)
metric_columns[1].metric("Accounts", len(accounts))
metric_columns[2].metric(
    "Addressable", sum(account.is_addressable for account in accounts)
)
metric_columns[3].metric(f"Qualified (≥ {gate})", len(qualified))

score_floor = st.sidebar.slider("Minimum score", 0, 100, 0, 5)
addressable_only = st.sidebar.checkbox("Addressable accounts only", value=True)
country_options = sorted(
    {account.country_code for account in accounts if account.country_code}
)
countries = st.sidebar.multiselect("Countries", country_options)

filtered = [
    account
    for account in accounts
    if account.icp_score >= score_floor
    and (not addressable_only or account.is_addressable)
    and (not countries or account.country_code in countries)
]

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
