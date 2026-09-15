"""Shape scored accounts into a sales brief instead of raw telemetry."""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.scoring import Signal

PORT_LIMIT = 6
# Only an explicit "port 5986" counts; a detail like "returned HTTP 502" must
# not be read as a port number.
PORT_PATTERN = re.compile(r"\bport\s+(\d{1,5})\b", re.IGNORECASE)


def _cited_ports(signals: Iterable[Signal], ports: frozenset[int]) -> list[int]:
    """Ports a positive signal actually talks about, in signal order."""
    cited: list[int] = []
    for signal in signals:
        if signal.weight <= 0:
            continue
        for token in PORT_PATTERN.findall(signal.detail):
            port = int(token)
            if port in ports and port not in cited:
                cited.append(port)
    return cited


def evidence_ports(
    ports: Iterable[int],
    signals: Iterable[Signal],
    limit: int = PORT_LIMIT,
) -> tuple[tuple[int, ...], int]:
    """Return the ports worth citing plus a count of the ones left out.

    An account can expose thousands of ports. A full list is telemetry, not a
    reason to call, so a signal-bearing port is always preferred. Only when no
    signal names a port does the brief fall back to showing a few, so that an
    account is never described with no observable surface at all.
    """
    unique_ports = sorted({int(port) for port in ports})
    cited = _cited_ports(signals, frozenset(unique_ports))
    ranked = cited or unique_ports
    return tuple(ranked[:limit]), max(0, len(unique_ports) - min(len(ranked), limit))
