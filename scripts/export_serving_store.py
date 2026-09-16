#!/usr/bin/env python3
"""Export a serving-only copy of the account store.

`banner_fact` is 85% of the built store, and the app reads exactly one number
from it: the corpus banner count. Copying `account_score` and materializing that
count into a small `store_summary` table keeps every account while shrinking the
artifact enough to host it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.duckdb_store import export_serving_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/signal_path.duckdb"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/signal_path_serving.duckdb")
    )
    parser.add_argument("--memory_limit", default="2GB")
    parser.add_argument("--threads", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    accounts = export_serving_store(
        args.source,
        args.output,
        memory_limit=args.memory_limit,
        threads=args.threads,
    )
    size_mib = args.output.stat().st_size / 1024**2
    print(f"wrote {args.output}: {accounts:,} accounts, {size_mib:,.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
