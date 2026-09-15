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
