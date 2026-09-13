"""Vertical plugins: ICP signal extractors for a sales motion.

To add a use case:
1. Create `config/verticals/<id>.yaml` with weights and identity denylists.
2. Add `src/verticals/<id>.py` with `extract_record_signals(record, rules)`.
3. Register it in `EXTRACTORS` below.
4. Set `VERTICAL=<id>` (or pass `vertical=` to scoring).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.verticals import cybersecurity

if TYPE_CHECKING:
    from src.scoring import Signal

RecordExtractor = Callable[[dict[str, Any], dict[str, Any]], dict[str, "Signal"]]

EXTRACTORS: dict[str, RecordExtractor] = {
    "cybersecurity": cybersecurity.extract_record_signals,
}


def get_extractor(vertical_id: str) -> RecordExtractor:
    try:
        return EXTRACTORS[vertical_id]
    except KeyError as exc:
        known = ", ".join(sorted(EXTRACTORS))
        raise ValueError(f"unknown vertical {vertical_id!r}; known: {known}") from exc
