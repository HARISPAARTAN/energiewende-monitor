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
# data roles (queryState keys) each internal visual type accepts; the generator and the lint both enforce them
ROLES = {
    "card": {"Values"},
    "slicer": {"Values"},
    "tableEx": {"Values"},
    "pivotTable": {"Rows", "Columns", "Values"},
    "lineChart": {"Category", "Series", "Y", "Y2"},
    "stackedAreaChart": {"Category", "Series", "Y", "Y2"},
    "columnChart": {"Category", "Series", "Y", "Y2"},
    "clusteredColumnChart": {"Category", "Series", "Y", "Y2"},
    "clusteredBarChart": {"Category", "Series", "Y", "Y2"},
    "scatterChart": {"Category", "Series", "X", "Y", "Size"},
    "textbox": set(),
}
ALT_PREFIX = {"card": "Kennzahl", "tableEx": "Tabelle", "pivotTable": "Matrix"}  # every other type: "Diagramm"


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


def _literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _set_alt_text(v: dict, alt: str | None) -> None:
    """Replace the template's alt text; None removes it (slicers and text boxes carry none)."""
    container = v["visual"].setdefault("visualContainerObjects", {})
    entries = container.get("general") or [{"properties": {}}]
    props = entries[0].setdefault("properties", {})
    props.pop("altText", None)
    if alt:
        props["altText"] = _literal("'" + alt.replace("'", "''") + "'")
    if props:
        container["general"] = entries
    else:
        container.pop("general", None)
    if not container:
        v["visual"].pop("visualContainerObjects", None)


def default_alt_text(visual_type: str, title: str | None) -> str | None:
    return f"{ALT_PREFIX.get(visual_type, 'Diagramm')}: {title}" if title else None


def _top_n_filter(name: str, spec: dict) -> dict:
    """Visual-level TopN filter in the shape Desktop writes: the filtered field is the item column, the ranking
    field is aggregated in a subquery ordered descending with `Top`, and the filter keeps the items In that subquery."""
    entity, prop = spec["field"][:2]
    by_entity, by_prop, by_kind = spec["by"]
    item = {"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": prop}}
    rank = {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": by_prop}},
                            "Function": AGGREGATIONS[by_kind]}}
    sub = {"Version": 2, "From": [{"Name": "p", "Entity": entity, "Type": 0}], "Select": [dict(item, Name="field")],
           "OrderBy": [{"Direction": 2, "Expression": rank}], "Top": spec["n"]}
    return {
        "name": name,
        "field": field_ref(entity, prop, "Column"),
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [{"Name": "subquery", "Expression": {"Subquery": {"Query": sub}}, "Type": 2},
                     {"Name": "p", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [item], "Table": {"SourceRef": {"Source": "subquery"}}}}}],
        },
    }


class Visual:
    """Builds a visual.json from a captured template by replacing position, title and query projections."""

    @staticmethod
    def from_template(visual_type: str, name: str, x: float, y: float, w: float, h: float, title: str | None,
                      roles: dict[str, list[tuple[str, str, str]]], z: int = 0, extra_objects: dict | None = None,
                      alt: str | None = None, sort: dict | None = None, top_n: dict | None = None) -> dict:
        """alt: alt text (None derives a German one from the title, "" leaves none); sort: {"field": [e, p, kind],
        "direction": "Descending"}; top_n: {"field": [e, p], "by": [e, p, aggregation], "n": 10}."""
        if visual_type not in ROLES:
            raise ValueError(f"unknown visual type {visual_type!r}")
        bad = set(roles) - ROLES[visual_type]
        if bad:
            raise ValueError(f"{visual_type} has no role(s) {sorted(bad)}; allowed: {sorted(ROLES[visual_type])}")
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
        _set_alt_text(v, default_alt_text(visual_type, title) if alt is None else alt)
        if sort:
            e, p, k = sort["field"]
            v["visual"]["query"]["sortDefinition"] = {"sort": [{"field": field_ref(e, p, k), "direction": sort["direction"]}]}
        if top_n:
            v["filterConfig"] = {"filters": [_top_n_filter(stable_name(name, "topn"), top_n)]}
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
        _set_alt_text(v, None)
        v["visual"]["objects"]["general"] = [{"properties": {"paragraphs": [
            {"textRuns": [{"value": p, "textStyle": {"fontSize": f"{font_size}pt"}}]} for p in paragraphs]}}]
        return v


def iter_fields(node, aliases: dict[str, str] | None = None):
    """Yield (entity, property, kind) for every Column or Measure reference anywhere below `node` (queryState,
    objects, sort, filters, bookmark filters). kind is the node type, so an aggregation yields its Column.
    A `Source` alias is resolved through the `From` entries (`Name` -> `Entity`) found below `node`."""
    if aliases is None:
        aliases = {}
        stack = [node]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "Name" in cur and "Entity" in cur and "Property" not in cur:
                    aliases[cur["Name"]] = cur["Entity"]
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            ref = node.get(kind)
            if isinstance(ref, dict) and "Property" in ref:
                source = ref.get("Expression", {}).get("SourceRef", {})
                entity = source.get("Entity") or aliases.get(source.get("Source", ""), "?" + source.get("Source", ""))
                yield entity, ref["Property"], kind
        for value in node.values():
            yield from iter_fields(value, aliases)
    elif isinstance(node, list):
        for value in node:
            yield from iter_fields(value, aliases)


@dataclass
class LintVisual:
    name: str
    visual_type: str
    raw: dict

    def bound_fields(self):
        """Every (entity, property, kind) the visual references, kind being 'Column' or 'Measure'."""
        return list(iter_fields(self.raw))

    def roles(self) -> set[str]:
        return set(self.raw.get("visual", {}).get("query", {}).get("queryState", {}))

    @property
    def title(self) -> str | None:
        props = (self.raw.get("visual", {}).get("visualContainerObjects", {}).get("title") or [{}])[0].get("properties", {})
        value = props.get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        return value[1:-1].replace("''", "'") if value else None

    @property
    def alt_text(self) -> str | None:
        props = (self.raw.get("visual", {}).get("visualContainerObjects", {}).get("general") or [{}])[0].get("properties", {})
        value = props.get("altText", {}).get("expr", {}).get("Literal", {}).get("Value")
        return value[1:-1].replace("''", "'") if value else None


@dataclass
class Page:
    name: str
    display_name: str
    width: int
    height: int
    visuals: list[LintVisual] = field(default_factory=list)
    drillthrough_fields: list[dict] = field(default_factory=list)  # the fieldExpr of each drillthrough parameter
    raw: dict = field(default_factory=dict)  # page.json


@dataclass
class Report:
    pages: list[Page]
    bookmarks: list[dict]
    theme_name: str | None
    bookmark_items: list[str] = field(default_factory=list)  # names listed in bookmarks/bookmarks.json


def load_report(definition_dir: Path) -> Report:
    d = Path(definition_dir)
    order = json.loads((d / "pages" / "pages.json").read_text(encoding="utf-8-sig"))["pageOrder"]
    pages = []
    for pid in order:
        pj = json.loads((d / "pages" / pid / "page.json").read_text(encoding="utf-8-sig"))
        page = Page(pid, pj["displayName"], int(pj["width"]), int(pj["height"]), raw=pj)
        binding = pj.get("pageBinding") or {}
        if binding.get("type") == "Drillthrough":
            for param in binding.get("parameters", []):
                page.drillthrough_fields.append(param["fieldExpr"])
        for vdir in sorted(p for p in (d / "pages" / pid / "visuals").iterdir() if p.is_dir()):
            vj = json.loads((vdir / "visual.json").read_text(encoding="utf-8-sig"))
            vtype = vj.get("visual", {}).get("visualType") or vj.get("visualGroup", {}).get("displayName", "group")
            page.visuals.append(LintVisual(vj["name"], vtype, vj))
        pages.append(page)
    bookmarks, items = [], []
    bdir = d / "bookmarks"
    if bdir.exists():
        for bf in sorted(bdir.glob("*.bookmark.json")):
            bookmarks.append(json.loads(bf.read_text(encoding="utf-8-sig")))
        meta = bdir / "bookmarks.json"
        if meta.exists():
            items = [i["name"] for i in json.loads(meta.read_text(encoding="utf-8-sig")).get("items", [])]
    rep = json.loads((d / "report.json").read_text(encoding="utf-8-sig"))
    theme = None
    for t in rep.get("themeCollection", {}).values():
        if isinstance(t, dict) and t.get("name") and t.get("type") == "RegisteredResources":
            theme = t["name"]
    return Report(pages, bookmarks, theme, items)
