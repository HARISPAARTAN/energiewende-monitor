"""Marktstammdatenregister: read the open-mastr 1.0 SQLite store, normalise units, map to the SMARD
Energietraeger dimension, aggregate installed capacity per Bundesland, Energietraeger and month."""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# open-mastr 1.0 table name -> the `data=[...]` short name used for the download
UNIT_TABLES = {
    "EinheitenWind": "wind",
    "EinheitenSolar": "solar",
    "EinheitenBiomasse": "biomass",
    "EinheitenWasser": "hydro",
    "EinheitenGeothermieGrubengasDruckentspannung": "gsgk",
    "EinheitenVerbrennung": "combustion",
    "EinheitenKernkraft": "nuclear",
    "EinheitenStromSpeicher": "storage",
}
SOURCE_COLUMNS = {  # normalised name -> MaStR column; missing optional columns become NULL
    "einheit": "EinheitMastrNummer",
    "bundesland": "Bundesland",
    "netto_kw": "Nettonennleistung",
    "inbetriebnahme": "Inbetriebnahmedatum",
    "status": "EinheitBetriebsstatus",
    "stilllegung": "DatumEndgueltigeStilllegung",
    "energietraeger_mastr": "Energietraeger",
    "technologie": "Technologie",
    "hauptbrennstoff": "Hauptbrennstoff",
    "lage": "Lage",
}
UNIT_COLUMNS = ("einheit", "tabelle", "bundesland", "status", "inbetriebnahme", "stilllegung", "netto_kw",
                "energietraeger_mastr", "technologie", "hauptbrennstoff", "lage", "datum_unplausibel")
SEED_COLUMNS = ("jahr_monat", "bundesland_kuerzel", "energietraeger", "zubau_mw", "anzahl_zubau", "abgang_mw",
                "anzahl_abgang", "anfangsbestand_mw", "anfangsbestand_anzahl")
STATUS_IN_PLANUNG = "In Planung"
STATUS_ENDGUELTIG = "Endgültig stillgelegt"
COUNTED_STATUS = ("In Betrieb", "Vorübergehend stillgelegt", STATUS_ENDGUELTIG)
OFFSHORE_LAGE = "Windkraft auf See"
AWZ, UNBEKANNT = "AWZ", "UNB"
FALLBACK = "Sonstige Konventionelle"
VERWERFEN = "VERWERFEN"
MIN_YEAR, MAX_YEAR = 1900, 2100
KEYS = ["jahr_monat", "bundesland_kuerzel", "energietraeger"]
VALUE_COLUMNS = list(SEED_COLUMNS[3:])

BUNDESLAND_KUERZEL = {
    "Baden-Württemberg": "BW", "Bayern": "BY", "Berlin": "BE", "Brandenburg": "BB", "Bremen": "HB", "Hamburg": "HH",
    "Hessen": "HE", "Mecklenburg-Vorpommern": "MV", "Niedersachsen": "NI", "Nordrhein-Westfalen": "NW",
    "Rheinland-Pfalz": "RP", "Saarland": "SL", "Sachsen": "SN", "Sachsen-Anhalt": "ST", "Schleswig-Holstein": "SH",
    "Thüringen": "TH",
}

ATTRIBUTION = ("Datenquelle: Marktstammdatenregister der Bundesnetzagentur, Datenlizenz Deutschland – Namensnennung – "
               "Version 2.0 (https://www.govdata.de/dl-de/by-2-0), Daten aggregiert")


def _existing_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}


def iter_units(sqlite_path: Path, chunksize: int = 500_000) -> Iterator[pd.DataFrame]:
    """Yield normalised unit chunks from every unit table; missing optional columns are NULL."""
    con = sqlite3.connect(str(sqlite_path))
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in UNIT_TABLES:
            if table not in tables:
                log.warning("MaStR-Tabelle %s fehlt in %s", table, sqlite_path)
                continue
            present = _existing_columns(con, table)
            select = ", ".join(
                f'"{src}" AS {dst}' if src in present else f"NULL AS {dst}" for dst, src in SOURCE_COLUMNS.items())
            for chunk in pd.read_sql_query(f'SELECT {select} FROM "{table}"', con, chunksize=chunksize):
                chunk.insert(1, "tabelle", table)
                yield _normalise(chunk)
    finally:
        con.close()


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise one raw chunk. A non-empty date that does not parse or lies outside MIN_YEAR..MAX_YEAR counts as
    missing (this also keeps dates beyond the datetime64[ns] limit of 2262-04-11 from raising); the number of units
    with such a date is flagged in the boolean column `datum_unplausibel`, which `aggregate` sums."""
    out = df.copy()
    unplausibel = pd.Series(False, index=out.index)
    for col in ("inbetriebnahme", "stilllegung"):
        raw = out[col].astype("string").str.strip().replace({"": pd.NA})
        parsed = pd.to_datetime(raw, errors="coerce", format="mixed")
        plausibel = parsed.dt.year.between(MIN_YEAR, MAX_YEAR)
        unplausibel |= raw.notna() & ~plausibel
        out[col] = parsed.where(plausibel).astype("datetime64[ns]")
    out["netto_kw"] = pd.to_numeric(out["netto_kw"], errors="coerce").astype("float64")
    for col in ("bundesland", "status", "energietraeger_mastr", "technologie", "hauptbrennstoff", "lage"):
        out[col] = out[col].astype("string").str.strip().replace({"": pd.NA})
    out["datum_unplausibel"] = unplausibel.astype(bool)
    return out[list(UNIT_COLUMNS)]


def load_mapping(path: Path) -> pd.DataFrame:
    mapping = pd.read_csv(path, dtype="string", encoding="utf-8")
    expected = ["tabelle", "feld", "wert", "energietraeger"]
    if list(mapping.columns) != expected:
        raise ValueError(f"{path}: Spalten {list(mapping.columns)} statt {expected}")
    leer = mapping.apply(lambda col: col.str.strip().fillna("") == "").any(axis=1)
    if leer.any():
        raise ValueError(f"{path}: leere Zellen in Zeile(n) {[i + 2 for i in mapping.index[leer]]}")
    feld_stern = (mapping["feld"] == "*") & (mapping["wert"] != "*")
    if feld_stern.any():
        raise ValueError(f"{path}: feld '*' verlangt wert '*' in Zeile(n) {[i + 2 for i in mapping.index[feld_stern]]}")
    return mapping


def map_energietraeger(df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """First matching mapping row per table wins; unmapped rows get FALLBACK and `unmapped`; VERWERFEN rows get `verworfen`."""
    out = df.copy()
    result = pd.Series(pd.NA, index=out.index, dtype="string")
    for row in mapping.itertuples(index=False):
        in_table = out["tabelle"] == row.tabelle
        if row.feld == "*" or row.wert == "*":
            hit = in_table if row.feld == "*" else in_table & out[row.feld].notna()
        else:
            hit = in_table & (out[row.feld] == row.wert).fillna(False)  # NULL never matches a value
        result = result.where(result.notna(), other=pd.Series(row.energietraeger, index=out.index, dtype="string").where(hit))
    out["unmapped"] = result.isna()
    out["energietraeger"] = result.fillna(FALLBACK)
    out["verworfen"] = out["energietraeger"] == VERWERFEN
    return out


def _bundesland_kuerzel(df: pd.DataFrame) -> pd.Series:
    kuerzel = df["bundesland"].map(BUNDESLAND_KUERZEL).astype("string")
    offshore = (df["lage"] == OFFSHORE_LAGE).fillna(False)  # an NA mask entry in where() would replace the value
    kuerzel = kuerzel.where(~(kuerzel.isna() & offshore), AWZ)
    return kuerzel.fillna(UNBEKANNT)


def aggregate(chunks: Iterable[pd.DataFrame], calendar_start: date, calendar_end: date,
              mapping: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Monthly Zubau, Abgang and Anfangsbestand per Bundesland and Energietraeger, plus statistics.

    Each chunk is pre-aggregated to one row per cell, so memory grows with the number of cells, not units.
    MW values are summed unrounded and rounded to 3 decimals per cell only at the end."""
    first_month = f"{calendar_start.year:04d}-{calendar_start.month:02d}"
    last_month = f"{calendar_end.year:04d}-{calendar_end.month:02d}"
    start_ts = pd.Timestamp(calendar_start)
    stats: Counter = Counter()
    parts: list[pd.DataFrame] = []
    for chunk in chunks:
        stats["einheiten"] += len(chunk)
        stats["datum_unplausibel"] += int(chunk["datum_unplausibel"].sum())
        m = map_energietraeger(chunk, mapping)
        stats["verworfen"] += int(m["verworfen"].sum())
        m = m[~m["verworfen"]]
        stats["unmapped"] += int(m["unmapped"].sum())
        stats["in_planung"] += int((m["status"] == STATUS_IN_PLANUNG).sum())
        stats["status_unbekannt"] += int((~m["status"].isin((*COUNTED_STATUS, STATUS_IN_PLANUNG))).sum())  # NULL counts
        m = m[m["status"].isin(COUNTED_STATUS)]
        stats["netto_fehlt"] += int(m["netto_kw"].isna().sum())
        m = m[m["netto_kw"].notna()]
        positiv = m["netto_kw"] > 0
        stats["netto_unplausibel"] += int((~positiv).sum())
        m = m[positiv]
        kuerzel = _bundesland_kuerzel(m)
        stats["bundesland_unbekannt"] += int((kuerzel == UNBEKANNT).sum())
        mw = m["netto_kw"] / 1000.0  # not rounded per unit: cells are rounded after summing
        endgueltig = (m["status"] == STATUS_ENDGUELTIG).fillna(False)
        abgang_ts = m["stilllegung"].where(endgueltig)
        stats["stilllegung_ohne_datum"] += int((endgueltig & m["stilllegung"].isna()).sum())
        vor_kalender_abgang = abgang_ts.notna() & (abgang_ts < start_ts)
        stats["vor_kalender_abgang"] += int(vor_kalender_abgang.sum())
        keep = ~vor_kalender_abgang
        m, kuerzel, mw, abgang_ts = m[keep], kuerzel[keep], mw[keep], abgang_ts[keep]
        fehlt = m["inbetriebnahme"].isna()
        stats["inbetriebnahme_fehlt"] += int(fehlt.sum())
        vor_kalender = m["inbetriebnahme"] < start_ts
        stats["vor_kalender_zubau"] += int(vor_kalender.sum())
        anfang = fehlt | vor_kalender
        zubau_monat = m["inbetriebnahme"].dt.strftime("%Y-%m").where(~anfang, first_month)
        base = pd.DataFrame({"bundesland_kuerzel": kuerzel.astype("string"), "energietraeger": m["energietraeger"].astype("string")})
        zubau = base.assign(jahr_monat=zubau_monat, zubau_mw=mw.where(~anfang, 0.0), anzahl_zubau=(~anfang).astype(int),
                            abgang_mw=0.0, anzahl_abgang=0, anfangsbestand_mw=mw.where(anfang, 0.0),
                            anfangsbestand_anzahl=anfang.astype(int))
        has_abgang = abgang_ts.notna()
        abgang = base[has_abgang].assign(jahr_monat=abgang_ts[has_abgang].dt.strftime("%Y-%m"), zubau_mw=0.0, anzahl_zubau=0,
                                         abgang_mw=mw[has_abgang], anzahl_abgang=1, anfangsbestand_mw=0.0, anfangsbestand_anzahl=0)
        rows = pd.concat([zubau, abgang], ignore_index=True)
        nach_kalender = rows["jahr_monat"] > last_month
        stats["nach_kalender"] += int(nach_kalender.sum())
        parts.append(rows[~nach_kalender].groupby(KEYS, as_index=False)[VALUE_COLUMNS].sum())
    if not parts:
        stats["zeilen"] = 0
        return pd.DataFrame(columns=list(SEED_COLUMNS)), dict(stats)
    seed = pd.concat(parts, ignore_index=True).groupby(KEYS, as_index=False)[VALUE_COLUMNS].sum()
    for col in ("zubau_mw", "abgang_mw", "anfangsbestand_mw"):
        seed[col] = seed[col].round(3)
    nonzero = (seed[["anzahl_zubau", "anzahl_abgang", "anfangsbestand_anzahl"]].sum(axis=1) > 0)
    seed = seed[nonzero].sort_values(KEYS).reset_index(drop=True)
    seed = seed[list(SEED_COLUMNS)]
    for col in KEYS:
        seed[col] = seed[col].astype(str)
    stats["zeilen"] = len(seed)
    return seed, dict(stats)


def write_seed(seed: pd.DataFrame, path: Path, stats: dict, export_date: date) -> None:
    lines = [f"# {ATTRIBUTION}", f"# Exportstand: {export_date.isoformat()}",
             "# Regeln: Zubau im Monat der Inbetriebnahme; Abgang im Monat der endgueltigen Stilllegung; "
             "Anfangsbestand im ersten Kalendermonat fuer aeltere Inbetriebnahmen und fehlende Daten; In Planung ausgeschlossen; "
             "endgueltig stillgelegt ohne Stilllegungsdatum bleibt im Bestand (stilllegung_ohne_datum)",
             "# Statistik: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items()))]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
        seed.to_csv(f, index=False, lineterminator="\n")


def read_seed(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#", encoding="utf-8", dtype={"jahr_monat": str, "bundesland_kuerzel": str, "energietraeger": str})
    missing = [c for c in SEED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: Spalten fehlen: {missing}")
    return df[list(SEED_COLUMNS)]


def sqlite_from_csv_dir(csv_dir: Path, sqlite_path: Path) -> Path:
    """Build an open-mastr-shaped SQLite file from CSV tables (fixtures and tests)."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    if sqlite_path.exists():
        sqlite_path.unlink()
    con = sqlite3.connect(str(sqlite_path))
    try:
        for csv_path in sorted(Path(csv_dir).glob("*.csv")):
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8")
            df = df.replace({"": None})
            df.to_sql(csv_path.stem, con, index=False)
        con.commit()
    finally:
        con.close()
    return sqlite_path


def profile(sqlite_path: Path, top: int = 25) -> str:
    """Distinct values with counts for the mapping-relevant columns and NULL rates, as Markdown."""
    con = sqlite3.connect(str(sqlite_path))
    out = ["# MaStR-Profil", "", f"Quelle: `{sqlite_path}`", ""]
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for table in UNIT_TABLES:
            if table not in tables:
                out.append(f"## {table}\n\nfehlt\n")
                continue
            present = _existing_columns(con, table)
            n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            out.append(f"## {table}\n\nEinheiten: {n}\n")
            for col in ("EinheitBetriebsstatus", "Energietraeger", "Technologie", "Hauptbrennstoff", "Lage"):
                if col not in present:
                    continue
                rows = con.execute(f'SELECT "{col}", COUNT(*) FROM "{table}" GROUP BY "{col}" ORDER BY 2 DESC LIMIT {top}').fetchall()
                out.append(f"### {col}\n\n| Wert | Anzahl |\n|---|---|")
                out.extend(f"| {v if v is not None else 'NULL'} | {c} |" for v, c in rows)
                out.append("")
            for col in ("Bundesland", "Inbetriebnahmedatum", "Nettonennleistung"):
                if col in present:
                    nulls = con.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NULL OR "{col}" = \'\'').fetchone()[0]
                    out.append(f"- {col} NULL: {nulls} von {n}")
            out.append("")
    finally:
        con.close()
    return "\n".join(out) + "\n"


def download(output_dir: Path, tables: Iterable[str], date_: str | None = None) -> Path:
    """Bulk download and parse with open-mastr (optional extra `mastr`); returns the SQLite path."""
    try:
        from open_mastr import Mastr
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("open-mastr fehlt: uv sync --extra mastr") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    Mastr(output_dir=str(output_dir)).download(method="bulk", data=list(tables), date=date_)
    return find_sqlite(output_dir)


def find_sqlite(output_dir: Path) -> Path:
    candidates = sorted((Path(output_dir) / "data" / "sqlite").glob("*.db"))
    if not candidates:
        raise FileNotFoundError(f"keine SQLite-Datei unter {output_dir / 'data' / 'sqlite'}")
    return candidates[-1]
