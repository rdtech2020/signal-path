"""Fetch the materialized account store for hosted deployments.

A hosted container cannot rebuild the store: that needs the full archive and
about twenty minutes. Instead the store is built once locally, uploaded to
object storage, and pulled into the container's ephemeral disk on first run.
"""

from __future__ import annotations

import gzip
import os
import shutil
import urllib.request
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import duckdb

ALLOWED_SCHEMES = ("https://", "http://", "file://")
CHUNK_BYTES = 1 << 20
DOWNLOAD_TIMEOUT_SECONDS = 120
REQUIRED_TABLES = ("account_score", "banner_fact")
MIN_FREE_GIB = 2


def _check_free_space(target: Path, min_free_gib: int) -> None:
    free_bytes = shutil.disk_usage(target).free
    if free_bytes < min_free_gib * 1024**3:
        raise RuntimeError(
            f"need at least {min_free_gib} GiB free to download the store; "
            f"only {free_bytes / 1024**3:.1f} GiB available"
        )


def _download(url: str, destination: Path, on_progress: Callable | None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "signal-path"})
    with urllib.request.urlopen(  # noqa: S310 - scheme is validated by caller
        request, timeout=DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        total_header = response.headers.get("Content-Length")
        total_bytes = int(total_header) if total_header else 0
        decompress = url.endswith(".gz")
        stream = gzip.GzipFile(fileobj=response) if decompress else response
        received = 0
        with destination.open("wb") as handle:
            while chunk := stream.read(CHUNK_BYTES):
                handle.write(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, 0 if decompress else total_bytes)


def _validate(path: Path) -> None:
    """Refuse a truncated or unrelated file before the app queries it."""
    try:
        with closing(duckdb.connect(str(path), read_only=True)) as connection:
            present = {
                str(row[0])
                for row in connection.execute("SHOW TABLES").fetchall()
            }
    except duckdb.Error as exc:
        raise RuntimeError(f"downloaded file is not a readable store: {exc}") from exc
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise RuntimeError(f"downloaded store is missing tables: {missing}")


def ensure_database(
    database_path: Path,
    database_url: str | None = None,
    *,
    min_free_gib: int = MIN_FREE_GIB,
    on_progress: Callable | None = None,
) -> Path:
    """Return a usable store path, downloading it once if it is absent."""
    if database_path.exists():
        return database_path
    if not database_url:
        raise FileNotFoundError(
            f"no account store at {database_path}. Build it locally with "
            "`python scripts/build_duckdb.py`, or set DATABASE_URL to a store "
            "this deployment can download."
        )
    if not database_url.startswith(ALLOWED_SCHEMES):
        raise ValueError(
            f"DATABASE_URL must start with one of {ALLOWED_SCHEMES}"
        )

    database_path.parent.mkdir(parents=True, exist_ok=True)
    _check_free_space(database_path.parent, min_free_gib)
    partial_path = database_path.with_suffix(database_path.suffix + ".part")
    try:
        _download(database_url, partial_path, on_progress)
        _validate(partial_path)
        # Rename last, so an interrupted download never looks like a store.
        os.replace(partial_path, database_path)
    finally:
        partial_path.unlink(missing_ok=True)
    return database_path
