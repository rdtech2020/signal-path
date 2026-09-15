import gzip
from contextlib import closing
from pathlib import Path

import pytest

from src.duckdb_store import (
    connect_database,
    ingest_records,
    materialize_account_scores,
)
from src.scoring import load_rules
from src.store_fetch import ensure_database
from tests.test_scoring import public_winrm_record


def built_store(directory: Path) -> Path:
    database_path = directory / "source.duckdb"
    rules = load_rules()
    with closing(
        connect_database(
            database_path,
            memory_limit="512MB",
            threads=1,
            temp_directory=directory / "spill",
            max_temp_size="1GB",
        )
    ) as connection:
        ingest_records(
            connection,
            [public_winrm_record()],
            rules,
            batch_size=100,
            stage_path=directory / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)
    return database_path


def test_existing_store_is_used_without_a_download(tmp_path):
    database_path = built_store(tmp_path)

    assert ensure_database(database_path, "https://example.invalid/store.duckdb") == (
        database_path
    )


def test_store_is_downloaded_and_validated(tmp_path):
    source = built_store(tmp_path)
    target = tmp_path / "fetched" / "signal_path.duckdb"
    seen: list[int] = []

    resolved = ensure_database(
        target,
        source.as_uri(),
        on_progress=lambda received, total: seen.append(received),
    )

    assert resolved.exists()
    assert seen
    with closing(connect_database(resolved, threads=1)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM account_score").fetchone()[
            0
        ] == 1


def test_gzipped_store_is_decompressed(tmp_path):
    source = built_store(tmp_path)
    archive = tmp_path / "store.duckdb.gz"
    archive.write_bytes(gzip.compress(source.read_bytes()))
    target = tmp_path / "fetched.duckdb"

    resolved = ensure_database(target, archive.as_uri())

    assert resolved.read_bytes() == source.read_bytes()


def test_truncated_download_is_rejected_and_leaves_no_store(tmp_path):
    broken = tmp_path / "broken.duckdb"
    broken.write_bytes(b"not a duckdb file")
    target = tmp_path / "fetched.duckdb"

    with pytest.raises(RuntimeError, match="not a readable store"):
        ensure_database(target, broken.as_uri())

    assert not target.exists()
    assert not target.with_suffix(".duckdb.part").exists()


def test_missing_store_without_a_url_explains_both_options(tmp_path):
    with pytest.raises(FileNotFoundError) as error:
        ensure_database(tmp_path / "absent.duckdb")

    message = str(error.value)
    assert "build_duckdb.py" in message
    assert "DATABASE_URL" in message


def test_unsupported_url_scheme_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ensure_database(tmp_path / "absent.duckdb", "ftp://example.invalid/store")
