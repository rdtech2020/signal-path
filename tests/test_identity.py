from src.identity import is_public_apex_domain, is_public_ip, is_sales_addressable
from src.scoring import account_identity, load_rules, score_accounts


def test_loopback_and_rfc1918_ips_are_not_public():
    assert is_public_ip("127.0.0.1") is False
    assert is_public_ip("::1") is False
    assert is_public_ip("10.1.2.3") is False
    assert is_public_ip("172.16.0.1") is False
    assert is_public_ip("172.31.255.1") is False
    assert is_public_ip("192.168.1.10") is False
    assert is_public_ip("169.254.12.34") is False
    assert is_public_ip("169.254.169.254") is False
    assert is_public_ip("8.8.8.8") is True


def test_placeholder_and_localhost_names_are_not_public_domains():
    rules = load_rules()
    assert is_public_apex_domain("localhost", rules) is False
    assert is_public_apex_domain("WORKSTATION1", rules) is False
    assert is_public_apex_domain("unknown", rules) is False
    assert is_public_apex_domain("null", rules) is False
    assert is_public_apex_domain("-", rules) is False
    assert is_public_apex_domain("103.in-addr.arpa", rules) is False
    assert is_public_apex_domain("host.local", rules) is False
    assert is_public_apex_domain("trap.honeypot", rules) is False
    assert is_public_apex_domain("example.com", rules) is False
    assert is_public_apex_domain("sakura.ne.jp", rules) is True


def test_localhost_on_a_public_ip_is_not_addressable():
    rules = load_rules()
    assert (
        is_sales_addressable(
            "localhost",
            ["27.76.95.70"],
            rules,
            is_named=True,
        )
        is False
    )


def test_ip_with_trailing_dot_is_not_a_named_account():
    record = {
        "domains": ["95.217.98.214."],
        "hostnames": ["95.217.98.214"],
        "ip_str": "95.217.98.214",
    }
    account_id, _, is_named = account_identity(record)
    assert account_id == "ip:95.217.98.214"
    assert is_named is False


def test_scored_localhost_is_kept_but_not_addressable():
    accounts = score_accounts(
        [
            {
                "ip_str": "27.76.95.70",
                "port": 80,
                "domains": ["localhost."],
                "hostnames": ["localhost"],
            }
        ]
    )
    assert len(accounts) == 1
    assert accounts[0].account_id == "domain:localhost"
    assert accounts[0].is_named is True
    assert accounts[0].is_addressable is False
