"""The DQ suite runs in its own database (EWM_DQ_DB_NAME, default energiewende_dq) that holds only the fixture
week, so whole-table assertions hold and the developer database is never written."""

import os
from dataclasses import replace
from datetime import date

import pytest

from ewmonitor import db
from ewmonitor.config import load_settings
from ewmonitor.dims import load_dims
from ewmonitor.ingest import ingest_fixtures
from ewmonitor.load import key_range, load_facts, write_stg

RESET_TABLES = ("stg.smard_series", "dw.fact_erzeugung", "dw.fact_last", "dw.fact_preis")


@pytest.fixture(scope="session")
def settings():
    base = load_settings()
    dq_name = os.environ.get("EWM_DQ_DB_NAME", "energiewende_dq")
    if dq_name.lower() == base.db.database.lower():
        pytest.exit(
            f"EWM_DQ_DB_NAME ({dq_name!r}) equals the developer database (settings.db.database); "
            "the DQ suite truncates its tables, so it needs a separate database.",
            returncode=2,
        )
    return replace(base, db=replace(base.db, database=dq_name))


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
    """Apply the DDL, empty staging and facts, then load the fixture week (Oct 20-26 2025, autumn DST)."""
    sql_dir = settings.root / "sql"
    db.run_ddl(con, sql_dir)  # idempotent; on a fresh database the tables do not exist before this
    for table in RESET_TABLES:
        con.execute(f"TRUNCATE TABLE {table}")
    con.commit()
    df = ingest_fixtures(settings.fixtures_dir)
    write_stg(con, df)
    load_dims(con, settings.seed_dir, date.fromisoformat(settings.start), date(2030, 12, 31))
    load_facts(con, sql_dir, *key_range(df))
