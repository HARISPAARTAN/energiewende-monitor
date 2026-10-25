from datetime import datetime

import pytest

from ewmonitor.checks import check_incomplete_hours, has_failures, run_checks

pytestmark = pytest.mark.db


def test_checks_pass_on_the_fixture_week(con):
    results = run_checks(con, 20251020, 20251026, now=datetime(2025, 11, 1))
    assert not has_failures(results), [r for r in results if r.status == "fail"]
    by_name = {r.name: r for r in results}
    assert by_name["viertelstunden_pro_tag"].status == "ok"
    assert by_name["fakten_vs_staging"].status == "ok", by_name["fakten_vs_staging"].detail
    for name in ["unvollstaendige_stunden", "last_viertelstunden_pro_tag", "last_nullwerte", "preis_stunden_pro_tag"]:
        assert by_name[name].status == "ok", by_name[name].detail
    assert by_name["aktualitaet"].status == "ok"


def test_freshness_warns_when_data_is_old(con):
    results = run_checks(con, 20251020, 20251026, now=datetime(2026, 6, 1))
    assert {r.name: r.status for r in results}["aktualitaet"] == "warn"


def test_partial_hour_is_null_in_the_hourly_view_and_counted_as_incomplete(con):
    con.execute("UPDATE dw.fact_last SET netzlast_mwh = NULL WHERE ts_utc = '2025-10-20 10:15'")
    try:
        row = con.execute(
            "SELECT netzlast_mwh, viertelstunden_netzlast_mwh, residuallast_mwh, viertelstunden_residuallast_mwh "
            "FROM rpt.v_last_stunde WHERE stunde_utc = '2025-10-20 10:00'"
        ).fetchone()
        assert row[0] is None and row[1] == 3
        assert row[2] is not None and row[3] == 4
        result = check_incomplete_hours(con, 20251020, 20251026)
        assert (result.status, result.detail[:9]) == ("warn", "1 von 169")  # autumn DST week: 169 hours
    finally:
        con.rollback()
