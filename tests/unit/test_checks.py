from datetime import datetime
from decimal import Decimal

from ewmonitor.checks import (
    PLAUSIBEL_GW,
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
    """Returns the given results in order, one per execute() call, via fetchone, fetchall or fetchval."""

    def __init__(self, *results):
        self._results = list(results)
        self._current = None
        self.sql = []

    def execute(self, sql, *_args):
        self.sql.append(sql)
        self._current = self._results.pop(0)
        return self

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current

    def fetchval(self):
        return self._current


def test_capacity_vs_staging_fails_when_the_sums_differ():
    stg = (Decimal("12.500"), 3, Decimal("1.000"), 1, Decimal("300.000"), 1)
    fact = (Decimal("12.500"), 3, Decimal("1.000"), 1, Decimal("0.000"), 0)
    result = check_capacity_vs_staging(_SeqCon(stg, fact, 1), 20251020, 20251026)
    assert result.status == "fail"
    assert result.detail == ("staging (12.500, 3, 1.000, 1, 300.000, 1) vs fakten (12.500, 3, 1.000, 1, 0.000, 0); "
                             "1 Paare mit abweichendem Endbestand")


def test_capacity_vs_staging_fails_when_a_pair_ends_with_a_different_bestand():
    row = (12.5, 3, 1.0, 1, 300.0, 1)
    con = _SeqCon(row, row, 2)
    result = check_capacity_vs_staging(con, 20251020, 20251026)
    assert result.status == "fail"
    assert result.detail.endswith("; 2 Paare mit abweichendem Endbestand")
    pair_sql = con.sql[2]
    assert "anfangsbestand_mw + s.zubau_mw - s.abgang_mw" in pair_sql and "FULL JOIN" in pair_sql


def test_capacity_vs_staging_ok_when_the_sums_match_and_on_empty_tables():
    row = (12.5, 3, 1.0, 1, 300.0, 1)
    assert check_capacity_vs_staging(_SeqCon(row, row, 0), 20251020, 20251026).status == "ok"
    empty = (None,) * 6
    assert check_capacity_vs_staging(_SeqCon(empty, empty, 0), 20251020, 20251026).status == "ok"


ALL_BOUNDED_OK = [("Photovoltaik", 100.0), ("Wind Onshore", 60.0), ("Wind Offshore", 9.0), ("Biomasse", 9.0),
                  ("Wasserkraft", 5.3), ("Braunkohle", 15.0), ("Steinkohle", 15.0), ("Erdgas", 35.0),
                  ("Pumpspeicher", 9.9), ("Sonstige Konventionelle", 13.9), ("Kernenergie", 0.0)]


def test_capacity_plausible_bounds_every_major_carrier():
    assert {"Wasserkraft", "Sonstige Konventionelle"} <= set(PLAUSIBEL_GW)
    assert {name for name, _ in ALL_BOUNDED_OK} >= set(PLAUSIBEL_GW)


def test_capacity_plausible_warns_outside_the_bounds_and_names_the_carrier():
    rows = [("Photovoltaik", 30.0) if name == "Photovoltaik" else (name, gw) for name, gw in ALL_BOUNDED_OK]
    result = check_capacity_plausible(_SeqCon(rows), 20251020, 20251026)
    assert result.status == "warn"
    assert result.detail == "Photovoltaik 30.0 GW (erwartet 60.0-200.0)"


def test_capacity_plausible_ok_inside_the_bounds_and_warns_without_data():
    result = check_capacity_plausible(_SeqCon(ALL_BOUNDED_OK), 20251020, 20251026)
    assert (result.status, result.detail) == ("ok", "Bestand im erwarteten Bereich")
    result = check_capacity_plausible(_SeqCon([]), 20251020, 20251026)
    assert (result.status, result.detail) == ("warn", "keine Kapazitaetsdaten")


def test_capacity_plausible_warns_when_a_bounded_carrier_is_missing():
    rows = [(name, gw) for name, gw in ALL_BOUNDED_OK if name not in ("Photovoltaik", "Erdgas")]  # no Solar, no Verbrennung gas
    result = check_capacity_plausible(_SeqCon(rows), 20251020, 20251026)
    assert result.status == "warn"
    assert result.detail == "Photovoltaik 0.0 GW (erwartet 60.0-200.0); Erdgas 0.0 GW (erwartet 20.0-50.0)"


def test_capacity_month_grid_fails_on_gaps_and_on_pairs_ending_before_the_last_month():
    result = check_capacity_month_grid(_StubCon((1, 0)), 20251020, 20251026)
    assert (result.status, result.detail) == (
        "fail", "1 Paare mit Luecken im Monatsraster, 0 Paare enden vor dem letzten Monat")
    result = check_capacity_month_grid(_StubCon((0, 2)), 20251020, 20251026)
    assert (result.status, result.detail) == (
        "fail", "0 Paare mit Luecken im Monatsraster, 2 Paare enden vor dem letzten Monat")
    assert check_capacity_month_grid(_StubCon((0, 0)), 20251020, 20251026).status == "ok"
    assert check_capacity_month_grid(_StubCon((None, None)), 20251020, 20251026).status == "ok"  # empty fact


def test_capacity_month_grid_compares_each_pair_with_the_newest_fact_month():
    con = _SeqCon((0, 0))
    check_capacity_month_grid(con, 20251020, 20251026)
    assert "MAX(datum_key) AS datum_key FROM dw.fact_kapazitaet" in con.sql[0] and "soll.bis < letzter.datum_key" in con.sql[0]


def test_capacity_non_negative_fails_on_negative_bestand_with_one_rounding_unit_of_tolerance():
    con = _ValCon(2)
    assert check_capacity_non_negative(con, 20251020, 20251026).status == "fail"
    assert "bestand_mw < -0.001" in con.sql[0]
    assert check_capacity_non_negative(_ValCon(0), 20251020, 20251026).status == "ok"
