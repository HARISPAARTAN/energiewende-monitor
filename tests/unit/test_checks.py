from datetime import datetime

from ewmonitor.checks import (
    CheckResult,
    check_facts_vs_staging,
    check_hourly_aggregate,
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


def test_hourly_aggregate_warns_on_hour_without_values():
    result = check_hourly_aggregate(_StubCon((datetime(2025, 10, 20), None, 12.5)), 20251020, 20251026)
    assert (result.status, result.detail) == ("warn", "Stunde ohne Werte")


def test_facts_vs_staging_fails_and_names_both_counts_per_fact():
    result = check_facts_vs_staging(_StubCon((7436, 7436, 676, 600, 169, 169)), 20251020, 20251026)
    assert result.status == "fail"
    assert result.detail == "erzeugung: Staging 7436, Fakten 7436; last: Staging 676, Fakten 600; preis: Staging 169, Fakten 169"


def test_facts_vs_staging_ok_when_all_counts_match():
    result = check_facts_vs_staging(_StubCon((7436, 7436, 676, 676, 169, 169)), 20251020, 20251026)
    assert result.status == "ok"
