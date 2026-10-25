import json
import os
from datetime import date
from pathlib import Path

import pytest
import requests
import responses

from ewmonitor.smard import WEEK_MS, SmardClient, chunk_end_ms, latest_chunks, select_chunks
from ewmonitor.timekeys import local_midnight_ms

BASE = "https://smard.test/app/chart_data"
MINUTE_MS = 60 * 1000
HOUR_MS = 60 * MINUTE_MS
AUTUMN_TS = 1760911200000  # chunk starting Monday 2025-10-20 00:00 local; 169 hours long
# The autumn chunk ends at 2025-10-27 00:00 local and counts as complete one publication-lag day later.
AUTUMN_COMPLETE_MS = local_midnight_ms(date(2025, 10, 28))


def test_select_chunks_keeps_weeks_overlapping_the_range():
    ts = [0, WEEK_MS, 2 * WEEK_MS, 3 * WEEK_MS]
    assert select_chunks(ts, start_ms=WEEK_MS + 5, end_ms=2 * WEEK_MS + 5) == [WEEK_MS, 2 * WEEK_MS]
    assert select_chunks(ts, start_ms=0, end_ms=0) == [0]
    assert select_chunks([], 0, 10) == []


def test_chunk_end_is_local_midnight_seven_days_later():
    assert chunk_end_ms(AUTUMN_TS) == AUTUMN_TS + 169 * HOUR_MS
    spring = local_midnight_ms(date(2026, 3, 23))
    assert chunk_end_ms(spring) == spring + 167 * HOUR_MS
    winter = local_midnight_ms(date(2026, 1, 5))
    assert chunk_end_ms(winter) == winter + WEEK_MS


def test_select_chunks_uses_exact_bounds_in_the_spring_week():
    first, second = local_midnight_ms(date(2026, 3, 23)), local_midnight_ms(date(2026, 3, 30))
    assert second - first == 167 * HOUR_MS  # clocks go forward on Sunday 2026-03-29
    ts = [first, second]
    assert select_chunks(ts, first, second - 1) == [first]  # 2026-03-23..2026-03-29
    assert select_chunks(ts, second, local_midnight_ms(date(2026, 4, 6)) - 1) == [second]  # 03-30..04-05


def test_latest_chunks_are_the_two_newest():
    assert latest_chunks([3, 1, 2]) == {2, 3}
    assert latest_chunks([7]) == {7}


@responses.activate
def test_download_chunk_uses_cache(tmp_path):
    url = f"{BASE}/410/DE-LU/410_DE-LU_quarterhour_1000.json"
    responses.get(url, json={"meta_data": {}, "series": [[1000, 1.0]]})
    client = SmardClient(BASE, tmp_path, retries=1, backoff_s=0)
    first = client.download_chunk(410, "DE-LU", "quarterhour", 1000)
    second = client.download_chunk(410, "DE-LU", "quarterhour", 1000)
    assert first == second == tmp_path / "410_DE-LU_quarterhour_1000.json"
    assert len(responses.calls) == 1
    assert json.loads(first.read_text(encoding="utf-8"))["series"] == [[1000, 1.0]]


@responses.activate
def test_download_chunk_force_refetches(tmp_path):
    url = f"{BASE}/410/DE-LU/410_DE-LU_quarterhour_1000.json"
    responses.get(url, json={"meta_data": {}, "series": [[1000, 1.0]]})
    responses.get(url, json={"meta_data": {}, "series": [[1000, 2.0]]})
    client = SmardClient(BASE, tmp_path, retries=1, backoff_s=0)
    client.download_chunk(410, "DE-LU", "quarterhour", 1000)
    path = client.download_chunk(410, "DE-LU", "quarterhour", 1000, force=True)
    assert len(responses.calls) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["series"] == [[1000, 2.0]]


@responses.activate
def test_fetch_index_retries_then_succeeds(tmp_path):
    url = f"{BASE}/410/DE-LU/index_quarterhour.json"
    responses.get(url, status=500)
    responses.get(url, json={"timestamps": [1, 2]})
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    assert client.fetch_index(410, "DE-LU", "quarterhour") == [1, 2]
    assert len(responses.calls) == 2


@responses.activate
def test_fetch_index_gives_up_after_retries(tmp_path):
    url = f"{BASE}/410/DE-LU/index_quarterhour.json"
    for _ in range(3):
        responses.get(url, status=503)
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        client.fetch_index(410, "DE-LU", "quarterhour")
    assert len(responses.calls) == 3


def _cache(path, value, mtime_ms):
    """Write a cached chunk file for AUTUMN_TS with the given modification time."""
    path.write_text(json.dumps({"meta_data": {}, "series": [[AUTUMN_TS, value]]}), encoding="utf-8")
    os.utime(path, ns=(mtime_ms * 1_000_000, mtime_ms * 1_000_000))


@responses.activate
def test_download_chunk_refetches_a_file_cached_before_the_chunk_was_complete(tmp_path):
    url = f"{BASE}/410/DE-LU/410_DE-LU_quarterhour_{AUTUMN_TS}.json"
    responses.get(url, json={"meta_data": {}, "series": [[AUTUMN_TS, 2.0]]})
    client = SmardClient(BASE, tmp_path, retries=1, backoff_s=0)
    path = client.chunk_path(410, "DE-LU", "quarterhour", AUTUMN_TS)
    _cache(path, 1.0, AUTUMN_COMPLETE_MS - 30 * MINUTE_MS)  # later than a naive start + 168 h + lag
    assert client.download_chunk(410, "DE-LU", "quarterhour", AUTUMN_TS) == path
    assert len(responses.calls) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["series"] == [[AUTUMN_TS, 2.0]]


@responses.activate
def test_download_chunk_reuses_a_file_cached_after_the_chunk_was_complete(tmp_path):
    client = SmardClient(BASE, tmp_path, retries=1, backoff_s=0)
    path = client.chunk_path(410, "DE-LU", "quarterhour", AUTUMN_TS)
    _cache(path, 1.0, AUTUMN_COMPLETE_MS + 30 * MINUTE_MS)
    assert client.download_chunk(410, "DE-LU", "quarterhour", AUTUMN_TS) == path
    assert len(responses.calls) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["series"] == [[AUTUMN_TS, 1.0]]


@responses.activate
def test_download_chunk_interrupted_write_keeps_the_cached_file(tmp_path, monkeypatch):
    url = f"{BASE}/410/DE-LU/410_DE-LU_quarterhour_1000.json"
    responses.get(url, json={"meta_data": {}, "series": [[1000, 2.0]]})
    client = SmardClient(BASE, tmp_path, retries=1, backoff_s=0)
    path = client.chunk_path(410, "DE-LU", "quarterhour", 1000)
    path.write_text(json.dumps({"meta_data": {}, "series": [[1000, 1.0]]}), encoding="utf-8")
    write_text = Path.write_text

    def write_half_then_fail(self, data, *args, **kwargs):
        write_text(self, data[: len(data) // 2], *args, **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", write_half_then_fail)
    with pytest.raises(OSError, match="disk full"):
        client.download_chunk(410, "DE-LU", "quarterhour", 1000, force=True)
    assert json.loads(path.read_text(encoding="utf-8"))["series"] == [[1000, 1.0]]
    assert [p.name for p in tmp_path.glob("*.json")] == [path.name]


def test_client_needs_at_least_one_attempt(tmp_path):
    with pytest.raises(ValueError, match="retries"):
        SmardClient(BASE, tmp_path, retries=0)


@responses.activate
def test_fetch_index_retries_a_connection_error(tmp_path):
    url = f"{BASE}/410/DE-LU/index_quarterhour.json"
    responses.get(url, body=requests.ConnectionError("connection reset"))
    responses.get(url, json={"timestamps": [1, 2]})
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    assert client.fetch_index(410, "DE-LU", "quarterhour") == [1, 2]
    assert len(responses.calls) == 2


@responses.activate
def test_fetch_index_retries_too_many_requests(tmp_path):
    url = f"{BASE}/410/DE-LU/index_quarterhour.json"
    responses.get(url, status=429)
    responses.get(url, json={"timestamps": [1, 2]})
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    assert client.fetch_index(410, "DE-LU", "quarterhour") == [1, 2]
    assert len(responses.calls) == 2


@responses.activate
def test_download_chunk_retries_an_invalid_json_body(tmp_path):
    url = f"{BASE}/410/DE-LU/410_DE-LU_quarterhour_1000.json"
    responses.get(url, body='{"meta_data": {}, "series": [[1000, 1.')  # truncated body
    responses.get(url, json={"meta_data": {}, "series": [[1000, 1.0]]})
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    path = client.download_chunk(410, "DE-LU", "quarterhour", 1000)
    assert len(responses.calls) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["series"] == [[1000, 1.0]]


@responses.activate
def test_fetch_index_does_not_retry_a_404(tmp_path):
    url = f"{BASE}/410/DE-LU/index_quarterhour.json"
    responses.get(url, status=404)
    client = SmardClient(BASE, tmp_path, retries=3, backoff_s=0)
    with pytest.raises(RuntimeError, match="failed after 1 attempts") as excinfo:
        client.fetch_index(410, "DE-LU", "quarterhour")
    assert isinstance(excinfo.value.__cause__, requests.HTTPError)
    assert len(responses.calls) == 1
