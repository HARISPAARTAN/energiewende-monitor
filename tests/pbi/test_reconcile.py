import os

import pytest

from tools.pbi import reconcile

pytestmark = [pytest.mark.pbi, pytest.mark.live]
TOLERANCE = {"R1": 0.5, "R2": 0.0005, "R3": 0, "R4": 0.005, "R5": 0.5, "R6": 0.5, "R7": 0.5, "R8": 0.5, "R9": 0}


@pytest.fixture(scope="module")
def port():
    p = reconcile.desktop_port()
    if p is None:
        pytest.skip("Power BI Desktop is not open with the project (no msmdsrv.port.txt)")
    if not reconcile.adomd_available():
        pytest.skip(
            "ADOMD client not found (uv run python tools/pbi/fetch_adomd.py, or install DAX Studio: winget install DaxStudio.DaxStudio)"
        )
    return p


@pytest.fixture(scope="module")
def sql_values():
    if not os.environ.get("MSSQL_SA_PASSWORD"):
        pytest.skip("MSSQL_SA_PASSWORD not set")
    from ewmonitor.config import load_settings
    from ewmonitor.db import connect

    con = connect(load_settings().db)
    out = {}
    for stmt in reconcile.sql_statements():
        row = con.execute(stmt).fetchone()
        out[row[0]] = float(row[1])
    return out


@pytest.mark.parametrize("rid", list(TOLERANCE))
def test_dax_matches_sql(port, sql_values, rid):
    dax_value = reconcile.dax_value(port, rid)
    assert abs(dax_value - sql_values[rid]) <= TOLERANCE[rid], (rid, dax_value, sql_values[rid])
