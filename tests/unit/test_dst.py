from collections import Counter
from datetime import UTC, date, datetime, timedelta

from ewmonitor.timekeys import BERLIN, date_key, local_keys, ms_to_utc, quarterhours_in_day


def test_quarterhours_normal_day():
    assert quarterhours_in_day(date(2025, 6, 1)) == 96


def test_quarterhours_spring_transition():
    assert quarterhours_in_day(date(2025, 3, 30)) == 92


def test_quarterhours_autumn_transition():
    assert quarterhours_in_day(date(2025, 10, 26)) == 100


def test_local_keys_winter_crosses_midnight():
    assert local_keys(datetime(2025, 1, 15, 23, 30, tzinfo=UTC)) == (20250116, 2)


def test_local_keys_summer_offset_two_hours():
    assert local_keys(datetime(2025, 7, 1, 22, 0, tzinfo=UTC)) == (20250702, 0)


def test_local_keys_autumn_repeated_wall_clock_hour():
    first = local_keys(datetime(2025, 10, 26, 0, 30, tzinfo=UTC))  # 02:30 CEST
    second = local_keys(datetime(2025, 10, 26, 1, 30, tzinfo=UTC))  # 02:30 CET
    assert first == second == (20251026, 10)


def test_local_keys_naive_input_is_utc():
    assert local_keys(datetime(2025, 1, 15, 23, 30)) == (20250116, 2)


def test_ms_to_utc_and_date_key():
    ts = ms_to_utc(1760911200000)
    assert ts == datetime(2025, 10, 19, 22, 0, tzinfo=UTC)
    assert ts.tzinfo is UTC
    assert date_key(date(2025, 10, 20)) == 20251020


def _day_keys(day: date) -> list[tuple[datetime, int]]:
    """(ts_utc, zeit_key) of every UTC quarter-hour that falls on the local day."""
    start = datetime(day.year, day.month, day.day, tzinfo=BERLIN).astimezone(UTC)
    out, ts = [], start
    while True:
        datum_key, zeit_key = local_keys(ts)
        if datum_key != date_key(day):
            return out
        out.append((ts, zeit_key))
        ts += timedelta(minutes=15)


def test_spring_transition_day_has_no_local_two_oclock_keys():
    keys = _day_keys(date(2025, 3, 30))
    zeit_keys = [k for _, k in keys]
    assert len(keys) == 92
    assert not set(range(8, 12)) & set(zeit_keys)  # 02:00-02:45 local does not exist
    assert zeit_keys[7:9] == [7, 12]  # 01:45 CET is followed by 03:00 CEST
    assert len(set(zeit_keys)) == 92


def test_autumn_transition_day_repeats_the_two_oclock_keys_with_distinct_utc():
    keys = _day_keys(date(2025, 10, 26))
    assert len(keys) == 100
    counts = Counter(k for _, k in keys)
    assert {k: counts[k] for k in range(8, 12)} == {8: 2, 9: 2, 10: 2, 11: 2}
    assert all(n == 1 for k, n in counts.items() if k not in range(8, 12))
    for k in range(8, 12):
        first, second = sorted(ts for ts, zk in keys if zk == k)
        assert second - first == timedelta(hours=1)  # 02:xx CEST, then 02:xx CET
