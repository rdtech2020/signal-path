#!/usr/bin/env python3
"""Build a resource-capped DuckDB score database from Shodan data."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.duckdb_store import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_TEMP_SIZE,
    DEFAULT_MEMORY_LIMIT,
    DEFAULT_MIN_FREE_GIB,
    DEFAULT_THREADS,
    build_database,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Shodan data into a bounded-resource DuckDB database."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/b2_download_file_by_id"),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/signal_path.duckdb"),
    )
    parser.add_argument("--vertical", default="cybersecurity")
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--memory_limit", default=DEFAULT_MEMORY_LIMIT)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--max_temp_size", default=DEFAULT_MAX_TEMP_SIZE)
    parser.add_argument("--min_free_gib", type=int, default=DEFAULT_MIN_FREE_GIB)
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Treat source as plain JSONL instead of the zstd archive.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    banner_count, account_count = build_database(
        args.source,
        args.database,
        vertical=args.vertical,
        compressed=not args.jsonl,
        batch_size=args.batch_size,
        memory_limit=args.memory_limit,
        threads=args.threads,
        max_temp_size=args.max_temp_size,
        min_free_gib=args.min_free_gib,
    )
    print(
        f"built {args.database}: "
        f"{banner_count:,} banners -> {account_count:,} accounts"
    )


if __name__ == "__main__":
    main()
