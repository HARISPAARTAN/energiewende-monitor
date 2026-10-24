import json

import pytest
import responses

from ewmonitor.smard import WEEK_MS, SmardClient, latest_chunks, select_chunks

BASE = "https://smard.test/app/chart_data"


def test_select_chunks_keeps_weeks_overlapping_the_range():
    ts = [0, WEEK_MS, 2 * WEEK_MS, 3 * WEEK_MS]
    assert select_chunks(ts, start_ms=WEEK_MS + 5, end_ms=2 * WEEK_MS + 5) == [WEEK_MS, 2 * WEEK_MS]
    assert select_chunks(ts, start_ms=0, end_ms=0) == [0]
    assert select_chunks([], 0, 10) == []


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
