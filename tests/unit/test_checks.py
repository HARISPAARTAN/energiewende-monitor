from datetime import datetime
from decimal import Decimal

from ewmonitor.checks import (
    CheckResult,
    check_capacity_month_grid,
    check_capacity_non_negative,
    check_capacity_plausible,
    check_capacity_vs_staging,
    check_facts_vs_staging,
    check_freshness,
    check_incomplete_hours,
    format_results,
    has_failures,
)


class _StubCon:
    def __init__(self, row):
        self._row = row

    def execute(self, *_args):
        return self

    def fetchone(self):
        return self._row


def test_has_failures_only_for_fail_status():
    ok = [CheckResult("a", "ok", ""), CheckResult("b", "warn", "x")]
    assert has_failures(ok) is False
    assert has_failures(ok + [CheckResult("c", "fail", "y")]) is True


def test_format_results_is_a_table():
    text = format_results([CheckResult("viertelstunden_pro_tag", "ok", "0 Abweichungen")])
    assert "viertelstunden_pro_tag" in text and "ok" in text and "0 Abweichungen" in text


def test_incomplete_hours_warns_when_the_range_has_no_load_data():
    result = check_incomplete_hours(_StubCon((0, None)), 20251020, 20251026)
    assert (result.status, result.detail) == ("warn", "keine Lastdaten im Zeitraum")


def test_incomplete_hours_warns_never_fails():
    result = check_incomplete_hours(_StubCon((168, 6)), 20261019, 20261024)
    assert result.status == "warn"
    assert result.detail.startswith("6 von 168 Stunden")
    assert check_incomplete_hours(_StubCon((168, 0)), 20261019, 20261024).status == "ok"


def test_facts_vs_staging_fails_and_names_both_counts_per_fact():
    result = check_facts_vs_staging(_StubCon((7436, 7436, 676, 600, 169, 169)), 20251020, 20251026)
    assert result.status == "fail"
    assert result.detail == "erzeugung: Staging 7436, Fakten 7436; last: Staging 676, Fakten 600; preis: Staging 169, Fakten 169"


def test_facts_vs_staging_ok_when_all_counts_match():
    result = check_facts_vs_staging(_StubCon((7436, 7436, 676, 676, 169, 169)), 20251020, 20251026)
    assert result.status == "ok"


class _ValCon:
    """Records the SQL and returns a fixed scalar from fetchval."""

    def __init__(self, value):
        self.value = value
        self.sql = []
        self.params = []

    def execute(self, sql, *params):
        self.sql.append(sql)
        self.params.append(params)
        return self

    def fetchval(self):
        return self.value


def test_freshness_uses_the_newest_non_null_netzlast_value():
    con = _ValCon(datetime(2026, 10, 24, 21, 45))
    result = check_freshness(con, now=datetime(2026, 10, 25, 8, 0))
    assert "netzlast_mwh IS NOT NULL" in con.sql[0]
    assert (result.status, result.detail) == ("ok", "letzter Netzlast-Wert 2026-10-24 21:45 UTC (0 Tage alt)")


def test_freshness_never_reports_a_negative_age_as_fresh():
    result = check_freshness(_ValCon(datetime(2026, 10, 24, 21, 45)), now=datetime(2025, 11, 1))
    assert result.status == "warn"
    assert "2026-10-24 21:45 UTC liegt nach der Referenzzeit 2025-11-01 00:00 UTC" in result.detail


def test_freshness_looks_only_up_to_the_end_of_the_checked_range():
    con = _ValCon(datetime(2025, 10, 26, 22, 45))
    check_freshness(con, now=datetime(2025, 10, 26, 22, 45), to_key=20251026)
    assert "datum_key <= ?" in con.sql[0] and con.params[0] == (20251026,)


def test_freshness_warns_after_45_days():
    assert check_freshness(_ValCon(datetime(2025, 10, 26, 22, 45)), now=datetime(2026, 6, 1)).status == "warn"


class _SeqCon:
    """Returns the given results in order, one per execute() call, via fetchone or fetchall."""

    def __init__(self, *results):
        self._results = list(results)
        self._current = None

    def execute(self, *_args):
        self._current = self._results.pop(0)
        return self

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


def test_capacity_vs_staging_fails_when_the_sums_differ():
    stg = (Decimal("12.500"), 3, Decimal("1.000"), 1, Decimal("300.000"), 1)
    fact = (Decimal("12.500"), 3, Decimal("1.000"), 1, Decimal("0.000"), 0)
    result = check_capacity_vs_staging(_SeqCon(stg, fact), 20251020, 20251026)
    assert result.status == "fail"
    assert result.detail == "staging (12.500, 3, 1.000, 1, 300.000, 1) vs fakten (12.500, 3, 1.000, 1, 0.000, 0)"


def test_capacity_vs_staging_ok_when_the_sums_match_and_on_empty_tables():
    row = (12.5, 3, 1.0, 1, 300.0, 1)
    assert check_capacity_vs_staging(_SeqCon(row, row), 20251020, 20251026).status == "ok"
    empty = (None,) * 6
    assert check_capacity_vs_staging(_SeqCon(empty, empty), 20251020, 20251026).status == "ok"


def test_capacity_plausible_warns_outside_the_bounds_and_names_the_carrier():
    result = check_capacity_plausible(_SeqCon([("Photovoltaik", 30.0), ("Wind Onshore", 60.0)]), 20251020, 20251026)
    assert result.status == "warn"
    assert result.detail == "Photovoltaik 30.0 GW (erwartet 60.0-200.0)"


def test_capacity_plausible_ok_inside_the_bounds_and_warns_without_data():
    rows = [("Photovoltaik", 100.0), ("Wind Onshore", 60.0), ("Kernenergie", 0.0)]
    assert check_capacity_plausible(_SeqCon(rows), 20251020, 20251026).status == "ok"
    result = check_capacity_plausible(_SeqCon([]), 20251020, 20251026)
    assert (result.status, result.detail) == ("warn", "keine Kapazitaetsdaten")


def test_capacity_month_grid_fails_on_one_pair_with_gaps():
    result = check_capacity_month_grid(_ValCon(1), 20251020, 20251026)
    assert (result.status, result.detail) == ("fail", "1 Paare mit Luecken im Monatsraster")
    assert check_capacity_month_grid(_ValCon(0), 20251020, 20251026).status == "ok"


def test_capacity_non_negative_fails_on_negative_bestand():
    assert check_capacity_non_negative(_ValCon(2), 20251020, 20251026).status == "fail"
    assert check_capacity_non_negative(_ValCon(0), 20251020, 20251026).status == "ok"
