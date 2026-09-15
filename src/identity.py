"""Sales-identity sanitization: public IPs and public apex domains only."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import Any

METADATA_IPS = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


def _normalize_name(value: str) -> str:
    return value.lower().strip().strip(".")


def is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(_normalize_name(value))
    except ValueError:
        return False
    return True


def matches_suffix(name: str, suffixes: Iterable[str]) -> bool:
    normalized = _normalize_name(name)
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in suffixes
        if suffix
    )


def is_public_ip(value: str) -> bool:
    """True only for globally routable addresses, excluding IMDS endpoints."""
    try:
        address = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return False
    if address in METADATA_IPS:
        return False
    return bool(address.is_global)


def is_public_apex_domain(name: str, rules: dict[str, Any]) -> bool:
    """True for a resolvable-looking public DNS name a salesperson can email."""
    if not isinstance(name, str) or not name.strip():
        return False
    normalized = _normalize_name(name)
    if not normalized or is_ip_address(normalized):
        return False
    if "." not in normalized:
        return False
    labels = normalized.split(".")
    if any(
        not label or label.startswith("-") or label.endswith("-") for label in labels
    ):
        return False
    if any(not label.replace("-", "").isalnum() for label in labels):
        return False

    placeholders = {
        _normalize_name(item)
        for item in (rules.get("placeholder_account_names") or ())
        if item
    }
    if normalized in placeholders:
        return False

    reserved_suffixes = tuple(rules.get("non_public_domain_suffixes") or ())
    honeypot_suffixes = tuple(rules.get("honeypot_domain_suffixes") or ())
    if matches_suffix(normalized, reserved_suffixes):
        return False
    if matches_suffix(normalized, honeypot_suffixes):
        return False
    return True


def is_hosted_platform(account_name: str, rules: dict[str, Any]) -> bool:
    return matches_suffix(
        account_name, tuple(rules.get("hosted_platform_domain_suffixes") or ())
    )


def is_sales_addressable(
    account_name: str,
    ip_addresses: Iterable[str],
    rules: dict[str, Any],
    *,
    is_named: bool,
) -> bool:
    """True when the account is a public domain on a public IP, not a tenant."""
    if not is_named:
        return False
    if not is_public_apex_domain(account_name, rules):
        return False
    if is_hosted_platform(account_name, rules):
        return False
    return any(is_public_ip(ip_str) for ip_str in ip_addresses)
