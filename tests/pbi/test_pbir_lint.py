import copy
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from tools.pbi.build_report import Colours
from tools.pbi.pbir import ROLES, default_alt_text, iter_fields, load_report, stable_name
from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2] / "powerbi"
REPORT = ROOT / "EnergiewendeMonitor.Report" / "definition"
MODEL = ROOT / "EnergiewendeMonitor.SemanticModel" / "definition"
THEME_FILE = ROOT / "EnergiewendeMonitor.Report" / "StaticResources" / "RegisteredResources" / "energiewende.json"
SPEC = json.loads((ROOT.parent / "tools" / "pbi" / "pages.json").read_text(encoding="utf-8"))
TOKENS = {name: code.upper() for name, code in SPEC["tokens"].items()}
PALETTE = {name: code.upper() for name, code in SPEC["palette"].items()}
PAGES = ["Überblick", "Erzeugung & Last", "Preise", "Ausbau", "Datenqualität & Quellen"]
CATEGORIES = {"Erneuerbar", "Konventionell"}  # Energieträger[Kategorie] values (kategorie_de in the dimension)
DRILLTHROUGH_FIELD = ("Datum", "Monatsanfang", "Column")
BOOKMARK_FIELD = ("Energieträger", "Kategorie", "Column")
GROUP_FIELD = ("Energieträger", "Gruppe", "Column")
PHASES_TITLE = "Längste negative Preisphasen"
TEMPLATE_ALT_PHRASES = ("CPU", "Distinct queries", "query duration", "Scatter plot of", "SQL")
CHROME_KEYS = ["brand", "nav0", "nav1", "nav2", "nav3", "nav4", "filler", "footer", "title", "stand"]
KPI_ORDER = ["KPI Erzeugung", "KPI EE-Anteil", "KPI Day-Ahead Ø", "KPI Negative Preisstunden", "KPI Installierte Leistung"]
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
URL_IN_TEXT = re.compile(r"https?://")
MONTH_AXIS = ("Datum", "Monatsanfang", "Column")
ADDRESSES = {"github.com/HARISPAARTAN/energiewende-monitor", "harispaartan.github.io", "www.govdata.de/dl-de/by-2-0"}


def chrome_names(page):
    return {key: stable_name(page.name, "chrome", key) for key in CHROME_KEYS}


def is_chrome(page, visual):
    return visual.name in chrome_names(page).values()


def content(page):
    """The page's own visuals: everything that is not navigation panel or header."""
    return [v for v in page.visuals if not is_chrome(page, v)]


def lit(prop):
    """The literal behind {"expr": {"Literal": {"Value": ...}}}, quotes kept."""
    return prop["expr"]["Literal"]["Value"]


def solid(prop):
    """The upper-case hex behind {"solid": {"color": {"expr": {"Literal": {"Value": "'#RRGGBB'"}}}}}."""
    return lit(prop["solid"]["color"]).strip("'").upper()


def props(visual, name, state=None, container=False):
    """The properties of the entry of an objects / visualContainerObjects group with this state selector (None: no selector)."""
    group = visual.raw["visual"].get("visualContainerObjects" if container else "objects", {}).get(name, [])
    for entry in group:
        if (entry.get("selector") or {}).get("id") == state:
            return entry["properties"]
    return {}


def runs_of(visual):
    """(paragraph index, run) of a text box."""
    paragraphs = visual.raw["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    return [(i, run) for i, paragraph in enumerate(paragraphs) for run in paragraph["textRuns"]]


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
    expected = {  # the page's own visuals; navigation panel and header are checked by test_every_page_has_the_chrome
        "Überblick": {"slicer": 4, "card": 5, "stackedAreaChart": 1, "lineChart": 2, "gauge": 3},
        "Erzeugung & Last": {"slicer": 1, "lineChart": 2, "pivotTable": 1, "columnChart": 1},
        "Preise": {"slicer": 1, "clusteredColumnChart": 2, "scatterChart": 1, "tableEx": 1},
        "Ausbau": {"slicer": 2, "clusteredBarChart": 1, "columnChart": 1, "tableEx": 1},
        "Datenqualität & Quellen": {"card": 3, "tableEx": 1, "textbox": 2},
    }
    for p in report.pages:
        assert dict(Counter(v.visual_type for v in content(p))) == expected[p.display_name], p.display_name
        assert len(p.visuals) == len(content(p)) + len(CHROME_KEYS), p.display_name
        # the names follow the spec order (the gauges are appended at the end of Überblick, so the older names stay)
        spec_page = next(s for s in SPEC["pages"] if s["displayName"] == p.display_name)
        assert {v.name for v in content(p)} == {stable_name(p.name, str(i)) for i in range(len(spec_page["visuals"]))}, p.display_name
        by_name = {v.name: v for v in p.visuals}
        assert [by_name[stable_name(p.name, str(i))].visual_type for i in range(len(spec_page["visuals"]))] == \
            [s["type"] for s in spec_page["visuals"]], p.display_name


def test_key_bindings(report):
    ueb = next(p for p in report.pages if p.display_name == "Überblick")
    cards = sorted((v for v in content(ueb) if v.visual_type == "card"), key=lambda v: v.raw["position"]["x"])
    # the five KPI texts, in this order, behind the cards titled as before
    assert [v.title for v in cards] == ["Erzeugung", "EE-Anteil", "Day-Ahead Ø", "Negative Preisstunden", "Installierte Leistung"]
    assert [v.bound_fields() for v in cards] == [[("Kennzahlen", n, "Measure")] for n in KPI_ORDER]
    for v in cards:  # 20D, not 24D: `92,87 €/MWh` would nearly fill the 200 px tile at 24D (about 197 of 200 px in Segoe UI Semibold)
        assert lit(props(v, "labels")["fontSize"]) == "20D" and lit(props(v, "labels")["labelDisplayUnits"]) == "1D", v.title
        assert lit(props(v, "categoryLabels")["show"]) == "false", v.title
    dq = next(p for p in report.pages if p.display_name == "Datenqualität & Quellen")
    dq_cards = sorted((v for v in content(dq) if v.visual_type == "card"), key=lambda v: v.raw["position"]["x"])
    assert [v.bound_fields() for v in dq_cards] == [[("Kennzahlen", n, "Measure")] for n in ("Datenstand", "Datenstand MaStR", "Zeilen")]
    # 20D in 88 px tall cards: at 18D in 80 px cards Desktop clipped the values at the top and the bottom
    assert [lit(props(v, "labels")["fontSize"]) for v in dq_cards] == ["20D"] * 3
    assert {geometry(v)[3] for v in dq_cards} == {88}
    # the histogram counts price hours, not the rows of all fact tables
    hist = by_title(report, "Preise", "Verteilung der Stundenpreise (Klassen à 10 €)")
    assert ("Kennzahlen", "Preisstunden", "Measure") in hist.bound_fields()
    assert ("Kennzahlen", "Zeilen", "Measure") not in hist.bound_fields()


def test_field_parameter_chart_binds_the_parameter_with_the_schema_shape(report):
    v = by_title(report, "Überblick", "Kennzahl-Auswahl je Monat")
    y = v.raw["visual"]["query"]["queryState"]["Y"]
    # the parameter column goes into `fieldParameters`, never in as a plain (text) projection
    assert [list(iter_fields(fp["parameterExpr"])) for fp in y["fieldParameters"]] == [[("Kennzahl-Auswahl", "Kennzahl-Auswahl", "Column")]]
    assert (y["fieldParameters"][0]["index"], y["fieldParameters"][0]["length"]) == (0, 1)
    assert [list(iter_fields(p["field"])) for p in y["projections"]] == [[("Kennzahlen", "Erzeugung (MWh)", "Measure")]]
    assert ("Kennzahl-Auswahl", "Kennzahl-Auswahl Fields", "Column") not in v.bound_fields()
    legend = v.raw["visual"]["objects"]["legend"][0]["properties"]
    assert legend["show"]["expr"]["Literal"]["Value"] == "true"


def group_colour_problems(visual):
    """One dataPoint per carrier group: a scopeId comparison on Energieträger[Gruppe] and the palette's hex colour."""
    found, out = {}, []
    for point in visual.raw["visual"].get("objects", {}).get("dataPoint", []):
        scope = point.get("selector", {}).get("data", [{}])[0].get("scopeId", {}).get("Comparison")
        if not scope or list(iter_fields(scope["Left"])) != [GROUP_FIELD]:
            out.append(f"{visual.name}: a dataPoint is not scoped to Energieträger[Gruppe]")
            continue
        found[scope["Right"]["Literal"]["Value"].strip("'")] = solid(point["properties"]["fill"])
    if found != PALETTE:
        out.append(f"{visual.name}: series colours {found} differ from the palette {PALETTE}")
    return out


def carrier_charts(report):
    """(page, chart) of the stacked area and column charts that split by an Energieträger column."""
    out = []
    for p in report.pages:
        for v in p.visuals:
            series = v.raw["visual"].get("query", {}).get("queryState", {}).get("Series", {}).get("projections", [])
            if v.visual_type in ("stackedAreaChart", "columnChart") and any(
                    f[0] == "Energieträger" for proj in series for f in iter_fields(proj["field"])):
                out.append((p, v))
    return out


def test_carrier_charts_bind_gruppe_and_carry_exactly_the_palette(report):
    charts = carrier_charts(report)
    assert [(p.display_name, v.title) for p, v in charts] == [
        ("Überblick", "Erzeugung nach Energieträger je Monat (MWh)"),
        ("Erzeugung & Last", "Erzeugung nach Energieträger (MWh)"),
        ("Ausbau", "Zubau nach Monat und Energieträger (MW)"),
    ]
    for _, v in charts:
        series = v.raw["visual"]["query"]["queryState"]["Series"]["projections"]
        assert [list(iter_fields(proj["field"])) for proj in series] == [[GROUP_FIELD]], v.title
        assert ("Energieträger", "Energieträger", "Column") not in v.bound_fields(), v.title  # the seed colours are gone
        assert group_colour_problems(v) == [], v.title
        assert len(v.raw["visual"]["objects"]["dataPoint"]) == len(PALETTE) == 8, v.title  # one per group


def test_palette_and_tokens_are_pinned():
    # validated with the dataviz validator on surface #102233 in this order: worst adjacent colour-vision ΔE 8.4,
    # normal-vision ΔE 19.8, every colour at least 3:1 against the surface (design spec section 16); Sonstige is the neutral fold
    assert list(PALETTE.items()) == [
        ("Biomasse", "#008300"), ("Wind", "#3987E5"), ("Photovoltaik", "#C98500"), ("Wasserkraft", "#199E70"),
        ("Erdgas", "#D95926"), ("Steinkohle", "#9085E9"), ("Braunkohle", "#E66767"), ("Sonstige", "#6B7A8C"),
    ]
    assert TOKENS == {
        "wallpaper": "#070E17", "canvas": "#0B1622", "panel": "#08111B", "panelHover": "#0D2533", "panelActive": "#0F3442",
        "surface": "#102233", "surfaceRaised": "#13304A", "hairline": "#1E3A55", "grid": "#1B3048", "ink": "#E8EEF4",
        "inkSecondary": "#A9B8C8", "inkMuted": "#8291A3", "accent": "#22D3EE",
    }
    # the palette order is the stack order: Gruppe's names by their sort number, then its default Sonstige
    gruppe = load_model(MODEL).tables["Energieträger"].columns["Gruppe"].expression
    numbered = sorted((int(n), name) for n, name in re.findall(r'(\d+), "([^"]+)"', gruppe))
    assert [name for _, name in numbered] + ["Sonstige"] == list(PALETTE)


def heatmap_colours():
    return {s["heatmap"][end].upper() for p in SPEC["pages"] for s in p["visuals"] if s.get("heatmap") for end in ("min", "max")}


def card_text_boxes():
    """Names of the content text boxes whose spec says `card: true`: the only content visuals that write literal container colours."""
    return {stable_name(page["id"], str(index)) for page in SPEC["pages"] for index, spec in enumerate(page["visuals"])
            if spec["type"] == "textbox" and spec.get("card")}


def container_literal_problems(page, visual, card_boxes):
    """Literal solid colours in the container objects (background, border, shadow ...) exist only on the chrome and on the text boxes
    whose spec says `card: true`; every other visual takes them from the theme."""
    if is_chrome(page, visual) or visual.name in card_boxes:
        return []
    out = []
    for group, entries in visual.raw.get("visual", {}).get("visualContainerObjects", {}).items():
        for entry in entries:
            for prop, value in entry.get("properties", {}).items():
                if isinstance(value, dict) and "Literal" in json.dumps(value.get("solid", {})):
                    out.append(f"{page.display_name}/{visual.title or visual.name}: a literal colour in {group}.{prop}")
    return out


def test_no_template_colour_literals_survive(report):
    """None of the template's hard-coded colours (red fill, mint background, white, border grey) remains; every hex colour in a
    visual is a token, a palette colour, the first data colour of the theme (series colours by measure) or a heatmap colour of
    the spec; literal colours in the container objects exist only on the chrome and on the text boxes that are cards."""
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    allowed = set(TOKENS.values()) | set(PALETTE.values()) | {theme["dataColors"][0].upper()} | heatmap_colours()
    for p in report.pages:
        for v in p.visuals:
            text = json.dumps(v.raw, ensure_ascii=False)
            for bad in ("#F6465A", "#EDF8F5", "#FFFFFF", "#D7DCE0", "#66717A"):
                assert bad not in text, (p.display_name, v.name, bad)
            stray = {c.upper() for c in HEX.findall(text)} - allowed
            assert not stray, (p.display_name, v.title or v.name, sorted(stray))
            assert container_literal_problems(p, v, card_text_boxes()) == []


def test_content_visuals_take_background_border_and_glow_from_the_theme(report):
    # a template's own container background, border or shadow would override the theme's tile look (surface, hairline, glow)
    for p in report.pages:
        for v in content(p):
            if v.visual_type != "textbox":  # text boxes opt in to the card look explicitly
                clash = {"background", "border", "dropShadow"} & set(v.raw["visual"].get("visualContainerObjects", {}))
                assert not clash, (p.display_name, v.title, sorted(clash))


def test_ueberblick_has_a_kategorie_slicer_for_readers(report):
    ueb = next(p for p in report.pages if p.display_name == "Überblick")
    slicers = [v for v in ueb.visuals if v.visual_type == "slicer" and v.bound_fields() == [BOOKMARK_FIELD]]
    assert len(slicers) == 1


def test_matrix_is_a_heatmap_and_bars_are_sorted(report):
    matrix = by_title(report, "Erzeugung & Last", "Residuallast Ø nach Tageszeit und Wochentag")
    fill = matrix.raw["visual"]["objects"]["values"][0]["properties"]["backColor"]["solid"]["color"]["expr"]["FillRule"]
    assert list(iter_fields(fill["Input"])) == [("Kennzahlen", "Residuallast Ø (MWh/15 min)", "Measure")]
    gradient = fill["FillRule"]["linearGradient2"]
    assert gradient["min"]["color"]["Literal"]["Value"] == "'#132A40'" and gradient["max"]["color"]["Literal"]["Value"] == "'#256ABF'"
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
    assert el.drillthrough_fields == [{"Column": {"Expression": {"SourceRef": {"Entity": "Datum"}}, "Property": "Monatsanfang"}}]
    assert drillthrough_problems(el, model) == []


def test_bookmarks_resolve_against_the_model(report, model):
    assert {b["displayName"] for b in report.bookmarks} == {"Erneuerbar", "Konventionell"}
    assert sorted(b["name"] for b in report.bookmarks) == sorted(report.bookmark_items)
    page_ids = {p.name for p in report.pages}
    problems = [msg for b in report.bookmarks for msg in bookmark_problems(b, model, page_ids)]
    assert not problems, problems


def test_theme_registered_and_colours(report):
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    assert report.theme_name == "energiewende.json"
    # the dark Leitstand theme: card surface and ink are tokens, the data colours are the documented dark order
    assert theme["background"].upper() == TOKENS["surface"] and theme["foreground"].upper() == TOKENS["ink"]
    assert theme["dataColors"] == ["#3987E5", "#D95926", "#199E70", "#C98500", "#D55181", "#008300", "#9085E9", "#E66767"]
    assert theme["tableAccent"].upper() == TOKENS["accent"]
    # the theme repeats the shared values, and they stay equal to the tokens the generator writes
    assert theme["firstLevelElements"].upper() == TOKENS["ink"]
    assert theme["secondLevelElements"].upper() == TOKENS["inkSecondary"]
    assert theme["thirdLevelElements"].upper() == TOKENS["grid"]
    assert theme["fourthLevelElements"].upper() == TOKENS["inkMuted"]
    page = theme["visualStyles"]["page"]["*"]
    assert page["background"][0]["color"]["solid"]["color"].upper() == TOKENS["canvas"]
    assert page["outspace"][0]["color"]["solid"]["color"].upper() == TOKENS["wallpaper"]
    everything = theme["visualStyles"]["*"]["*"]
    assert everything["background"][0]["color"]["solid"]["color"].upper() == TOKENS["surface"]
    assert everything["border"][0]["color"]["solid"]["color"].upper() == TOKENS["hairline"]
    assert everything["dropShadow"][0]["color"]["solid"]["color"].upper() == TOKENS["accent"]
    # the heatmap runs from the theme's minimum to its maximum
    assert (theme["minimum"].upper(), theme["maximum"].upper()) == tuple(
        c.upper() for s in SPEC["pages"][1]["visuals"] if s.get("heatmap") for c in (s["heatmap"]["min"], s["heatmap"]["max"]))


# --- Leitstand chrome: navigation panel and header on every page -------------------------------------------------------

PANEL_TILES = {  # key -> x, y, width, height on the 1280 x 720 canvas
    "brand": (0, 0, 200, 104), "nav0": (0, 104, 200, 48), "nav1": (0, 152, 200, 48), "nav2": (0, 200, 200, 48),
    "nav3": (0, 248, 200, 48), "nav4": (0, 296, 200, 48), "filler": (0, 344, 200, 272), "footer": (0, 616, 200, 104),
}
# the data stand is 396 px wide, not 300: `Datenstand: SMARD 28.12.2026 · MaStR September 2026` measures about 345 px at 10 pt
# Segoe UI Semibold (the card font of the theme) and has to stay on one line; the card ends at the 1264 margin, 12 px right of the title
HEADER_TILES = {"title": (216, 12, 640, 40), "stand": (868, 12, 396, 40)}


def geometry(visual):
    pos = visual.raw["position"]
    return pos["x"], pos["y"], pos["width"], pos["height"]


def lit_of(properties, key):
    return lit(properties[key]) if key in properties else None


def colour_of(properties, key):
    return solid(properties[key]) if key in properties else None


def text_runs(visual):
    """[(text, font size, font weight, colour, url)] of every run of a text box, paragraph by paragraph."""
    paragraphs = visual.raw["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    return [[(r["value"], r["textStyle"].get("fontSize"), r["textStyle"].get("fontWeight"),
              (r["textStyle"].get("color") or "").upper() or None, r.get("url")) for r in p["textRuns"]] for p in paragraphs]


def panel_look_problems(visual, where):
    out = []
    background = props(visual, "background", container=True)
    if (lit_of(background, "show"), colour_of(background, "color"), lit_of(background, "transparency")) != ("true", TOKENS["panel"], "0D"):
        out.append(f"{where}: the container background is not the panel colour")
    border = props(visual, "border", container=True)
    if (lit_of(border, "show"), lit_of(border, "radius")) != ("false", "0D"):
        out.append(f"{where}: the panel tile has a border or a radius")
    if lit_of(props(visual, "dropShadow", container=True), "show") != "false":
        out.append(f"{where}: the panel tile has a shadow")
    if lit_of(props(visual, "title", container=True), "show") != "false":
        out.append(f"{where}: the title of the panel tile is shown")
    return out


def button_problems(visual, target, current, where):
    out = []
    link = props(visual, "visualLink", container=True)
    if (lit_of(link, "show"), lit_of(link, "type"), lit_of(link, "showDefaultTooltip")) != ("true", "'PageNavigation'", "false"):
        out.append(f"{where}: not a page navigation without default tooltip")
    if lit_of(link, "navigationSection") != f"'{target.name}'":
        out.append(f"{where}: navigates to {lit_of(link, 'navigationSection')}, expected '{target.name}'")
    if visual.title != target.display_name or visual.alt_text != f"Navigation: {target.display_name}":
        out.append(f"{where}: hidden title / alt text is not the page name")
    if lit_of(props(visual, "title", container=True), "show") != "false":
        out.append(f"{where}: the title is shown")
    if visual.raw["visual"].get("query"):
        out.append(f"{where}: a button has no query")
    if lit_of(props(visual, "icon", "default"), "shapeType") != "'blank'" or lit_of(props(visual, "outline"), "show") != "false":
        out.append(f"{where}: icon must be blank and the outline off")
    states = {"default": (TOKENS["panelActive"], TOKENS["accent"]), "hover": (TOKENS["panelActive"], TOKENS["accent"])} if current else \
        {"default": (TOKENS["panel"], TOKENS["inkSecondary"]), "hover": (TOKENS["panelHover"], TOKENS["ink"])}
    for state, (fill, ink) in states.items():
        fill_props, text_props = props(visual, "fill", state), props(visual, "text", state)
        if (colour_of(fill_props, "fillColor"), lit_of(fill_props, "transparency")) != (fill, "0D"):
            out.append(f"{where}: {state} fill is {colour_of(fill_props, 'fillColor')}, expected {fill}")
        if colour_of(text_props, "fontColor") != ink:
            out.append(f"{where}: {state} text colour is {colour_of(text_props, 'fontColor')}, expected {ink}")
        if lit_of(text_props, "bold") != ("true" if current else None):
            out.append(f"{where}: {state} text must be {'bold' if current else 'regular'}")
    default = props(visual, "text", "default")
    if (lit_of(default, "text"), lit_of(default, "fontSize"), lit_of(default, "horizontalAlignment"), lit_of(default, "leftMargin")) != \
            (f"'{target.display_name}'", "10D", "'left'", "20L"):  # an integer literal, as Desktop writes leftMargin
        # 10D: at 11D Desktop cut the bold label of the current page to "Datenqualität &..."
        out.append(f"{where}: button text is not the page name at 10D, left aligned, 20L margin")
    if lit_of(props(visual, "text"), "show") != "true" or lit_of(props(visual, "fill"), "show") != "true":
        out.append(f"{where}: text and fill must be shown")
    return out


def chrome_problems(page, pages):
    """Navigation panel and header of one page: every tile at its place, five buttons in page order navigating to the right page
    with the current one highlighted, brand and footer text, title, data stand, panel look, and a unique tab order ending in the footer."""
    names = chrome_names(page)
    by_name = {v.name: v for v in page.visuals}
    missing = [key for key, name in names.items() if name not in by_name]
    if missing:
        return [f"{page.display_name}: chrome tiles missing: {missing}"]
    tile = {key: by_name[name] for key, name in names.items()}
    out = []
    for key, box in {**PANEL_TILES, **HEADER_TILES}.items():
        if geometry(tile[key]) != box:
            out.append(f"{page.display_name}/{key}: at {geometry(tile[key])}, expected {box}")
    for key in PANEL_TILES:
        out += panel_look_problems(tile[key], f"{page.display_name}/{key}")
    for i, target in enumerate(pages):
        if tile[f"nav{i}"].visual_type != "actionButton":
            out.append(f"{page.display_name}/nav{i}: not an action button")
        out += button_problems(tile[f"nav{i}"], target, target.name == page.name, f"{page.display_name}/nav{i}")
    ink, accent, muted = TOKENS["ink"], TOKENS["accent"], TOKENS["inkMuted"]
    if text_runs(tile["brand"]) != [[("ENERGIEWENDE", "13pt", "bold", ink, None)], [("MONITOR", "13pt", "bold", accent, None)],
                                    [("Strommarkt und Ausbau in Deutschland", "9pt", None, muted, None)]]:
        out.append(f"{page.display_name}/brand: wrong text or style {text_runs(tile['brand'])}")
    if text_runs(tile["filler"]) != [[("", "12pt", None, None, None)]]:
        out.append(f"{page.display_name}/filler: not one empty paragraph")
    # one source per line and no link: in 168 px the old lines broke inside "(dl-de/by-2-0)" and "energiewende-monitor"
    if text_runs(tile["footer"]) != [[("Daten: SMARD (CC BY 4.0)", "8pt", None, muted, None)],
                                     [("MaStR (dl-de/by-2-0)", "8pt", None, muted, None)],
                                     [("Harithas Harikaran", "8pt", None, muted, None)],
                                     [("GitHub: energiewende-monitor", "8pt", None, muted, None)]]:
        out.append(f"{page.display_name}/footer: wrong text or style {text_runs(tile['footer'])}")
    for key, top in (("brand", "14D"), ("footer", "8D")):  # the text starts 20 px in, in line with the button labels
        padding = props(tile[key], "padding", container=True)
        if [lit_of(padding, side) for side in ("left", "right", "top", "bottom")] != ["20D", "12D", top, "0D"]:
            out.append(f"{page.display_name}/{key}: container padding must be 20D left, 12D right, {top} top, 0D bottom")
    if text_runs(tile["title"]) != [[(page.display_name, "18pt", "bold", ink, None)]]:
        out.append(f"{page.display_name}/title: not the page name at 18pt bold ink")
    for key in ("background", "border", "dropShadow"):
        if lit_of(props(tile["title"], key, container=True), "show") != "false":
            out.append(f"{page.display_name}/title: container {key} must be off")
    stand = tile["stand"]
    if stand.visual_type != "card" or stand.bound_fields() != [("Kennzahlen", "Datenstand Kopfzeile", "Measure")]:
        out.append(f"{page.display_name}/stand: not a card bound to Datenstand Kopfzeile")
    labels = props(stand, "labels")
    if (lit_of(labels, "fontSize"), colour_of(labels, "color")) != ("10D", muted) or lit_of(props(stand, "categoryLabels"), "show") != "false":
        out.append(f"{page.display_name}/stand: labels must be 10D in the muted ink, category labels off")
    for key in ("background", "border", "dropShadow"):
        if lit_of(props(stand, key, container=True), "show") != "false":
            out.append(f"{page.display_name}/stand: container {key} must be off")
    if lit_of(props(stand, "title", container=True), "show") != "false" or stand.title != "Datenstand":
        out.append(f"{page.display_name}/stand: the title must be hidden and read Datenstand")
    # no padding on title and data stand: the base theme pads every visual by 14 to 16 px, which clipped the 40 px data stand
    for key in ("title", "stand"):
        if {lit_of(props(tile[key], "padding", container=True), side) for side in ("left", "right", "top", "bottom")} != {"0D"}:
            out.append(f"{page.display_name}/{key}: the container padding must be 0D on every side")
    order = {v.name: v.raw["position"]["tabOrder"] for v in page.visuals}
    if len(set(order.values())) != len(order) or len({v.raw["position"]["z"] for v in page.visuals}) != len(order):
        out.append(f"{page.display_name}: z and tabOrder must be unique")
    head = [names["brand"], *(names[f"nav{i}"] for i in range(5)), names["title"], names["stand"]]
    if [order[n] for n in head] != sorted(order[n] for n in head) or max(order[n] for n in head) > min(order[v.name] for v in content(page)):
        out.append(f"{page.display_name}: tab order must be brand, buttons, title, data stand, then the content")
    if order[names["footer"]] != max(order.values()):
        out.append(f"{page.display_name}: the footer must come last in the tab order")
    return out


def test_every_page_has_the_chrome(report):
    assert [p.display_name for p in report.pages] == PAGES
    problems = [msg for p in report.pages for msg in chrome_problems(p, report.pages)]
    assert not problems, problems


def test_content_sits_right_of_the_panel_and_inside_the_margins(report):
    for p in report.pages:
        for v in content(p):
            x, y, w, h = geometry(v)
            assert x >= 216 and x + w <= 1264 and y >= 60 and y + h <= 704, (p.display_name, v.title or v.name, geometry(v))


GAUGES = [  # title, subtitle, palette group, target measure, x
    ("Photovoltaik", "Ziel 2030: 215 GW", "Photovoltaik", "Zielerreichung Photovoltaik %", 796),
    ("Wind an Land", "Ziel 2030: 115 GW", "Wind", "Zielerreichung Wind an Land %", 956),
    ("Wind auf See", "Ziel 2030: 30 GW", "Wind", "Zielerreichung Wind auf See %", 1116),
]


def gauge_problems(visual, title, subtitle, group, measure, x):
    out = []
    if visual.title != title or visual.alt_text != f"Messinstrument: {title}":
        out.append(f"{title}: title or alt text")
    sub = props(visual, "subTitle", container=True)
    if (lit_of(sub, "show"), lit_of(sub, "text")) != ("true", f"'{subtitle}'"):
        out.append(f"{title}: subtitle is {lit_of(sub, 'text')}, expected '{subtitle}'")
    if geometry(visual) != (x, 224, 148, 236):
        out.append(f"{title}: at {geometry(visual)}")
    if visual.roles() != {"Y"} or visual.bound_fields() != [("Kennzahlen", measure, "Measure")]:
        out.append(f"{title}: role Y must hold {measure} and nothing else, found {visual.bound_fields()}")
    axis = props(visual, "axis")
    if (lit_of(axis, "min"), lit_of(axis, "max")) != ("0D", "1D"):
        out.append(f"{title}: the scale is {lit_of(axis, 'min')} to {lit_of(axis, 'max')}, expected 0D to 1D")
    if lit_of(props(visual, "target"), "show") != "false" or lit_of(props(visual, "calloutValue"), "show") != "true" \
            or lit_of(props(visual, "labels"), "show") != "false":
        out.append(f"{title}: target and labels must be off, the callout value on")
    if colour_of(props(visual, "dataPoint"), "fill") != PALETTE[group]:
        out.append(f"{title}: fill is {colour_of(props(visual, 'dataPoint'), 'fill')}, expected the palette's {group}")
    return out


def test_three_gauges_show_the_2030_targets(report):
    ueb = next(p for p in report.pages if p.display_name == "Überblick")
    gauges = sorted((v for v in ueb.visuals if v.visual_type == "gauge"), key=lambda v: v.raw["position"]["x"])
    assert len(gauges) == 3
    problems = [msg for v, spec in zip(gauges, GAUGES, strict=True) for msg in gauge_problems(v, *spec)]
    assert not problems, problems
    assert [v.name for v in gauges] == [stable_name("ueberblick", str(i)) for i in (12, 13, 14)]  # appended after the older visuals
    assert not [v for p in report.pages if p is not ueb for v in p.visuals if v.visual_type == "gauge"]


def test_ee_anteil_chart_emphasises_the_current_year(report):
    v = by_title(report, "Überblick", "EE-Anteil vs. Vorjahr")
    points = {pt["selector"]["metadata"]: solid(pt["properties"]["fill"]) for pt in v.raw["visual"]["objects"]["dataPoint"]}
    # current year in the first data colour of the theme, the previous year muted
    assert points == {"Kennzahlen.EE-Anteil %": "#3987E5", "Kennzahlen.EE-Anteil Vorjahr %": TOKENS["inkMuted"]}
    refs = {proj["queryRef"] for proj in v.raw["visual"]["query"]["queryState"]["Y"]["projections"]}
    assert set(points) == refs  # the selectors are the queryRefs the projections write
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    assert theme["dataColors"][0].upper() == "#3987E5"


def card_container_problems(visual):
    """The card look written out for a text box: surface, hairline border with radius 10, faint accent glow, inner padding."""
    out = []
    background = props(visual, "background", container=True)
    if (lit_of(background, "show"), colour_of(background, "color"), lit_of(background, "transparency")) != ("true", TOKENS["surface"], "0D"):
        out.append(f"{visual.name}: background is not the surface")
    border = props(visual, "border", container=True)
    if (lit_of(border, "show"), colour_of(border, "color"), lit_of(border, "radius")) != ("true", TOKENS["hairline"], "10D"):
        out.append(f"{visual.name}: border is not the hairline with radius 10D")
    glow = props(visual, "dropShadow", container=True)
    expected = {"show": "true", "position": "'Outer'", "preset": "'Custom'", "shadowBlur": "12D", "shadowDistance": "0D",
                "shadowSpread": "0D", "angle": "45D", "transparency": "88D"}
    if {k: lit_of(glow, k) for k in expected} != expected or colour_of(glow, "color") != TOKENS["accent"]:
        out.append(f"{visual.name}: the glow is not the theme's (accent, Outer, Custom, blur 12D, distance 0D, spread 0D, 45D, 88D)")
    padding = props(visual, "padding", container=True)
    if [lit_of(padding, side) for side in ("left", "right", "top", "bottom")] != ["16D", "16D", "12D", "12D"]:
        out.append(f"{visual.name}: padding must be 16D left and right, 12D top and bottom (a text box has none, the text touched the border)")
    return out


def test_datenqualitaet_text_boxes_are_cards_with_a_heading(report):
    page = next(p for p in report.pages if p.display_name == "Datenqualität & Quellen")
    boxes = sorted((v for v in content(page) if v.visual_type == "textbox"), key=lambda v: v.raw["position"]["y"])
    # the gap table at full height on the left, sources and project stacked on the right: beside a table of the same
    # height the sources card was half empty
    assert [geometry(v) for v in boxes] == [(864, 160, 400, 316), (864, 488, 400, 216)]
    table = next(v for v in content(page) if v.visual_type == "tableEx")
    assert geometry(table) == (216, 160, 636, 544)
    ink, secondary = TOKENS["ink"], TOKENS["inkSecondary"]
    for box in boxes:
        assert card_container_problems(box) == []
        first, *rest = text_runs(box)
        assert [(size, weight, colour) for _, size, weight, colour, _ in first] == [("12pt", "bold", ink)]
        for paragraph in rest:
            assert {(size, weight, colour, url) for _, size, weight, colour, url in paragraph} == {("10pt", None, secondary, None)}


def test_addresses_are_plain_text_without_a_scheme(report):
    # Desktop draws a link run of a text box in a fixed dark blue (#1D5899 measured on the panel), whatever colour the run or
    # the theme's hyperlink sets, and that is not readable on the dark tiles. So the addresses are plain text, and without
    # "https://": the generator turns a URL with a scheme into a link run
    seen = set()
    for p in report.pages:
        for v in p.visuals:
            if v.visual_type == "textbox":
                for value, _, _, _, url in (run for paragraph in text_runs(v) for run in paragraph):
                    assert url is None and not URL_IN_TEXT.search(value), (p.display_name, v.name, value)
                    seen |= {address for address in ADDRESSES if address in value}
    assert seen == ADDRESSES


def link_run_problems(visual, where):
    """No run of a text box is a link or decorated (see test_addresses_are_plain_text_without_a_scheme)."""
    out = []
    for _, run in runs_of(visual):
        if run.get("url"):
            out.append(f"{where}: {run['value']!r} is a link run; Desktop draws it in a fixed dark blue")
        if "textDecoration" in run["textStyle"]:
            out.append(f"{where}: {run['value']!r} is decorated")
    return out


def test_text_boxes_have_no_link_runs_and_no_decoration(report):
    problems = [msg for p in report.pages for v in p.visuals if v.visual_type == "textbox"
                for msg in link_run_problems(v, f"{p.display_name}/{v.name}")]
    assert not problems, problems


def card_font_problems(visual, where):
    """The value of a card is drawn in the theme's callout class (Segoe UI Semibold): the visual sets a size, no font family and no bold flag."""
    labels = props(visual, "labels")
    out = [f"{where}: labels.{key} overrides the font of the theme's callout class" for key in ("fontFamily", "bold") if key in labels]
    if "fontSize" not in labels:
        out.append(f"{where}: labels has no fontSize")
    return out


def test_card_values_take_the_theme_callout_font(report):
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    assert theme["textClasses"]["callout"]["fontFace"] == "Segoe UI Semibold"
    cards = [(p, v) for p in report.pages for v in p.visuals if v.visual_type == "card"]
    assert len(cards) == 5 + 3 + 5  # the KPI row, the three quality cards and the data stand of each page
    problems = [msg for p, v in cards for msg in card_font_problems(v, f"{p.display_name}/{v.title}")]
    assert not problems, problems


def test_colour_names_resolve_to_tokens_palette_entries_and_the_first_data_colour_only():
    colours = Colours(SPEC)
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    first, *others = theme["dataColors"]
    assert colours("accent") == TOKENS["accent"] and colours("Wind") == PALETTE["Wind"]
    assert colours(first) == colours(first.lower()) == first.upper()  # the series colour of a measure
    for rejected in [*others, "#123456", "nonsense"]:  # the other seven data colours are no spec colours
        with pytest.raises(ValueError):
            colours(rejected)


def test_hidden_titles_keep_their_text_for_the_alt_text(report):
    for p in report.pages:
        tile = {key: v for v in p.visuals for key, name in chrome_names(p).items() if v.name == name}
        buttons = [tile[f"nav{i}"] for i in range(5)]
        assert [v.title for v in buttons] == PAGES
        for v in buttons + [tile["stand"]]:
            assert lit_of(props(v, "title", container=True), "show") == "false", v.name
            assert v.alt_text == default_alt_text(v.visual_type, v.title), v.name
        assert [v.alt_text for v in buttons] == [f"Navigation: {name}" for name in PAGES]
        assert tile["stand"].alt_text == "Kennzahl: Datenstand"
    gauges = sorted((v for p in report.pages for v in p.visuals if v.visual_type == "gauge"), key=lambda v: v.raw["position"]["x"])
    assert [v.alt_text for v in gauges] == [f"Messinstrument: {title}" for title, *_ in GAUGES]


MONTH_CHARTS = [  # (page, title) of the charts with one point or bar a month
    ("Überblick", "Erzeugung nach Energieträger je Monat (MWh)"), ("Überblick", "EE-Anteil vs. Vorjahr"),
    ("Überblick", "Kennzahl-Auswahl je Monat"), ("Preise", "Negative Preisstunden je Monat"),
    ("Ausbau", "Zubau nach Monat und Energieträger (MW)"),
]


def axis_fields(visual, role):
    return [f for proj in visual.raw["visual"]["query"]["queryState"][role]["projections"] for f in iter_fields(proj["field"])]


def test_month_charts_have_a_continuous_date_axis(report):
    # On the text column Jahr-Monat the axis is categorical: Desktop keeps about 20 px a month and adds a scroll bar after
    # about two years (preferredCategoryWidth did not change that). The date column Monatsanfang makes the axis continuous.
    for page, title in MONTH_CHARTS:
        assert axis_fields(by_title(report, page, title), "Category") == [MONTH_AXIS], (page, title)
    for p in report.pages:
        for v in p.visuals:
            assert ("Datum", "Jahr-Monat", "Column") not in v.bound_fields(), (p.display_name, v.title)


def comparison_filters(visual):
    """(entity, property, kind, ComparisonKind, literal) of every visual-level comparison filter."""
    out = []
    for f in visual.raw.get("filterConfig", {}).get("filters", []):
        if f.get("type") == "Advanced":
            (where,) = f["filter"]["Where"]
            comparison = where["Condition"]["Comparison"]
            ((kind, left),) = comparison["Left"].items()
            (source,) = f["filter"]["From"]
            assert left["Expression"]["SourceRef"]["Source"] == source["Name"]
            out.append((source["Entity"], left["Property"], kind, comparison["ComparisonKind"], comparison["Right"]["Literal"]["Value"]))
    return out


def test_filters_keep_visuals_to_the_period_with_data(report):
    # the calendar runs from 1990 to 2030 (the register since 1990, the targets to 2030); SMARD data start in 2023
    def slicer(page, field):
        return next(v for p in report.pages if p.display_name == page for v in p.visuals
                    if v.visual_type == "slicer" and axis_fields(v, "Values") == [field])
    year = ("Datum", "Jahr", "Column")
    cases = [
        (slicer("Überblick", year), [("Kennzahlen", "Erzeugung (MWh)", "Measure", 1, "0D")]),
        (slicer("Preise", year), [("Kennzahlen", "Preisstunden", "Measure", 1, "0D")]),
        (slicer("Ausbau", year), [("Kennzahlen", "Zubau (MW)", "Measure", 1, "0D")]),
        # the date range spans the days with generation data, not 01.01.1990 to 31.12.2030
        (slicer("Erzeugung & Last", ("Datum", "Datum", "Column")), [("Kennzahlen", "Erzeugung (MWh)", "Measure", 1, "0D")]),
        # the previous-year line ran on for twelve months past the data stand
        (by_title(report, "Überblick", "EE-Anteil vs. Vorjahr"), [("Kennzahlen", "EE-Anteil %", "Measure", 1, "0D")]),
        # additions from 2019: the register is incomplete before (see the note on the quality page)
        (by_title(report, "Ausbau", "Zubau nach Monat und Energieträger (MW)"), [("Datum", "Jahr", "Column", 2, "2019L")]),
        # full load hours exist for the years with generation; capacity alone (before 2023, carried on to 2030) gave empty rows
        (by_title(report, "Ausbau", "Volllaststunden nach Energieträger und Jahr"),
         [("Kennzahlen", "Volllaststunden (h)", "Measure", 1, "0D")]),
    ]
    for visual, expected in cases:
        assert comparison_filters(visual) == expected, visual.title or visual.bound_fields()
    filtered = {id(v) for v, _ in cases}
    others = [(p.display_name, v.title) for p in report.pages for v in p.visuals if id(v) not in filtered and comparison_filters(v)]
    assert not others, others


def test_carrier_legends_show_all_eight_groups(report):
    # in one row at 9 pt the eight groups need about 545 px: Desktop cut labels ("Photovolt...") or paged the legend
    carriers = {id(v): (p.display_name, v) for p, v in carrier_charts(report)}
    legends = {(page, v.title): (lit(props(v, "legend")["position"]), lit_of(props(v, "legend"), "fontSize"))
               for page, v in carriers.values()}
    assert legends == {
        ("Überblick", "Erzeugung nach Energieträger je Monat (MWh)"): ("'Bottom'", "8D"),  # 236 px: six lines on the right
        ("Erzeugung & Last", "Erzeugung nach Energieträger (MWh)"): ("'Right'", None),
        ("Ausbau", "Zubau nach Monat und Energieträger (MW)"): ("'Right'", None),
    }
    for p in report.pages:  # every other legend that is shown sits at the bottom (no position: the theme's, Bottom)
        for v in p.visuals:
            if id(v) not in carriers and lit_of(props(v, "legend"), "show") == "true":
                assert lit_of(props(v, "legend"), "position") in (None, "'Bottom'"), (p.display_name, v.title)


def test_slicers_have_no_search_and_the_measure_slicer_selects_one(report):
    slicers = [(p.display_name, v) for p in report.pages for v in p.visuals if v.visual_type == "slicer"]
    for page, v in slicers:  # the captured slicer template has search switched on
        assert lit(props(v, "general")["selfFilterEnabled"]) == "false", (page, axis_fields(v, "Values"))
    by_field = {(page, *axis_fields(v, "Values")): v for page, v in slicers}
    # one measure at a time: with "Select all" the chart drew the four measures on one axis; single select picks the
    # first entry, Erzeugung (MWh), when nothing is selected
    selection = props(by_field[("Überblick", ("Kennzahl-Auswahl", "Kennzahl-Auswahl", "Column"))], "selection")
    assert (lit(selection["strictSingleSelect"]), lit(selection["selectAllCheckboxEnabled"])) == ("true", "false")
    # the two category tiles without a third "Select all" tile
    assert lit(props(by_field[("Überblick", BOOKMARK_FIELD)], "selection")["selectAllCheckboxEnabled"]) == "false"


def test_heatmap_has_the_weekdays_as_rows(report):
    # seven weekdays down and four times of day across fit the 518 px tile; the other way round the last columns were cut
    matrix = by_title(report, "Erzeugung & Last", "Residuallast Ø nach Tageszeit und Wochentag")
    assert axis_fields(matrix, "Rows") == [("Datum", "Wochentag", "Column")]
    assert axis_fields(matrix, "Columns") == [("Zeit", "Tageszeit", "Column")]


def test_labels_and_markers_that_cluttered_are_off(report):
    # the histogram wrote "0.0K" over every empty class; a label on each month crowded the negative-hours bars
    for title in ("Verteilung der Stundenpreise (Klassen à 10 €)", "Negative Preisstunden je Monat"):
        assert lit(props(by_title(report, "Preise", title), "labels")["show"]) == "false", title
    area = by_title(report, "Überblick", "Erzeugung nach Energieträger je Monat (MWh)")
    assert lit(props(area, "lineStyles")["showMarker"]) == "false"  # the template's markers dotted every stack edge


def test_table_headers_fit_their_tiles(report):
    def headers(visual):
        return [proj.get("displayName") for proj in visual.raw["visual"]["query"]["queryState"]["Values"]["projections"]]
    # short headers through the projection's displayName: the measure names cut the last column off in 518 px
    assert headers(by_title(report, "Preise", PHASES_TITLE)) == [None, None, None, "Min €/MWh", "Ø €/MWh"]
    volll = by_title(report, "Ausbau", "Volllaststunden nach Energieträger und Jahr")
    assert headers(volll) == [None, None, None, "Leistung (MW)", "Volllaststunden"]
    assert [lit(props(volll, key)["fontSize"]) for key in ("columnHeaders", "values")] == ["9D", "9D"]
    assert lit(props(volll, "total")["totals"]) == "false"  # a total of full load hours over carriers means nothing


def test_theme_switches_the_automatic_subtitles_off():
    # the base theme switches subtitles on for every visual and Desktop fills them in English ("Erzeugung by Jahr");
    # the gauges show their own at visual level (test_three_gauges_show_the_2030_targets)
    theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))
    assert theme["visualStyles"]["*"]["*"]["subTitle"][0]["show"] is False


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
    assert GROUP_FIELD in v.bound_fields() and field_problems(v.raw, model) == []
    assert group_colour_problems(v) == []
    for ref in find_values(v.raw["visual"]["objects"], "Column"):
        ref["Property"] = "Farbe2"
    assert field_problems(v.raw, model)


def test_mutation_missing_or_wrong_carrier_colour_is_caught(report):
    v = _visual(report, "Überblick", "Erzeugung nach Energieträger je Monat (MWh)")
    assert group_colour_problems(v) == []
    missing = copy.deepcopy(v)
    del missing.raw["visual"]["objects"]["dataPoint"][0]
    assert group_colour_problems(missing)
    wrong = copy.deepcopy(v)
    wrong.raw["visual"]["objects"]["dataPoint"][0]["properties"]["fill"]["solid"]["color"]["expr"]["Literal"]["Value"] = "'#000000'"
    assert group_colour_problems(wrong)
    ungrouped = copy.deepcopy(v)  # a point scoped to the carrier instead of the group is not the palette either
    for ref in find_values(ungrouped.raw["visual"]["objects"], "Column"):
        ref["Property"] = "Energieträger"
    assert group_colour_problems(ungrouped)


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


ORDERED_AXES = {("Datum", "Monatsanfang"), ("Datum", "Datum"), ("Zeit", "Uhrzeit"), ("Preis", "Preis Klasse (10 €)")}


def _column(field):
    col = (field or {}).get("Column", {})
    return col.get("Expression", {}).get("SourceRef", {}).get("Entity"), col.get("Property")


def test_time_and_class_axes_sort_ascending(report):
    # without a sortDefinition Desktop may sort a category axis by the first measure (seen on Überblick in the session)
    problems = []
    for page in report.pages:
        for v in page.visuals:
            query = v.raw.get("visual", {}).get("query", {})
            projections = query.get("queryState", {}).get("Category", {}).get("projections", [])
            sorts = query.get("sortDefinition", {}).get("sort", [])
            for axis in {_column(p.get("field")) for p in projections} & ORDERED_AXES:
                if not any(_column(s.get("field")) == axis and s.get("direction") == "Ascending" for s in sorts):
                    problems.append(f"{page.display_name} / {v.title}: no ascending sort on {axis[0]}[{axis[1]}]")
    assert not problems, problems


def _page(report, name):
    return copy.deepcopy(next(p for p in report.pages if p.display_name == name))


def _tile(page, key):
    return next(v for v in page.visuals if v.name == chrome_names(page)[key])


def test_mutation_button_pointing_at_the_wrong_page_is_caught(report):
    page = _page(report, "Preise")
    assert chrome_problems(page, report.pages) == []
    props(_tile(page, "nav3"), "visualLink", container=True)["navigationSection"]["expr"]["Literal"]["Value"] = "'preise'"
    assert any("navigates to" in msg for msg in chrome_problems(page, report.pages))


def test_mutation_highlighting_the_wrong_button_is_caught(report):
    page = _page(report, "Preise")  # the third button is the current one
    for state in ("default", "hover"):
        props(_tile(page, "nav2"), "fill", state)["fillColor"]["solid"]["color"]["expr"]["Literal"]["Value"] = "'#08111B'"
    assert any("fill" in msg for msg in chrome_problems(page, report.pages))
    other = _page(report, "Preise")
    props(_tile(other, "nav0"), "text", "default")["fontColor"]["solid"]["color"]["expr"]["Literal"]["Value"] = "'#22D3EE'"
    assert any("text colour" in msg for msg in chrome_problems(other, report.pages))


def test_mutation_header_and_panel_defects_are_caught(report):
    def stand_binding(page):
        _tile(page, "stand").raw["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"] = "Datenstand"

    def footer_missing(page):
        page.visuals = [v for v in page.visuals if v.name != chrome_names(page)["footer"]]

    def title_text(page):
        _tile(page, "title").raw["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["value"] = "Preise"

    def tab_order(page):
        _tile(page, "footer").raw["position"]["tabOrder"] = 0

    def panel_colour(page):
        props(_tile(page, "filler"), "background", container=True)["color"]["solid"]["color"]["expr"]["Literal"]["Value"] = "'#102233'"

    def geometry_moved(page):
        _tile(page, "brand").raw["position"]["height"] = 100

    def stand_padded(page):
        props(_tile(page, "stand"), "padding", container=True)["top"]["expr"]["Literal"]["Value"] = "14D"

    def footer_at_the_edge(page):
        props(_tile(page, "footer"), "padding", container=True)["left"]["expr"]["Literal"]["Value"] = "0D"

    for mutate in (stand_binding, footer_missing, title_text, tab_order, panel_colour, geometry_moved, stand_padded,
                   footer_at_the_edge):
        page = _page(report, "Ausbau")
        assert chrome_problems(page, report.pages) == []
        mutate(page)
        assert chrome_problems(page, report.pages), mutate.__name__


def test_mutation_gauge_and_card_defects_are_caught(report):
    gauge = copy.deepcopy(next(v for v in next(p for p in report.pages if p.name == "ueberblick").visuals
                               if v.name == stable_name("ueberblick", "12")))
    assert gauge_problems(gauge, *GAUGES[0]) == []

    def scale(g):
        props(g, "axis")["max"]["expr"]["Literal"]["Value"] = "100D"

    def fill(g):
        props(g, "dataPoint")["fill"]["solid"]["color"]["expr"]["Literal"]["Value"] = "'#3987E5'"

    def measure(g):
        g.raw["visual"]["query"]["queryState"]["Y"]["projections"][0]["field"]["Measure"]["Property"] = "EE-Anteil %"

    def target_line(g):
        props(g, "target")["show"]["expr"]["Literal"]["Value"] = "true"

    for mutate in (scale, fill, measure, target_line):
        broken = copy.deepcopy(gauge)
        mutate(broken)
        assert gauge_problems(broken, *GAUGES[0]), mutate.__name__
    box = copy.deepcopy(next(v for v in _page(report, "Datenqualität & Quellen").visuals if v.visual_type == "textbox"
                             and v.name not in chrome_names(_page(report, "Datenqualität & Quellen")).values()))
    assert card_container_problems(box) == []
    for key in ("dropShadow", "padding"):
        broken = copy.deepcopy(box)
        del broken.raw["visual"]["visualContainerObjects"][key]
        assert card_container_problems(broken), key


def test_mutation_link_run_or_decoration_is_caught(report):
    page = _page(report, "Datenqualität & Quellen")
    footer = next(v for v in page.visuals if v.name == chrome_names(page)["footer"])
    assert link_run_problems(footer, "footer") == []
    linked = copy.deepcopy(footer)
    runs_of(linked)[-1][1]["url"] = "https://github.com/HARISPAARTAN/energiewende-monitor"
    underlined = copy.deepcopy(footer)
    runs_of(underlined)[0][1]["textStyle"]["textDecoration"] = "underline"
    for broken in (linked, underlined):
        assert link_run_problems(broken, "footer")


def test_mutation_card_with_its_own_font_is_caught(report):
    card = _visual(report, "Überblick", "Erzeugung")
    assert card_font_problems(card, "card") == []
    for key, value in (("bold", "false"), ("fontFamily", "'Arial'")):
        broken = copy.deepcopy(card)
        props(broken, "labels")[key] = {"expr": {"Literal": {"Value": value}}}
        assert card_font_problems(broken, "card"), key


def test_mutation_literal_container_colours_only_on_the_chrome_and_card_text_boxes(report):
    page = _page(report, "Datenqualität & Quellen")
    boxes = [v for v in content(page) if v.visual_type == "textbox"]
    assert len(boxes) == 2 and {v.name for v in boxes} == card_text_boxes()  # both content text boxes are cards in the spec
    for box in boxes:
        assert container_literal_problems(page, box, card_text_boxes()) == []
        assert container_literal_problems(page, box, set())  # the same colours on a text box without `card: true` are a finding
    stray = copy.deepcopy(next(v for v in content(page) if v.visual_type == "card"))  # any other content visual, too
    stray.raw["visual"]["visualContainerObjects"]["background"] = [
        {"properties": {"color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#102233'"}}}}}}}]
    assert container_literal_problems(page, stray, card_text_boxes())
    brand = next(v for v in page.visuals if v.name == chrome_names(page)["brand"])
    assert container_literal_problems(page, brand, set()) == []  # the chrome may carry them
