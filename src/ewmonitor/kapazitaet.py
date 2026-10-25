"""Capacity seed to staging: the seed is complete, so the staging table is replaced as a whole."""

from __future__ import annotations

import pandas as pd

from .db import bulk_insert, df_rows
from .mastr import SEED_COLUMNS


def write_stg_kapazitaet(con, seed: pd.DataFrame) -> int:
    """TRUNCATE stg.mastr_kapazitaet and insert the seed in one transaction (bulk_insert commits or rolls back).

    bulk_insert returns early without committing when there are no rows, so an empty seed commits the TRUNCATE
    here: the staging table is then empty and the fact load leaves dw.fact_kapazitaet empty too."""
    rows = df_rows(seed, list(SEED_COLUMNS))
    cur = con.cursor()  # not "with": pyodbc's Cursor.__exit__ commits
    try:
        cur.execute("TRUNCATE TABLE stg.mastr_kapazitaet")
        if not rows:
            con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
    return bulk_insert(con, "stg.mastr_kapazitaet", list(SEED_COLUMNS), rows)
