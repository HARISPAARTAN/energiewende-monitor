from datetime import datetime

from ewmonitor.checks import (
    CheckResult,
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
