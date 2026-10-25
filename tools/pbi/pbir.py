"""PBIR helpers: read a report folder for linting; build visuals from the templates captured in Task 1."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"
SCHEMAS = json.loads((Path(__file__).parent / "schema_versions.json").read_text(encoding="utf-8"))
AGGREGATIONS = {"Sum": 0, "Avg": 1, "Count": 2, "Min": 3, "Max": 4}  # PBIR Aggregation.Function codes


def stable_name(*parts: str) -> str:
    """A deterministic 20-hex visual or page name, so regenerating the report does not churn git."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "ewm:" + ":".join(parts)).hex[:20]


def field_ref(entity: str, prop: str, kind: str) -> dict:
    """kind: 'Column', 'Measure', or an aggregation of a column ('Sum', 'Avg', 'Count', 'Min', 'Max')."""
    if kind in AGGREGATIONS:
        column = {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}
        return {"Aggregation": {"Expression": column, "Function": AGGREGATIONS[kind]}}
    return {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def projection(entity: str, prop: str, kind: str, active: bool = False) -> dict:
    query_ref = f"{kind}({entity}.{prop})" if kind in AGGREGATIONS else f"{entity}.{prop}"
    p = {"field": field_ref(entity, prop, kind), "queryRef": query_ref, "nativeQueryRef": prop}
    if active:
        p["active"] = True
    return p


def _title(title: str | None) -> list[dict]:
    if title is None:
        return [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
    return [{"properties": {"show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}}}}]


class Visual:
    """Builds a visual.json from a captured template by replacing position, title and query projections."""

    @staticmethod
    def from_template(visual_type: str, name: str, x: float, y: float, w: float, h: float, title: str | None,
                      roles: dict[str, list[tuple[str, str, str]]], z: int = 0, extra_objects: dict | None = None) -> dict:
        tpl = json.loads((TEMPLATES / f"{visual_type}.json").read_text(encoding="utf-8-sig"))
        v = copy.deepcopy(tpl)
        v["$schema"] = SCHEMAS["visual.json"]
        v["name"] = name
        v["position"] = {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}
        v["visual"]["visualType"] = visual_type
        state = v["visual"].setdefault("query", {}).setdefault("queryState", {})
        state.clear()
        for role, fields in roles.items():
            active = role in ("Category", "Rows", "Columns") or visual_type == "slicer"
            state[role] = {"projections": [projection(e, p, k, active and k == "Column") for e, p, k in fields]}
        v["visual"].setdefault("visualContainerObjects", {})["title"] = _title(title)
        if extra_objects:
            objects = v["visual"].setdefault("objects", {})
            for key, items in extra_objects.items():
                # merge into the template's first entry so its other captured properties survive
                if objects.get(key) and items:
                    objects[key][0].setdefault("properties", {}).update(items[0].get("properties", {}))
                else:
                    objects[key] = items
        v["visual"]["drillFilterOtherVisuals"] = True
        return v

    @staticmethod
    def textbox(name: str, x: float, y: float, w: float, h: float, paragraphs: list[str], font_size: int = 12) -> dict:
        tpl = json.loads((TEMPLATES / "textbox.json").read_text(encoding="utf-8-sig"))
        v = copy.deepcopy(tpl)
        v["$schema"] = SCHEMAS["visual.json"]
        v["name"] = name
        v["position"] = {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}
        v["visual"]["objects"]["general"] = [{"properties": {"paragraphs": [
            {"textRuns": [{"value": p, "textStyle": {"fontSize": f"{font_size}pt"}}]} for p in paragraphs]}}]
        return v


@dataclass
class LintVisual:
    name: str
    visual_type: str
    raw: dict

    def bound_fields(self):
        out = []
        state = self.raw.get("visual", {}).get("query", {}).get("queryState", {})
        for role in state.values():
            for proj in role.get("projections", []):
                f = proj.get("field", {})
                for kind in ("Column", "Measure", "Aggregation"):
                    node = f.get(kind)
                    if kind == "Aggregation" and node:
                        node = node.get("Expression", {}).get("Column", {})
                    if node:
                        out.append((node["Expression"]["SourceRef"]["Entity"], node["Property"], kind))
        return out


@dataclass
class Page:
    name: str
    display_name: str
    width: int
    height: int
    visuals: list[LintVisual] = field(default_factory=list)
    drillthrough_fields: list[str] = field(default_factory=list)


@dataclass
class Report:
    pages: list[Page]
    bookmarks: list[dict]
    theme_name: str | None


def load_report(definition_dir: Path) -> Report:
    d = Path(definition_dir)
    order = json.loads((d / "pages" / "pages.json").read_text(encoding="utf-8-sig"))["pageOrder"]
    pages = []
    for pid in order:
        pj = json.loads((d / "pages" / pid / "page.json").read_text(encoding="utf-8-sig"))
        page = Page(pid, pj["displayName"], int(pj.get("width", 1280)), int(pj.get("height", 720)))
        binding = pj.get("pageBinding") or {}
        if binding.get("type") == "Drillthrough":
            for param in binding.get("parameters", []):
                page.drillthrough_fields.append(json.dumps(param.get("fieldExpr", {}), ensure_ascii=False))
        for vdir in sorted((d / "pages" / pid / "visuals").glob("*")):
            vj = json.loads((vdir / "visual.json").read_text(encoding="utf-8-sig"))
            vtype = vj.get("visual", {}).get("visualType") or vj.get("visualGroup", {}).get("displayName", "group")
            page.visuals.append(LintVisual(vj["name"], vtype, vj))
        pages.append(page)
    bookmarks = []
    bdir = d / "bookmarks"
    if bdir.exists():
        for bf in sorted(bdir.glob("*.bookmark.json")):
            bookmarks.append(json.loads(bf.read_text(encoding="utf-8-sig")))
    rep = json.loads((d / "report.json").read_text(encoding="utf-8-sig"))
    theme = None
    for t in rep.get("themeCollection", {}).values():
        if isinstance(t, dict) and t.get("name") and t.get("type") == "RegisteredResources":
            theme = t["name"]
    return Report(pages, bookmarks, theme)
