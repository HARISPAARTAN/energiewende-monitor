"""Marktstammdatenregister: read the unit tables of the bulk export (the Gesamtdatenexport zip directly, or the
open-mastr 1.0 SQLite store), normalise units, map to the SMARD Energietraeger dimension, aggregate installed
capacity per Bundesland, Energietraeger and month."""

from __future__ import annotations

import logging
import re
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from lxml import etree

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


# --- Gesamtdatenexport zip (XML) ------------------------------------------------------------------------------
# The export holds one zip with UTF-16 XML members: `<Tabelle>.xml` or `<Tabelle>_1.xml ... _N.xml`. The root tag is
# the table name, the row tag its singular (`<EinheitenSolar><EinheitSolar>...`). Catalog-coded fields carry a
# numeric id that `Katalogwerte.xml` (`<Katalogwerte><Katalogwert><Id>/<Wert>`) resolves; the ids are global.
KATALOG = "Katalogwerte"
KATALOG_COLUMNS = tuple(SOURCE_COLUMNS[c] for c in ("bundesland", "status", "energietraeger_mastr", "technologie",
                                                    "hauptbrennstoff", "lage"))
EXPORT_PATTERN = re.compile(r"Gesamtdatenexport_(\d{8})\.zip")


def xml_members(names: Iterable[str], table: str) -> list[str]:
    """The zip members of one table in numeric order (`_2` before `_10`); a single `<table>.xml` counts as 0."""
    pattern = re.compile(rf"{re.escape(table)}(?:_(\d+))?\.xml")
    hits = [(int(m.group(1) or 0), name) for name in names if (m := pattern.fullmatch(name))]
    return [name for _, name in sorted(hits)]


def _row_tag(table: str) -> str:
    return table.replace("Einheiten", "Einheit", 1)


def _release(elem) -> None:
    """Free a processed element and everything before it, so memory stays flat over a 400 MB member."""
    elem.clear(keep_tail=True)
    while elem.getprevious() is not None:
        del elem.getparent()[0]


def load_katalog(zip_path: Path) -> dict[str, str]:
    """Catalog id -> text from the `Katalogwerte` member(s) of the export zip."""
    katalog: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members = xml_members(zf.namelist(), KATALOG)
        if not members:
            raise FileNotFoundError(f"{KATALOG}.xml fehlt in {zip_path}")
        for member in members:
            with zf.open(member) as f:
                for _, elem in etree.iterparse(f, events=("end",), tag="Katalogwert"):
                    katalog[(elem.findtext("Id") or "").strip()] = elem.findtext("Wert")
                    _release(elem)
    return katalog


def _xml_chunk(table: str, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame.from_records(rows, columns=list(SOURCE_COLUMNS))
    kw = df["netto_kw"].astype("string").str.replace(r"\s", "", regex=True).str.replace(",", ".", regex=False)
    df["netto_kw"] = pd.to_numeric(kw, errors="coerce").astype("float64")
    df.insert(1, "tabelle", table)
    return _normalise(df)


def iter_units_xml(zip_path: Path, tables: Iterable[str], katalog: dict[str, str],
                   chunksize: int = 200_000) -> Iterator[pd.DataFrame]:
    """Yield normalised unit chunks straight from the export zip, the same frame `iter_units` yields.

    Streams every member with lxml iterparse and keeps only the SOURCE_COLUMNS fields. Catalog-coded fields are
    resolved through `katalog`; a value that is not a catalog id (for example a multi-value `710 3183`) stays as
    it is. `Nettonennleistung` accepts a comma or a dot as decimal separator and ignores spaces."""
    wanted = {src: dst for dst, src in SOURCE_COLUMNS.items()}
    coded = set(KATALOG_COLUMNS)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for table in tables:
            members = xml_members(names, table)
            if not members:
                log.warning("MaStR-Tabelle %s fehlt in %s", table, zip_path)
                continue
            row_tag, table_units = _row_tag(table), 0
            for member in members:
                started, member_units, rows = time.perf_counter(), 0, []
                with zf.open(member) as f:
                    for _, elem in etree.iterparse(f, events=("end",), tag=row_tag):
                        record = {}
                        for child in elem:
                            dst = wanted.get(child.tag)
                            if dst is not None:
                                text = child.text
                                if child.tag in coded and text is not None:
                                    text = katalog.get(text.strip(), text)
                                record[dst] = text
                        rows.append(record)
                        _release(elem)
                        if len(rows) >= chunksize:
                            member_units += len(rows)
                            yield _xml_chunk(table, rows)
                            rows = []
                if rows:
                    member_units += len(rows)
                    yield _xml_chunk(table, rows)
                table_units += member_units
                log.info("%s: %d Einheiten in %.1f s", member, member_units, time.perf_counter() - started)
            log.info("%s: %d Einheiten aus %d Datei(en)", table, table_units, len(members))


def find_zip(output_dir: Path) -> Path:
    """The newest `Gesamtdatenexport_YYYYMMDD.zip` under `<output_dir>/data/xml_download`."""
    folder = Path(output_dir) / "data" / "xml_download"
    candidates = sorted(p for p in folder.glob("Gesamtdatenexport_*.zip") if EXPORT_PATTERN.fullmatch(p.name))
    if not candidates:
        raise FileNotFoundError(f"kein Gesamtdatenexport_YYYYMMDD.zip unter {folder}")
    return candidates[-1]


def zip_export_date(zip_path: Path) -> date | None:
    """The export date in the zip name, or None when the name carries none."""
    m = EXPORT_PATTERN.fullmatch(Path(zip_path).name)
    if not m:
        return None
    digits = m.group(1)
    return date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))


def xml_export_from_csv_dir(csv_dir: Path, zip_path: Path, rows_per_member: int = 5) -> Path:
    """Build an export-shaped zip from CSV tables (fixtures and tests): one `Katalogwerte.xml` with an id for every
    text in a catalog-coded column, and per table the rows with those ids, UTF-16 with BOM like the real export.
    A table with more than `rows_per_member` rows is split into `<table>_1.xml ... _N.xml`; empty cells are left
    out, as the export does. Deterministic: same input, same member bytes."""
    tables = {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8")
              for p in sorted(Path(csv_dir).glob("*.csv"))}
    texts = sorted({v for df in tables.values() for col in KATALOG_COLUMNS if col in df for v in df[col] if v})
    ids = {text: str(1000 + i) for i, text in enumerate(texts)}

    def member(root: str, row: str, records: list[dict]) -> bytes:
        body = "".join(
            f"<{row}>" + "".join(f"<{k}>{escape(v)}</{k}>" for k, v in rec.items() if v) + f"</{row}>" for rec in records)
        return f"<?xml version='1.0' encoding='UTF-16'?><{root}>{body}</{root}>".encode("utf-16")

    out = {f"{KATALOG}.xml": member(KATALOG, "Katalogwert", [
        {"Id": i, "Wert": text, "KatalogKategorieId": "1"} for text, i in ids.items()])}
    for table, df in tables.items():
        records = [{c: (ids[v] if c in KATALOG_COLUMNS and v else v) for c, v in rec.items()}
                   for rec in df.to_dict(orient="records")]
        parts = [records[i:i + rows_per_member] for i in range(0, len(records), rows_per_member)] or [[]]
        for n, part in enumerate(parts, start=1):
            name = f"{table}.xml" if len(parts) == 1 else f"{table}_{n}.xml"
            out[name] = member(table, _row_tag(table), part)
    Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in out.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), data, compress_type=zipfile.ZIP_DEFLATED)
    return Path(zip_path)


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


PROFILE_VALUES = ("status", "energietraeger_mastr", "technologie", "hauptbrennstoff", "lage", "bundesland")
PROFILE_NULLS = {"bundesland": "Bundesland", "inbetriebnahme": "Inbetriebnahmedatum", "netto_kw": "Nettonennleistung"}
NULL_TEXT = "NULL"


class Profile:
    """Distinct values with counts per unit table, collected from normalised chunks while they stream past, so
    profiling the multi-GB export needs no second pass. Works for both readers."""

    def __init__(self) -> None:
        self.einheiten: Counter = Counter()
        self.werte: defaultdict[tuple[str, str], Counter] = defaultdict(Counter)
        self.nulls: Counter = Counter()

    def add(self, chunk: pd.DataFrame) -> None:
        for table, part in chunk.groupby("tabelle", sort=False):
            self.einheiten[table] += len(part)
            for col in PROFILE_VALUES:
                self.werte[(table, col)].update(part[col].fillna(NULL_TEXT).value_counts().to_dict())
            for col in PROFILE_NULLS:
                self.nulls[(table, col)] += int(part[col].isna().sum())

    def wrap(self, chunks: Iterable[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        for chunk in chunks:
            self.add(chunk)
            yield chunk

    def markdown(self, source: str, top: int = 40) -> str:
        """Markdown per table; a column that is NULL for every unit of a table is left out."""
        out = ["# MaStR-Profil", "", f"Quelle: `{source}`", ""]
        for table in UNIT_TABLES:
            n = self.einheiten[table]
            out.append(f"## {table}\n\nEinheiten: {n}\n")
            for col in PROFILE_VALUES:
                counts = self.werte.get((table, col), Counter())
                if set(counts) <= {NULL_TEXT}:
                    continue
                out.append(f"### {SOURCE_COLUMNS[col]}\n\n| Wert | Anzahl |\n|---|---|")
                ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                out.extend(f"| {v} | {c} |" for v, c in ranked[:top])
                if len(ranked) > top:
                    out.append(f"| ({len(ranked) - top} weitere) | {sum(c for _, c in ranked[top:])} |")
                out.append("")
            out.extend(f"- {label} NULL: {self.nulls[(table, col)]} von {n}" for col, label in PROFILE_NULLS.items())
            out.append("")
        return "\n".join(out) + "\n"


def profile(chunks: Iterable[pd.DataFrame], source: str, top: int = 40) -> str:
    """Distinct values with counts for the mapping-relevant columns and NULL rates, as Markdown."""
    prof = Profile()
    for _ in prof.wrap(chunks):
        pass
    return prof.markdown(source, top)


def download(output_dir: Path, tables: Iterable[str], date_: str | None = None) -> None:
    """Bulk download with open-mastr (optional extra `mastr`). open-mastr also parses the zip into its SQLite store;
    `find_zip` and `find_sqlite` locate the results."""
    try:
        from open_mastr import Mastr
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("open-mastr fehlt: uv sync --extra mastr") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    Mastr(output_dir=str(output_dir)).download(method="bulk", data=list(tables), date=date_)


def find_sqlite(output_dir: Path) -> Path:
    candidates = sorted((Path(output_dir) / "data" / "sqlite").glob("*.db"))
    if not candidates:
        raise FileNotFoundError(f"keine SQLite-Datei unter {output_dir / 'data' / 'sqlite'}")
    return candidates[-1]
