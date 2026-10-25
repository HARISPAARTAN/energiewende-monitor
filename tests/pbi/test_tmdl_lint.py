import re
from pathlib import Path

import pytest

from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / "powerbi" / "EnergiewendeMonitor.SemanticModel" / "definition"
MEASURES = [
    "Erzeugung (MWh)", "Erzeugung Erneuerbar (MWh)", "EE-Anteil %", "Netzlast (MWh)", "Residuallast (MWh)",
    "Residuallast Minimum (MWh/15 min)", "Residuallast Ø (MWh/15 min)", "Day-Ahead Ø (€/MWh)", "Day-Ahead Max (€/MWh)",
    "Day-Ahead Min (€/MWh)", "Negative Preisstunden", "Erzeugung Vorjahr (MWh)", "Erzeugung Δ Vorjahr %",
    "EE-Anteil Vorjahr %", "EE-Anteil Δ Vorjahr (pp)", "Netzlast Vormonat (MWh)", "Netzlast Δ Vormonat %", "Zubau (MW)",
    "Zubau YTD (MW)", "Installierte Leistung (MW)", "Volllaststunden (h)", "Anzahl Einheiten Zubau", "Datenstand", "Zeilen",
    "Datenstand MaStR",
]
RELATIONSHIPS = {
    ("Erzeugung.Datum Key", "Datum.Datum Key"), ("Erzeugung.Zeit Key", "Zeit.Zeit Key"),
    ("Erzeugung.Region Key", "Region.Region Key"), ("Erzeugung.Energieträger Key", "Energieträger.Energieträger Key"),
    ("Last.Datum Key", "Datum.Datum Key"), ("Last.Zeit Key", "Zeit.Zeit Key"), ("Last.Region Key", "Region.Region Key"),
    ("Preis.Datum Key", "Datum.Datum Key"), ("Preis.Zeit Key", "Zeit.Zeit Key"), ("Preis.Region Key", "Region.Region Key"),
    ("Last Stunde.Datum Key", "Datum.Datum Key"), ("Last Stunde.Region Key", "Region.Region Key"),
    ("Kapazität.Datum Key", "Datum.Datum Key"), ("Kapazität.Bundesland Key", "Bundesland.Bundesland Key"),
    ("Kapazität.Energieträger Key", "Energieträger.Energieträger Key"), ("Preisphasen.Start Datum Key", "Datum.Datum Key"),
}
TABLES = ["Erzeugung", "Last", "Preis", "Kapazität", "Datum", "Zeit", "Energieträger", "Region", "Bundesland", "Kennzahlen",
          "Kennzahl-Auswahl", "Last Stunde", "Preisphasen", "Datenlücken"]


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL_DIR)


def test_tables_present(model):
    assert set(TABLES) <= set(model.tables)


def test_all_25_measures_exist_with_format_and_description(model):
    kz = model.tables["Kennzahlen"].measures
    missing = [m for m in MEASURES if m not in kz]
    assert not missing, missing
    for name in MEASURES:
        m = kz[name]
        assert m.description, name
        if name not in ("Datenstand", "Datenstand MaStR"):  # text results carry no formatString
            assert m.format_string, name


def test_dax_references_resolve(model):
    # a qualified reference is `Table[Column]` or `'Table name'[Column]`; the table must be a bare identifier or quoted
    ref = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([^\W\d][\w\-]*))\[([^\]]+)\]")
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    meas = {(t, m) for t, tab in model.tables.items() for m in tab.measures}
    for m in model.tables["Kennzahlen"].measures.values():
        for quoted, bare, item in ref.findall(m.expression):
            table = quoted or bare
            assert (table, item) in cols or (table, item) in meas or table in ("Kennzahlen",), (m.name, table, item)


def test_unqualified_dax_references_are_measures(model):
    unqualified = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
    names = {m for tab in model.tables.values() for m in tab.measures}
    for m in model.tables["Kennzahlen"].measures.values():
        for item in unqualified.findall(m.expression):
            assert item in names, (m.name, item)


def test_relationships_bind_existing_columns_single_direction(model):
    assert len(model.relationships) == 16
    assert {(r.from_column, r.to_column) for r in model.relationships} == RELATIONSHIPS
    for r in model.relationships:
        ft, fc = r.from_column.split(".", 1)
        tt, tc = r.to_column.split(".", 1)
        assert fc in model.tables[ft].columns and tc in model.tables[tt].columns, (ft, fc, tt, tc)
        assert r.cross_filtering_behavior in (None, "oneDirection"), r.name


def test_relationship_targets_are_dimension_keys(model):
    # the "one" side of every relationship is a dimension table's key column
    dims = {"Datum", "Zeit", "Region", "Energieträger", "Bundesland"}
    for r in model.relationships:
        tt, tc = r.to_column.split(".", 1)
        assert tt in dims and tc.endswith(" Key"), r.name


def test_datum_is_date_table_and_keys_hidden(model):
    datum = model.tables["Datum"]
    assert datum.data_category == "Time" and datum.columns["Datum"].is_key
    for name in ("Erzeugung", "Last", "Preis", "Kapazität"):
        t = model.tables[name]
        for col in t.columns.values():
            if col.name.endswith(" Key"):
                assert col.is_hidden, (name, col.name)


def test_every_key_column_is_hidden_and_not_summarized(model):
    for tname, t in model.tables.items():
        for col in t.columns.values():
            if col.name.endswith(" Key"):
                assert col.is_hidden, (tname, col.name)
                assert col.summarize_by == "none", (tname, col.name)


def test_time_column_format_is_clock_time(model):
    assert model.tables["Zeit"].columns["Uhrzeit"].format_string == "HH:mm"
    assert model.tables["Datum"].columns["Datum"].format_string == "dd.MM.yyyy"


def test_role_and_field_parameter(model):
    assert any(r.name == "Landesbehörde BW" and 'Bundesland[Kürzel] = "BW"' in r.table_permissions.get("Bundesland", "") for r in model.roles)
    fp = model.tables["Kennzahl-Auswahl"]
    assert "ParameterMetadata" in (fp.raw or "")
    assert fp.partition_source and "NAMEOF('Kennzahlen'[Erzeugung (MWh)])" in fp.partition_source


def test_every_field_parameter_entry_is_a_measure(model):
    fp = model.tables["Kennzahl-Auswahl"]
    names = set(re.findall(r"NAMEOF\('Kennzahlen'\[([^\]]+)\]\)", fp.partition_source or ""))
    assert len(names) == 4 and names <= set(model.tables["Kennzahlen"].measures), names


def test_sort_by_columns(model):
    expected = {
        ("Datum", "Monat Name"): "Monat", ("Datum", "Monat Name (EN)"): "Monat",
        ("Datum", "Wochentag"): "Wochentag Nr", ("Datum", "Wochentag (EN)"): "Wochentag Nr",
        ("Zeit", "Tageszeit"): "Tageszeit Nr", ("Zeit", "Tageszeit (EN)"): "Tageszeit Nr",
        ("Energieträger", "Energieträger"): "Sortierung", ("Energieträger", "Energieträger (EN)"): "Sortierung",
        ("Preis", "Preis Klasse (10 €)"): "Preis Klasse Sortierung",
    }
    for (table, col), sort_col in expected.items():
        column = model.tables[table].columns[col]
        assert column.sort_by_column == sort_col, (table, col)
        assert sort_col in model.tables[table].columns, (table, sort_col)


def test_kalender_hierarchy_and_culture(model):
    assert model.tables["Datum"].hierarchies["Kalender"] == ["Jahr", "Quartal", "Monat Name", "Datum"]
    assert model.culture == "de-DE"
    assert model.discourage_implicit_measures
    assert (MODEL_DIR / "cultures" / "de-DE.tmdl").exists()


def test_no_description_property_only_triple_slash():
    # descriptions are written as /// lines; a `description:` property would be a second, conflicting source
    for path in MODEL_DIR.rglob("*.tmdl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            assert not line.strip().startswith("description:"), path.name


def test_no_aggregate_inside_calculate_filter_comparison(model):
    # a boolean CALCULATE filter may not call MAX/MIN (engine error "used in a True/False expression");
    # hoist the aggregate into a VAR and compare against the variable
    cmp_agg = re.compile(r"(?:<=|>=|<>|<|>|=)\s*(?:MAX|MIN)\(|(?:MAX|MIN)\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?:<=|>=|<>|<|>|=)")
    for m in model.tables["Kennzahlen"].measures.values():
        for line in m.expression.splitlines():
            body = re.sub(r"^\s*VAR\s+\w+\s*=\s*", "", line)
            if "CALCULATE" in body:
                assert not cmp_agg.search(body), (m.name, line)
    # the guard itself must bite on the pattern it targets
    assert cmp_agg.search("CALCULATE(SUM(x[a]), d[Datum] <= MAX(d[Datum]))")
    assert cmp_agg.search("CALCULATETABLE(VALUES(x[a]), MIN(d[Datum]) <= d[Datum])")
    assert not cmp_agg.search("CALCULATE(MAX(x[a]), REMOVEFILTERS(d), d[Datum] <= Bis)")
