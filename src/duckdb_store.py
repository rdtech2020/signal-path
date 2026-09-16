"""Bounded-resource DuckDB ingestion and account-score materialization."""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from collections.abc import Iterable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import duckdb

from src.identity import is_hosted_platform, is_public_ip, is_sales_addressable
from src.ingester import iter_json_objects, iter_jsonl, normalize_banner
from src.scoring import (
    AccountScore,
    Signal,
    account_identity,
    identity_signals,
    load_rules,
)
from src.verticals import get_extractor

DEFAULT_BATCH_SIZE = 5_000
DEFAULT_MEMORY_LIMIT = "4GB"
DEFAULT_THREADS = 2
DEFAULT_MAX_TEMP_SIZE = "20GB"
DEFAULT_MIN_FREE_GIB = 15
VALID_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_SIZE = re.compile(r"^[1-9][0-9]*(?:MB|GB|TB)$")

BASE_COLUMNS = (
    "account_id",
    "account_name",
    "is_named",
    "is_addressable",
    "country_code",
    "org",
    "ip_str",
    "port",
)


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _validate_settings(
    memory_limit: str,
    max_temp_size: str,
    threads: int,
    batch_size: int,
) -> None:
    if not VALID_SIZE.fullmatch(memory_limit):
        raise ValueError("memory_limit must look like '4GB' or '512MB'")
    if not VALID_SIZE.fullmatch(max_temp_size):
        raise ValueError("max_temp_size must look like '20GB'")
    if not 1 <= threads <= 16:
        raise ValueError("threads must be between 1 and 16")
    if not 100 <= batch_size <= 100_000:
        raise ValueError("batch_size must be between 100 and 100000")


def _signal_codes(rules: dict[str, Any]) -> tuple[str, ...]:
    codes = tuple(str(code) for code in rules["weights"])
    invalid = [code for code in codes if not VALID_IDENTIFIER.fullmatch(code)]
    if invalid:
        raise ValueError(f"signal codes must be safe SQL identifiers: {invalid}")
    return codes


def _detail_columns(signal_codes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"detail_{code}" for code in signal_codes)


def connect_database(
    database_path: Path,
    *,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
    temp_directory: Path | None = None,
    max_temp_size: str = DEFAULT_MAX_TEMP_SIZE,
) -> duckdb.DuckDBPyConnection:
    """Open DuckDB with explicit CPU, memory, and spill limits."""
    _validate_settings(memory_limit, max_temp_size, threads, DEFAULT_BATCH_SIZE)
    spill_path = temp_directory or database_path.parent / "duckdb_tmp"
    spill_path.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(database_path))
    connection.execute(f"SET threads = {threads}")
    connection.execute(f"SET memory_limit = {_sql_string(memory_limit)}")
    connection.execute(f"SET temp_directory = {_sql_string(str(spill_path))}")
    connection.execute(
        f"SET max_temp_directory_size = {_sql_string(max_temp_size)}"
    )
    connection.execute("SET preserve_insertion_order = false")
    return connection


def iter_zstd_json(path: Path) -> Iterator[dict[str, Any]]:
    """Stream concatenated JSON objects from a zstd archive."""
    zstd_path = shutil.which("zstd")
    if not zstd_path:
        raise RuntimeError("zstd is required; install it with `brew install zstd`")


    process = subprocess.Popen(
        [zstd_path, "-d", "-c", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    try:
        yield from iter_json_objects(process.stdout)
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
        return_code = process.wait()
        if return_code not in {0, -13, -15}:
            raise RuntimeError(f"zstd exited with status {return_code}")


def _fact_row(
    record: dict[str, Any],
    rules: dict[str, Any],
    signal_codes: tuple[str, ...],
) -> tuple[object, ...] | None:
    normalized = normalize_banner(record)
    if normalized is None:
        return None

    account_id, account_name, is_named = account_identity(normalized)
    ip_str = str(normalized["ip_str"])
    if not is_public_ip(ip_str):
        return None
    is_addressable = is_sales_addressable(
        account_name,
        [ip_str],
        rules,
        is_named=is_named,
    )
    location = normalized.get("location")
    country_code = (
        location.get("country_code") if isinstance(location, dict) else None
    )
    org = str(normalized["org"]) if normalized.get("org") else None

    extractor = get_extractor(str(rules["id"]))
    signals = dict(extractor(normalized, rules))
    signals.update(
        identity_signals(
            is_named=is_named,
            is_hosted=is_hosted_platform(account_name, rules),
            org=org,
            weights=rules["weights"],
            hyperscaler_terms=tuple(rules.get("hyperscaler_org_terms") or ()),
        )
    )

    return (
        account_id,
        account_name,
        is_named,
        is_addressable,
        country_code,
        org,
        ip_str,
        int(normalized["port"]),
        *(code in signals for code in signal_codes),
        *(
            signals[code].detail if code in signals else None
            for code in signal_codes
        ),
    )


def _create_fact_table(
    connection: duckdb.DuckDBPyConnection, signal_codes: tuple[str, ...]
) -> None:
    signal_columns = ",\n".join(f"{code} BOOLEAN NOT NULL" for code in signal_codes)
    detail_columns = ",\n".join(
        f"{column} VARCHAR" for column in _detail_columns(signal_codes)
    )
    connection.execute("DROP TABLE IF EXISTS account_score")
    connection.execute("DROP TABLE IF EXISTS banner_fact")
    connection.execute(
        f"""
        CREATE TABLE banner_fact (
            account_id VARCHAR NOT NULL,
            account_name VARCHAR NOT NULL,
            is_named BOOLEAN NOT NULL,
            is_addressable BOOLEAN NOT NULL,
            country_code VARCHAR,
            org VARCHAR,
            ip_str VARCHAR NOT NULL,
            port INTEGER NOT NULL,
            {signal_columns},
            {detail_columns}
        )
        """
    )


def _flush_rows(
    connection: duckdb.DuckDBPyConnection,
    rows: list[tuple[object, ...]],
    stage_path: Path,
    columns: tuple[str, ...],
) -> None:
    with stage_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    column_sql = ", ".join(columns)
    connection.execute(
        f"""
        COPY banner_fact ({column_sql})
        FROM {_sql_string(str(stage_path))}
        (
            FORMAT CSV,
            HEADER FALSE,
            DELIMITER ',',
            QUOTE '"',
            ESCAPE '"',
            NULL '',
            AUTO_DETECT FALSE
        )
        """
    )
    stage_path.unlink(missing_ok=True)


def ingest_records(
    connection: duckdb.DuckDBPyConnection,
    records: Iterable[dict[str, Any]],
    rules: dict[str, Any],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    stage_path: Path,
    progress_every: int = 100_000,
) -> int:
    """Ingest normalized facts while retaining at most one batch in memory."""
    _validate_settings(DEFAULT_MEMORY_LIMIT, DEFAULT_MAX_TEMP_SIZE, 1, batch_size)
    signal_codes = _signal_codes(rules)
    columns = BASE_COLUMNS + signal_codes + _detail_columns(signal_codes)
    _create_fact_table(connection, signal_codes)

    rows: list[tuple[object, ...]] = []
    record_count = 0
    for record in records:
        row = _fact_row(record, rules, signal_codes)
        if row is None:
            continue
        rows.append(row)
        record_count += 1
        if len(rows) >= batch_size:
            _flush_rows(connection, rows, stage_path, columns)
            rows.clear()
        if progress_every and record_count % progress_every == 0:
            print(f"ingested {record_count:,} banners", flush=True)

    if rows:
        _flush_rows(connection, rows, stage_path, columns)
    return record_count


def materialize_account_scores(
    connection: duckdb.DuckDBPyConnection,
    rules: dict[str, Any],
) -> int:
    """Roll up banner facts and materialize YAML-weighted account scores."""
    signal_codes = _signal_codes(rules)
    flag_sql = ",\n".join(
        f"BOOL_OR({code}) AS {code}" for code in signal_codes
    )
    score_sql = "\n+".join(
        f"CAST({code} AS INTEGER) * {int(rules['weights'][code])}"
        for code in signal_codes
    )
    detail_sql = ",\n".join(
        f"ANY_VALUE(detail_{code}) FILTER (detail_{code} IS NOT NULL) "
        f"AS detail_{code}"
        for code in signal_codes
    )
    signal_list_sql = ",\n".join(
        f"CASE WHEN {code} THEN {_sql_string(code)} ELSE NULL END"
        for code in sorted(signal_codes)
    )
    # Details stay positionally aligned with signal_codes: both lists are built
    # in sorted-code order and filtered on the same flag.
    detail_list_sql = ",\n".join(
        f"CASE WHEN {code} THEN COALESCE(detail_{code}, {_sql_string(code)}) "
        "ELSE NULL END"
        for code in sorted(signal_codes)
    )
    connection.execute("DROP TABLE IF EXISTS account_score")
    connection.execute(
        f"""
        CREATE TABLE account_score AS
        WITH rolled_up AS (
            SELECT
                account_id,
                ANY_VALUE(account_name) AS account_name,
                BOOL_OR(is_named) AS is_named,
                BOOL_OR(is_addressable) AS is_addressable,
                ANY_VALUE(country_code) FILTER (country_code IS NOT NULL)
                    AS country_code,
                ANY_VALUE(org) FILTER (org IS NOT NULL) AS org,
                LIST(DISTINCT port ORDER BY port) AS ports,
                LIST(DISTINCT ip_str ORDER BY ip_str) AS ip_addresses,
                COUNT(*) AS banner_count,
                {flag_sql},
                {detail_sql}
            FROM banner_fact
            GROUP BY account_id
        ),
        scored AS (
            SELECT
                *,
                GREATEST(0, LEAST(100, {score_sql}))::INTEGER AS icp_score,
                LIST_FILTER(
                    [{signal_list_sql}],
                    signal_code -> signal_code IS NOT NULL
                ) AS signal_codes,
                LIST_FILTER(
                    [{detail_list_sql}],
                    signal_detail -> signal_detail IS NOT NULL
                ) AS signal_details
            FROM rolled_up
        )
        SELECT
            account_id,
            account_name,
            is_named,
            is_addressable,
            icp_score,
            country_code,
            org,
            ports,
            ip_addresses,
            banner_count,
            signal_codes,
            signal_details,
            {_sql_string(str(rules['id']))} AS vertical
        FROM scored
        """
    )
    connection.execute("CREATE INDEX account_score_id_idx ON account_score(account_id)")
    connection.execute("CHECKPOINT")
    return int(connection.execute("SELECT COUNT(*) FROM account_score").fetchone()[0])


def build_database(
    source_path: Path,
    database_path: Path,
    *,
    vertical: str | None = None,
    compressed: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
    max_temp_size: str = DEFAULT_MAX_TEMP_SIZE,
    min_free_gib: int = DEFAULT_MIN_FREE_GIB,
) -> tuple[int, int]:
    """Build a queryable score database without extracting full raw JSON."""
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    free_bytes = shutil.disk_usage(database_path.parent).free
    required_bytes = min_free_gib * 1024**3
    if free_bytes < required_bytes:
        raise RuntimeError(
            f"need at least {min_free_gib} GiB free; "
            f"only {free_bytes / 1024**3:.1f} GiB available"
        )

    rules = load_rules(vertical=vertical)
    stage_path = database_path.parent / ".duckdb_ingest_stage.csv"
    records = iter_zstd_json(source_path) if compressed else iter_jsonl(source_path)
    with closing(
        connect_database(
            database_path,
            memory_limit=memory_limit,
            threads=threads,
            max_temp_size=max_temp_size,
        )
    ) as connection:
        try:
            banner_count = ingest_records(
                connection,
                records,
                rules,
                batch_size=batch_size,
                stage_path=stage_path,
            )
            account_count = materialize_account_scores(connection, rules)
            refresh_sales_eligibility(connection, rules)
            account_count = int(
                connection.execute("SELECT COUNT(*) FROM account_score").fetchone()[0]
            )
        finally:
            stage_path.unlink(missing_ok=True)
    return banner_count, account_count


def refresh_sales_eligibility(
    connection: duckdb.DuckDBPyConnection,
    rules: dict[str, Any] | None = None,
) -> int:
    """Recompute is_addressable from names and IPs without re-ingesting banners."""
    active_rules = rules or load_rules()
    rows = connection.execute(
        """
        SELECT account_id, account_name, ip_addresses, is_named
        FROM account_score
        """
    ).fetchall()
    updates = [
        (
            is_sales_addressable(
                str(account_name),
                list(ip_addresses or ()),
                active_rules,
                is_named=bool(is_named),
            ),
            str(account_id),
        )
        for account_id, account_name, ip_addresses, is_named in rows
    ]
    connection.execute(
        """
        CREATE TEMP TABLE eligibility_update (
            is_addressable BOOLEAN,
            account_id VARCHAR
        )
        """
    )
    if updates:
        connection.executemany(
            "INSERT INTO eligibility_update VALUES (?, ?)",
            updates,
        )
    connection.execute(
        """
        UPDATE account_score
        SET is_addressable = eligibility_update.is_addressable
        FROM eligibility_update
        WHERE account_score.account_id = eligibility_update.account_id
        """
    )
    connection.execute("DROP TABLE eligibility_update")
    connection.execute("CHECKPOINT")
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM account_score WHERE is_addressable"
        ).fetchone()[0]
    )


def refresh_database_eligibility(database_path: Path) -> int:
    """Apply current YAML sanitization rules to an existing DuckDB file."""
    with closing(connect_database(database_path)) as connection:
        return refresh_sales_eligibility(connection)


def account_from_row(
    row: dict[str, Any], rules: dict[str, Any] | None = None
) -> AccountScore:
    """Rebuild the scoring contract from one materialized account row."""
    weights = (rules or load_rules())["weights"]
    codes = [str(code) for code in row["signal_codes"]]
    details = [str(detail) for detail in row.get("signal_details") or ()]
    return AccountScore(
        account_id=str(row["account_id"]),
        account_name=str(row["account_name"]),
        is_named=bool(row["is_named"]),
        is_addressable=bool(row["is_addressable"]),
        icp_score=int(row["icp_score"]),
        country_code=str(row["country_code"]) if row["country_code"] else None,
        org=str(row["org"]) if row["org"] else None,
        ports=tuple(int(port) for port in row["ports"]),
        ip_addresses=tuple(str(address) for address in row["ip_addresses"]),
        banner_count=int(row["banner_count"]),
        signals=tuple(
            Signal(
                code=code,
                weight=int(weights[code]),
                detail=details[index] if index < len(details) else code,
            )
            for index, code in enumerate(codes)
        ),
        vertical=str(row["vertical"]),
    )


def query_qualified_accounts(
    database_path: Path,
    *,
    minimum_score: int | None = None,
    country_codes: tuple[str, ...] = (),
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Read a small, ranked lead set; never load banner facts into Python."""
    rules = load_rules()
    score = int(minimum_score or rules["llm_gate_score"])
    parameters: list[object] = [score]
    country_sql = ""
    if country_codes:
        placeholders = ", ".join("?" for _ in country_codes)
        country_sql = f"AND country_code IN ({placeholders})"
        parameters.extend(country_codes)
    parameters.append(limit)

    with closing(duckdb.connect(str(database_path), read_only=True)) as connection:
        cursor = connection.execute(
            f"""
            SELECT *
            FROM account_score
            WHERE is_addressable
              AND icp_score >= ?
              {country_sql}
            ORDER BY icp_score DESC, account_name
            LIMIT ?
            """,
            parameters,
        )
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def query_ranked_accounts(
    database_path: Path,
    *,
    minimum_score: int = 0,
    addressable_only: bool = True,
    country_codes: tuple[str, ...] = (),
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query a bounded account page without scanning facts in Python."""
    clauses = ["icp_score >= ?"]
    parameters: list[object] = [minimum_score]
    if addressable_only:
        clauses.append("is_addressable")
    if country_codes:
        placeholders = ", ".join("?" for _ in country_codes)
        clauses.append(f"country_code IN ({placeholders})")
        parameters.extend(country_codes)
    parameters.append(limit)

    with closing(duckdb.connect(str(database_path), read_only=True)) as connection:
        cursor = connection.execute(
            f"""
            SELECT *
            FROM account_score
            WHERE {" AND ".join(clauses)}
            ORDER BY icp_score DESC, account_name
            LIMIT ?
            """,
            parameters,
        )
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def query_database_summary(database_path: Path, gate: int) -> dict[str, int]:
    """Return queue metrics from materialized tables.

    A serving-only export drops `banner_fact`, so the corpus banner count comes
    from `store_summary` when the facts are not present.
    """
    with closing(duckdb.connect(str(database_path), read_only=True)) as connection:
        tables = {
            str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()
        }
        if "banner_fact" in tables:
            banner_sql = "(SELECT COUNT(*) FROM banner_fact)"
        elif "store_summary" in tables:
            banner_sql = "(SELECT banners FROM store_summary)"
        else:
            banner_sql = "0"
        row = connection.execute(
            f"""
            SELECT
                {banner_sql} AS banners,
                COUNT(*) AS accounts,
                COUNT(*) FILTER (WHERE is_addressable) AS addressable,
                COUNT(*) FILTER (
                    WHERE is_addressable AND icp_score >= ?
                ) AS qualified
            FROM account_score
            """,
            [gate],
        ).fetchone()
    return {
        "banners": int(row[0]),
        "accounts": int(row[1]),
        "addressable": int(row[2]),
        "qualified": int(row[3]),
    }


def export_serving_store(
    source_path: Path,
    output_path: Path,
    *,
    memory_limit: str = "2GB",
    threads: int = 2,
) -> int:
    """Copy account scores plus corpus counts into a hostable store."""
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (output_path, output_path.with_suffix(output_path.suffix + ".wal")):
        stale.unlink(missing_ok=True)

    with closing(
        connect_database(output_path, memory_limit=memory_limit, threads=threads)
    ) as connection:
        connection.execute(f"ATTACH {_sql_string(str(source_path))} AS source_store")
        connection.execute(
            "CREATE TABLE account_score AS SELECT * FROM source_store.account_score"
        )
        connection.execute(
            """
            CREATE TABLE store_summary AS
            SELECT
                (SELECT COUNT(*) FROM source_store.banner_fact) AS banners,
                COUNT(*) AS accounts,
                COUNT(*) FILTER (WHERE is_addressable) AS addressable
            FROM source_store.account_score
            """
        )
        # No account_id index here: queue queries filter on score and
        # addressability, and the index would more than double the download.
        connection.execute("DETACH source_store")
        connection.execute("CHECKPOINT")
        return int(
            connection.execute("SELECT COUNT(*) FROM account_score").fetchone()[0]
        )


def query_country_codes(database_path: Path) -> list[str]:
    """Return countries represented in the scored account table."""
    with closing(duckdb.connect(str(database_path), read_only=True)) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT country_code
            FROM account_score
            WHERE country_code IS NOT NULL
            ORDER BY country_code
            """
        ).fetchall()
    return [str(row[0]) for row in rows]
