"""Regenerate the PBIR report pages, bookmarks and theme registration from tools/pbi/pages.json.

Deterministic: fixed names (uuid5 of page id and visual index), sorted keys, two-space indent, UTF-8 without BOM, LF.
Only page folders carrying the annotation `ewm:generated` are replaced; `bookmarks/` is owned entirely by this script.

pages.json holds the page specs plus `tokens` (the named UI colours) and `palette` (one colour per carrier group). Every
colour written to the report comes from them, from the theme's first data colour (series colours by measure) or from a
heatmap spec. Every page gets the same chrome: a 200 px navigation panel (brand, one button per page, filler, footer) on the left and
a header (page title, data stand) on top; the page's own visuals sit to the right of the panel and below the header.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))  # lets `python tools/pbi/build_report.py` import the tools package

from tools.pbi.pbir import SCHEMAS, Visual, field_ref, stable_name  # noqa: E402

REPORT_DIR = HERE.parent.parent / "powerbi" / "EnergiewendeMonitor.Report" / "definition"
REGISTERED = REPORT_DIR.parent / "StaticResources" / "RegisteredResources"
SPEC = HERE / "pages.json"
GENERATED = "ewm:generated"
CHARTS = {"lineChart", "stackedAreaChart", "columnChart", "clusteredColumnChart", "clusteredBarChart", "scatterChart"}
COLOURED_BY_GROUP = {"stackedAreaChart", "columnChart"}
GROUP = ("Energieträger", "Gruppe")  # the model column the carrier charts colour and stack by
PANEL_WIDTH, NAV_TOP, NAV_HEIGHT = 200, 104, 48  # side panel on the 1280 x 720 canvas: brand 0..104, buttons, filler, footer 616..720


def _lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _solid(hexcode: str) -> dict:
    return {"solid": {"color": _lit("'" + hexcode + "'")}}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _column(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


class Colours:
    """The colour names of the spec: tokens, palette entries (carrier groups) and, as hex, the first data colour of the theme
    (the series colour of a measure, for example the current year of EE-Anteil vs. Vorjahr)."""

    def __init__(self, spec: dict) -> None:
        self.tokens = {name: code.upper() for name, code in spec["tokens"].items()}
        self.palette = {name: code.upper() for name, code in spec["palette"].items()}
        if set(self.tokens) & set(self.palette):
            raise ValueError(f"tokens and palette share names: {sorted(set(self.tokens) & set(self.palette))}")
        theme = json.loads((REGISTERED / spec["theme"]).read_text(encoding="utf-8"))
        self.series_colour = theme["dataColors"][0].upper()

    def __call__(self, ref: str) -> str:
        for known in (self.tokens, self.palette):
            if ref in known:
                return known[ref]
        if ref.upper() == self.series_colour:
            return self.series_colour
        raise ValueError(f"colour {ref!r} is neither a token, a palette entry nor the first data colour of the theme "
                         f"({self.series_colour})")


def _group_colours(entity: str, prop: str, colours: Colours) -> list[dict]:
    """One dataPoint entry per carrier group in the shape Desktop writes for manual series colours: a `scopeId` comparison
    on the series column and a literal fill, in palette order."""
    items = []
    for group, hexcode in colours.palette.items():
        scope = {"Comparison": {"ComparisonKind": 0, "Left": _column(entity, prop),
                                "Right": {"Literal": {"Value": "'" + group.replace("'", "''") + "'"}}}}
        items.append({"properties": {"fill": _solid(hexcode)}, "selector": {"data": [{"scopeId": scope}]}})
    return items


def _measure_colours(series: dict[str, str], colours: Colours) -> list[dict]:
    """One dataPoint entry per measure series (selector: the queryRef of the measure), for lines coloured by measure."""
    return [{"properties": {"fill": _solid(colours(colour))}, "selector": {"metadata": query_ref}}
            for query_ref, colour in series.items()]


def _heatmap(spec: dict) -> list[dict]:
    """Cell background gradient on a matrix value field (conditional formatting by `FillRule`)."""
    entity, prop, kind = spec["field"]
    colour = lambda c: {"color": _lit("'" + c + "'")["expr"]}  # noqa: E731
    rule = {"linearGradient2": {"min": colour(spec["min"]), "max": colour(spec["max"]),
                                "nullColoringStrategy": {"strategy": _lit("'noColor'")["expr"]}}}
    fill = {"solid": {"color": {"expr": {"FillRule": {"Input": field_ref(entity, prop, kind), "FillRule": rule}}}}}
    return [{"properties": {"backColor": fill},
             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{entity}.{prop}"}}]


def _formatting(spec: dict, colours: Colours) -> dict:
    """Visual-level objects: card label size, legend at the bottom (carrier groups: on the right, or at 8 pt in a low chart),
    one fill per carrier group, series colours by measure, the gauge's scale and fill."""
    objects: dict = {}
    roles = spec.get("roles", {})
    kind = spec["type"]
    if kind == "card":
        labels = {"fontSize": _lit(f"{spec.get('label_size', 24)}D"), "labelDisplayUnits": _lit("1D")}
        if spec.get("label_colour"):
            labels["color"] = _solid(colours(spec["label_colour"]))
        objects["labels"] = [{"properties": labels}]
        objects["categoryLabels"] = [{"properties": {"show": _lit("false")}}]
    if kind in CHARTS and (len(roles.get("Series", [])) or len(roles.get("Y", [])) > 1 or spec.get("legend")):
        # The eight carrier groups need about 545 px in one row at 9 pt, more than the 486 to 536 px inside the 518 and 568 px
        # tiles: Desktop cut labels ("Photovolt...") or paged the legend (six of eight shown). A carrier chart of 280 px or more
        # lists them on the right, one a line; the 236 px area chart on Überblick has room for six lines there and paged
        # again, so it keeps the bottom row at 8 pt (about 485 px).
        legend = {"show": _lit("true"), "position": _lit("'Bottom'")}
        if any(f[:2] == list(GROUP) for f in roles.get("Series", [])):
            legend.update({"position": _lit("'Right'")} if spec["h"] >= 280 else {"fontSize": _lit("8D")})
        objects["legend"] = [{"properties": legend}]
    if kind == "columnChart":
        objects["labels"] = [{"properties": {"show": _lit("false")}}]
    if kind in COLOURED_BY_GROUP and any(f[:2] == list(GROUP) for f in roles.get("Series", [])):
        objects["dataPoint"] = _group_colours(*GROUP, colours)
    if spec.get("series_colours"):
        objects["dataPoint"] = _measure_colours(spec["series_colours"], colours)
    if kind == "gauge":  # a ratio against its limit: scale 0 to 100 %, no target line, the value in the middle
        objects["axis"] = [{"properties": {"min": _lit("0D"), "max": _lit("1D")}}]
        objects["target"] = [{"properties": {"show": _lit("false")}}]
        objects["calloutValue"] = [{"properties": {"show": _lit("true")}}]
        objects["labels"] = [{"properties": {"show": _lit("false")}}]
        objects["dataPoint"] = [{"properties": {"fill": _solid(colours(spec["fill"]))}}]
    if spec.get("heatmap"):
        objects["values"] = _heatmap(spec["heatmap"])
    if kind == "slicer":  # no search box: the captured slicer template has search (selfFilterEnabled) switched on
        objects["general"] = [{"properties": {"selfFilterEnabled": _lit("false")}}]
    for key, items in spec.get("objects", {}).items():
        # a spec entry without selector adds its properties to the entry above, so a slicer keeps search off next to its orientation
        plain = len(items) == 1 and "selector" not in items[0] and len(objects.get(key, [])) == 1 and "selector" not in objects[key][0]
        objects[key] = [{"properties": {**objects[key][0]["properties"], **items[0]["properties"]}}] if plain else items
    return objects


def _bare_container() -> dict:
    """No container background, border, shadow or padding: the visual sits directly on the canvas. The base theme pads every
    visual by 14 to 16 px, which leaves the 40 px data-stand card no room for its line and clips it."""
    bare = {key: [{"properties": {"show": _lit("false")}}] for key in ("background", "border", "dropShadow")}
    bare["padding"] = [{"properties": {side: _lit("0D") for side in ("bottom", "left", "right", "top")}}]
    return bare


def _panel_container(colours: Colours) -> dict:
    """Tiles of the side panel: flat panel colour, no border, no shadow; they touch, so the panel reads as one surface."""
    return {
        "background": [{"properties": {"show": _lit("true"), "color": _solid(colours("panel")), "transparency": _lit("0D")}}],
        "border": [{"properties": {"show": _lit("false"), "radius": _lit("0D")}}],
        "dropShadow": [{"properties": {"show": _lit("false")}}],
    }


def _panel_text_container(colours: Colours, top: int) -> dict:
    """A text tile of the side panel (brand, footer): the panel look plus padding, so that the text starts 20 px in, in line with
    the button labels (leftMargin 20), and does not touch the canvas edge."""
    padding = {"left": _lit("20D"), "right": _lit("12D"), "top": _lit(f"{top}D"), "bottom": _lit("0D")}
    return {**_panel_container(colours), "padding": [{"properties": padding}]}


def _card_container(colours: Colours) -> dict:
    """The card look of the theme, written out for a text box (the theme switches these off for text boxes): surface,
    hairline border with radius 10, the faint accent glow, and padding (a text box has none, so its text touched the border)."""
    glow = {"show": _lit("true"), "position": _lit("'Outer'"), "preset": _lit("'Custom'"), "color": _solid(colours("accent")),
            "shadowBlur": _lit("12D"), "shadowDistance": _lit("0D"), "shadowSpread": _lit("0D"), "angle": _lit("45D"),
            "transparency": _lit("88D")}
    return {
        "background": [{"properties": {"show": _lit("true"), "color": _solid(colours("surface")), "transparency": _lit("0D")}}],
        "border": [{"properties": {"show": _lit("true"), "color": _solid(colours("hairline")), "radius": _lit("10D")}}],
        "dropShadow": [{"properties": glow}],
        "padding": [{"properties": {"left": _lit("16D"), "right": _lit("16D"), "top": _lit("12D"), "bottom": _lit("12D")}}],
    }


def _page_link(page_id: str) -> list[dict]:
    return [{"properties": {"show": _lit("true"), "showDefaultTooltip": _lit("false"), "type": _lit("'PageNavigation'"),
                            "navigationSection": _lit("'" + page_id + "'")}}]


def _button_objects(label: str, current: bool, colours: Colours) -> dict:
    """Text and fill of a navigation button, each with a default and a hover state; the button of the current page keeps
    the active fill, the accent colour and bold text in both states."""
    fills = (colours("panelActive"),) * 2 if current else (colours("panel"), colours("panelHover"))
    inks = (colours("accent"),) * 2 if current else (colours("inkSecondary"), colours("ink"))
    bold = {"bold": _lit("true")} if current else {}
    text = [
        {"properties": {"show": _lit("true")}},
        # 10 pt: the bold label of the current page, "Datenqualität & Quellen", has to fit the 200 px button minus the 20 px left
        # margin and the 12 px right margin of the base theme; at 11 pt Desktop cut it to "Datenqualität &..."
        {"properties": {"text": _lit("'" + label.replace("'", "''") + "'"), "fontColor": _solid(inks[0]), "fontSize": _lit("10D"),
                        "horizontalAlignment": _lit("'left'"), "leftMargin": _lit("20L"), **bold},
         "selector": {"id": "default"}},
        {"properties": {"fontColor": _solid(inks[1]), **bold}, "selector": {"id": "hover"}},
    ]
    fill = [
        {"properties": {"show": _lit("true")}},
        {"properties": {"fillColor": _solid(fills[0]), "transparency": _lit("0D")}, "selector": {"id": "default"}},
        {"properties": {"fillColor": _solid(fills[1]), "transparency": _lit("0D")}, "selector": {"id": "hover"}},
    ]
    return {"text": text, "fill": fill}


def _page_json(page: dict) -> dict:
    pid = page["id"]
    data = {
        "$schema": SCHEMAS["page.json"],
        "name": pid,
        "displayName": page["displayName"],
        "displayOption": "FitToPage",
        "width": 1280,
        "height": 720,
        "annotations": [{"name": GENERATED, "value": "tools/pbi/pages.json"}],
    }
    if page.get("drillthrough"):
        filter_name = stable_name(pid, "drillthrough-filter")
        params, filters = [], []
        for n, (entity, prop) in enumerate(page["drillthrough"]):
            fname = filter_name if n == 0 else stable_name(pid, "drillthrough-filter", str(n))
            fexpr = _column(entity, prop)
            params.append({"name": stable_name(pid, "drillthrough-parameter", str(n)), "boundFilter": fname, "fieldExpr": fexpr})
            filters.append({"name": fname, "field": fexpr, "type": "Categorical", "howCreated": "Drillthrough"})
        data["type"] = "Drillthrough"
        data["pageBinding"] = {"name": stable_name(pid, "binding"), "type": "Drillthrough", "parameters": params}
        data["filterConfig"] = {"filters": filters}
    return data


def _textbox(colours: Colours, *args, **kwargs) -> dict:
    """Visual.textbox with the accent token as the colour of its link runs (they are underlined as well)."""
    return Visual.textbox(*args, link_colour=colours("accent"), **kwargs)


def _paragraph(paragraph: str | dict, colours: Colours) -> str | dict:
    """A spec paragraph is a string or {"text", "size", "bold", "colour" (a colour name), "url"}; the colour becomes a hex code."""
    if isinstance(paragraph, str) or "colour" not in paragraph:
        return paragraph
    return {**paragraph, "colour": colours(paragraph["colour"])}


def _visual_json(name: str, spec: dict, colours: Colours) -> dict:
    if spec["type"] == "textbox":
        container = _card_container(colours) if spec.get("card") else None
        return _textbox(colours, name, spec["x"], spec["y"], spec["w"], spec["h"],
                        [_paragraph(p, colours) for p in spec["paragraphs"]], container=container)
    roles = {role: [tuple(f) for f in fields] for role, fields in spec["roles"].items()}
    parameters = {role: {"parameter": tuple(p["parameter"]), "default": tuple(p["default"])}
                  for role, p in spec.get("field_parameters", {}).items()}
    return Visual.from_template(spec["type"], name, spec["x"], spec["y"], spec["w"], spec["h"], spec.get("title"),
                                roles, extra_objects=_formatting(spec, colours), alt=spec.get("alt"),
                                sort=spec.get("sort"), top_n=spec.get("top_n"), field_parameters=parameters,
                                subtitle=spec.get("subtitle"), title_hidden=spec.get("title_hidden", False),
                                container=_bare_container() if spec.get("bare") else None, filters=spec.get("filters"))


def _chrome(page: dict, pages: list[dict], colours: Colours) -> dict[str, dict]:
    """The visuals every page shares, by key; names are stable_name(page id, "chrome", key)."""
    if len(pages) != 5:
        raise ValueError(f"the side panel is laid out for five page buttons, the spec has {len(pages)} pages")
    pid = page["id"]
    ink, accent, muted = colours("ink"), colours("accent"), colours("inkMuted")
    panel = _panel_container(colours)
    name = lambda key: stable_name(pid, "chrome", key)  # noqa: E731
    out = {
        "brand": _textbox(colours, name("brand"), 0, 0, PANEL_WIDTH, NAV_TOP, [
            {"text": "ENERGIEWENDE", "size": 13, "bold": True, "colour": ink},
            {"text": "MONITOR", "size": 13, "bold": True, "colour": accent},
            {"text": "Strommarkt und Ausbau in Deutschland", "size": 9, "colour": muted},
        ], container=_panel_text_container(colours, 14)),
    }
    for i, target in enumerate(pages):
        out[f"nav{i}"] = Visual.from_template(
            "actionButton", name(f"nav{i}"), 0, NAV_TOP + NAV_HEIGHT * i, PANEL_WIDTH, NAV_HEIGHT, target["displayName"], {},
            extra_objects=_button_objects(target["displayName"], target["id"] == pid, colours), title_hidden=True,
            container={**panel, "visualLink": _page_link(target["id"])})
    nav_end = NAV_TOP + NAV_HEIGHT * len(pages)
    out["filler"] = _textbox(colours, name("filler"), 0, nav_end, PANEL_WIDTH, 616 - nav_end, [""], container=panel)
    # one source per line and a short repository line: in the 168 px between the paddings the old lines broke inside "(dl-de/by-2-0)"
    # and inside "energiewende-monitor". Plain text, no link run: Desktop draws a link in a fixed dark blue (#1D5899 measured on the
    # panel) whatever colour the run or the theme's hyperlink sets, and that is not readable on the panel
    out["footer"] = _textbox(colours, name("footer"), 0, 616, PANEL_WIDTH, 104, [
        {"text": "Daten: SMARD (CC BY 4.0)", "size": 8, "colour": muted},
        {"text": "MaStR (dl-de/by-2-0)", "size": 8, "colour": muted},
        {"text": "Harithas Harikaran", "size": 8, "colour": muted},
        {"text": "GitHub: energiewende-monitor", "size": 8, "colour": muted},
    ], container=_panel_text_container(colours, 8))
    out["title"] = _textbox(colours, name("title"), 216, 12, 640, 40, [
        {"text": page["displayName"], "size": 18, "bold": True, "colour": ink}], container=_bare_container())
    # 396 px wide (right edge at the 1264 margin, 12 px right of the title box): `Datenstand: SMARD 28.12.2026 · MaStR September 2026`
    # measures about 345 px at 10 pt Segoe UI Semibold and has to stay on one line
    stand = {"type": "card", "x": 868, "y": 12, "w": 396, "h": 40, "title": "Datenstand", "title_hidden": True, "bare": True,
             "label_size": 10, "label_colour": "inkMuted", "roles": {"Values": [["Kennzahlen", "Datenstand Kopfzeile", "Measure"]]}}
    out["stand"] = _visual_json(name("stand"), stand, colours)
    return out


def _page_visuals(page: dict, pages: list[dict], colours: Colours) -> list[dict]:
    """All visuals of a page in tab order: brand, navigation buttons, title, data stand, the page's own visuals in spec order,
    the panel filler and the footer last. z and tabOrder are that position, so they are unique per page."""
    pid = page["id"]
    chrome = _chrome(page, pages, colours)
    content = [_visual_json(stable_name(pid, str(index)), spec, colours) for index, spec in enumerate(page["visuals"])]
    ordered = [chrome["brand"], *(chrome[f"nav{i}"] for i in range(len(pages))), chrome["title"], chrome["stand"],
               *content, chrome["filler"], chrome["footer"]]
    for position, visual in enumerate(ordered):
        visual["position"]["z"] = visual["position"]["tabOrder"] = position
    return ordered


def _bookmark_json(page_ids: set[str], bm: dict) -> dict:
    if bm["page"] not in page_ids:
        raise ValueError(f"bookmark {bm['displayName']!r} refers to the unknown page {bm['page']!r}")
    flt = bm["filter"]
    entity, prop = flt["entity"], flt["property"]
    tpl = json.loads((HERE / "templates" / "bookmark.json").read_text(encoding="utf-8-sig"))
    tpl["$schema"] = SCHEMAS["bookmark.json"]
    tpl["displayName"] = bm["displayName"]
    tpl["name"] = stable_name("bookmark", bm["displayName"])
    tpl["explorationState"]["activeSection"] = bm["page"]
    values = [[{"Literal": {"Value": "'" + v.replace("'", "''") + "'"}}] for v in flt["values"]]
    tpl["explorationState"]["sections"] = {bm["page"]: {
        "visualContainers": {},
        "filters": {"byExpr": [{
            "name": stable_name("bookmark", bm["displayName"], "filter"),
            "type": "Categorical",
            "expression": _column(entity, prop),
            "filter": {
                "Version": 2,
                "From": [{"Name": "e", "Entity": entity, "Type": 0}],
                "Where": [{"Condition": {"In": {
                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "e"}}, "Property": prop}}],
                    "Values": values}}}],
            },
        }]},
    }}
    return tpl


def _register_theme(theme: str) -> None:
    resource = REGISTERED / theme
    if not resource.is_file():
        raise FileNotFoundError(f"theme {theme!r} from pages.json is not at {resource}")
    path = REPORT_DIR / "report.json"
    rep = json.loads(path.read_text(encoding="utf-8-sig"))
    rep["themeCollection"]["customTheme"] = {
        "name": theme,
        "reportVersionAtImport": SCHEMAS["baseTheme"]["reportVersionAtImport"],
        "type": "RegisteredResources",
    }
    packages = [p for p in rep.get("resourcePackages", []) if p.get("name") != "RegisteredResources"]
    packages.append({"name": "RegisteredResources", "type": "RegisteredResources",
                     "items": [{"name": theme, "path": theme, "type": "CustomTheme"}]})
    rep["resourcePackages"] = packages
    write_json(path, rep)


def _remove_generated_pages() -> None:
    pages_dir = REPORT_DIR / "pages"
    for page_json in pages_dir.glob("*/page.json"):
        data = json.loads(page_json.read_text(encoding="utf-8-sig"))
        if any(a.get("name") == GENERATED for a in data.get("annotations", [])):
            shutil.rmtree(page_json.parent)


def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    colours = Colours(spec)
    pages = spec["pages"]
    ids = [p["id"] for p in pages]
    _remove_generated_pages()
    for page in pages:
        pdir = REPORT_DIR / "pages" / page["id"]
        write_json(pdir / "page.json", _page_json(page))
        for v in _page_visuals(page, pages, colours):
            write_json(pdir / "visuals" / v["name"] / "visual.json", v)
    write_json(REPORT_DIR / "pages" / "pages.json",
               {"$schema": SCHEMAS["pages.json"], "pageOrder": ids, "activePageName": ids[0]})
    bdir = REPORT_DIR / "bookmarks"
    if bdir.exists():
        shutil.rmtree(bdir)
    items = []
    for bm in spec.get("bookmarks", []):
        data = _bookmark_json(set(ids), bm)
        write_json(bdir / f"{data['name']}.bookmark.json", data)
        items.append({"name": data["name"]})
    if items:
        write_json(bdir / "bookmarks.json", {"$schema": SCHEMAS["bookmarks.json"], "items": items})
    _register_theme(spec["theme"])


if __name__ == "__main__":
    main()
