"""Which series to fetch, and the download-parse-filter chain for a date range."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from .config import Settings
from .smard import STG_COLUMNS, latest_chunks, parse_chunk_file, select_chunks
from .timekeys import BERLIN, date_key

log = logging.getLogger(__name__)


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


def _local_midnight_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=BERLIN).timestamp() * 1000)


def ingest_range(
    settings: Settings, client, start: date, end: date, regions: Sequence[str] | None = None
) -> pd.DataFrame:
    """Download (or reuse cached) chunks covering [start, end] local days and return staging rows
    for those days.
    """
    start_ms, end_ms = _local_midnight_ms(start), _local_midnight_ms(end) + 24 * 3600 * 1000 - 1
    frames: list[pd.DataFrame] = []
    for spec in series_specs(settings, regions):
        index = client.fetch_index(spec.filter_id, spec.region, spec.resolution)
        latest = latest_chunks(index)
        chunks = select_chunks(index, start_ms, end_ms)
        log.info("%s %s %s: %d chunk(s)", spec.filter_id, spec.region, spec.resolution, len(chunks))
        for ts_ms in chunks:
            path = client.download_chunk(
                spec.filter_id, spec.region, spec.resolution, ts_ms, force=ts_ms in latest
            )
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
