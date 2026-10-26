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
    assert len(measures) == 35
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


KPI_MEASURES = ["KPI Erzeugung", "KPI EE-Anteil", "KPI Day-Ahead Ø", "KPI Negative Preisstunden", "KPI Installierte Leistung"]


def test_kpi_entries_say_why_text_and_that_it_is_display_only(sections):
    assert "Warum Text" in sections["Anzeigetexte (KPI-Kennzahlen)"] and "Nur zur Anzeige" in sections["Anzeigetexte (KPI-Kennzahlen)"]
    for name in KPI_MEASURES + ["Datenstand Kopfzeile"]:
        assert "Gebietsschema de-DE" in sections[name], name
        assert "Anzeigetexte" in sections[name], name
    for name in KPI_MEASURES:
        assert "Nur zur Anzeige" in sections[name] and "`Text`" in sections[name], name


def test_target_entries_name_the_law_with_paragraph_and_the_caveats(sections):
    expected = {
        "Zielerreichung Photovoltaik %": "§ 4 Nr. 3 Buchst. d EEG 2023",
        "Zielerreichung Wind an Land %": "§ 4 Nr. 1 Buchst. d EEG 2023",
        "Zielerreichung Wind auf See %": "§ 1 Abs. 2 WindSeeG",
    }
    for name, law in expected.items():
        section = sections[name]
        assert law in section, name
        assert "2026-10-26 auf gesetze-im-internet.de gelesen" in section, name  # the date the law texts were read
        assert "Kapazitäten und Grenzen" in section, name  # MaStR capacity as modelled
        assert "amtliche Zielüberwachung der Bundesnetzagentur kann abweichen" in section, name
        assert "Landesbehörde BW" in section and "Energieträger, Gruppe und Kategorie" in section, name
        assert "2030" in section, name
    for name in ("Zielerreichung Photovoltaik %", "Zielerreichung Wind an Land %"):  # the offshore value has no yearly path in § 4
        assert "nicht zum jährlichen Ausbaupfad" in sections[name], name
        assert "Werte für 2024, 2026 und 2028" in sections[name], name  # § 4 also sets these; they are not used here


def test_gruppe_section_names_the_four_carriers_and_repeats_the_dax():
    text = GLOSSARY.read_text(encoding="utf-8")
    section = re.split(r"^## ", text, flags=re.MULTILINE)
    section = next(p for p in section if p.startswith("Energieträger-Gruppen"))
    for carrier in ("Kernenergie", "Pumpspeicher", "Sonstige Erneuerbare", "Sonstige Konventionelle"):
        assert carrier in section, carrier
    assert "höchstens acht Farben" in section and "Tabellen und Slicern" in section
    columns = load_model(MODEL_DIR).tables["Energieträger"].columns
    for name in ("Gruppe", "Gruppe Sortierung"):
        assert columns[name].expression in section, f"{name}: DAX in the glossary differs from the TMDL"
