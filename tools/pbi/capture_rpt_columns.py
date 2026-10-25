"""Read the columns and SQL types of the twelve rpt views; write tools/pbi/rpt_columns.json (committed).

Usage: uv run --env-file .env python tools/pbi/capture_rpt_columns.py
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from ewmonitor.config import load_settings
from ewmonitor.db import connect

VIEWS = [
    "v_dim_datum", "v_dim_zeit", "v_dim_energietraeger", "v_dim_region", "v_dim_bundesland", "v_erzeugung",
    "v_last", "v_preis", "v_preis_last_stunde", "v_negative_preisphasen", "v_dq_luecken", "v_kapazitaet",
]
SQL = (
    "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
    "WHERE TABLE_SCHEMA = 'rpt' ORDER BY TABLE_NAME, ORDINAL_POSITION"
)


def main() -> None:
    out: dict[str, list[list[str]]] = {v: [] for v in VIEWS}
    with closing(connect(load_settings().db)) as con:
        for table, column, data_type in con.execute(SQL).fetchall():
            if table in out:
                out[table].append([column, data_type])
    missing = [v for v, cols in out.items() if not cols]
    if missing:
        raise SystemExit(f"views missing in schema rpt: {missing}")
    path = Path(__file__).parent / "rpt_columns.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print({v: len(c) for v, c in out.items()})


if __name__ == "__main__":
    main()
