from ewmonitor.checks import CheckResult, format_results, has_failures


def test_has_failures_only_for_fail_status():
    ok = [CheckResult("a", "ok", ""), CheckResult("b", "warn", "x")]
    assert has_failures(ok) is False
    assert has_failures(ok + [CheckResult("c", "fail", "y")]) is True


def test_format_results_is_a_table():
    text = format_results([CheckResult("viertelstunden_pro_tag", "ok", "0 Abweichungen")])
    assert "viertelstunden_pro_tag" in text and "ok" in text and "0 Abweichungen" in text
