"""Staging writes (replace per series and range) and set-based fact loads (replace per day range)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .db import bulk_insert, df_rows, run_sql_file
from .smard import STG_COLUMNS

log = logging.getLogger(__name__)


def key_range(df: pd.DataFrame) -> tuple[int, int]:
    return int(df["datum_key"].min()), int(df["datum_key"].max())


def write_stg(con, df: pd.DataFrame) -> int:
    """Delete the covered timestamp range of every (filter, region, resolution) in df, then insert df."""
    if df.empty:
        return 0
    cur = con.cursor()
    for (filter_id, region, resolution), group in df.groupby(["filter_id", "region", "resolution"]):
        cur.execute(
            "DELETE FROM stg.smard_series WHERE filter_id = ? AND region = ? AND resolution = ? AND ts_utc BETWEEN ? AND ?",
            int(filter_id), str(region), str(resolution),
            group["ts_utc"].min().to_pydatetime(), group["ts_utc"].max().to_pydatetime(),
        )
    con.commit()
    return bulk_insert(con, "stg.smard_series", STG_COLUMNS, df_rows(df, STG_COLUMNS))


def load_facts(con, sql_dir: Path, from_key: int, to_key: int) -> None:
    """Run every sql/load/*.sql in name order; each replaces its fact rows for datum_key in [from_key, to_key]."""
    for path in sorted((Path(sql_dir) / "load").glob("*.sql")):
        run_sql_file(con, path, from_key, to_key)
        log.info("loaded %s for %d..%d", path.stem, from_key, to_key)
