from pathlib import Path

from ewmonitor.config import load_settings

ROOT = Path(__file__).resolve().parents[2]


def test_settings_read_config_toml():
    s = load_settings(ROOT)
    assert s.start == "2023-01-01"
    assert s.regions == ("DE-LU",)
    assert s.smard.price == 4169
    assert s.smard.price_regions == ("DE-LU",)
    assert len(s.smard.generation) == 12 and len(s.smard.consumption) == 3
    assert s.smard.quarterhour_filters == s.smard.generation + s.smard.consumption
    assert s.raw_dir == ROOT / "data" / "raw"
    assert s.fixtures_dir == ROOT / "data" / "fixtures"


def test_db_config_from_env(monkeypatch):
    monkeypatch.setenv("MSSQL_SA_PASSWORD", "pw")
    monkeypatch.setenv("EWM_DB_SERVER", "db.example,1433")
    monkeypatch.setenv("EWM_DB_NAME", "ewm_test")
    s = load_settings(ROOT)
    cs = s.db.connection_string()
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in cs
    assert "SERVER=db.example,1433" in cs and "DATABASE=ewm_test" in cs
    assert "UID=sa" in cs and "PWD=pw" in cs
    assert "Encrypt=yes" in cs and "TrustServerCertificate=yes" in cs
    assert "DATABASE=master" in s.db.connection_string("master")
