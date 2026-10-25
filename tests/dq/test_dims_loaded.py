import pytest

pytestmark = pytest.mark.db


def test_dimension_row_counts(con):
    counts = {
        table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchval()
        for table in ["dw.dim_zeit", "dw.dim_energietraeger", "dw.dim_region", "dw.dim_bundesland"]
    }
    assert counts == {"dw.dim_zeit": 96, "dw.dim_energietraeger": 12, "dw.dim_region": 5, "dw.dim_bundesland": 18}


def test_dim_datum_covers_the_calendar(con, settings):
    n = con.execute("SELECT COUNT(*) FROM dw.dim_datum").fetchval()
    days = (settings.calendar_end - settings.calendar_start).days + 1
    assert n == days  # 1990-01-01 to 2030-12-31 = 14975 days
    first, last = con.execute("SELECT MIN(datum), MAX(datum) FROM dw.dim_datum").fetchone()
    assert (first, last) == (settings.calendar_start, settings.calendar_end)


def test_calendar_has_dst_days(con):
    assert con.execute("SELECT viertelstunden FROM dw.dim_datum WHERE datum_key = 20251026").fetchval() == 100
    assert con.execute("SELECT viertelstunden FROM dw.dim_datum WHERE datum_key = 20250330").fetchval() == 92
