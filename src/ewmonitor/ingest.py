"""Which series to fetch, and the download-parse-filter chain for a date range."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from .config import Settings
from .smard import STG_COLUMNS, chunk_end_ms, latest_chunks, parse_chunk_file, select_chunks
from .timekeys import BERLIN, date_key, local_midnight_ms, ms_to_utc

log = logging.getLogger(__name__)

DAY_MS = 86_400_000


class SeriesSpec(NamedTuple):
    filter_id: int
    region: str
    resolution: str


def series_specs(settings: Settings, regions: Sequence[str] | None = None) -> list[SeriesSpec]:
    """Quarter-hour generation and consumption series per region, plus the hourly price per market area."""
    specs: list[SeriesSpec] = []
    for region in regions or settings.regions:
        specs.extend(SeriesSpec(f, region, "quarterhour") for f in settings.smard.quarterhour_filters)
        if region in settings.smard.price_regions:
            specs.append(SeriesSpec(settings.smard.price, region, "hour"))
    return specs


def ingest_range(
    settings: Settings,
    client,
    start: date,
    end: date,
    regions: Sequence[str] | None = None,
    refresh_days: int = 60,
    now_ms: int | None = None,
) -> pd.DataFrame:
    """Download (or reuse cached) chunks covering [start, end] local days and return staging rows
    for those days.

    A chunk is re-downloaded (force) when it is one of the two newest, or when it ends within the last
    `refresh_days` days: SMARD republishes complete weekly chunks weeks after the fact.

    Logs one INFO line per downloaded chunk (series, chunk start, rows) and a summary at the end.
    """
    start_ms, end_ms = local_midnight_ms(start), local_midnight_ms(end + timedelta(days=1)) - 1
    if now_ms is None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
    refresh_from_ms = now_ms - refresh_days * DAY_MS
    frames: list[pd.DataFrame] = []
    specs = series_specs(settings, regions)
    downloaded = from_cache = 0
    for spec in specs:
        index = client.fetch_index(spec.filter_id, spec.region, spec.resolution)
        latest = latest_chunks(index)
        chunks = select_chunks(index, start_ms, end_ms)
        log.debug("%s %s %s: %d chunk(s)", spec.filter_id, spec.region, spec.resolution, len(chunks))
        for ts_ms in chunks:
            force = ts_ms in latest or chunk_end_ms(ts_ms) >= refresh_from_ms
            cached = not force and client.is_cached(spec.filter_id, spec.region, spec.resolution, ts_ms)
            path = client.download_chunk(spec.filter_id, spec.region, spec.resolution, ts_ms, force=force)
            frame = parse_chunk_file(path)
            frames.append(frame)
            chunk_start = ms_to_utc(ts_ms).astimezone(BERLIN).date()
            if cached:
                from_cache += 1
                log.debug("chunk %s %s %s %s: %d rows (cache)", spec.filter_id, spec.region, spec.resolution,
                          chunk_start, len(frame))
            else:
                downloaded += 1
                log.info("chunk %s %s %s %s: %d rows downloaded", spec.filter_id, spec.region, spec.resolution,
                         chunk_start, len(frame))
    if frames:
        df = pd.concat(frames, ignore_index=True)
        mask = (df["datum_key"] >= date_key(start)) & (df["datum_key"] <= date_key(end))
        df = df[mask].reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=STG_COLUMNS)
    log.info("ingest: %d series, %d chunks downloaded, %d chunks from cache, %d rows staged",
             len(specs), downloaded, from_cache, len(df))
    return df


def ingest_fixtures(fixtures_dir: Path) -> pd.DataFrame:
    """All chunk files under data/fixtures/smard, for CI and local smoke runs without network."""
    files = sorted((Path(fixtures_dir) / "smard").glob("*.json"))
    frames = [parse_chunk_file(p) for p in files]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=STG_COLUMNS)
