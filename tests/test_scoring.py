from __future__ import annotations

from typing import Any

import pytest

from src.scoring import account_identity, load_rules, qualified_accounts, score_accounts


def public_winrm_record() -> dict[str, Any]:
    return {
        "ip_str": "8.8.8.8",
        "port": 5985,
        "domains": ["acme-security.io"],
        "product": "WinRM",
        "http": {"status": 404, "server": "Microsoft-HTTPAPI/2.0"},
        "ntlm": {"os": "Windows"},
        "location": {"country_code": "US"},
        "org": "Acme Ltd",
    }


def test_ip_with_trailing_dot_is_not_a_named_account():
    record = {
        "domains": ["95.217.98.214."],
        "hostnames": ["95.217.98.214"],
        "ip_str": "95.217.98.214",
    }
    account_id, _, is_named = account_identity(record)
    assert account_id == "ip:95.217.98.214"
    assert is_named is False


def test_named_accounts_roll_up_and_qualify():
    accounts = score_accounts(
        [
            public_winrm_record(),
            {**public_winrm_record(), "port": 5986},
            {
                "ip_str": "1.1.1.1",
                "port": 80,
                "domains": ["cdn-edge.net"],
                "tags": ["cdn"],
                "http": {"status": 200},
            },
        ]
    )
    by_id = {account.account_id: account for account in accounts}
    acme = by_id["domain:acme-security.io"]
    assert acme.banner_count == 2
    assert acme.is_addressable is True
    assert acme.icp_score >= 40
    assert {signal.code for signal in acme.signals} >= {
        "exposed_winrm",
        "windows_auth_leak",
    }
    qualified = qualified_accounts(accounts, {**load_rules(), "llm_gate_score": 40})
    assert [account.account_id for account in qualified] == [
        "domain:acme-security.io"
    ]


def test_unknown_vertical_is_rejected():
    with pytest.raises(ValueError, match="unknown vertical"):
        score_accounts(
            [{"ip_str": "203.0.113.10", "port": 80}],
            vertical="payroll",
        )


def test_accounts_are_tagged_with_active_vertical():
    accounts = score_accounts([public_winrm_record()])
    assert accounts[0].vertical == "cybersecurity"
