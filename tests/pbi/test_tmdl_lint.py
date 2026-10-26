import csv
import re
from pathlib import Path

import pytest

from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
MODEL_DIR = Path(__file__).resolve().parents[2] / "powerbi" / "EnergiewendeMonitor.SemanticModel" / "definition"
MEASURES = [
    "Erzeugung (MWh)", "Erzeugung Erneuerbar (MWh)", "EE-Anteil %", "Netzlast (MWh)", "Residuallast (MWh)",
    "Residuallast Minimum (MWh/15 min)", "Residuallast Ø (MWh/15 min)", "Day-Ahead Ø (€/MWh)", "Day-Ahead Max (€/MWh)",
    "Day-Ahead Min (€/MWh)", "Negative Preisstunden", "Preisstunden", "Erzeugung Vorjahr (MWh)", "Erzeugung Δ Vorjahr %",
    "EE-Anteil Vorjahr %", "EE-Anteil Δ Vorjahr (pp)", "Netzlast Vormonat (MWh)", "Netzlast Δ Vormonat %", "Zubau (MW)",
    "Zubau YTD (MW)", "Installierte Leistung (MW)", "Volllaststunden (h)", "Anzahl Einheiten Zubau", "Datenstand", "Zeilen",
    "Datenstand MaStR",
    "KPI Erzeugung", "KPI EE-Anteil", "KPI Day-Ahead Ø", "KPI Negative Preisstunden", "KPI Installierte Leistung",
    "Zielerreichung Photovoltaik %", "Zielerreichung Wind an Land %", "Zielerreichung Wind auf See %", "Datenstand Kopfzeile",
]
KPI_MEASURES = ["KPI Erzeugung", "KPI EE-Anteil", "KPI Day-Ahead Ø", "KPI Negative Preisstunden", "KPI Installierte Leistung"]
TEXT_MEASURES = {"Datenstand", "Datenstand MaStR", "Datenstand Kopfzeile", *KPI_MEASURES}  # text results carry no formatString
# measure -> (carrier of Energieträger[Energieträger], statutory 2030 value in MW)
TARGETS = {
    "Zielerreichung Photovoltaik %": ("Photovoltaik", 215000),
    "Zielerreichung Wind an Land %": ("Wind Onshore", 115000),
    "Zielerreichung Wind auf See %": ("Wind Offshore", 30000),
}
SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "dim_energietraeger.csv"
GROUPS = ["Biomasse", "Wind", "Photovoltaik", "Wasserkraft", "Erdgas", "Steinkohle", "Braunkohle", "Sonstige"]  # stack and sort order
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


def test_all_35_measures_exist_with_format_and_description(model):
    kz = model.tables["Kennzahlen"].measures
    missing = [m for m in MEASURES if m not in kz]
    assert not missing, missing
    assert len(MEASURES) == len(kz) == 35, sorted(set(kz) - set(MEASURES))
    for name in MEASURES:
        m = kz[name]
        assert m.description, name
        if name in TEXT_MEASURES:
            assert m.format_string is None, name
        else:
            assert m.format_string, name


def test_dax_references_resolve(model):
    # a qualified reference is `Table[Column]` or `'Table name'[Column]`; the table must be a bare identifier or quoted
    ref = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
    cols = {(t, c) for t, tab in model.tables.items() for c in tab.columns}
    meas = {(t, m) for t, tab in model.tables.items() for m in tab.measures}
    for m in model.tables["Kennzahlen"].measures.values():
        for quoted, bare, item in ref.findall(m.expression):
            table = quoted or bare
            assert (table, item) in cols or (table, item) in meas or table in ("Kennzahlen",), (m.name, table, item)


def test_dax_quotes_table_names_that_are_not_plain_ascii(model):
    # DAX accepts a bare table name only for ASCII letters, digits and underscores; umlauts, spaces and hyphens
    # need quotes (Desktop rejects 'Energieträger[...]' with "Invalid token"), and Python's \w would let them pass
    special = [t for t in model.tables if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t)]
    bare = re.compile(r"(?<![\w'])(" + "|".join(map(re.escape, special)) + r")(?=\s*[\[),])")
    expressions = [(m.name, m.expression) for tab in model.tables.values() for m in tab.measures.values()]
    expressions += [(f"{r.name}/{t}", e) for r in model.roles for t, e in r.table_permissions.items()]
    expressions += [(f"{t.name}[{c.name}]", c.expression) for t in model.tables.values() for c in t.columns.values() if c.expression]
    expressions += [(t.name, t.partition_source or "") for t in model.tables.values()]
    offenders = [(name, hit) for name, expr in expressions for hit in bare.findall(expr)]
    assert not offenders, offenders

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


NUMERIC = ("int64", "double", "decimal")
NOT_ADDITIVE = re.compile(r"€/MWh|bestand", re.IGNORECASE)  # prices and stock levels: a sum over hours, months or carriers means nothing


def test_prices_and_stock_levels_are_not_summed_and_desktop_keeps_it(model):
    # Desktop recomputes summarizeBy when it re-types a column marked SummarizationSetBy = Automatic: on the first save it turned
    # the prices and stock levels from none to sum (decimal -> double). A deliberate none on a number is therefore marked User,
    # the value Desktop writes for a choice made by hand.
    matched = []
    for tname, t in model.tables.items():
        for col in t.columns.values():
            if col.data_type not in NUMERIC:
                continue
            if NOT_ADDITIVE.search(col.name):
                matched.append(f"{tname}.{col.name}")
                assert col.summarize_by == "none", (tname, col.name)
            if col.summarize_by == "none":
                assert col.annotations.get("SummarizationSetBy") == "User", (tname, col.name, col.annotations)
    assert len(matched) == 8, matched  # Day-Ahead in Preis and Last Stunde, Min and Ø in Preisphasen, four stock columns


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
        ("Energieträger", "Gruppe"): "Gruppe Sortierung",
        ("Preis", "Preis Klasse (10 €)"): "Preis Klasse Sortierung",
    }
    for (table, col), sort_col in expected.items():
        column = model.tables[table].columns[col]
        assert column.sort_by_column == sort_col, (table, col)
        assert sort_col in model.tables[table].columns, (table, sort_col)


def test_calculated_columns_and_sort_keys_have_no_circular_dependency(model):
    # The engine computes a calculated column after every column and measure its DAX reads, and a column after its
    # sort-by column. A cycle through either kind of edge fails every table on load ("A circular dependency was
    # detected"), and neither the TMDL parser nor TOM reports it: a sort key must not read the column it sorts.
    ref = re.compile(r"(?:'([^']+)'|(?<![\w\]'])([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
    unqualified = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")
    measure_table = {m: t for t, tab in model.tables.items() for m in tab.measures}

    def reads(table, expression):
        found = {(quoted or bare, item) for quoted, bare, item in ref.findall(expression)}
        for item in unqualified.findall(expression):
            if item in measure_table:
                found.add((measure_table[item], item))
            elif item in model.tables[table].columns:
                found.add((table, item))
        return found

    edges = {}
    for t, tab in model.tables.items():
        for name, col in tab.columns.items():
            edges[(t, name)] = (reads(t, col.expression) if col.expression else set()) | (
                {(t, col.sort_by_column)} if col.sort_by_column else set())
        for name, m in tab.measures.items():
            edges[(t, name)] = reads(t, m.expression)
    state, path = {}, []

    def visit(node):
        state[node] = "open"
        path.append(node)
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == "open":
                cycle = path[path.index(nxt):] + [nxt]
                pytest.fail("circular dependency: " + " -> ".join(f"{t}[{c}]" for t, c in cycle))
            if nxt not in state:
                visit(nxt)
        state[node] = "done"
        path.pop()

    for node in sorted(edges):
        if node not in state:
            visit(node)


def test_kalender_hierarchy_and_culture(model):
    assert model.tables["Datum"].hierarchies["Kalender"] == ["Jahr", "Quartal", "Monat Name", "Datum"]
    assert model.culture == "de-DE"
    assert model.discourage_implicit_measures
    assert (MODEL_DIR / "cultures" / "de-DE.tmdl").exists()


def test_monatsanfang_is_a_date_for_the_month_axes(model):
    # the axis of the monthly charts and the drillthrough field: as a date the axis is continuous; on the text column
    # Jahr-Monat Desktop kept about 20 px a month and scrolled
    column = model.tables["Datum"].columns["Monatsanfang"]
    assert column.expression == "DATE('Datum'[Jahr], 'Datum'[Monat], 1)"
    assert (column.data_type, column.format_string, column.summarize_by, column.is_hidden) == ("dateTime", "MMM yyyy", "none", False)
    assert column.description


def test_diagram_places_every_table_once_without_overlap(model):
    # the model view of the README: dimensions above the facts, so the relationship lines run between two rows of tables;
    # checked on what Desktop keeps when it saves the file (names, positions, sizes)
    import json
    diagram = json.loads((MODEL_DIR.parent / "diagramLayout.json").read_text(encoding="utf-8"))["diagrams"][0]
    nodes = {n["nodeIndex"]: (n["location"]["x"], n["location"]["y"], n["size"]["width"], n["size"]["height"]) for n in diagram["nodes"]}
    assert len(diagram["nodes"]) == len(nodes) and set(nodes) == set(model.tables)
    boxes = list(nodes.items())
    for i, (a, (ax, ay, aw, ah)) in enumerate(boxes):
        for b, (bx, by, bw, bh) in boxes[i + 1:]:
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, (a, b)
    dimensions, facts = {"Datum", "Zeit", "Region", "Energieträger", "Bundesland"}, {"Erzeugung", "Last", "Preis", "Last Stunde",
                                                                                      "Kapazität", "Preisphasen"}
    assert max(nodes[t][1] + nodes[t][3] for t in dimensions) < min(nodes[t][1] for t in facts)


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


def test_volllaststunden_are_blank_unless_all_bundeslaender_are_visible(model):
    # the generation has no relationship to Bundesland: under a state selection or the RLS role the ratio would mix a
    # national numerator with a state denominator. 18 = rows of dim_bundesland (16 Länder, AWZ, Unbekannt).
    m = model.tables["Kennzahlen"].measures["Volllaststunden (h)"]
    flat = re.sub(r"\s+", " ", m.expression)
    assert flat.startswith("IF( ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18, BLANK(),"), flat[:200]
    assert "national only" in m.description.lower() and "RLS" in m.description


def test_renewable_generation_respects_an_outer_kategorie_filter(model):
    m = model.tables["Kennzahlen"].measures["Erzeugung Erneuerbar (MWh)"]
    assert "KEEPFILTERS('Energieträger'[Kategorie] = \"Erneuerbar\")" in m.expression


# --- Leitstand additions: KPI display text, 2030 target measures, carrier groups ----------------------------------------


# a filter context without data must show an empty tile, not a bare unit or a zero text
KPI_BLANK_GUARD = re.compile(r"IF\(ISBLANK\(Wert\),\s*BLANK\(\),\s*FORMAT\(Wert,")


def test_kpi_blank_guard_pattern_rejects_a_missing_or_wrong_guard():
    assert KPI_BLANK_GUARD.search('RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "#,0", "de-DE") & " h")')
    for broken in ('RETURN FORMAT(Wert, "#,0", "de-DE") & " h"',  # no guard: an empty filter shows a bare unit
                   'RETURN IF(ISBLANK(Wert), "0 h", FORMAT(Wert, "#,0", "de-DE") & " h")',  # zero text instead of an empty tile
                   'RETURN IF(ISBLANK(Wert), FORMAT(Wert, "#,0", "de-DE"), BLANK())'):  # branches swapped
        assert not KPI_BLANK_GUARD.search(broken), broken


def test_kpi_measures_are_display_only_text_in_the_german_locale(model):
    kz = model.tables["Kennzahlen"].measures
    assert sorted(n for n in kz if n.startswith("KPI ")) == sorted(KPI_MEASURES)
    for name in KPI_MEASURES:
        m = kz[name]
        # the explicit locale is the point: visuals format numbers by the viewer's setting, FORMAT(..., "de-DE") does not
        assert 'FORMAT(Wert, "' in m.expression and '", "de-DE")' in m.expression, name
        assert KPI_BLANK_GUARD.search(m.expression), name
        assert m.format_string is None, name
        assert "de-DE" in m.description and "display-only" in m.description.lower(), name
        assert "calculation" in m.description.lower(), name
        formatted = re.search(r"\[([^\]]+)\]", m.expression).group(1)  # the measure the text is made from
        assert formatted in m.description, name
    # display text feeds no calculation
    display = [f"[{n}]" for n in (*KPI_MEASURES, "Datenstand Kopfzeile")]
    for name, m in kz.items():
        assert not any(ref in m.expression for ref in display), name


def test_target_measures_carry_the_national_guard_their_carrier_and_constant(model):
    kz = model.tables["Kennzahlen"].measures
    flat = lambda m: re.sub(r"\s+", " ", m.expression)  # noqa: E731
    volllast = flat(kz["Volllaststunden (h)"])
    guard = volllast[: volllast.index("BLANK(),") + len("BLANK(),")]  # IF( ISFILTERED(...) || ... < 18, BLANK(),
    assert guard == "IF( ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18, BLANK(),"
    for name, (carrier, megawatt) in TARGETS.items():
        m = kz[name]
        assert flat(m).startswith(guard), name
        assert (f"DIVIDE(CALCULATE([Installierte Leistung (MW)], REMOVEFILTERS('Energieträger'), "
                f"'Energieträger'[Energieträger] = \"{carrier}\"), {megawatt})") in flat(m), name
        assert m.format_string == "0 %", name
        assert "national" in m.description.lower() and "RLS" in m.description, name
        assert "2030" in m.description and "carrier, group and category" in m.description, name
    # the source with paragraph, as read on gesetze-im-internet.de
    assert "EEG 2023 § 4 Nr. 3 Buchst. d" in kz["Zielerreichung Photovoltaik %"].description
    assert "EEG 2023 § 4 Nr. 1 Buchst. d" in kz["Zielerreichung Wind an Land %"].description
    assert "WindSeeG § 1 Abs. 2" in kz["Zielerreichung Wind auf See %"].description


def test_datenstand_kopfzeile_is_one_german_line_over_both_sources(model):
    m = model.tables["Kennzahlen"].measures["Datenstand Kopfzeile"]
    assert "Erzeugung[Zeitstempel UTC]" in m.expression and "'Kapazität'[Datum Key]" in m.expression
    assert m.expression.count("REMOVEFILTERS()") == 2 and m.expression.count('"de-DE"') == 2
    assert m.format_string is None


def split_dax_args(call: str) -> list[str]:
    """The top-level arguments of `NAME(a, b, ...)`; commas inside quotes, brackets and nested calls are kept."""
    body = call[call.index("(") + 1 : call.rstrip().rindex(")")]
    args, buf, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            buf.append(ch)
            quote = None if ch == quote else quote  # a doubled quote closes and reopens on the next character
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    args.append("".join(buf).strip())
    return args


def parse_switch(expression: str):
    """(subject, [(value, result), ...], default or None) of `SWITCH(subject, v1, r1, ..., default)`; strings and integers."""
    assert expression.startswith("SWITCH("), expression[:30]
    subject, *rest = split_dax_args(expression)
    value = lambda text: text[1:-1] if text.startswith('"') else int(text)  # noqa: E731
    default = value(rest.pop()) if len(rest) % 2 else None
    return subject, [(value(k), value(v)) for k, v in zip(rest[0::2], rest[1::2], strict=True)], default


def test_gruppe_folds_the_twelve_seed_carriers_into_eight_groups(model):
    table = model.tables["Energieträger"]
    column, key = table.columns["Gruppe"], table.columns["Gruppe Sortierung"]
    assert column.data_type == "string" and column.summarize_by == "none" and not column.is_hidden
    assert column.expression, "Gruppe is a calculated column: `column Gruppe = <DAX>`"
    with SEED.open(encoding="utf-8", newline="") as fh:
        carriers = [r["name_de"] for r in csv.DictReader(fh)]
    assert len(carriers) == 12
    # the carrier-to-group mapping lives in the sort key (carrier -> number); Gruppe only names the numbers
    key_subject, key_pairs, key_default = parse_switch(key.expression)
    assert key_subject == "'Energieträger'[Energieträger]"
    number = dict(key_pairs)
    assert len(number) == len(key_pairs), "a carrier is listed twice"
    assert set(number) <= set(carriers), sorted(set(number) - set(carriers))
    subject, pairs, default = parse_switch(column.expression)
    assert subject == "'Energieträger'[Gruppe Sortierung]"
    name = dict(pairs)
    mapping = {carrier: name.get(n, default) for carrier, n in number.items()}
    assert mapping == {"Biomasse": "Biomasse", "Wind Onshore": "Wind", "Wind Offshore": "Wind", "Photovoltaik": "Photovoltaik",
                       "Wasserkraft": "Wasserkraft", "Erdgas": "Erdgas", "Steinkohle": "Steinkohle", "Braunkohle": "Braunkohle"}
    assert name.get(key_default, default) == "Sonstige"
    # what the default branch catches: exactly these four carriers of the seed
    assert set(carriers) - set(number) == {"Kernenergie", "Pumpspeicher", "Sonstige Erneuerbare", "Sonstige Konventionelle"}
    assert {mapping.get(c, "Sonstige") for c in carriers} == set(GROUPS)


def test_gruppe_sorts_by_the_hidden_sort_key_in_stack_order(model):
    table = model.tables["Energieträger"]
    gruppe, key = table.columns["Gruppe"], table.columns["Gruppe Sortierung"]
    assert gruppe.sort_by_column == "Gruppe Sortierung"
    assert key.is_hidden and key.data_type == "int64" and key.format_string == "0" and key.summarize_by == "none"
    assert key.expression, "Gruppe Sortierung is a calculated column"
    # Gruppe names the numbers 1..7 in stack order; Sonstige is the default of both: number 8, name Sonstige
    subject, pairs, default = parse_switch(gruppe.expression)
    assert subject == "'Energieträger'[Gruppe Sortierung]"
    by_number = sorted(pairs)
    assert [n for n, _ in by_number] == list(range(1, len(GROUPS)))
    assert [g for _, g in by_number] + [default] == GROUPS
    _, key_pairs, key_default = parse_switch(key.expression)
    assert key_default == len(GROUPS) and len(GROUPS) not in dict(pairs)
    # every number the key hands out has a name, so no carrier lands in Sonstige by accident
    assert {n for _, n in key_pairs} == set(range(1, len(GROUPS)))
