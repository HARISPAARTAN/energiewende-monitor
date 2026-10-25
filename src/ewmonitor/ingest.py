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
from .timekeys import date_key, local_midnight_ms

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
    """
    start_ms, end_ms = local_midnight_ms(start), local_midnight_ms(end + timedelta(days=1)) - 1
    if now_ms is None:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
    refresh_from_ms = now_ms - refresh_days * DAY_MS
    frames: list[pd.DataFrame] = []
    for spec in series_specs(settings, regions):
        index = client.fetch_index(spec.filter_id, spec.region, spec.resolution)
        latest = latest_chunks(index)
        chunks = select_chunks(index, start_ms, end_ms)
        log.info("%s %s %s: %d chunk(s)", spec.filter_id, spec.region, spec.resolution, len(chunks))
        for ts_ms in chunks:
            force = ts_ms in latest or chunk_end_ms(ts_ms) >= refresh_from_ms
            path = client.download_chunk(spec.filter_id, spec.region, spec.resolution, ts_ms, force=force)
            frames.append(parse_chunk_file(path))
    if not frames:
        return pd.DataFrame(columns=STG_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    mask = (df["datum_key"] >= date_key(start)) & (df["datum_key"] <= date_key(end))
    return df[mask].reset_index(drop=True)


def ingest_fixtures(fixtures_dir: Path) -> pd.DataFrame:
    """All chunk files under data/fixtures/smard, for CI and local smoke runs without network."""
    files = sorted((Path(fixtures_dir) / "smard").glob("*.json"))
    frames = [parse_chunk_file(p) for p in files]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=STG_COLUMNS)
