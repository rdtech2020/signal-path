from contextlib import closing

import duckdb

from src.duckdb_store import (
    connect_database,
    count_ranked_accounts,
    export_serving_store,
    ingest_records,
    materialize_account_scores,
    query_database_summary,
    query_qualified_accounts,
    query_ranked_accounts,
)
from src.ingester import normalize_banner
from src.scoring import load_rules, score_accounts
from tests.test_scoring import public_winrm_record


def _records() -> list[dict]:
    return [
        public_winrm_record(),
        {
            "ip_str": "1.1.1.1",
            "port": 443,
            "domains": ["cdn-edge.net"],
            "tags": ["cdn"],
            "http": {"status": 200},
            "ssl": {"cert": {"expired": True}},
        },
        {
            "ip_str": "10.0.0.7",
            "port": 80,
            "domains": ["internal.corp"],
        },
    ]


def test_duckdb_scoring_matches_python_contract(tmp_path):
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    records = _records()
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        banner_count = ingest_records(
            connection,
            records,
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)
        sql_rows = connection.execute(
            """
            SELECT
                account_id,
                icp_score,
                is_addressable,
                signal_codes,
                signal_details
            FROM account_score
            ORDER BY account_id
            """
        ).fetchall()

        public_records = [
            normalized
            for record in records
            if record["ip_str"] != "10.0.0.7"
            and (normalized := normalize_banner(record)) is not None
        ]
    python_rows = sorted(
        (
            account.account_id,
            account.icp_score,
            account.is_addressable,
            [signal.code for signal in account.signals],
            [signal.detail for signal in account.signals],
        )
        for account in score_accounts(public_records)
    )
    assert banner_count == 2
    assert sql_rows == python_rows


def test_persisted_details_describe_the_evidence(tmp_path):
    """Codes alone make a generic brief; the SQL path must keep the wording."""
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        ingest_records(
            connection,
            [public_winrm_record()],
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)
        codes, details = connection.execute(
            "SELECT signal_codes, signal_details FROM account_score"
        ).fetchone()

    assert len(codes) == len(details)
    winrm_detail = details[codes.index("exposed_winrm")]
    assert "5985" in winrm_detail
    assert "deterministic rule" not in winrm_detail


def test_qualified_query_only_returns_addressable_results(tmp_path):
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        ingest_records(
            connection,
            _records(),
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)

    accounts = query_qualified_accounts(database_path, minimum_score=40)
    assert accounts
    assert all(account["is_addressable"] for account in accounts)
    assert all(account["icp_score"] >= 40 for account in accounts)
    assert all(account["account_name"] != "localhost" for account in accounts)


def test_paging_walks_every_account_exactly_once(tmp_path):
    """Offset paging is only safe if the sort order is fully deterministic."""
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    records = [
        {
            "ip_str": f"8.8.8.{index}",
            "port": 5985,
            "domains": [f"acme-{index}.io"],
            "product": "WinRM",
        }
        for index in range(1, 8)
    ]
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        ingest_records(
            connection,
            records,
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)

    total = count_ranked_accounts(database_path, addressable_only=False)
    assert total == len(records)

    seen: list[str] = []
    for offset in range(0, total, 3):
        page = query_ranked_accounts(
            database_path, addressable_only=False, limit=3, offset=offset
        )
        seen.extend(str(row["account_id"]) for row in page)

    assert len(seen) == total
    assert len(set(seen)) == total


def test_serving_export_keeps_every_account_and_the_corpus_counts(tmp_path):
    """Hosting the queue must not mean hosting the facts behind it."""
    source_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    with closing(
        connect_database(
            source_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        ingest_records(
            connection,
            _records(),
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)

    full_summary = query_database_summary(source_path, 40)
    serving_path = tmp_path / "serving.duckdb"
    accounts = export_serving_store(source_path, serving_path, memory_limit="512MB")

    assert accounts == full_summary["accounts"]
    assert query_database_summary(serving_path, 40) == full_summary
    assert serving_path.stat().st_size < source_path.stat().st_size
    with closing(duckdb.connect(str(serving_path), read_only=True)) as connection:
        tables = {str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()}
    assert "banner_fact" not in tables


def test_private_ips_are_dropped_during_duckdb_ingest(tmp_path):
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=tmp_path / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        count = ingest_records(
            connection,
            [
                {"ip_str": "10.0.0.7", "port": 80, "domains": ["internal.corp"]},
                {"ip_str": "127.0.0.1", "port": 80, "hostnames": ["localhost"]},
                {"ip_str": "8.8.8.8", "port": 443, "domains": ["dns.google"]},
            ],
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        assert count == 1
        stored = connection.execute("SELECT ip_str FROM banner_fact").fetchall()
        assert stored == [("8.8.8.8",)]
