"""The SMARD filter IDs hard-coded in the load scripts and checks.py must match config.toml (review m2):
if config.toml changed alone, a fact table would silently stop updating."""

import re
from pathlib import Path

from ewmonitor import checks
from ewmonitor.config import load_settings

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = load_settings(ROOT)


def _sql(name: str) -> str:
    return (ROOT / "sql" / "load" / name).read_text(encoding="utf-8")


def test_fact_last_pivots_the_configured_consumption_filters_in_order():
    sql = _sql("120_fact_last.sql")
    pivot = [int(x) for x in re.findall(r"WHEN s\.filter_id = (\d+)\s+THEN", sql)]
    assert pivot == list(SETTINGS.smard.consumption)  # order: Netzlast, Residuallast, Pumpspeicher
    in_list = re.search(r"s\.filter_id IN \(([\d,\s]+)\)", sql).group(1)
    assert [int(x) for x in in_list.split(",")] == list(SETTINGS.smard.consumption)


def test_fact_preis_selects_the_configured_price_filter():
    ids = [int(x) for x in re.findall(r"s\.filter_id = (\d+)", _sql("130_fact_preis.sql"))]
    assert ids == [SETTINGS.smard.price]


def test_fact_erzeugung_has_no_hard_coded_filter_ids():
    assert not re.search(r"filter_id\s*(=|IN)\s*\(?\d", _sql("110_fact_erzeugung.sql"))


def test_checks_use_the_configured_filters_and_no_other_literals():
    assert checks.LAST_FILTER_IDS == SETTINGS.smard.consumption
    assert checks.PREIS_FILTER_ID == SETTINGS.smard.price
    source = Path(checks.__file__).read_text(encoding="utf-8")
    configured = {*SETTINGS.smard.consumption, SETTINGS.smard.price, *SETTINGS.smard.generation}
    for line in source.splitlines():
        if line.startswith(("LAST_FILTER_IDS", "PREIS_FILTER_ID")):
            continue
        assert not configured & {int(x) for x in re.findall(r"\b\d{3,4}\b", line)}, line
