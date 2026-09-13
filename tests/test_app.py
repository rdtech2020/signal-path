from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_sample_metrics(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "missing.duckdb"))
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(app_path, default_timeout=30).run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["100", "85", "18", "4"]
    assert len(app.dataframe) == 1
