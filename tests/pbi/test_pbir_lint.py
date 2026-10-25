import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from tools.pbi.pbir import ROLES, default_alt_text, iter_fields, load_report
from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2] / "powerbi"
REPORT = ROOT / "EnergiewendeMonitor.Report" / "definition"
MODEL = ROOT / "EnergiewendeMonitor.SemanticModel" / "definition"
PAGES = ["Überblick", "Erzeugung & Last", "Preise", "Ausbau", "Datenqualität & Quellen"]
CATEGORIES = {"Erneuerbar", "Konventionell"}  # Energieträger[Kategorie] values (kategorie_de in the dimension)
DRILLTHROUGH_FIELD = ("Datum", "Jahr-Monat", "Column")
BOOKMARK_FIELD = ("Energieträger", "Kategorie", "Column")
PHASES_TITLE = "Längste negative Preisphasen"
TEMPLATE_ALT_PHRASES = ("CPU", "Distinct queries", "query duration", "Scatter plot of", "SQL")


@pytest.fixture(scope="module")
def report():
    return load_report(REPORT)


@pytest.fixture(scope="module")
def model():
    return load_model(MODEL)


# --- checks, written as functions returning problems so that the mutation tests below can prove they bite ---------


def find_values(obj, key):
    """Every value stored under `key` anywhere below obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from find_values(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from find_values(v, key)


def field_problems(raw, model, where=""):
    """Every Column / Measure node must name a column / measure of an existing table (kind-checked)."""
    out = []
    for entity, prop, kind in iter_fields(raw):
        table = model.tables.get(entity)
        if table is None:
            out.append(f"{where}: unknown table {entity!r}")
            continue
        pool = table.columns if kind == "Column" else table.measures
        if prop not in pool:
            out.append(f"{where}: {entity}[{prop}] is used as a {kind} but the model has no such {kind.lower()}")
    return out


def role_problems(visual, where=""):
    allowed = ROLES.get(visual.visual_type)
    if allowed is None:
        return [f"{where}: visual type {visual.visual_type!r} is not in the allowed set"]
    return [f"{where}: role {r!r} is not valid for {visual.visual_type}" for r in sorted(visual.roles() - allowed)]


def drillthrough_problems(page, model):
    out = field_problems(page.raw, model, page.display_name)
    binding = page.raw.get("pageBinding") or {}
    if page.raw.get("type") != "Drillthrough" or binding.get("type") != "Drillthrough":
        out.append("page is not a drillthrough page")
    filters = {f.get("name"): f for f in page.raw.get("filterConfig", {}).get("filters", [])}
    params = binding.get("parameters", [])
    if len(params) != 1:
        out.append(f"expected one drillthrough parameter, found {len(params)}")
    for param in params:
        if list(iter_fields(param.get("fieldExpr", {}))) != [DRILLTHROUGH_FIELD]:
            out.append(f"drillthrough field is {list(iter_fields(param.get('fieldExpr', {})))}, expected {DRILLTHROUGH_FIELD}")
        flt = filters.get(param.get("boundFilter"))
        if flt is None:
            out.append(f"boundFilter {param.get('boundFilter')!r} names no page filter")
            continue
        if flt.get("field") != param.get("fieldExpr"):
            out.append("the bound filter filters another field than the parameter")
        if flt.get("type") != "Categorical" or flt.get("howCreated") != "Drillthrough":
            out.append("the bound filter is not a Categorical Drillthrough filter")
    return out


def bookmark_problems(bm, model, page_ids):
    out = field_problems(bm, model, bm.get("displayName", "?"))
    state = bm.get("explorationState", {})
    if state.get("activeSection") not in page_ids:
        out.append(f"activeSection {state.get('activeSection')!r} is not a page")
    for section, content in state.get("sections", {}).items():
        if section not in page_ids:
            out.append(f"section {section!r} is not a page")
        filters = content.get("filters", {}).get("byExpr", [])
        if not filters:
            out.append(f"section {section!r} has no filter")
        for flt in filters:
            if list(iter_fields(flt.get("expression", {}))) != [BOOKMARK_FIELD]:
                out.append(f"bookmark filter targets {list(iter_fields(flt.get('expression', {})))}, expected {BOOKMARK_FIELD}")
            if list(iter_fields(flt.get("filter", {}))) != [BOOKMARK_FIELD]:
                out.append("the filter condition targets another column than the filter expression")
            values = {lit["Literal"]["Value"].strip("'") for rows in find_values(flt, "Values") for tup in rows for lit in tup}
            if not values or not values <= CATEGORIES or values != {bm.get("displayName")}:
                out.append(f"bookmark {bm.get('displayName')!r} filters on {sorted(values)}")
    return out


def phases_problems(visual, model):
    """The ten longest runs: sorted by Stunden descending and a TopN 10 filter on the runs ranked by Stunden."""
    out = field_problems(visual.raw, model, PHASES_TITLE)
    sort = visual.raw.get("visual", {}).get("query", {}).get("sortDefinition", {}).get("sort", [])
    if len(sort) != 1 or sort[0].get("direction") != "Descending" or list(iter_fields(sort[0])) != [("Preisphasen", "Stunden", "Column")]:
        out.append("not sorted by Preisphasen[Stunden] descending")
    topn = [f for f in visual.raw.get("filterConfig", {}).get("filters", []) if f.get("type") == "TopN"]
    if len(topn) != 1:
        out.append(f"expected one TopN filter, found {len(topn)}")
        return out
    flt = topn[0]
    if list(iter_fields(flt.get("field", {}))) != [("Preisphasen", "Start (lokal)", "Column")]:
        out.append("the TopN filter does not target the runs (Preisphasen[Start (lokal)])")
    if list(find_values(flt, "Top")) != [10]:
        out.append("the TopN filter does not keep 10 items")
    order = list(find_values(flt, "OrderBy"))
    if len(order) != 1 or [o.get("Direction") for o in order[0]] != [2] or \
            ("Preisphasen", "Stunden", "Column") not in list(iter_fields(flt)):
        out.append("the TopN filter does not rank by Preisphasen[Stunden] descending")
    return out


def by_title(report, page_name, title):
    page = next(p for p in report.pages if p.display_name == page_name)
    return next(v for v in page.visuals if v.title == title)


# --- the lint ------------------------------------------------------------------------------------------------------


def test_five_pages_in_order_and_16_9(report):
    assert [p.display_name for p in report.pages] == PAGES
    for p in report.pages:
        assert (p.width, p.height) == (1280, 720), p.display_name


def test_every_bound_field_exists_in_the_model_with_the_right_kind(report, model):
    problems = []
    for p in report.pages:
        problems += field_problems(p.raw, model, p.display_name)
        for v in p.visuals:
            problems += field_problems(v.raw, model, f"{p.display_name}/{v.name}")
    for bm in report.bookmarks:
        problems += field_problems(bm, model, bm["displayName"])
    assert not problems, problems


def test_roles_are_valid_for_the_visual_type(report):
    problems = [msg for p in report.pages for v in p.visuals for msg in role_problems(v, f"{p.display_name}/{v.name}")]
    assert not problems, problems


def test_no_map_or_custom_visuals(report):
    for p in report.pages:
        for v in p.visuals:
            assert v.visual_type not in ("map", "filledMap", "azureMap", "shapeMap"), (p.display_name, v.name)
            assert not v.visual_type.startswith("PBI_CV_"), v.visual_type


def test_page_contents_match_the_spec(report):
    expected = {
        "Überblick": {"slicer": 4, "card": 5, "stackedAreaChart": 1, "lineChart": 2},
        "Erzeugung & Last": {"slicer": 1, "lineChart": 2, "pivotTable": 1, "columnChart": 1},
        "Preise": {"slicer": 1, "clusteredColumnChart": 2, "scatterChart": 1, "tableEx": 1},
        "Ausbau": {"slicer": 2, "clusteredBarChart": 1, "columnChart": 1, "tableEx": 1},
        "Datenqualität & Quellen": {"card": 3, "tableEx": 1, "textbox": 2},
    }
    for p in report.pages:
        assert dict(Counter(v.visual_type for v in p.visuals)) == expected[p.display_name], p.display_name


def test_key_bindings(report):
    ueb = next(p for p in report.pages if p.display_name == "Überblick")
    cards = {tuple(f[:2]) for v in ueb.visuals if v.visual_type == "card" for f in v.bound_fields()}
    assert cards == {("Kennzahlen", n) for n in ("Erzeugung (MWh)", "EE-Anteil %", "Day-Ahead Ø (€/MWh)", "Negative Preisstunden", "Installierte Leistung (MW)")}
    dq = next(p for p in report.pages if p.display_name == "Datenqualität & Quellen")
    dq_cards = {tuple(f[:2]) for v in dq.visuals if v.visual_type == "card" for f in v.bound_fields()}
    assert dq_cards == {("Kennzahlen", n) for n in ("Datenstand", "Datenstand MaStR", "Zeilen")}
    # the histogram counts price hours, not the rows of all fact tables
    hist = by_title(report, "Preise", "Verteilung der Stundenpreise (Klassen à 10 €)")
    assert ("Kennzahlen", "Preisstunden", "Measure") in hist.bound_fields()
    assert ("Kennzahlen", "Zeilen", "Measure") not in hist.bound_fields()


def test_field_parameter_chart_shows_its_legend(report):
    v = by_title(report, "Überblick", "Kennzahl-Auswahl je Monat")
    assert ("Kennzahl-Auswahl", "Kennzahl-Auswahl Fields", "Column") in v.bound_fields()
    legend = v.raw["visual"]["objects"]["legend"][0]["properties"]
    assert legend["show"]["expr"]["Literal"]["Value"] == "true"


def test_ueberblick_has_a_kategorie_slicer_for_readers(report):
    ueb = next(p for p in report.pages if p.display_name == "Überblick")
    slicers = [v for v in ueb.visuals if v.visual_type == "slicer" and v.bound_fields() == [BOOKMARK_FIELD]]
    assert len(slicers) == 1


def test_matrix_is_a_heatmap_and_bars_are_sorted(report):
    matrix = by_title(report, "Erzeugung & Last", "Residuallast Ø nach Tageszeit und Wochentag")
    fill = matrix.raw["visual"]["objects"]["values"][0]["properties"]["backColor"]["solid"]["color"]["expr"]["FillRule"]
    assert list(iter_fields(fill["Input"])) == [("Kennzahlen", "Residuallast Ø (MWh/15 min)", "Measure")]
    gradient = fill["FillRule"]["linearGradient2"]
    assert gradient["min"]["color"]["Literal"]["Value"] == "'#F7F7F4'" and gradient["max"]["color"]["Literal"]["Value"] == "'#1F5FA8'"
    bar = by_title(report, "Ausbau", "Installierte Leistung nach Bundesland (MW)")
    sort = bar.raw["visual"]["query"]["sortDefinition"]["sort"]
    assert len(sort) == 1 and sort[0]["direction"] == "Descending"
    assert list(iter_fields(sort[0])) == [("Kennzahlen", "Installierte Leistung (MW)", "Measure")]


def test_longest_negative_price_runs_are_sorted_and_limited(report, model):
    assert phases_problems(by_title(report, "Preise", PHASES_TITLE), model) == []


def test_visuals_sit_inside_the_canvas_and_do_not_overlap(report):
    for p in report.pages:
        boxes = [(v.name, v.raw["position"]) for v in p.visuals]
        for name, pos in boxes:
            assert pos["x"] >= 0 and pos["y"] >= 0, (p.display_name, name)
            assert pos["x"] + pos["width"] <= p.width and pos["y"] + pos["height"] <= p.height, (p.display_name, name)
        for i, (a, pa) in enumerate(boxes):
            for b, pb in boxes[i + 1:]:
                apart = (pa["x"] + pa["width"] <= pb["x"] or pb["x"] + pb["width"] <= pa["x"]
                         or pa["y"] + pa["height"] <= pb["y"] or pb["y"] + pb["height"] <= pa["y"])
                assert apart, (p.display_name, a, b)


def test_alt_text_is_ours_and_none_leaks_from_the_templates(report):
    for p in report.pages:
        for v in p.visuals:
            text = json.dumps(v.raw, ensure_ascii=False)
            for phrase in TEMPLATE_ALT_PHRASES:
                assert phrase not in text, (p.display_name, v.name, phrase)
            if v.visual_type in ("slicer", "textbox"):
                assert v.alt_text is None, (p.display_name, v.name)
            else:
                assert v.alt_text == default_alt_text(v.visual_type, v.title) and v.alt_text, (p.display_name, v.name)


def test_attributions_and_links_present(report):
    page = next(p for p in report.pages if p.display_name == "Datenqualität & Quellen")
    text = json.dumps([v.raw for v in page.visuals], ensure_ascii=False)
    assert "Bundesnetzagentur | SMARD.de" in text
    assert "Marktstammdatenregister der Bundesnetzagentur" in text and "dl-de/by-2-0" in text
    assert "github.com/HARISPAARTAN/energiewende-monitor" in text and "harispaartan.github.io" in text


def test_drillthrough_resolves_against_the_model(report, model):
    el = next(p for p in report.pages if p.display_name == "Erzeugung & Last")
    assert el.drillthrough_fields == [{"Column": {"Expression": {"SourceRef": {"Entity": "Datum"}}, "Property": "Jahr-Monat"}}]
    assert drillthrough_problems(el, model) == []


def test_bookmarks_resolve_against_the_model(report, model):
    assert {b["displayName"] for b in report.bookmarks} == {"Erneuerbar", "Konventionell"}
    assert sorted(b["name"] for b in report.bookmarks) == sorted(report.bookmark_items)
    page_ids = {p.name for p in report.pages}
    problems = [msg for b in report.bookmarks for msg in bookmark_problems(b, model, page_ids)]
    assert not problems, problems


def test_theme_registered_and_colours(report):
    theme = json.loads((ROOT / "EnergiewendeMonitor.Report" / "StaticResources" / "RegisteredResources" / "energiewende.json").read_text(encoding="utf-8"))
    assert theme["background"].upper() == "#F7F7F4" and theme["foreground"].upper() == "#14181D"
    assert report.theme_name == "energiewende.json"


# --- the lint must bite: each mutation of a good report has to be reported -------------------------------------------


def _visual(report, page_name, title):
    return copy.deepcopy(by_title(report, page_name, title))


def test_mutation_measure_node_turned_into_column_is_caught(report, model):
    v = _visual(report, "Überblick", "Erzeugung")
    assert field_problems(v.raw, model) == []
    node = v.raw["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]
    node["Column"] = node.pop("Measure")
    assert field_problems(v.raw, model)


def test_mutation_unknown_column_in_objects_is_caught(report, model):
    v = _visual(report, "Überblick", "Erzeugung nach Energieträger je Monat (MWh)")
    assert ("Energieträger", "Farbe", "Column") in v.bound_fields() and field_problems(v.raw, model) == []
    for ref in find_values(v.raw["visual"]["objects"], "Column"):
        if ref.get("Property") == "Farbe":
            ref["Property"] = "Farbe2"
    assert field_problems(v.raw, model)


def test_mutation_drillthrough_field_is_caught(report, model):
    page = copy.deepcopy(next(p for p in report.pages if p.display_name == "Erzeugung & Last"))
    for ref in find_values(page.raw, "Column"):
        ref["Property"] = "Jahr"  # a real column of Datum, but not the one the spec asks for
    assert drillthrough_problems(page, model)


def test_mutation_drillthrough_binding_is_caught(report, model):
    page = copy.deepcopy(next(p for p in report.pages if p.display_name == "Erzeugung & Last"))
    del page.raw["filterConfig"]
    page.raw["pageBinding"]["parameters"][0]["boundFilter"] = "nope"
    assert drillthrough_problems(page, model)


def test_mutation_bookmark_column_is_caught(report, model):
    page_ids = {p.name for p in report.pages}
    bm = copy.deepcopy(report.bookmarks[0])
    assert bookmark_problems(bm, model, page_ids) == []
    for ref in find_values(bm, "Column"):
        ref["Property"] = "Sortierung"
    assert bookmark_problems(bm, model, page_ids)


def test_mutation_bookmark_value_is_caught(report, model):
    page_ids = {p.name for p in report.pages}
    bm = copy.deepcopy(report.bookmarks[0])
    for rows in find_values(bm, "Values"):
        rows[0][0]["Literal"]["Value"] = "'Atom'"
    assert bookmark_problems(bm, model, page_ids)


def test_mutation_role_outside_the_visual_type_is_caught(report):
    v = _visual(report, "Überblick", "Erzeugung")
    assert role_problems(v) == []
    state = v.raw["visual"]["query"]["queryState"]
    state["Y"] = state.pop("Values")
    assert role_problems(v)


def test_mutation_missing_sort_or_topn_is_caught(report, model):
    v = _visual(report, "Preise", PHASES_TITLE)
    assert phases_problems(v, model) == []
    no_sort = copy.deepcopy(v)
    del no_sort.raw["visual"]["query"]["sortDefinition"]
    assert phases_problems(no_sort, model)
    no_topn = copy.deepcopy(v)
    del no_topn.raw["filterConfig"]
    assert phases_problems(no_topn, model)
    top_20 = copy.deepcopy(v)
    for sub in find_values(top_20.raw, "Query"):
        sub["Top"] = 20
    assert phases_problems(top_20, model)
