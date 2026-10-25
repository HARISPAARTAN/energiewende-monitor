"""SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0): weekly JSON chunks parsed into staging rows.

Parsing: `parse_chunk` and `parse_chunk_file` turn one chunk ({"meta_data": ..., "series": [[ms, value|null],
...]}) into staging rows with a naive UTC timestamp and Europe/Berlin date and quarter-hour keys.

Selection: a chunk starts at local midnight on a Monday and ends at local midnight seven calendar days later
(`chunk_end_ms`), so it spans 167 hours in the spring daylight-saving week and 169 in the autumn one.
`select_chunks` picks the chunks of an index that overlap a time range, `latest_chunks` names the newest
ones, which SMARD is still filling.

Client: `SmardClient` fetches indexes and chunks over HTTP and retries transient failures. It caches each
chunk as a JSON file, writes that file atomically and downloads it again while it may be incomplete.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

from .timekeys import BERLIN, local_keys, local_midnight_ms, ms_to_utc

log = logging.getLogger(__name__)

STG_COLUMNS = ["filter_id", "region", "resolution", "ts_utc", "value", "datum_key", "zeit_key"]
WEEK_MS = 7 * 24 * 3600 * 1000  # nominal chunk length; daylight-saving weeks differ, see chunk_end_ms
PUBLICATION_LAG_MS = 24 * 3600 * 1000  # a chunk is complete this long after its end, see download_chunk


def chunk_name(filter_id: int, region: str, resolution: str, ts_ms: int) -> str:
    return f"{filter_id}_{region}_{resolution}_{ts_ms}.json"


def chunk_end_ms(ts_ms: int) -> int:
    """Exclusive end of the chunk starting at `ts_ms`: local midnight seven calendar days later.

    SMARD chunks start at Europe/Berlin local midnight on a Monday, so a chunk spans 168 hours, 167 in the
    spring daylight-saving week and 169 in the autumn one.
    """
    start_day = ms_to_utc(ts_ms).astimezone(BERLIN).date()
    return local_midnight_ms(start_day + timedelta(days=7))


def parse_chunk(payload: dict, filter_id: int, region: str, resolution: str) -> pd.DataFrame:
    """One chunk payload ({"meta_data": ..., "series": [[ms, value|null], ...]}) to a staging frame.

    Nulls become NaN; any other value that is not numeric raises ValueError.
    """
    rows = []
    for ts_ms, value in payload["series"]:
        ts = ms_to_utc(int(ts_ms))
        datum_key, zeit_key = local_keys(ts)
        rows.append((filter_id, region, resolution, ts.replace(tzinfo=None), value, datum_key, zeit_key))
    df = pd.DataFrame(rows, columns=STG_COLUMNS)
    df["value"] = pd.to_numeric(df["value"]).astype("float64")
    df["ts_utc"] = pd.to_datetime(df["ts_utc"]).astype("datetime64[ns]")
    return df


def parse_chunk_file(path: Path) -> pd.DataFrame:
    """Parse a cached chunk; filter, region and resolution come from the file name."""
    filter_id, region, resolution, _ts = path.stem.split("_")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(f"{path}: {exc.msg}", exc.doc, exc.pos) from exc
    return parse_chunk(payload, int(filter_id), region, resolution)


def select_chunks(timestamps: list[int], start_ms: int, end_ms: int) -> list[int]:
    """Chunk start timestamps whose chunk overlaps the closed range [start_ms, end_ms].

    A chunk covers [ts, chunk_end_ms(ts)), so daylight-saving weeks are matched exactly.
    """
    return [ts for ts in sorted(timestamps) if ts <= end_ms and chunk_end_ms(ts) > start_ms]


def latest_chunks(timestamps: list[int], n: int = 2) -> set[int]:
    """The newest chunks are still being filled by SMARD and are always re-downloaded."""
    return set(sorted(timestamps)[-n:])


def _is_transient(exc: requests.RequestException) -> bool:
    """Connection errors, timeouts, HTTP 429 and 5xx and invalid JSON bodies are worth another attempt."""
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status == 429 or 500 <= status <= 599
    return isinstance(exc, (requests.ConnectionError, requests.Timeout, requests.JSONDecodeError))


class SmardClient:
    def __init__(
        self,
        base_url: str,
        cache_dir: Path,
        session: requests.Session | None = None,
        retries: int = 3,
        backoff_s: float = 2.0,
        timeout_s: float = 60.0,
    ) -> None:
        if retries < 1:
            raise ValueError(f"retries must be at least 1, got {retries}")
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()
        self.retries = retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s

    def fetch_index(self, filter_id: int, region: str, resolution: str) -> list[int]:
        url = f"{self.base_url}/{filter_id}/{region}/index_{resolution}.json"
        return [int(ts) for ts in self._get_json(url)["timestamps"]]

    def chunk_path(self, filter_id: int, region: str, resolution: str, ts_ms: int) -> Path:
        return self.cache_dir / chunk_name(filter_id, region, resolution, ts_ms)

    def download_chunk(
        self, filter_id: int, region: str, resolution: str, ts_ms: int, force: bool = False
    ) -> Path:
        """Return the cache file of a chunk, downloading the chunk first when needed.

        A cached file is reused unless `force` is set or the file is stale, that is, last modified before
        the chunk was complete: local midnight seven days after the chunk start (`chunk_end_ms`) plus
        PUBLICATION_LAG_MS. A chunk cached while SMARD was still filling its week is therefore downloaded
        again on the next run, however much later that run is. The payload goes to a sibling ".part" file
        that then replaces the cache file, so an interrupted write never leaves a truncated chunk behind.
        """
        path = self.chunk_path(filter_id, region, resolution, ts_ms)
        complete_ms = chunk_end_ms(ts_ms) + PUBLICATION_LAG_MS
        if not force and path.exists() and path.stat().st_mtime_ns >= complete_ms * 1_000_000:
            return path
        url = f"{self.base_url}/{filter_id}/{region}/{chunk_name(filter_id, region, resolution, ts_ms)}"
        payload = self._get_json(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text(json.dumps(payload), encoding="utf-8")
        part.replace(path)
        return path

    def _get_json(self, url: str) -> dict:
        """GET a JSON document, retrying transient failures (`_is_transient`) with a linear backoff.

        Any other failure, or a failure on the last attempt, raises RuntimeError with the cause attached.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(url, timeout=self.timeout_s)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt >= self.retries or not _is_transient(exc):
                    raise RuntimeError(f"GET {url} failed after {attempt} attempts") from exc
                log.warning("GET %s failed (attempt %d/%d), retrying: %s", url, attempt, self.retries, exc)
                time.sleep(self.backoff_s * attempt)
