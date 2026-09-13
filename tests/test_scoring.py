from pathlib import Path

import pytest

from src.ingester import load_records, normalize_banner
from src.scoring import account_identity, qualified_accounts, score_accounts

SAMPLE_PATH = Path("data/readable/shodan_100.jsonl")


def sample_accounts():
    records = [
        normalized
        for record in load_records(SAMPLE_PATH)
        if (normalized := normalize_banner(record)) is not None
    ]
    return score_accounts(records)


def test_ip_with_trailing_dot_is_not_a_named_account():
    record = {
        "domains": ["95.217.98.214."],
        "hostnames": ["95.217.98.214"],
        "ip_str": "95.217.98.214",
    }
    account_id, _, is_named = account_identity(record)
    assert account_id == "ip:95.217.98.214"
    assert is_named is False


def test_sample_rollup_is_stable():
    accounts = sample_accounts()
    assert len(accounts) == 85
    assert sum(account.is_named for account in accounts) == 25
    assert sum(account.is_addressable for account in accounts) == 18


def test_sample_gate_returns_four_addressable_accounts():
    assert len(qualified_accounts(sample_accounts())) == 4


def test_unknown_vertical_is_rejected():
    with pytest.raises(ValueError, match="unknown vertical"):
        score_accounts(
            [{"ip_str": "203.0.113.10", "port": 80}],
            vertical="payroll",
        )


def test_accounts_are_tagged_with_active_vertical():
    accounts = sample_accounts()
    assert accounts
    assert all(account.vertical == "cybersecurity" for account in accounts)


def test_sensitive_payloads_are_removed():
    record = {
        "ip_str": "203.0.113.10",
        "port": 443,
        "data": "raw banner",
        "http": {"html": "<html>secret</html>", "status": 200},
        "ssl": {"chain": ["certificate"], "jarm": "hash"},
    }
    normalized = normalize_banner(record)
    assert normalized is not None
    assert "data" not in normalized
    assert "html" not in normalized["http"]
    assert "chain" not in normalized["ssl"]
