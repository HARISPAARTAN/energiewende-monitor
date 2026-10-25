import os
from datetime import date

import pytest

from ewmonitor import db
from ewmonitor.config import load_settings
from ewmonitor.dims import load_dims
from ewmonitor.ingest import ingest_fixtures
from ewmonitor.load import key_range, load_facts, write_stg


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def con(settings):
    if not os.environ.get("MSSQL_SA_PASSWORD"):
        pytest.skip("MSSQL_SA_PASSWORD not set; database tests need the SQL Server container")
    db.ensure_database(settings.db)
    connection = db.connect(settings.db)
    yield connection
    connection.close()


@pytest.fixture(scope="session", autouse=True)
def fixture_week_loaded(con, settings):
    """Load the fixture week when the facts are empty, so the suite also runs against a fresh database."""
    sql_dir = settings.root / "sql"
    db.run_ddl(con, sql_dir)  # idempotent; on a fresh database dw.fact_last does not exist before this
    if con.execute("SELECT COUNT(*) FROM dw.fact_last").fetchval() == 0:
        df = ingest_fixtures(settings.fixtures_dir)
        write_stg(con, df)
        load_dims(con, settings.seed_dir, date(2023, 1, 1), date(2030, 12, 31))
        load_facts(con, sql_dir, *key_range(df))
