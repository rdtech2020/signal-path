"""Read and normalize Shodan banner records without retaining raw payloads."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SENSITIVE_FIELDS = {"data"}
SENSITIVE_HTTP_FIELDS = {"html", "favicon"}
SENSITIVE_SSL_FIELDS = {"chain", "chain_sha256", "cert"}


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from a JSONL file."""
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
            if isinstance(record, dict):
                yield record


def read_json_array(path: Path) -> list[dict[str, Any]]:
    """Read a development-sized JSON array."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(
        isinstance(record, dict) for record in payload
    ):
        raise ValueError(f"{path} must contain an array of JSON objects")
    return payload


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load a local sample; use JSONL for anything beyond development size."""
    if path.suffix == ".jsonl":
        return list(iter_jsonl(path))
    return read_json_array(path)


def normalize_banner(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return scoring-safe fields, excluding raw third-party content."""
    ip_str = record.get("ip_str")
    port = record.get("port")
    if not ip_str or not isinstance(port, int):
        return None

    normalized = {
        key: value for key, value in record.items() if key not in SENSITIVE_FIELDS
    }

    http = normalized.get("http")
    if isinstance(http, dict):
        normalized["http"] = {
            key: value
            for key, value in http.items()
            if key not in SENSITIVE_HTTP_FIELDS
        }

    ssl = normalized.get("ssl")
    if isinstance(ssl, dict):
        normalized["ssl"] = {
            key: value for key, value in ssl.items() if key not in SENSITIVE_SSL_FIELDS
        }

    return normalized
