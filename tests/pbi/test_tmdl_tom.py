"""Optional: parse the TMDL folder with Microsoft's own TmdlSerializer (the parser Desktop uses).

Skipped unless build/tom/ holds the TOM client (tools/pbi/fetch_tom.py) and pythonnet with a .NET runtime is
available (uv sync --group pbi). A TMDL syntax error fails here with the file, line and reason.
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "build" / "tom"
MODEL = ROOT / "powerbi" / "EnergiewendeMonitor.SemanticModel" / "definition"


@pytest.fixture(scope="module")
def serializer():
    if not (LIB / "Microsoft.AnalysisServices.Tabular.dll").exists():
        pytest.skip("TOM client not downloaded (uv run python tools/pbi/fetch_tom.py)")
    try:
        from pythonnet import load

        try:
            load("coreclr")
        except RuntimeError:
            pass  # a runtime is already loaded in this process
        import clr
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pythonnet or the .NET runtime is not available: {exc}")
    sys.path.append(str(LIB))
    clr.AddReference(str(LIB / "Microsoft.AnalysisServices.Tabular.dll"))
    from Microsoft.AnalysisServices.Tabular import TmdlSerializer

    return TmdlSerializer


def test_tom_parses_the_model(serializer):
    db = serializer.DeserializeDatabaseFromFolder(str(MODEL))
    tables = {t.Name for t in db.Model.Tables}
    assert len(tables) >= 12, tables
    for table in db.Model.Tables:
        for partition in table.Partitions:
            if str(partition.SourceType) == "M":
                assert 'Sql.Database("127.0.0.1,1433", "energiewende")' in str(partition.Source.Expression), table.Name
