"""Command line: ingest (SMARD to staging), load (DDL, dims, facts), check (data quality), all."""

from __future__ import annotations

import logging
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from . import db, mastr
from .checks import format_results, has_failures, run_checks
from .config import Settings, load_settings
from .dims import load_dims
from .ingest import ingest_fixtures, ingest_range
from .kapazitaet import write_stg_kapazitaet
from .load import key_range, load_facts, write_stg
from .smard import SmardClient
from .timekeys import BERLIN, date_key

app = typer.Typer(help="Energiewende-Monitor Pipeline: SMARD -> SQL Server Star-Schema.", no_args_is_help=True)

FromOpt = Annotated[datetime | None, typer.Option("--from", help="erster Tag (YYYY-MM-DD), Standard: config scope.start")]
ToOpt = Annotated[datetime | None, typer.Option("--to", help="letzter Tag (YYYY-MM-DD), Standard: gestern")]
RegionsOpt = Annotated[list[str] | None, typer.Option("--regions", help="SMARD-Regionen, Standard: config")]
FixturesOpt = Annotated[bool, typer.Option("--fixtures", help="data/fixtures statt Netzwerk verwenden")]
RefreshOpt = Annotated[int, typer.Option(
    "--refresh-days", min=0,
    help="Chunks, die in den letzten N Tagen enden, neu laden (SMARD veröffentlicht Wochen nachträglich neu)")]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _range(settings: Settings, from_: datetime | None, to: datetime | None) -> tuple[date, date]:
    """The requested day range: not before [scope] start (SMARD data begins there) and not after the
    calendar end, because every fact row references its day in dim_datum."""
    first, last = date.fromisoformat(settings.start), settings.calendar_end
    start = from_.date() if from_ else first
    end = to.date() if to else (datetime.now(BERLIN).date() - timedelta(days=1))
    if start < first:
        raise typer.BadParameter(f"--from {start} liegt vor dem Datenbeginn {first}; erlaubt ist {first} bis {last}")
    if end > last:
        raise typer.BadParameter(f"--to {end} liegt nach dem Kalenderende {last}; erlaubt ist {first} bis {last}")
    if end < start:
        raise typer.BadParameter("--to liegt vor --from")
    return start, end


def _export_date(value: str | None) -> date | None:
    """The MaStR export date from --date: exactly eight digits forming a real calendar day, or None."""
    if value is None:
        return None
    if not (len(value) == 8 and value.isascii() and value.isdigit()):
        raise typer.BadParameter(f"{value!r} ist nicht im Format YYYYMMDD", param_hint="--date")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as exc:
        raise typer.BadParameter(f"{value!r} ist kein gültiges Datum ({exc})", param_hint="--date") from exc


def _stage_capacity(settings: Settings, con, fixtures: bool) -> None:
    """Replace stg.mastr_kapazitaet with the capacity seed (the fixture seed with --fixtures)."""
    seed_path = (settings.fixtures_dir / "mastr" if fixtures else settings.seed_dir) / "kapazitaet_monat.csv"
    typer.echo(f"kapazitaet staging: {write_stg_kapazitaet(con, mastr.read_seed(seed_path))} Zeilen")


def _prepare(settings: Settings):
    db.ensure_database(settings.db)
    con = db.connect(settings.db)
    db.run_ddl(con, settings.root / "sql")
    return con


def _ingest(settings: Settings, con, start: date, end: date, fixtures: bool, regions: list[str] | None,
            refresh_days: int):
    if fixtures:
        df = ingest_fixtures(settings.fixtures_dir)
    else:
        client = SmardClient(settings.smard.base_url, settings.raw_dir / "smard")
        df = ingest_range(settings, client, start, end, regions, refresh_days=refresh_days)
    n = write_stg(con, df)
    typer.echo(f"staging: {n} Zeilen")
    return df


@app.command()
def ingest(from_: FromOpt = None, to: ToOpt = None, fixtures: FixturesOpt = False, regions: RegionsOpt = None,
           refresh_days: RefreshOpt = 60) -> None:
    """SMARD-Chunks laden (Cache in data/raw) und nach stg.smard_series schreiben."""
    settings = load_settings()
    start, end = _range(settings, from_, to)
    with closing(_prepare(settings)) as con:
        _ingest(settings, con, start, end, fixtures, regions, refresh_days)


@app.command()
def load(from_: FromOpt = None, to: ToOpt = None) -> None:
    """DDL anwenden, Dimensionen laden, Fakten für den Zeitraum aus dem Staging neu aufbauen."""
    settings = load_settings()
    start, end = _range(settings, from_, to)
    with closing(_prepare(settings)) as con:
        typer.echo(f"dimensionen: {load_dims(con, settings.seed_dir, settings.calendar_start, settings.calendar_end)}")
        _stage_capacity(settings, con, fixtures=False)
        load_facts(con, settings.root / "sql", date_key(start), date_key(end))
        typer.echo(f"fakten: {date_key(start)}..{date_key(end)}")


@app.command()
def check(from_: FromOpt = None, to: ToOpt = None) -> None:
    """Datenqualität prüfen; Exit-Code 1 bei mindestens einem fail."""
    settings = load_settings()
    start, end = _range(settings, from_, to)
    with closing(db.connect(settings.db)) as con:
        results = run_checks(con, date_key(start), date_key(end))
    typer.echo(format_results(results))
    if has_failures(results):
        raise typer.Exit(code=1)


@app.command(name="all")
def run_all(from_: FromOpt = None, to: ToOpt = None, fixtures: FixturesOpt = False, regions: RegionsOpt = None,
            refresh_days: RefreshOpt = 60) -> None:
    """ingest + load + check in einem Lauf. Mit --fixtures ergibt sich der Zeitraum aus den Fixture-Daten."""
    settings = load_settings()
    start, end = _range(settings, from_, to)
    with closing(_prepare(settings)) as con:
        df = _ingest(settings, con, start, end, fixtures, regions, refresh_days)
        lo, hi = key_range(df) if fixtures and not df.empty else (date_key(start), date_key(end))
        typer.echo(f"dimensionen: {load_dims(con, settings.seed_dir, settings.calendar_start, settings.calendar_end)}")
        _stage_capacity(settings, con, fixtures)
        load_facts(con, settings.root / "sql", lo, hi)
        # fixture data is historical: judge freshness against the fixture week's end, not today
        now = df["ts_utc"].max().to_pydatetime() if fixtures and not df.empty else None
        results = run_checks(con, lo, hi, now=now)
    typer.echo(format_results(results))
    if has_failures(results):
        raise typer.Exit(code=1)


@app.command(name="seed-mastr")
def seed_mastr(
    date_: Annotated[str | None, typer.Option("--date", help="MaStR-Exportstand YYYYMMDD, Standard: aktuell")] = None,
    skip_download: Annotated[bool, typer.Option("--skip-download", help="vorhandenen Export (Zip bzw. SQLite) verwenden")] = False,
    fixtures: FixturesOpt = False,
    profile: Annotated[bool, typer.Option("--profile", help="docs/mastr-profil.md mit den Wertelisten schreiben")] = False,
    out: Annotated[Path | None, typer.Option("--out", help="Zielpfad der Seed-CSV (Standard: data/seed bzw. data/fixtures)")] = None,
    source: Annotated[str, typer.Option(
        "--source", help="Leser: xml (Standard, liest den Gesamtdatenexport-Zip direkt) oder sqlite (open-mastr-Datenbank); "
                         "--fixtures liest immer die SQLite-Fixture")] = "xml",
) -> None:
    """MaStR-Gesamtdatenexport lesen und data/seed/kapazitaet_monat.csv neu erzeugen (nur auf dem Entwicklerrechner)."""
    if source not in ("xml", "sqlite"):
        raise typer.BadParameter(f"{source!r}: erlaubt sind xml und sqlite", param_hint="--source")
    export_date = _export_date(date_)
    settings = load_settings()
    if fixtures:
        quelle = mastr.sqlite_from_csv_dir(settings.fixtures_dir / "mastr" / "tables",
                                           settings.root / "data" / "raw" / "mastr_fixture" / "open-mastr.db")
        chunks = mastr.iter_units(quelle)
        target = out or settings.fixtures_dir / "mastr" / "kapazitaet_monat.csv"
    else:
        if not skip_download:
            mastr.download(settings.mastr_output_dir, settings.mastr_tables, date_)
        if source == "xml":
            quelle = mastr.find_zip(settings.mastr_output_dir)
            export_date = export_date or mastr.zip_export_date(quelle)
            chunks = mastr.iter_units_xml(quelle, mastr.UNIT_TABLES, mastr.load_katalog(quelle))
        else:
            quelle = mastr.find_sqlite(settings.mastr_output_dir)
            chunks = mastr.iter_units(quelle)
        target = out or settings.seed_dir / "kapazitaet_monat.csv"
    typer.echo(f"quelle: {quelle}")
    prof = mastr.Profile()
    mapping = mastr.load_mapping(settings.seed_dir / "mastr_energietraeger_mapping.csv")
    seed, stats = mastr.aggregate(prof.wrap(chunks), settings.calendar_start, settings.calendar_end, mapping)
    typer.echo("einheiten je tabelle: " + " ".join(f"{t}={prof.einheiten[t]}" for t in mastr.UNIT_TABLES))
    if profile:
        try:
            label = quelle.relative_to(settings.root).as_posix()
        except ValueError:
            label = quelle.name
        (settings.root / "docs" / "mastr-profil.md").write_text(prof.markdown(label), encoding="utf-8", newline="\n")
        typer.echo("profil: docs/mastr-profil.md")
    mastr.write_seed(seed, target, stats, export_date or date.today())
    typer.echo(f"seed: {target} " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())))
