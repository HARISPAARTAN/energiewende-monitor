from datetime import UTC, date, datetime

from ewmonitor.timekeys import date_key, local_keys, ms_to_utc, quarterhours_in_day


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
    assert date_key(date(2025, 10, 20)) == 20251020
