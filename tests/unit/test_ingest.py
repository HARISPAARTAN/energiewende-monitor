import json
from datetime import date
from pathlib import Path

from ewmonitor.config import load_settings
from ewmonitor.ingest import SeriesSpec, ingest_fixtures, ingest_range, series_specs
from ewmonitor.smard import STG_COLUMNS, chunk_name
from ewmonitor.timekeys import local_midnight_ms

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures" / "smard"
WEEK_TS = 1760911200000


class StubClient:
    def __init__(self, index=(WEEK_TS - 7 * 86400000, WEEK_TS)):
        self.index = list(index)
        self.calls = []

    def fetch_index(self, filter_id, region, resolution):
        return [] if filter_id == 1224 else list(self.index)

    def download_chunk(self, filter_id, region, resolution, ts_ms, force=False):
        self.calls.append((filter_id, region, resolution, ts_ms, force))
        return FIXTURES / f"{filter_id}_{region}_{resolution}_{ts_ms}.json"


class SyntheticClient(StubClient):
    """Writes a one-value chunk on demand, for weeks that have no fixture files."""

    def __init__(self, index, cache_dir):
        super().__init__(index)
        self.cache_dir = cache_dir

    def download_chunk(self, filter_id, region, resolution, ts_ms, force=False):
        self.calls.append((filter_id, region, resolution, ts_ms, force))
        path = self.cache_dir / chunk_name(filter_id, region, resolution, ts_ms)
        path.write_text(json.dumps({"meta_data": {}, "series": [[ts_ms, 1.0]]}), encoding="utf-8")
        return path


def test_series_specs_quarterhour_plus_price_for_market_area():
    s = load_settings(ROOT)
    specs = series_specs(s)
    assert len(specs) == 16
    assert specs[0] == SeriesSpec(1223, "DE-LU", "quarterhour")
    assert specs[-1] == SeriesSpec(4169, "DE-LU", "hour")
    assert series_specs(s, ["TenneT"]) == [
        SeriesSpec(f, "TenneT", "quarterhour") for f in s.smard.quarterhour_filters
    ]


def test_ingest_range_downloads_only_overlapping_chunks_and_filters_days():
    s = load_settings(ROOT)
    client = StubClient()
    df = ingest_range(s, client, date(2025, 10, 20), date(2025, 10, 25))
    assert list(df.columns) == STG_COLUMNS
    assert all(call[3] == WEEK_TS for call in client.calls)  # the earlier week does not overlap the range
    assert all(call[4] is True for call in client.calls)  # WEEK_TS is one of the two latest chunks
    assert len(client.calls) == 15  # 14 quarter-hour series + price; 1224 has no chunk
    assert sorted(df["datum_key"].unique()) == [20251020 + i for i in range(6)]
    assert 20251026 not in set(df["datum_key"])


def test_ingest_range_full_week_row_count():
    s = load_settings(ROOT)
    df = ingest_range(s, StubClient(), date(2025, 10, 20), date(2025, 10, 26))
    assert len(df) == 14 * 676 + 169


def test_ingest_range_mid_week_start_keeps_only_the_requested_days():
    s = load_settings(ROOT)
    df = ingest_range(s, StubClient(), date(2025, 10, 22), date(2025, 10, 26))
    assert len(df) == 14 * 484 + 121  # 4 x 96 + 100 quarter-hours and 4 x 24 + 25 hours
    assert df["datum_key"].min() == 20251022


def test_ingest_range_does_not_force_chunks_outside_the_newest_two():
    s = load_settings(ROOT)
    later = [local_midnight_ms(date(2025, 10, 27)), local_midnight_ms(date(2025, 11, 3))]
    client = StubClient([WEEK_TS, *later])
    ingest_range(s, client, date(2025, 10, 20), date(2025, 10, 26))
    assert len(client.calls) == 15
    assert all(call[3] == WEEK_TS and call[4] is False for call in client.calls)


def test_ingest_range_spring_week_selects_only_its_own_chunk(tmp_path):
    s = load_settings(ROOT)
    first, second = local_midnight_ms(date(2026, 3, 23)), local_midnight_ms(date(2026, 3, 30))
    client = SyntheticClient([first, second], tmp_path)
    df = ingest_range(s, client, date(2026, 3, 23), date(2026, 3, 29))  # ends on the 23-hour Sunday
    assert {call[3] for call in client.calls} == {first}
    assert df["datum_key"].unique().tolist() == [20260323]
    client = SyntheticClient([first, second], tmp_path)
    ingest_range(s, client, date(2026, 3, 30), date(2026, 4, 5))
    assert {call[3] for call in client.calls} == {second}


def test_ingest_fixtures_reads_every_file():
    df = ingest_fixtures(ROOT / "data" / "fixtures")
    assert len(df) == 14 * 676 + 169
    assert df["filter_id"].nunique() == 15
