import json
from pathlib import Path

import pytest

from tools.pbi.pbir import load_report
from tools.pbi.tmdl import load_model

pytestmark = pytest.mark.pbi
ROOT = Path(__file__).resolve().parents[2] / "powerbi"
REPORT = ROOT / "EnergiewendeMonitor.Report" / "definition"
MODEL = ROOT / "EnergiewendeMonitor.SemanticModel" / "definition"
PAGES = ["Überblick", "Erzeugung & Last", "Preise", "Ausbau", "Datenqualität & Quellen"]


@pytest.fixture(scope="module")
def report():
    return load_report(REPORT)


def test_five_pages_in_order_and_16_9(report):
    assert [p.display_name for p in report.pages] == PAGES
    for p in report.pages:
        assert (p.width, p.height) == (1280, 720), p.display_name


def test_every_bound_field_exists_in_the_model(report):
    model = load_model(MODEL)
    for p in report.pages:
        for v in p.visuals:
            for entity, prop, _kind in v.bound_fields():
                table = model.tables.get(entity)
                assert table is not None, (p.display_name, v.name, entity)
                assert prop in table.columns or prop in table.measures, (p.display_name, v.name, entity, prop)


def test_no_map_or_custom_visuals(report):
    for p in report.pages:
        for v in p.visuals:
            assert v.visual_type not in ("map", "filledMap", "azureMap", "shapeMap"), (p.display_name, v.name)
            assert not v.visual_type.startswith("PBI_CV_"), v.visual_type


def test_page_contents_match_the_spec(report):
    by = {p.display_name: p for p in report.pages}

    def types(name):
        return sorted(v.visual_type for v in by[name].visuals)

    assert types("Überblick").count("card") == 5
    assert "stackedAreaChart" in types("Überblick") and "lineChart" in types("Überblick") and types("Überblick").count("slicer") >= 2
    assert "lineChart" in types("Erzeugung & Last") and "pivotTable" in types("Erzeugung & Last") and "columnChart" in types("Erzeugung & Last")
    assert "clusteredColumnChart" in types("Preise") and "scatterChart" in types("Preise") and "tableEx" in types("Preise")
    assert "clusteredBarChart" in types("Ausbau") and "columnChart" in types("Ausbau") and "tableEx" in types("Ausbau")
    assert "tableEx" in types("Datenqualität & Quellen") and types("Datenqualität & Quellen").count("textbox") >= 2


def test_attributions_and_links_present(report):
    page = next(p for p in report.pages if p.display_name == "Datenqualität & Quellen")
    text = json.dumps([v.raw for v in page.visuals], ensure_ascii=False)
    assert "Bundesnetzagentur | SMARD.de" in text
    assert "Marktstammdatenregister der Bundesnetzagentur" in text and "dl-de/by-2-0" in text
    assert "github.com/HARISPAARTAN/energiewende-monitor" in text and "harispaartan.github.io" in text


def test_drillthrough_and_bookmarks(report):
    el = next(p for p in report.pages if p.display_name == "Erzeugung & Last")
    assert el.drillthrough_fields and any("Datum" in f for f in el.drillthrough_fields)
    names = {b["displayName"] for b in report.bookmarks}
    assert {"Erneuerbar", "Konventionell"} <= names


def test_theme_registered_and_colours(report):
    theme = json.loads((ROOT / "EnergiewendeMonitor.Report" / "StaticResources" / "RegisteredResources" / "energiewende.json").read_text(encoding="utf-8"))
    assert theme["background"].upper() == "#F7F7F4" and theme["foreground"].upper() == "#14181D"
    assert report.theme_name == "energiewende.json"
