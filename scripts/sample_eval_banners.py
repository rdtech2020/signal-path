#!/usr/bin/env python3
"""Pull candidate eval banners from the archive for hand labelling.

The labelled set has to contain accounts on both sides of the outreach gate,
otherwise contact precision and recall measure nothing. This walks a prefix of
the archive and collects addressable accounts whose banners land in the
requested score band, then stops.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.duckdb_store import iter_zstd_json
from src.identity import is_public_ip
from src.ingester import normalize_banner
from src.scoring import account_identity, load_rules, score_accounts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path("data/b2_download_file_by_id")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum_score", type=int, default=80)
    parser.add_argument("--wanted", type=int, default=5)
    parser.add_argument("--max_records", type=int, default=2_000_000)
    parser.add_argument(
        "--require_signal",
        action="append",
        default=[],
        help="only collect accounts carrying this signal code (repeatable)",
    )
    parser.add_argument(
        "--exclude_labels",
        type=Path,
        default=Path("evals/datasets/accounts_labelled.jsonl"),
    )
    return parser.parse_args()


def excluded_account_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {json.loads(line)["account_id"] for line in handle if line.strip()}


def main() -> int:
    args = parse_args()
    rules = load_rules()
    excluded = excluded_account_ids(args.exclude_labels)
    collected: dict[str, dict] = {}

    for index, record in enumerate(iter_zstd_json(args.source)):
        if index >= args.max_records or len(collected) >= args.wanted:
            break
        normalized = normalize_banner(record)
        if normalized is None or not is_public_ip(str(normalized["ip_str"])):
            continue
        account_id, _, _ = account_identity(normalized)
        if account_id in excluded or account_id in collected:
            continue
        account = score_accounts([normalized], rules)[0]
        codes = {signal.code for signal in account.signals}
        if not set(args.require_signal) <= codes:
            continue
        if account.is_addressable and account.icp_score >= args.minimum_score:
            collected[account_id] = normalized
            print(
                f"{account.account_id} score={account.icp_score} "
                f"signals={[s.code for s in account.signals]}",
                flush=True,
            )

    with args.output.open("w", encoding="utf-8") as handle:
        for normalized in collected.values():
            handle.write(json.dumps(normalized) + "\n")
    print(f"wrote {len(collected)} banners to {args.output}")
    return 0 if collected else 1


if __name__ == "__main__":
    raise SystemExit(main())
