from ewmonitor.checks import (
    CheckResult,
    check_facts_vs_staging,
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
