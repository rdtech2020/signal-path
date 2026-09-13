from contextlib import closing
from pathlib import Path

from src.duckdb_store import (
    connect_database,
    ingest_records,
    materialize_account_scores,
    query_qualified_accounts,
)
from src.ingester import load_records, normalize_banner
from src.scoring import load_rules, score_accounts

SAMPLE_PATH = Path("data/readable/shodan_100.jsonl")


def test_duckdb_scoring_matches_python_contract(tmp_path):
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
        banner_count = ingest_records(
            connection,
            load_records(SAMPLE_PATH),
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        account_count = materialize_account_scores(connection, rules)
        sql_rows = connection.execute(
            """
            SELECT account_id, icp_score, signal_codes
            FROM account_score
            ORDER BY account_id
            """
        ).fetchall()

    normalized_records = [
        normalized
        for record in load_records(SAMPLE_PATH)
        if (normalized := normalize_banner(record)) is not None
    ]
    python_rows = sorted(
        (
            account.account_id,
            account.icp_score,
            [signal.code for signal in account.signals],
        )
        for account in score_accounts(normalized_records)
    )
    assert banner_count == 100
    assert account_count == 85
    assert sql_rows == python_rows


def test_qualified_query_only_returns_small_addressable_result(tmp_path):
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
            load_records(SAMPLE_PATH),
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)

    accounts = query_qualified_accounts(database_path)
    assert len(accounts) == 4
    assert all(account["is_addressable"] for account in accounts)
    assert all(account["icp_score"] >= 40 for account in accounts)
