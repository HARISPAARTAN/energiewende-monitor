from pathlib import Path

import pytest

from ewmonitor.config import DbConfig, load_settings

ROOT = Path(__file__).resolve().parents[2]

GENERATION = (1223, 1224, 1225, 1226, 1227, 1228, 4066, 4067, 4068, 4069, 4070, 4071)
CONSUMPTION = (410, 4359, 4387)


def _db(user: str = "sa", password: str = "pw") -> DbConfig:
    return DbConfig(
        server="localhost,1433",
        database="energiewende",
        user=user,
        password=password,
        driver="ODBC Driver 18 for SQL Server",
    )


def _write_config(root: Path, **lists: str) -> None:
    """A minimal config.toml; keyword arguments replace the TOML value of a list key."""
    values = {
        "regions": '["DE-LU"]',
        "generation": "[1223]",
        "consumption": "[410]",
        "price_regions": '["DE-LU"]',
    }
    values.update(lists)
    (root / "config.toml").write_text(
        f"""[scope]
start = "2023-01-01"
regions = {values["regions"]}

[smard]
base_url = "https://example.invalid/chart_data"
generation = {values["generation"]}
consumption = {values["consumption"]}
price = 4169
price_regions = {values["price_regions"]}

[paths]
raw = "data/raw"
seed = "data/seed"
fixtures = "data/fixtures"
""",
        encoding="utf-8",
    )


def test_settings_read_config_toml():
    s = load_settings(ROOT)
    assert s.start == "2023-01-01"
    assert s.regions == ("DE-LU",)
    assert s.smard.price == 4169
    assert s.smard.price_regions == ("DE-LU",)
    assert s.smard.generation == GENERATION
    assert s.smard.consumption == CONSUMPTION
    assert s.smard.quarterhour_filters == GENERATION + CONSUMPTION
    assert s.raw_dir == ROOT / "data" / "raw"
    assert s.fixtures_dir == ROOT / "data" / "fixtures"


def test_db_config_from_env(monkeypatch):
    monkeypatch.setenv("MSSQL_SA_PASSWORD", "pw")
    monkeypatch.setenv("EWM_DB_SERVER", "db.example,1433")
    monkeypatch.setenv("EWM_DB_NAME", "ewm_test")
    monkeypatch.delenv("EWM_DB_USER", raising=False)
    monkeypatch.delenv("EWM_DB_DRIVER", raising=False)
    s = load_settings(ROOT)
    cs = s.db.connection_string()
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in cs
    assert "SERVER=db.example,1433" in cs and "DATABASE=ewm_test" in cs
    assert "UID={sa}" in cs and "PWD={pw}" in cs
    assert "Encrypt=yes" in cs and "TrustServerCertificate=yes" in cs
    assert "DATABASE=master" in s.db.connection_string("master")


def test_connection_string_quotes_user_and_password():
    cs = _db(user="ewm}user", password="p;w}d").connection_string()
    assert "UID={ewm}}user};" in cs
    assert "PWD={p;w}}d};" in cs


def test_db_config_repr_hides_password():
    assert "s3cret" not in repr(_db(password="s3cret"))


def test_empty_password_raises_on_connection_string(monkeypatch):
    monkeypatch.delenv("MSSQL_SA_PASSWORD", raising=False)
    s = load_settings(ROOT)  # loading stays lenient, e.g. for the unit tests
    assert s.db.password == ""
    with pytest.raises(ValueError, match="MSSQL_SA_PASSWORD fehlt"):
        s.db.connection_string()


def test_minimal_config_loads(tmp_path):
    _write_config(tmp_path)
    s = load_settings(tmp_path)
    assert s.regions == ("DE-LU",)
    assert s.smard.quarterhour_filters == (1223, 410)


@pytest.mark.parametrize(
    ("key", "value"),
    [("regions", '"DE-LU"'), ("generation", "1223"), ("consumption", "410"), ("price_regions", '"DE-LU"')],
)
def test_non_list_config_value_raises(tmp_path, key, value):
    _write_config(tmp_path, **{key: value})
    with pytest.raises(ValueError, match=rf"\b{key}\b"):
        load_settings(tmp_path)
