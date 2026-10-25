from datetime import datetime

import pytest

from ewmonitor.checks import has_failures, run_checks

pytestmark = pytest.mark.db


def test_checks_pass_on_the_fixture_week(con):
    results = run_checks(con, 20251020, 20251026, now=datetime(2025, 11, 1))
    assert not has_failures(results), [r for r in results if r.status == "fail"]
    by_name = {r.name: r for r in results}
    assert by_name["viertelstunden_pro_tag"].status == "ok"
    assert by_name["fakten_vs_staging"].status == "ok", by_name["fakten_vs_staging"].detail
    assert by_name["stunden_aggregat"].status == "ok"
    assert by_name["aktualitaet"].status == "ok"


def test_freshness_warns_when_data_is_old(con):
    results = run_checks(con, 20251020, 20251026, now=datetime(2026, 6, 1))
    assert {r.name: r.status for r in results}["aktualitaet"] == "warn"
