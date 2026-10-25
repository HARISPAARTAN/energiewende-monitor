"""Calendar and quarter-hour dimensions generated in Python; seed dimensions from CSV; idempotent loads."""

from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pandas as pd

from .db import bulk_insert, df_rows
from .timekeys import date_key, quarterhours_in_day

MONATE_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
             "November", "Dezember"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
WOCHENTAGE_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DIM_DATUM_COLUMNS = ["datum_key", "datum", "jahr", "quartal", "monat", "monat_name_de", "monat_name_en", "jahr_monat",
                     "iso_jahr", "iso_woche", "tag", "wochentag_nr", "wochentag_de", "wochentag_en", "ist_wochenende",
                     "saison_de", "viertelstunden"]
DIM_ZEIT_COLUMNS = ["zeit_key", "uhrzeit", "stunde", "viertelstunde", "tageszeit_de", "tageszeit_en"]

SEED_TABLES = {
    "dw.dim_energietraeger": ("dim_energietraeger.csv", "energietraeger_key"),
    "dw.dim_region": ("dim_region.csv", "region_key"),
    "dw.dim_bundesland": ("dim_bundesland.csv", "bundesland_key"),
}


def saison_de(month: int) -> str:
    return {12: "Winter", 1: "Winter", 2: "Winter", 3: "Frühling", 4: "Frühling", 5: "Frühling",
            6: "Sommer", 7: "Sommer", 8: "Sommer"}.get(month, "Herbst")


def tageszeit(hour: int) -> tuple[str, str]:
    if hour < 6:
        return "Nacht", "Night"
    if hour < 12:
        return "Morgen", "Morning"
    if hour < 18:
        return "Mittag", "Midday"
    return "Abend", "Evening"


def build_dim_datum(start: date, end: date) -> pd.DataFrame:
    rows = []
    d = start
    while d <= end:
        iso_year, iso_week, _ = d.isocalendar()
        wd = d.weekday()
        rows.append((date_key(d), d, d.year, (d.month - 1) // 3 + 1, d.month, MONATE_DE[d.month - 1],
                     MONTHS_EN[d.month - 1], f"{d.year:04d}-{d.month:02d}", iso_year, iso_week, d.day, wd + 1,
                     WOCHENTAGE_DE[wd], WEEKDAYS_EN[wd], int(wd >= 5), saison_de(d.month), quarterhours_in_day(d)))
        d += timedelta(days=1)
    return pd.DataFrame(rows, columns=DIM_DATUM_COLUMNS)


def build_dim_zeit() -> pd.DataFrame:
    rows = []
    for key in range(96):
        hour, quarter = divmod(key, 4)
        de, en = tageszeit(hour)
        rows.append((key, time(hour, quarter * 15), hour, quarter, de, en))
    return pd.DataFrame(rows, columns=DIM_ZEIT_COLUMNS)


def _insert_missing(con, table: str, key_col: str, df: pd.DataFrame) -> int:
    existing = {row[0] for row in con.execute(f"SELECT {key_col} FROM {table}").fetchall()}
    new = df[~df[key_col].isin(existing)]
    return bulk_insert(con, table, list(df.columns), df_rows(new, list(df.columns)))


def _upsert_seed(con, table: str, key_col: str, df: pd.DataFrame) -> int:
    cols = [c for c in df.columns if c != key_col]
    cur = con.cursor()
    cur.executemany(
        f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in cols)} WHERE {key_col} = ?",
        [row[1:] + (row[0],) for row in df_rows(df, [key_col] + cols)],
    )
    con.commit()
    return _insert_missing(con, table, key_col, df)


def load_dims(con, seed_dir: Path, start: date, end: date) -> dict[str, int]:
    """Insert missing calendar and quarter-hour rows; upsert the CSV seeds. Safe to re-run."""
    inserted = {
        "dw.dim_datum": _insert_missing(con, "dw.dim_datum", "datum_key", build_dim_datum(start, end)),
        "dw.dim_zeit": _insert_missing(con, "dw.dim_zeit", "zeit_key", build_dim_zeit()),
    }
    for table, (file_name, key_col) in SEED_TABLES.items():
        df = pd.read_csv(Path(seed_dir) / file_name, encoding="utf-8")
        inserted[table] = _upsert_seed(con, table, key_col, df)
    return inserted
