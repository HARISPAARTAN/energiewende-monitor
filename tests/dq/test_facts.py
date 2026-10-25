from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from ewmonitor.load import load_facts

pytestmark = pytest.mark.db


def test_fixture_week_row_counts(con):
    assert con.execute("SELECT COUNT(*) FROM dw.fact_erzeugung").fetchval() == 11 * 676
    assert con.execute("SELECT COUNT(*) FROM dw.fact_last").fetchval() == 676
    assert con.execute("SELECT COUNT(*) FROM dw.fact_preis").fetchval() == 169
    assert con.execute("SELECT COUNT(DISTINCT energietraeger_key) FROM dw.fact_erzeugung").fetchval() == 11


def test_autumn_transition_day_has_100_quarter_hours(con):
    assert con.execute("SELECT COUNT(*) FROM dw.fact_last WHERE datum_key = 20251026").fetchval() == 100
    assert con.execute("SELECT COUNT(*) FROM dw.fact_last WHERE datum_key = 20251020").fetchval() == 96


def test_fact_last_pivot_has_all_three_measures(con):
    row = con.execute(
        "SELECT netzlast_mwh, residuallast_mwh, pumpspeicher_verbrauch_mwh FROM dw.fact_last "
        "WHERE datum_key = 20251020 AND zeit_key = 0"
    ).fetchone()
    assert all(v is not None and v > 0 for v in row)


def test_hourly_view_sums_four_quarter_hours(con):
    quarter = con.execute(
        "SELECT SUM(netzlast_mwh) FROM dw.fact_last WHERE ts_utc >= '2025-10-20 10:00' AND ts_utc < '2025-10-20 11:00'"
    ).fetchval()
    hour = con.execute(
        "SELECT netzlast_mwh FROM rpt.v_last_stunde WHERE stunde_utc = '2025-10-20 10:00'"
    ).fetchval()
    assert abs(Decimal(quarter) - Decimal(hour)) < Decimal("0.001")


def test_price_join_view_has_169_rows(con):
    assert con.execute("SELECT COUNT(*) FROM rpt.v_preis_last_stunde").fetchval() == 169


def test_views_exist_and_run(con):
    for view in ["rpt.v_erzeugung", "rpt.v_last", "rpt.v_preis", "rpt.v_dim_datum", "rpt.v_dim_zeit",
                 "rpt.v_dim_energietraeger", "rpt.v_dim_region", "rpt.v_dim_bundesland",
                 "rpt.v_negative_preisphasen", "rpt.v_dq_luecken"]:
        con.execute(f"SELECT TOP 1 * FROM {view}").fetchall()


def test_dq_luecken_reports_no_gaps_for_the_fixture_week(con):
    assert con.execute("SELECT COUNT(*) FROM rpt.v_dq_luecken").fetchval() == 11
    assert con.execute("SELECT ISNULL(SUM(fehlend), 0) FROM rpt.v_dq_luecken").fetchval() == 0
    assert con.execute("SELECT MAX(fehlend) FROM rpt.v_dq_luecken").fetchval() == 0
    assert con.execute("SELECT MIN(fehlend) FROM rpt.v_dq_luecken").fetchval() == 0


def test_negative_price_phases_for_the_fixture_week(con):
    phases, hours = con.execute("SELECT COUNT(*), SUM(stunden) FROM rpt.v_negative_preisphasen").fetchone()
    assert (phases, hours) == (3, 11)
    rows = con.execute(
        "SELECT start_datum_key, start_utc, ende_utc, start_lokal, ende_lokal, stunden "
        "FROM rpt.v_negative_preisphasen ORDER BY start_utc"
    ).fetchall()
    for _key, start_utc, ende_utc, _sl, _el, stunden in rows:
        assert ende_utc == start_utc + timedelta(hours=stunden)  # exclusive end
    # Friday 2025-10-24 in summer time (UTC+2), Sunday 2025-10-26 after the switch to winter time (UTC+1)
    assert tuple(rows[0][:5]) == (20251024, datetime(2025, 10, 24, 11), datetime(2025, 10, 24, 13),
                                  datetime(2025, 10, 24, 13), datetime(2025, 10, 24, 15))
    assert tuple(rows[2][:5]) == (20251026, datetime(2025, 10, 26, 7), datetime(2025, 10, 26, 15),
                                  datetime(2025, 10, 26, 8), datetime(2025, 10, 26, 16))


def test_bundesland_kuerzel_is_not_padded(con):
    row = con.execute("SELECT kuerzel, DATALENGTH(kuerzel) FROM rpt.v_dim_bundesland WHERE kuerzel = 'BW'").fetchone()
    assert tuple(row) == ("BW", 2)


CAPACITY_FINGERPRINT = """
SELECT COUNT(*), SUM(zubau_mw), SUM(anzahl_zubau), SUM(abgang_mw), SUM(anzahl_abgang), SUM(anfangsbestand_mw),
       SUM(anfangsbestand_anzahl), SUM(bestand_mw), SUM(bestand_anzahl) FROM dw.fact_kapazitaet"""


def test_reload_is_idempotent(con, settings):
    before = con.execute("SELECT COUNT(*) FROM dw.fact_erzeugung").fetchval()
    kapazitaet_before = tuple(con.execute(CAPACITY_FINGERPRINT).fetchone())
    assert kapazitaet_before[0] > 0
    load_facts(con, settings.root / "sql", 20251020, 20251026)
    assert con.execute("SELECT COUNT(*) FROM dw.fact_erzeugung").fetchval() == before
    assert tuple(con.execute(CAPACITY_FINGERPRINT).fetchone()) == kapazitaet_before
