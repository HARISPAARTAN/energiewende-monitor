"""Regression tests for review finding C1: an error raised by a later statement of a batch must surface and
roll back the statements before it, instead of being discarded with the cursor and committed."""

import pyodbc
import pytest

from ewmonitor.db import run_sql_file
from ewmonitor.load import load_facts

pytestmark = pytest.mark.db

FACTS = ("dw.fact_erzeugung", "dw.fact_last", "dw.fact_preis")


def test_error_after_delete_in_one_batch_raises_and_keeps_the_rows(con, tmp_path):
    con.execute("IF OBJECT_ID(N'tempdb..#c1') IS NOT NULL DROP TABLE #c1")
    con.execute("CREATE TABLE #c1 (k int PRIMARY KEY)")
    con.execute("INSERT INTO #c1 (k) VALUES (1), (2)")
    con.commit()
    script = tmp_path / "delete_then_violate.sql"
    # shaped like sql/load/*.sql before the fix: DECLARE, DELETE, INSERT, no SET NOCOUNT
    script.write_text(
        "DECLARE @from_key int = ?, @to_key int = ?;\n"
        "DELETE FROM #c1 WHERE k BETWEEN @from_key AND @to_key;\n"
        "INSERT INTO #c1 (k) VALUES (1), (1);\n",
        encoding="utf-8",
    )
    try:
        with pytest.raises(pyodbc.IntegrityError):
            run_sql_file(con, script, 1, 2)
        assert con.execute("SELECT COUNT(*) FROM #c1").fetchval() == 2
    finally:
        con.rollback()
        con.execute("DROP TABLE #c1")
        con.commit()


def _fact_counts(con) -> dict[str, int]:
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchval() for t in FACTS}


def test_load_facts_outside_the_calendar_raises_and_leaves_the_facts_unchanged(con, settings):
    """A staging row dated before dim_datum (1990-01-01) breaks every fact INSERT on its date foreign key."""
    first_key = con.execute("SELECT MIN(datum_key) FROM dw.dim_datum").fetchval()
    assert first_key == 19900101
    before = _fact_counts(con)
    assert all(n > 0 for n in before.values())
    stg = [  # 1989-12-31 00:00 Europe/Berlin = 1989-12-30 23:00 UTC
        (1223, "DE-LU", "quarterhour"),
        (410, "DE-LU", "quarterhour"),
        (4169, "DE-LU", "hour"),
    ]
    cur = con.cursor()
    try:
        for filter_id, region, resolution in stg:
            cur.execute(
                "INSERT INTO stg.smard_series (filter_id, region, resolution, ts_utc, value, datum_key, zeit_key) "
                "VALUES (?, ?, ?, '1989-12-30 23:00', 1.0, 19891231, 0)",
                filter_id, region, resolution,
            )
        con.commit()
    finally:
        cur.close()
    sql_dir = settings.root / "sql"
    try:
        with pytest.raises(pyodbc.IntegrityError):
            load_facts(con, sql_dir, 19891231, 20301231)
        assert _fact_counts(con) == before
        for path in sorted((sql_dir / "load").glob("*.sql")):  # each script on its own, not only the first
            with pytest.raises(pyodbc.IntegrityError):
                run_sql_file(con, path, 19891231, 20301231)
            assert _fact_counts(con) == before, path.name
    finally:
        con.rollback()
        con.execute("DELETE FROM stg.smard_series WHERE datum_key = 19891231")
        con.commit()
