import pytest

pytestmark = pytest.mark.db


def test_dimension_row_counts(con):
    counts = {
        table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchval()
        for table in ["dw.dim_zeit", "dw.dim_energietraeger", "dw.dim_region", "dw.dim_bundesland"]
    }
    assert counts == {"dw.dim_zeit": 96, "dw.dim_energietraeger": 12, "dw.dim_region": 5, "dw.dim_bundesland": 17}


def test_calendar_covers_2023_to_2030_with_dst_days(con):
    first, last = con.execute("SELECT MIN(datum_key), MAX(datum_key) FROM dw.dim_datum").fetchone()
    assert first == 20230101 and last == 20301231
    assert con.execute("SELECT viertelstunden FROM dw.dim_datum WHERE datum_key = 20251026").fetchval() == 100
    assert con.execute("SELECT viertelstunden FROM dw.dim_datum WHERE datum_key = 20250330").fetchval() == 92
