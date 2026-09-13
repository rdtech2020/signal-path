"""Vertical-agnostic account rollup and scoring."""

from __future__ import annotations

import ipaddress
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings

VERTICALS_DIR = Path("config/verticals")


@dataclass(frozen=True)
class Signal:
    code: str
    weight: int
    detail: str


@dataclass(frozen=True)
class AccountScore:
    account_id: str
    account_name: str
    is_named: bool
    is_addressable: bool
    icp_score: int
    country_code: str | None
    org: str | None
    ports: tuple[int, ...]
    ip_addresses: tuple[str, ...]
    banner_count: int
    signals: tuple[Signal, ...]
    vertical: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ports"] = list(self.ports)
        result["ip_addresses"] = list(self.ip_addresses)
        result["signals"] = [asdict(signal) for signal in self.signals]
        return result


def vertical_config_path(vertical: str | None = None) -> Path:
    return VERTICALS_DIR / f"{vertical or settings.vertical}.yaml"


def load_rules(path: Path | None = None, vertical: str | None = None) -> dict[str, Any]:
    config_path = path or vertical_config_path(vertical)
    if not config_path.exists():
        known = sorted(p.stem for p in VERTICALS_DIR.glob("*.yaml"))
        raise ValueError(
            f"unknown vertical {config_path.stem!r}; known: {', '.join(known)}"
        )
    with config_path.open(encoding="utf-8") as handle:
        rules = yaml.safe_load(handle)
    if not isinstance(rules, dict) or not isinstance(rules.get("weights"), dict):
        raise ValueError(f"invalid scoring rules: {config_path}")
    rules.setdefault("id", config_path.stem)
    return rules


def _first_text(values: object) -> str | None:
    if not isinstance(values, list):
        return None
    return next((value for value in values if isinstance(value, str) and value), None)


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def account_identity(record: dict[str, Any]) -> tuple[str, str, bool]:
    """Return stable account_id, display name, and whether it is named."""
    domain = _first_text(record.get("domains"))
    normalized_domain = domain.lower().strip(".") if domain else None
    if normalized_domain and not _is_ip_address(normalized_domain):
        return f"domain:{normalized_domain}", normalized_domain, True

    hostname = _first_text(record.get("hostnames"))
    normalized_hostname = hostname.lower().strip(".") if hostname else None
    if normalized_hostname and not _is_ip_address(normalized_hostname):
        return f"domain:{normalized_hostname}", normalized_hostname, True

    ip_str = str(record.get("ip_str") or "unknown")
    return f"ip:{ip_str}", ip_str, False


def _is_hosted_platform(account_name: str, suffixes: tuple[str, ...]) -> bool:
    return any(
        account_name == suffix or account_name.endswith(f".{suffix}")
        for suffix in suffixes
    )


def _identity_signals(
    *,
    is_named: bool,
    is_addressable: bool,
    org: str | None,
    weights: dict[str, Any],
    hyperscaler_terms: tuple[str, ...],
) -> dict[str, Signal]:
    signals: dict[str, Signal] = {}
    if (
        not is_named
        and "hyperscaler_unnamed" in weights
        and any(
            term.casefold() in str(org or "").casefold() for term in hyperscaler_terms
        )
    ):
        code = "hyperscaler_unnamed"
        signals[code] = Signal(
            code=code,
            weight=int(weights[code]),
            detail="Unnamed asset belongs to a hyperscaler network",
        )
    if is_named and not is_addressable and "hosted_platform_domain" in weights:
        code = "hosted_platform_domain"
        signals[code] = Signal(
            code=code,
            weight=int(weights[code]),
            detail="Provider-owned hostname cannot identify the buying account",
        )
    return signals


def score_accounts(
    records: Iterable[dict[str, Any]],
    rules: dict[str, Any] | None = None,
    vertical: str | None = None,
) -> list[AccountScore]:
    """Aggregate observations and calculate one explainable score per account."""
    active_rules = rules or load_rules(vertical=vertical)
    vertical_id = str(active_rules.get("id") or vertical or settings.vertical)
    from src.verticals import get_extractor

    extract_record_signals = get_extractor(vertical_id)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: dict[str, tuple[str, bool]] = {}

    for record in records:
        account_id, account_name, is_named = account_identity(record)
        groups[account_id].append(record)
        identities[account_id] = (account_name, is_named)

    hyperscaler_terms = tuple(active_rules.get("hyperscaler_org_terms") or ())
    hosted_suffixes = tuple(active_rules.get("hosted_platform_domain_suffixes") or ())
    weights = active_rules["weights"]
    scored_accounts: list[AccountScore] = []

    for account_id, banners in groups.items():
        account_name, is_named = identities[account_id]
        is_addressable = is_named and not _is_hosted_platform(
            account_name, hosted_suffixes
        )
        merged_signals: dict[str, Signal] = {}
        for banner in banners:
            merged_signals.update(extract_record_signals(banner, active_rules))

        org = next((banner.get("org") for banner in banners if banner.get("org")), None)
        merged_signals.update(
            _identity_signals(
                is_named=is_named,
                is_addressable=is_addressable,
                org=str(org) if org else None,
                weights=weights,
                hyperscaler_terms=hyperscaler_terms,
            )
        )

        signal_list = tuple(sorted(merged_signals.values(), key=lambda item: item.code))
        raw_score = sum(signal.weight for signal in signal_list)
        location = next(
            (
                banner["location"]
                for banner in banners
                if isinstance(banner.get("location"), dict)
            ),
            {},
        )
        ports = tuple(
            sorted(
                {
                    banner["port"]
                    for banner in banners
                    if isinstance(banner.get("port"), int)
                }
            )
        )
        ip_addresses = tuple(
            sorted(
                {str(banner["ip_str"]) for banner in banners if banner.get("ip_str")}
            )
        )

        scored_accounts.append(
            AccountScore(
                account_id=account_id,
                account_name=account_name,
                is_named=is_named,
                is_addressable=is_addressable,
                icp_score=max(0, min(100, raw_score)),
                country_code=location.get("country_code"),
                org=str(org) if org else None,
                ports=ports,
                ip_addresses=ip_addresses,
                banner_count=len(banners),
                signals=signal_list,
                vertical=vertical_id,
            )
        )

    return sorted(
        scored_accounts,
        key=lambda account: (
            -account.icp_score,
            not account.is_named,
            account.account_name,
        ),
    )


def qualified_accounts(
    accounts: Iterable[AccountScore], rules: dict[str, Any] | None = None
) -> list[AccountScore]:
    active_rules = rules or load_rules()
    gate = int(active_rules["llm_gate_score"])
    return [
        account
        for account in accounts
        if account.is_named and account.icp_score >= gate and account.is_addressable
    ]
