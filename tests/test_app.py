import json
from contextlib import closing
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.duckdb_store import (
    connect_database,
    ingest_records,
    materialize_account_scores,
)
from src.scoring import load_rules
from tests.test_scoring import public_winrm_record


def test_dashboard_renders_database_metrics(monkeypatch, tmp_path):
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

    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=30).run()
    assert not app.exception
    assert app.metric[0].value == "1"
    assert app.metric[1].value == "1"
    assert app.metric[2].value == "1"
    assert app.metric[3].value == "0"
    assert len(app.dataframe) == 1


def test_queue_shows_evidence_text_not_signal_codes(monkeypatch, tmp_path):
    """A seller and the model must read the same wording."""
    database_path = tmp_path / "signal_path.duckdb"
    rules = load_rules()
    record = {
        **public_winrm_record(),
        "tags": ["self-signed"],
        "http": {"status": 503, "server": "Microsoft-HTTPAPI/2.0"},
    }
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
            [record],
            rules,
            batch_size=100,
            stage_path=tmp_path / "stage.csv",
            progress_every=0,
        )
        materialize_account_scores(connection, rules)

    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=30).run()

    assert not app.exception
    assert app.metric[3].value == "1"
    brief = json.loads(app.json[0].body)
    details = [signal["detail"] for signal in brief["signals"]]
    assert any("5985" in detail for detail in details)
    assert not any("deterministic rule" in detail for detail in details)
