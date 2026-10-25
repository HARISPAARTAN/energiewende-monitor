import pytest

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "stg.smard_series",
    "dw.dim_datum",
    "dw.dim_zeit",
    "dw.dim_energietraeger",
    "dw.dim_region",
    "dw.dim_bundesland",
    "dw.fact_erzeugung",
    "dw.fact_last",
    "dw.fact_preis",
}


def test_all_tables_exist(con):
    rows = con.execute(
        "SELECT s.name + '.' + t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id"
    ).fetchall()
    names = {r[0] for r in rows}
    assert EXPECTED_TABLES <= names


def test_fact_primary_keys(con):
    sql = """
    SELECT t.name, COUNT(*) FROM sys.key_constraints k
    JOIN sys.tables t ON t.object_id = k.parent_object_id
    JOIN sys.index_columns ic ON ic.object_id = k.parent_object_id AND ic.index_id = k.unique_index_id
    WHERE k.type = 'PK' AND t.name LIKE 'fact_%' GROUP BY t.name
    """
    counts = dict(con.execute(sql).fetchall())
    assert counts == {"fact_erzeugung": 3, "fact_last": 2, "fact_preis": 2, "fact_kapazitaet": 3}
