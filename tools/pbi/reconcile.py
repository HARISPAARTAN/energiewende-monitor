"""Reconciliation of the Power BI measures against the warehouse: nine SQL values against nine DAX values.

SQL side: sql/queries/reconcile_m3.sql (ids R1 to R9). DAX side: the queries below, run against the local
Analysis Services instance of an open Power BI Desktop through the ADOMD client (pythonnet).

    uv run --env-file .env python -m tools.pbi.reconcile sql      # the nine SQL values
    uv run python -m tools.pbi.reconcile dax-queries              # the nine DAX queries, for Desktop's DAX query view
    uv run --env-file .env --group pbi python -m tools.pbi.reconcile compare   # needs Desktop open and ADOMD

The live test (tests/pbi/test_reconcile.py) does the comparison with tolerances and skips cleanly when Desktop
or the ADOMD client is absent. Nothing here starts Desktop or installs anything system-wide.
"""

from __future__ import annotations

import glob
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "sql" / "queries" / "reconcile_m3.sql"
ADOMD_DIR = ROOT / "build" / "adomd"  # filled by tools/pbi/fetch_adomd.py (.NET build of the ADOMD client)
ADOMD_DLL = "Microsoft.AnalysisServices.AdomdClient.dll"


@dataclass(frozen=True)
class Pair:
    id: str
    label: str
    dax: str  # the scalar expression that is evaluated with EVALUATE ROW("wert", <dax>)
    tolerance: float  # absolute, in the unit of the value
    decimals: int  # rounding the glossary table shows


PAIRS: tuple[Pair, ...] = (
    Pair("R1", "Erzeugung gesamt 2025 (MWh)", "CALCULATE([Erzeugung (MWh)], Datum[Jahr] = 2025)", 0.5, 0),
    Pair("R2", "EE-Anteil 2025 (Anteil)", "CALCULATE([EE-Anteil %], Datum[Jahr] = 2025)", 0.0005, 4),
    Pair("R3", "Negative Preisstunden 2025", "CALCULATE([Negative Preisstunden], Datum[Jahr] = 2025)", 0, 0),
    Pair("R4", "Day-Ahead Ø 2025 (EUR/MWh)", "CALCULATE([Day-Ahead Ø (€/MWh)], Datum[Jahr] = 2025)", 0.005, 2),
    Pair("R5", "Installierte Leistung, neuester Monat (MW)", "[Installierte Leistung (MW)]", 0.5, 0),
    Pair("R6", "Installierte Leistung Ende 2024 (MW)", "CALCULATE([Installierte Leistung (MW)], Datum[Jahr] = 2024)", 0.5, 0),
    Pair(
        "R7",
        "Zubau 2024 Photovoltaik (MW)",
        'CALCULATE([Zubau (MW)], Datum[Jahr] = 2024, Energieträger[Energieträger] = "Photovoltaik")',
        0.5,
        0,
    ),
    Pair(
        "R8",
        "Volllaststunden Wind Onshore 2025 (h)",
        'CALCULATE([Volllaststunden (h)], Datum[Jahr] = 2025, Energieträger[Energieträger] = "Wind Onshore")',
        0.5,
        0,
    ),
    Pair("R9", "Zeilen gesamt", "[Zeilen]", 0, 0),
)
TOLERANCE = {p.id: p.tolerance for p in PAIRS}


def dax_query(rid: str) -> str:
    pair = next(p for p in PAIRS if p.id == rid)
    return f'EVALUATE ROW("wert", {pair.dax})'


def dax_queries() -> dict[str, str]:
    return {p.id: dax_query(p.id) for p in PAIRS}


def sql_statements(path: Path = SQL_FILE) -> list[str]:
    """The statements of the reconciliation script, in file order, without comments. Each returns (id, wert)."""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--")]
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    return statements


def sql_values() -> dict[str, float]:
    """Run the nine statements against the warehouse (password from MSSQL_SA_PASSWORD, never printed)."""
    from contextlib import closing

    from ewmonitor.config import load_settings
    from ewmonitor.db import connect

    out: dict[str, float] = {}
    with closing(connect(load_settings().db)) as con:
        for stmt in sql_statements():
            row = con.execute(stmt).fetchone()
            out[row[0]] = float(row[1])
    return out


# --- Power BI Desktop ---------------------------------------------------------------------------------------

def _workspace_roots() -> list[Path]:
    roots = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces")
    profile = os.environ.get("USERPROFILE")
    if profile:  # Microsoft Store build
        roots.append(Path(profile) / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces")
    return roots


def desktop_port() -> int | None:
    """Port of the local Analysis Services instance of an open Desktop, or None.

    msmdsrv.port.txt is UTF-16 and lives in <workspace root>/AnalysisServicesWorkspace*/Data/. A leftover file
    of a closed Desktop is ignored: the newest file wins and it must accept a TCP connection.
    """
    import socket

    candidates: list[Path] = []
    for root in _workspace_roots():
        candidates += [Path(p) for p in glob.glob(str(root / "*" / "Data" / "msmdsrv.port.txt"))]
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            port = int(path.read_text(encoding="utf-16").strip().lstrip("\ufeff"))
        except (OSError, ValueError):
            continue
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return port
        except OSError:
            continue
    return None


# --- ADOMD ---------------------------------------------------------------------------------------------------

def _adomd_candidates() -> list[tuple[Path, str]]:
    """(dll, runtime) pairs: the .NET build under build/adomd first, then DAX Studio, then the .NET Framework GAC."""
    found: list[tuple[Path, str]] = []
    if (ADOMD_DIR / ADOMD_DLL).exists():
        found.append((ADOMD_DIR / ADOMD_DLL, "coreclr"))
    pf = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    for base in filter(None, pf):
        for hit in glob.glob(str(Path(base) / "DAX Studio*" / "**" / ADOMD_DLL), recursive=True):
            found.append((Path(hit), "netfx"))
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for pattern in (
        rf"{windir}\Microsoft.NET\assembly\GAC_MSIL\Microsoft.AnalysisServices.AdomdClient\*\{ADOMD_DLL}",
        rf"{windir}\assembly\GAC_MSIL\Microsoft.AnalysisServices.AdomdClient\*\{ADOMD_DLL}",
    ):
        found += [(Path(hit), "netfx") for hit in glob.glob(pattern)]
    return found


def adomd_available() -> bool:
    try:
        import pythonnet  # noqa: F401
    except ImportError:
        return False
    return bool(_adomd_candidates())


def _load_adomd():
    from pythonnet import load

    errors = []
    for dll, runtime in _adomd_candidates():
        try:
            try:
                load(runtime)
            except RuntimeError:
                pass  # a runtime is already loaded in this process
            import clr

            sys.path.append(str(dll.parent))
            clr.AddReference(str(dll))
            from Microsoft.AnalysisServices.AdomdClient import AdomdConnection

            return AdomdConnection
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{dll}: {exc}")
    raise RuntimeError("ADOMD client could not be loaded: " + "; ".join(errors))


def _clean(value):
    if value is None or value.__class__.__name__ == "DBNull":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def dax(port: int, query: str) -> list[dict]:
    """Run a DAX query against the first database of the local instance; rows as dicts (column names unbracketed)."""
    connection_cls = _load_adomd()
    con = connection_cls(f"Data Source=localhost:{port}")
    con.Open()
    try:
        from Microsoft.AnalysisServices.AdomdClient import AdomdCommand

        cmd = AdomdCommand(query, con)
        reader = cmd.ExecuteReader()
        names = [re.sub(r"^\[|\]$", "", str(reader.GetName(i))) for i in range(reader.FieldCount)]
        rows = []
        while reader.Read():
            rows.append({n: _clean(reader.GetValue(i)) for i, n in enumerate(names)})
        reader.Close()
        return rows
    finally:
        con.Close()


def dax_value(port: int, rid: str) -> float:
    rows = dax(port, dax_query(rid))
    value = rows[0]["wert"]
    if value is None:
        raise ValueError(f"{rid}: the DAX query returned BLANK")
    return float(value)


# --- command line --------------------------------------------------------------------------------------------

def _fmt(value: float | None, decimals: int) -> str:
    return "-" if value is None else f"{value:,.{decimals}f}"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the labels contain Ø and umlauts
    command = args[0] if args else "compare"
    if command == "dax-queries":
        for rid, query in dax_queries().items():
            print(f"-- {rid} {next(p.label for p in PAIRS if p.id == rid)}\n{query}\n")
        return 0
    sql = sql_values()
    if command == "sql":
        for p in PAIRS:
            print(f"{p.id}  {p.label:<45} {_fmt(sql[p.id], p.decimals)}")
        return 0
    if command != "compare":
        print(__doc__)
        return 2
    port = desktop_port()
    if port is None or not adomd_available():
        print("Power BI Desktop is not open with the project, or the ADOMD client is missing; nothing compared.")
        return 3
    bad = 0
    for p in PAIRS:
        d = dax_value(port, p.id)
        ok = abs(d - sql[p.id]) <= p.tolerance
        bad += not ok
        print(f"{p.id}  {p.label:<45} SQL {_fmt(sql[p.id], p.decimals):>16}  DAX {_fmt(d, p.decimals):>16}  {'ok' if ok else 'DIFF'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
