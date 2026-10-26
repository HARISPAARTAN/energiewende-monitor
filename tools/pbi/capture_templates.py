"""Capture minimal visual templates from Microsoft's open-source PBIR reports (microsoft/fabric-toolbox, MIT).

Each template keeps the visualType and the generic formatting objects of one real Desktop-written visual.json;
query state, filters, series-specific formatting (objects with a selector) and the title are removed, and
$schema is set to the pinned visualContainer version. The bookmark template is built from the pinned schema.

Usage: uv run python tools/pbi/capture_templates.py [--from <local fabric-toolbox checkout>]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "templates"
COMMIT = "29264d36e5fdf483498faf97013ecf4dd0bd8a10"  # microsoft/fabric-toolbox main, 2026-10-09
RAW = f"https://raw.githubusercontent.com/microsoft/fabric-toolbox/{COMMIT}/"
FUAM = "monitoring/fabric-unified-admin-monitoring/src/FUAM_Core_Report.Report/definition/pages/"
FCA = "monitoring/fabric-cost-analysis/src/FCA_Core_Report.Report/definition/pages/"
QCC = "monitoring/query-capacity-correlation/Template/Query Capacity Correlation.Report/"
SOURCES = {
    "card": FCA + "df46552c6a3e07628f04/visuals/868e1c7e98e906177c84/visual.json",
    "lineChart": QCC + "definition/pages/dec6ca10089791a9a8a4/visuals/b3019a58595c63487980/visual.json",
    "stackedAreaChart": FUAM + "688e721a1b14ddc8d3bf/visuals/c3a103baf973b1389307/visual.json",
    "columnChart": FUAM + "b5d594eb912b41d58e08/visuals/b578a3168b812e4f8693/visual.json",
    "clusteredBarChart": FUAM + "8d39b414abb490008ab4/visuals/3a2389c850b5dd6638de/visual.json",
    "clusteredColumnChart": FCA + "ce90cb875cce385c58bf/visuals/6caac5df45468d874b6d/visual.json",
    "pivotTable": FUAM + "5e229a1d829e52ca29a0/visuals/a2f6b34ec53adbd98095/visual.json",
    "tableEx": FCA + "9e15d3671d9a3010bd29/visuals/fc0a449316d8eba4da1d/visual.json",
    "slicer": FCA + "85ebcf71ac1b1f9c1ef2/visuals/baacb70ed1417be32b31/visual.json",
    "scatterChart": QCC + "definition/pages/60a8309d95b9f8104e53/visuals/24bf8d23ffd9064054ee/visual.json",
    "textbox": FCA + "df46552c6a3e07628f04/visuals/05a172cf755d9e5899f4/visual.json",
    "gauge": FCA + "85ebcf71ac1b1f9c1ef2/visuals/0b978f632c4d409c5dde/visual.json",
    "actionButton": FCA + "b73ca32b395d659400ae/visuals/9811c0cd492f3a80c8e7/visual.json",
}
BASE_THEME = QCC + "StaticResources/SharedResources/BaseThemes/Fluent2-CY26SU08.json"
DROP_TOP = ("filterConfig", "isHidden", "parentGroupName", "howCreated", "annotations")
# container objects and properties that point into the source report (its canvas tooltip page, the page a button opens)
DROP_CONTAINER_OBJECTS = ("title", "visualHeaderTooltip")
DROP_CONTAINER_PROPERTIES = ("navigationSection", "drillthroughSection", "bookmark", "section", "showTooltipButton")


def fetch(rel: str, src: Path | None) -> bytes:
    if src is not None:
        return (src / rel).read_bytes()
    url = RAW + urllib.request.quote(rel)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def keeps(entry: dict) -> bool:
    """Generic formatting stays: an entry without selector or with a visual-state selector (`{"id": "default"}`, `{"id": "hover"}`).
    Entries scoped to series (data, metadata selectors) and entries bound to fields of the source model go."""
    selector = entry.get("selector")
    if selector and set(selector) != {"id"}:
        return False
    return "SourceRef" not in json.dumps(entry)


def strip_container_references(container: dict) -> dict:
    """The container objects without the title and without anything that points into the source report."""
    out = {}
    for key, entries in container.items():
        if key in DROP_CONTAINER_OBJECTS:
            continue
        kept = []
        for entry in entries:
            props = {k: val for k, val in entry.get("properties", {}).items() if k not in DROP_CONTAINER_PROPERTIES}
            if props:
                kept.append({**entry, "properties": props})
        if kept:
            out[key] = kept
    return out


def minimise(visual: dict, visual_type: str, schema: str) -> dict:
    assert visual["visual"]["visualType"] == visual_type, (visual["visual"]["visualType"], visual_type)
    out = {k: v for k, v in visual.items() if k not in DROP_TOP}
    out["$schema"] = schema
    out["name"] = "template"
    out["position"] = {"x": 0, "y": 0, "z": 0, "height": 100, "width": 100, "tabOrder": 0}
    v = out["visual"]
    if "query" in v:
        v["query"] = {"queryState": {}}
    v.pop("expansionStates", None)
    v.pop("syncGroup", None)
    objects = {}
    for key, entries in v.get("objects", {}).items():
        kept = [e for e in entries if keeps(e)]
        if kept:
            objects[key] = kept
    if visual_type == "textbox":
        objects["general"] = [{"properties": {"paragraphs": [{"textRuns": [{"value": "Text"}]}]}}]
    v["objects"] = objects
    vco = strip_container_references(v.get("visualContainerObjects", {}))
    if vco:
        v["visualContainerObjects"] = vco
    else:
        v.pop("visualContainerObjects", None)
    return out


def bookmark_template(schema: str) -> dict:
    return {
        "$schema": schema,
        "displayName": "TEMPLATE",
        "name": "template",
        "options": {"targetVisualNames": []},
        "explorationState": {"version": "1.3", "activeSection": "PAGE",
                             "sections": {"PAGE": {"visualContainers": {}}}, "objects": {}},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=Path, default=None)
    args = ap.parse_args()
    versions = json.loads((HERE / "schema_versions.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for visual_type, rel in SOURCES.items():
        visual = json.loads(fetch(rel, args.src).decode("utf-8-sig"))
        tpl = minimise(visual, visual_type, versions["visual.json"])
        (OUT / f"{visual_type}.json").write_text(json.dumps(tpl, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("template", visual_type)
    (OUT / "bookmark.json").write_text(json.dumps(bookmark_template(versions["bookmark.json"]), indent=2) + "\n",
                                       encoding="utf-8")
    theme_dir = OUT / "basetheme"
    theme_dir.mkdir(exist_ok=True)
    (theme_dir / "Fluent2-CY26SU08.json").write_bytes(fetch(BASE_THEME, args.src))
    print("base theme Fluent2-CY26SU08")


if __name__ == "__main__":
    main()
