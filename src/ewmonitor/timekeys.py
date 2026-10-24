"""Europe/Berlin local keys for UTC instants. All daylight-saving handling lives here."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def ms_to_utc(ms: int) -> datetime:
    """Unix milliseconds to a timezone-aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def date_key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def local_keys(ts_utc: datetime) -> tuple[int, int]:
    """Return (datum_key yyyymmdd, zeit_key 0..95) of a UTC instant in Europe/Berlin wall-clock time.

    On the autumn transition day two UTC instants share one wall-clock quarter-hour; that is intended,
    the fact tables are keyed by ts_utc, the zeit_key only describes the wall clock.
    """
    if ts_utc.tzinfo is None:
        ts_utc = ts_utc.replace(tzinfo=UTC)
    local = ts_utc.astimezone(BERLIN)
    return date_key(local.date()), local.hour * 4 + local.minute // 15


def quarterhours_in_day(day: date) -> int:
    """Quarter-hours of a local day: 96 normally, 92 on the spring transition, 100 on the autumn one."""
    start = datetime(day.year, day.month, day.day, tzinfo=BERLIN).astimezone(UTC)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=BERLIN).astimezone(UTC)
    return int((end - start).total_seconds() // 900)
