#!/usr/bin/env python3
"""Recompute sales eligibility on an existing DuckDB without a full rebuild."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.duckdb_store import refresh_database_eligibility


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply public-IP and public-domain sanitization to account_score."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/signal_path.duckdb"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    addressable = refresh_database_eligibility(args.database)
    print(f"updated {args.database}: {addressable:,} addressable accounts")


if __name__ == "__main__":
    main()
