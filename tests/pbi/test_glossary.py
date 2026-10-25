import re
from pathlib import Path

import pytest

from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2]
GLOSSARY = ROOT / "docs" / "kpi-glossar.md"
MODEL_DIR = ROOT / "powerbi" / "EnergiewendeMonitor.SemanticModel" / "definition"


@pytest.fixture(scope="module")
def sections():
    text = GLOSSARY.read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    return {p.split("\n", 1)[0].strip(): p for p in parts}


def test_every_measure_has_a_section_with_its_dax(sections):
    measures = load_model(MODEL_DIR).tables["Kennzahlen"].measures
    assert len(measures) == 26
    for name, measure in measures.items():
        assert name in sections, name
        section = sections[name]
        for label in ("**Definition:**", "**Einheit:**", "**Quelle:**", "**Formel**"):
            assert label in section, (name, label)
        assert measure.expression in section, f"{name}: DAX in the glossary differs from the TMDL"


def test_glossary_covers_the_capacity_caveats(sections):
    text = GLOSSARY.read_text(encoding="utf-8")
    for needle in ("Monatsendbestand", "LASTNONBLANK", "Durchschnitt", "7,45 GW", "3,0 GW", "0,6 GW", "vor 2019", "angebrochen"):
        assert needle in text, needle


def test_reconciliation_table_lists_the_nine_pairs():
    text = GLOSSARY.read_text(encoding="utf-8")
    assert re.search(r"^### Abgleich am \d{4}-\d{2}-\d{2}", text, flags=re.MULTILINE)
    for i in range(1, 10):
        assert re.search(rf"^\| R{i} \|", text, flags=re.MULTILINE), i
