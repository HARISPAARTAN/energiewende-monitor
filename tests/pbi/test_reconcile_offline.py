"""Offline checks of the reconciliation definitions: the nine pairs exist on both sides and the DAX only uses
measures and columns that the TMDL model declares. The comparison itself is tests/pbi/test_reconcile.py (live)."""

import re
from pathlib import Path

import pytest

from tools.pbi import reconcile
from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / "powerbi" / "EnergiewendeMonitor.SemanticModel" / "definition"
IDS = [f"R{i}" for i in range(1, 10)]


def test_nine_sql_statements_with_ids_in_order():
    statements = reconcile.sql_statements()
    assert len(statements) == 9
    ids = [re.search(r"SELECT\s+'(R\d)'", s).group(1) for s in statements]
    assert ids == IDS


def test_pairs_cover_the_same_ids_and_tolerances_match_the_live_test():
    assert [p.id for p in reconcile.PAIRS] == IDS
    assert reconcile.TOLERANCE == {
        "R1": 0.5, "R2": 0.0005, "R3": 0, "R4": 0.005, "R5": 0.5, "R6": 0.5, "R7": 0.5, "R8": 0.5, "R9": 0,
    }


def test_dax_queries_use_only_declared_measures_and_columns():
    model = load_model(MODEL_DIR)
    measures = set(model.tables["Kennzahlen"].measures)
    for rid, query in reconcile.dax_queries().items():
        assert query.startswith('EVALUATE ROW("wert", '), rid
        pair = next(p for p in reconcile.PAIRS if p.id == rid)
        for name in re.findall(r"(?<![\w\]'])\[([^\]]+)\]", pair.dax):  # bare [Measure] references
            assert name in measures, (rid, name)
        for quoted, bare, column in re.findall(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]", pair.dax):  # DAX: quoted or plain-ASCII table names
            table = quoted or bare
            assert table in model.tables, (rid, table)
            assert column in model.tables[table].columns, (rid, table, column)


def test_every_measure_of_the_pairs_is_declared():
    kz = load_model(MODEL_DIR).tables["Kennzahlen"].measures
    used = {m for p in reconcile.PAIRS for m in re.findall(r"\[([^\]]+)\]", p.dax) if m in kz}
    assert {"Erzeugung (MWh)", "EE-Anteil %", "Negative Preisstunden", "Day-Ahead Ø (€/MWh)", "Installierte Leistung (MW)",
            "Zubau (MW)", "Volllaststunden (h)", "Zeilen"} == used


def test_desktop_port_is_none_without_a_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert reconcile.desktop_port() is None


def test_desktop_port_reads_utf16_file_of_a_listening_instance(tmp_path, monkeypatch):
    import socket

    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        data = tmp_path / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces" / "AnalysisServicesWorkspace_x" / "Data"
        data.mkdir(parents=True)
        (data / "msmdsrv.port.txt").write_text(str(port), encoding="utf-16")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert reconcile.desktop_port() == port
    assert reconcile.desktop_port() is None  # the port no longer accepts connections (stale file of a closed Desktop)


def test_desktop_port_reads_a_port_file_without_bom(tmp_path, monkeypatch):
    # the Store build writes msmdsrv.port.txt as UTF-16 LE without a BOM, which the text reader rejects
    import socket

    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        data = tmp_path / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces" / "AnalysisServicesWorkspace_x" / "Data"
        data.mkdir(parents=True)
        (data / "msmdsrv.port.txt").write_bytes(str(port).encode("utf-16-le"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert reconcile.desktop_port() == port
