"""Cybersecurity ICP: buying signals from public scan banners."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.scoring import Signal


def _contains_case_insensitive(value: object, needle: str) -> bool:
    return needle.casefold() in str(value or "").casefold()


def _offered_legacy_tls(versions: object) -> bool:
    if not isinstance(versions, list):
        return False
    return any(version in {"TLSv1", "TLSv1.1"} for version in versions)


def extract_record_signals(
    record: dict[str, Any], rules: dict[str, Any]
) -> dict[str, Signal]:
    from src.scoring import Signal

    weights = rules["weights"]
    tags = set(record.get("tags") or [])
    port = record.get("port")
    product = record.get("product")
    http = record.get("http") if isinstance(record.get("http"), dict) else {}
    ssl = record.get("ssl") if isinstance(record.get("ssl"), dict) else {}
    signals: dict[str, Signal] = {}

    def add(code: str, detail: str) -> None:
        signals[code] = Signal(code=code, weight=int(weights[code]), detail=detail)

    if (
        port in {5985, 5986}
        or _contains_case_insensitive(product, "winrm")
        or _contains_case_insensitive(http.get("server"), "httpapi")
    ):
        add("exposed_winrm", f"Public Windows remote-management service on port {port}")

    if record.get("pptp") or port == 1723 or "vpn" in tags:
        add("legacy_vpn", f"Legacy or exposed VPN service on port {port}")

    if "eol-product" in tags:
        product_name = str(product or "unknown product")
        version = str(record.get("version") or "").strip()
        add("eol_software", f"EOL-tagged software: {product_name} {version}".strip())

    if record.get("ntlm"):
        add("windows_auth_leak", "NTLM metadata is exposed by the service")

    cert = ssl.get("cert") if isinstance(ssl.get("cert"), dict) else {}
    if (
        cert.get("expired")
        or "self-signed" in tags
        or _offered_legacy_tls(ssl.get("versions"))
    ):
        add("weak_tls", "Expired, self-signed, or legacy TLS configuration")

    if http and not http.get("waf") and "cdn" not in tags:
        add("origin_no_waf", "HTTP origin is visible without a detected WAF")

    status = http.get("status")
    if isinstance(status, int) and 500 <= status < 600:
        add("http_server_error", f"Public endpoint returned HTTP {status}")

    if record.get("cpe"):
        add("identified_cpe", "Service exposes a machine-readable product identifier")

    if "cdn" in tags:
        add("cdn_edge", "Banner appears to be from a CDN edge, not the origin")

    return signals
