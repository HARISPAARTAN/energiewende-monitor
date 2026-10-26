"""Write the PBIP skeleton (semantic model in TMDL, report in PBIR) from the public formats.

Reads tools/pbi/rpt_columns.json (written by capture_rpt_columns.py) and tools/pbi/schema_versions.json.
Deterministic: lineage tags are uuid5 values derived from object names, so reruns do not churn git.
Refuses to overwrite an existing project unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PBI = ROOT / "powerbi"
NAME = "EnergiewendeMonitor"
SERVER = "127.0.0.1,1433"
DATABASE = "energiewende"
VIEWS = [
    "v_dim_datum", "v_dim_zeit", "v_dim_energietraeger", "v_dim_region", "v_dim_bundesland", "v_erzeugung",
    "v_last", "v_preis", "v_preis_last_stunde", "v_negative_preisphasen", "v_dq_luecken", "v_kapazitaet",
]
# SQL decimal and numeric reach Power Query as type number, which Desktop loads as double: on the first refresh it re-typed
# every column declared decimal (fixed decimal needs Currency.Type in the query, as money and smallmoney get)
SQL_TO_TMDL = {
    "bigint": "int64", "int": "int64", "smallint": "int64", "tinyint": "int64",
    "decimal": "double", "numeric": "double", "money": "decimal", "smallmoney": "decimal",
    "float": "double", "real": "double",
    "date": "dateTime", "datetime": "dateTime", "datetime2": "dateTime", "smalldatetime": "dateTime",
    "datetimeoffset": "dateTime", "time": "dateTime",
    "bit": "boolean",
    "char": "string", "varchar": "string", "nchar": "string", "nvarchar": "string", "text": "string", "ntext": "string",
}
FORMATS = {"int64": "0", "dateTime": "General Date"}
SCHEMAS = json.loads((HERE / "schema_versions.json").read_text(encoding="utf-8"))
SKELETON_PAGE = "skelett"


def tag(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "ewm:" + ":".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when it contains a dot, equals, colon, quote or whitespace."""
    if any(c in name for c in ".=:' \t") or not name:
        return "'" + name.replace("'", "''") + "'"
    return name


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # UTF-8 without BOM, LF; Desktop may rewrite with CRLF


def write_json(path: Path, data: dict) -> None:
    write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def table_tmdl(view: str, columns: list[list[str]]) -> str:
    t = "\t"
    lines = [f"table {q(view)}", f"{t}lineageTag: {tag('table', view)}", ""]
    for col, sql_type in columns:
        dtype = SQL_TO_TMDL.get(sql_type.lower())
        if dtype is None:
            raise SystemExit(f"unmapped SQL type {sql_type} in {view}.{col}")
        numeric = dtype in ("int64", "decimal", "double")
        lines += [f"{t}column {q(col)}", f"{t}{t}dataType: {dtype}"]
        if dtype in FORMATS:
            lines.append(f"{t}{t}formatString: {FORMATS[dtype]}")
        lines += [
            f"{t}{t}lineageTag: {tag('column', view, col)}",
            f"{t}{t}summarizeBy: {'sum' if numeric else 'none'}",
            f"{t}{t}sourceColumn: {col}",
            "",
            f"{t}{t}annotation SummarizationSetBy = Automatic",
            "",
        ]
    lines += [
        f"{t}partition {q(view)} = m",
        f"{t}{t}mode: import",
        f"{t}{t}source =",
        f"{t}{t}{t}{t}let",
        f'{t}{t}{t}{t}    Quelle = Sql.Database("{SERVER}", "{DATABASE}"),',
        f'{t}{t}{t}{t}    rpt_{view} = Quelle{{[Schema="rpt",Item="{view}"]}}[Data]',
        f"{t}{t}{t}{t}in",
        f"{t}{t}{t}{t}    rpt_{view}",
        "",
        f"{t}annotation PBI_NavigationStepName = Navigation",
        "",
        f"{t}annotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(lines)


def semantic_model(columns: dict[str, list[list[str]]]) -> None:
    sm = PBI / f"{NAME}.SemanticModel"
    write_json(sm / "definition.pbism", {"$schema": SCHEMAS["definition.pbism"]["$schema"],
                                          "version": SCHEMAS["definition.pbism"]["version"], "settings": {}})
    d = sm / "definition"
    write(d / "database.tmdl", f"database\n\tcompatibilityLevel: {SCHEMAS['tmdl']['compatibilityLevel']}\n\n")
    order = json.dumps(VIEWS, ensure_ascii=False).replace(", ", ",")
    model = [
        "model Model",
        "\tculture: de-DE",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: de-DE",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        f"annotation PBI_QueryOrder = {order}",
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
    ]
    model += [f"ref table {q(v)}" for v in VIEWS]
    model += ["", "ref cultureInfo de-DE", ""]
    write(d / "model.tmdl", "\n".join(model))
    write(d / "cultures" / "de-DE.tmdl", "cultureInfo de-DE\n\n")
    for view in VIEWS:
        write(d / "tables" / f"{view}.tmdl", table_tmdl(view, columns[view]))


def report() -> None:
    rp = PBI / f"{NAME}.Report"
    write_json(rp / "definition.pbir", {"$schema": SCHEMAS["definition.pbir"]["$schema"],
                                         "version": SCHEMAS["definition.pbir"]["version"],
                                         "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    base = SCHEMAS["baseTheme"]
    d = rp / "definition"
    write_json(d / "version.json", {"$schema": SCHEMAS["version.json"], "version": "2.0.0"})
    write_json(d / "report.json", {
        "$schema": SCHEMAS["report.json"],
        "themeCollection": {"baseTheme": {"name": base["name"], "reportVersionAtImport": base["reportVersionAtImport"],
                                          "type": "SharedResources"}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
            {"name": base["name"], "path": f"BaseThemes/{base['name']}.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    })
    write_json(d / "pages" / "pages.json", {"$schema": SCHEMAS["pages.json"], "pageOrder": [SKELETON_PAGE],
                                            "activePageName": SKELETON_PAGE})
    write_json(d / "pages" / SKELETON_PAGE / "page.json", {
        "$schema": SCHEMAS["page.json"], "name": SKELETON_PAGE, "displayName": "Seite 1",
        "displayOption": "FitToPage", "height": 720, "width": 1280,
        "annotations": [{"name": "ewm:generated", "value": "skeleton"}],
    })
    theme_src = HERE / "templates" / "basetheme" / f"{base['name']}.json"
    theme_dst = rp / "StaticResources" / "SharedResources" / "BaseThemes" / f"{base['name']}.json"
    theme_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(theme_src, theme_dst)


def pbip() -> None:
    write_json(PBI / f"{NAME}.pbip", {"$schema": SCHEMAS["pbip"], "version": "1.0",
                                      "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                      "settings": {"enableAutoRecovery": True}})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if (PBI / f"{NAME}.pbip").exists() and not args.force:
        raise SystemExit("powerbi/ already holds the project; use --force to rewrite the skeleton")
    columns = json.loads((HERE / "rpt_columns.json").read_text(encoding="utf-8"))
    missing = [v for v in VIEWS if not columns.get(v)]
    if missing:
        raise SystemExit(f"rpt_columns.json lacks {missing}")
    semantic_model(columns)
    report()
    pbip()
    print("skeleton written to", PBI)


if __name__ == "__main__":
    main()
