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


ROLE_TOTALS = (
    'EVALUATE ROW("Erzeugung", [Erzeugung (MWh)], "Volllaststunden", [Volllaststunden (h)], "PV", [Zielerreichung Photovoltaik %], '
    '"Wind an Land", [Zielerreichung Wind an Land %], "Wind auf See", [Zielerreichung Wind auf See %])'
)
STATES_WITH_CAPACITY = (
    'EVALUATE SELECTCOLUMNS(FILTER(SUMMARIZECOLUMNS(Bundesland[Bundesland], "MW", [Installierte Leistung (MW)]), NOT ISBLANK([MW])), '
    '"Bundesland", Bundesland[Bundesland])'
)


def test_role_landesbehoerde_bw_sees_only_baden_wuerttemberg(port):
    # the RLS check of the owner checklist (View as "Landesbehörde BW"): capacity only for BW, no full-load hours and no 2030 gauges
    # (both need the national capacity), generation unchanged (SMARD data is national and not filtered by the role)
    states = [row["Bundesland"] for row in reconcile.dax(port, STATES_WITH_CAPACITY, role="Landesbehörde BW")]
    assert states == ["Baden-Württemberg"]
    assert len(reconcile.dax(port, STATES_WITH_CAPACITY)) > 1
    everyone, bw = reconcile.dax(port, ROLE_TOTALS)[0], reconcile.dax(port, ROLE_TOTALS, role="Landesbehörde BW")[0]
    assert bw["Erzeugung"] == everyone["Erzeugung"]
    assert all(bw[k] is None for k in ("Volllaststunden", "PV", "Wind an Land", "Wind auf See")), bw
    assert all(everyone[k] is not None for k in ("Volllaststunden", "PV", "Wind an Land", "Wind auf See")), everyone


@pytest.mark.parametrize("rid", list(TOLERANCE))
def test_dax_matches_sql(port, sql_values, rid):
    dax_value = reconcile.dax_value(port, rid)
    assert abs(dax_value - sql_values[rid]) <= TOLERANCE[rid], (rid, dax_value, sql_values[rid])
