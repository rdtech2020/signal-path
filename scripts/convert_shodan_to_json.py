#!/usr/bin/env python3
"""Convert the Zstd Shodan dump into readable JSON.

The source file is Zstandard-compressed JSON objects (NDJSON or concatenated
JSON). Pretty-printing the entire ~10 GB dump is not practical (~tens of GB
uncompressed), so this script:

  * writes a 100-record subset as JSONL and pretty-printed JSON
  * optionally writes the full dump as compact JSONL (--full_jsonl)

Usage:
  python3 scripts/convert_shodan_to_json.py
  python3 scripts/convert_shodan_to_json.py --full_jsonl
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO

DEFAULT_INPUT = Path("data/b2_download_file_by_id")
DEFAULT_OUTPUT_DIR = Path("data/readable")
DEFAULT_SUBSET_SIZE = 100
READ_CHUNK_BYTES = 64 * 1024
PROGRESS_EVERY = 500
MAX_BUFFER_BYTES = 128 * 1024 * 1024
MIN_FREE_BYTES_FOR_FULL = 40 * 1024 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the Shodan Zstd dump into readable JSON files."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output_dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--subset_size", type=int, default=DEFAULT_SUBSET_SIZE)
    parser.add_argument(
        "--full_jsonl",
        action="store_true",
        help="Also stream the entire dump to compact JSONL (can be tens of GB).",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def require_zstd() -> str:
    zstd_path = shutil.which("zstd")
    if not zstd_path:
        sys.exit(
            "zstd is not installed. Install it (e.g. brew install zstd) and retry."
        )
    return zstd_path


def iter_json_objects(raw_stdout: Any) -> Iterator[dict]:
    decoder = json.JSONDecoder()
    buffer = ""

    while True:
        cursor = 0
        while True:
            while cursor < len(buffer) and buffer[cursor].isspace():
                cursor += 1
            if cursor >= len(buffer):
                buffer = ""
                break
            try:
                record, next_cursor = decoder.raw_decode(buffer, cursor)
            except json.JSONDecodeError:
                buffer = buffer[cursor:]
                break
            cursor = next_cursor
            if isinstance(record, dict):
                yield record
        chunk = raw_stdout.read(READ_CHUNK_BYTES)
        if not chunk:
            return
        buffer += chunk.decode("utf-8", errors="replace")
        if len(buffer) > MAX_BUFFER_BYTES:
            raise ValueError(
                "one JSON record exceeded the 128 MiB safety limit; "
                "aborting instead of silently dropping source data"
            )


def write_pretty_object(handle: TextIO, record: dict, first: bool) -> None:
    if not first:
        handle.write(",\n")
    # Do not re-indent with splitlines(): Shodan banners can contain unicode
    # line breaks that would split inside a JSON string and corrupt the file.
    handle.write(json.dumps(record, indent=2, ensure_ascii=False))


def convert(args: argparse.Namespace) -> None:
    input_path = args.input
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    subset_jsonl_path = output_dir / f"shodan_{args.subset_size}.jsonl"
    subset_pretty_path = output_dir / f"shodan_{args.subset_size}_pretty.json"
    full_jsonl_path = output_dir / "shodan_full.jsonl"

    if args.full_jsonl:
        free_bytes = shutil.disk_usage(output_dir.resolve()).free
        if free_bytes < MIN_FREE_BYTES_FOR_FULL:
            sys.exit(
                "Not enough free disk for --full_jsonl "
                f"(need ~40 GiB, have {free_bytes / (1024**3):.1f} GiB)."
            )

    zstd_path = require_zstd()
    proc = subprocess.Popen(
        [zstd_path, "-d", "-c", str(input_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdout is not None

    record_count = 0
    subset_count = 0
    first_pretty = True
    full_handle = None

    log(f"reading {input_path}")
    try:
        if args.full_jsonl:
            full_handle = full_jsonl_path.open("w", encoding="utf-8")

        with (
            subset_jsonl_path.open("w", encoding="utf-8") as subset_jsonl,
            subset_pretty_path.open("w", encoding="utf-8") as subset_pretty,
        ):
            subset_pretty.write("[\n")
            for record in iter_json_objects(proc.stdout):
                line = json.dumps(record, ensure_ascii=False)
                record_count += 1

                if subset_count < args.subset_size:
                    subset_jsonl.write(line + "\n")
                    write_pretty_object(subset_pretty, record, first_pretty)
                    first_pretty = False
                    subset_count += 1
                    if subset_count % PROGRESS_EVERY == 0:
                        log(f"subset {subset_count:,} / {args.subset_size:,}")

                if full_handle is not None:
                    full_handle.write(line + "\n")
                    if record_count % PROGRESS_EVERY == 0:
                        log(f"full jsonl {record_count:,}")
                elif subset_count >= args.subset_size:
                    break

            subset_pretty.write("\n]\n")
            subset_jsonl.flush()
            subset_pretty.flush()
    finally:
        if full_handle is not None:
            full_handle.close()
        if proc.stdout:
            proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    log(f"wrote {subset_count:,} records to {subset_jsonl_path}")
    log(f"wrote {subset_count:,} records to {subset_pretty_path}")
    if args.full_jsonl:
        log(f"wrote {record_count:,} records to {full_jsonl_path}")


if __name__ == "__main__":
    convert(parse_args())
