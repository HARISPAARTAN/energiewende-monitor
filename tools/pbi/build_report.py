"""Regenerate the PBIR report pages, bookmarks and theme registration from tools/pbi/pages.json.

Deterministic: fixed names (uuid5 of page id and visual index), sorted keys, two-space indent, UTF-8 without BOM, LF.
Only page folders carrying the annotation `ewm:generated` are replaced; `bookmarks/` is owned entirely by this script.
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
SPEC = HERE / "pages.json"
GENERATED = "ewm:generated"
CHARTS = {"lineChart", "stackedAreaChart", "columnChart", "clusteredColumnChart", "clusteredBarChart", "scatterChart"}
COLOURED_BY_FARBE = {"stackedAreaChart", "columnChart"}


def _lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _column(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def _heatmap(spec: dict) -> list[dict]:
    """Cell background gradient on a matrix value field (conditional formatting by `FillRule`)."""
    entity, prop, kind = spec["field"]
    colour = lambda c: {"color": _lit("'" + c + "'")["expr"]}  # noqa: E731
    rule = {"linearGradient2": {"min": colour(spec["min"]), "max": colour(spec["max"]),
                                "nullColoringStrategy": {"strategy": _lit("'noColor'")["expr"]}}}
    fill = {"solid": {"color": {"expr": {"FillRule": {"Input": field_ref(entity, prop, kind), "FillRule": rule}}}}}
    return [{"properties": {"backColor": fill},
             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{entity}.{prop}"}}]


def _formatting(spec: dict) -> dict:
    """Visual-level objects: card font size, legend at the bottom, series colours from Energieträger[Farbe]."""
    objects: dict = {}
    roles = spec.get("roles", {})
    kind = spec["type"]
    if kind == "card":
        objects["labels"] = [{"properties": {"fontSize": _lit("28D")}}]
    if kind in CHARTS and (len(roles.get("Series", [])) or len(roles.get("Y", [])) > 1 or spec.get("legend")):
        objects["legend"] = [{"properties": {"show": _lit("true"), "position": _lit("'Bottom'")}}]
    if kind == "columnChart":
        objects["labels"] = [{"properties": {"show": _lit("false")}}]
    if kind in COLOURED_BY_FARBE and any(f[:2] == ["Energieträger", "Energieträger"] for f in roles.get("Series", [])):
        objects["dataPoint"] = [{"properties": {"fill": {"solid": {"color": {"expr": _column("Energieträger", "Farbe")}}}}}]
    if spec.get("heatmap"):
        objects["values"] = _heatmap(spec["heatmap"])
    for key, items in spec.get("objects", {}).items():
        objects[key] = items
    return objects


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


def _visual_json(pid: str, index: int, spec: dict) -> dict:
    name = stable_name(pid, str(index))
    if spec["type"] == "textbox":
        v = Visual.textbox(name, spec["x"], spec["y"], spec["w"], spec["h"], spec["paragraphs"])
        v["position"]["z"] = v["position"]["tabOrder"] = index
        return v
    roles = {role: [tuple(f) for f in fields] for role, fields in spec["roles"].items()}
    return Visual.from_template(spec["type"], name, spec["x"], spec["y"], spec["w"], spec["h"], spec.get("title"),
                                roles, z=index, extra_objects=_formatting(spec), alt=spec.get("alt"),
                                sort=spec.get("sort"), top_n=spec.get("top_n"))


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
    resource = REPORT_DIR.parent / "StaticResources" / "RegisteredResources" / theme
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
    pages = spec["pages"]
    ids = [p["id"] for p in pages]
    _remove_generated_pages()
    for page in pages:
        pdir = REPORT_DIR / "pages" / page["id"]
        write_json(pdir / "page.json", _page_json(page))
        for index, vspec in enumerate(page["visuals"]):
            v = _visual_json(page["id"], index, vspec)
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
