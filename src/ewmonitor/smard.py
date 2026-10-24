"""SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0): weekly JSON chunks parsed into staging rows."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

from .timekeys import local_keys, ms_to_utc

STG_COLUMNS = ["filter_id", "region", "resolution", "ts_utc", "value", "datum_key", "zeit_key"]
WEEK_MS = 7 * 24 * 3600 * 1000


def chunk_name(filter_id: int, region: str, resolution: str, ts_ms: int) -> str:
    return f"{filter_id}_{region}_{resolution}_{ts_ms}.json"


def parse_chunk(payload: dict, filter_id: int, region: str, resolution: str) -> pd.DataFrame:
    """One chunk payload ({"meta_data": ..., "series": [[ms, value|null], ...]}) to a staging frame."""
    rows = []
    for ts_ms, value in payload["series"]:
        ts = ms_to_utc(int(ts_ms))
        datum_key, zeit_key = local_keys(ts)
        rows.append((filter_id, region, resolution, ts.replace(tzinfo=None), value, datum_key, zeit_key))
    df = pd.DataFrame(rows, columns=STG_COLUMNS)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    df["ts_utc"] = pd.to_datetime(df["ts_utc"]).astype("datetime64[ns]")
    return df


def parse_chunk_file(path: Path) -> pd.DataFrame:
    """Parse a cached chunk; filter, region and resolution come from the file name."""
    filter_id, region, resolution, _ts = path.stem.split("_")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_chunk(payload, int(filter_id), region, resolution)


log = logging.getLogger(__name__)


def select_chunks(timestamps: list[int], start_ms: int, end_ms: int) -> list[int]:
    """Chunk start timestamps whose week overlaps the closed range [start_ms, end_ms]."""
    return [ts for ts in sorted(timestamps) if ts + WEEK_MS > start_ms and ts <= end_ms]


def latest_chunks(timestamps: list[int], n: int = 2) -> set[int]:
    """The newest chunks are still being filled by SMARD and are always re-downloaded."""
    return set(sorted(timestamps)[-n:])


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
        path = self.chunk_path(filter_id, region, resolution, ts_ms)
        if path.exists() and not force:
            return path
        url = f"{self.base_url}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{ts_ms}.json"
        payload = self._get_json(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _get_json(self, url: str) -> dict:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout_s)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                log.warning("GET %s failed (attempt %d/%d): %s", url, attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(self.backoff_s * attempt)
        raise RuntimeError(f"GET {url} failed after {self.retries} attempts") from last_exc
