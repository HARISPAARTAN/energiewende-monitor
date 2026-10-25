from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ewmonitor import mastr

FIXTURE_TABLES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "mastr" / "tables"
SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
CAL_START, CAL_END = date(1990, 1, 1), date(2030, 12, 31)
ENDGUELTIG = "Endgültig stillgelegt"


@pytest.fixture(scope="module")
def sqlite_path(tmp_path_factory):
    return mastr.sqlite_from_csv_dir(FIXTURE_TABLES, tmp_path_factory.mktemp("mastr") / "open-mastr.db")


@pytest.fixture(scope="module")
def units(sqlite_path):
    return pd.concat(list(mastr.iter_units(sqlite_path, chunksize=7)), ignore_index=True)


@pytest.fixture(scope="module")
def mapping():
    return mastr.load_mapping(SEED_DIR / "mastr_energietraeger_mapping.csv")


def _raw(*rows: dict) -> pd.DataFrame:
    """Hand-made units, normalised like an iter_units chunk; each dict overrides the defaults (BY solar, 10 kW)."""
    base = {"einheit": "X", "tabelle": "EinheitenSolar", "bundesland": "Bayern", "status": "In Betrieb",
            "inbetriebnahme": "2020-05-01", "stilllegung": None, "netto_kw": "10", "energietraeger_mastr": None,
            "technologie": None, "hauptbrennstoff": None, "lage": None}
    return mastr._normalise(pd.DataFrame([{**base, **row} for row in rows], columns=list(mastr.UNIT_COLUMNS)))


def test_iter_units_reads_every_table_with_normalised_columns(units):
    assert list(units.columns) == list(mastr.UNIT_COLUMNS)
    assert set(units["tabelle"]) == set(mastr.UNIT_TABLES)
    assert len(units) == 61
    assert units["inbetriebnahme"].dtype == "datetime64[ns]"
    assert units["netto_kw"].dtype == "float64"
    assert units.loc[units["einheit"] == "SEE900000000001", "lage"].item() == "Windkraft auf See"


def test_mapping_values_exist_in_dim_energietraeger(mapping):
    names = set(pd.read_csv(SEED_DIR / "dim_energietraeger.csv")["name_de"])
    assert set(mapping["energietraeger"]) - {"VERWERFEN"} <= names


def test_map_energietraeger(units, mapping):
    mapped = mastr.map_energietraeger(units, mapping)
    by = mapped.set_index("einheit")
    assert by.loc["SEE900000000001", "energietraeger"] == "Wind Offshore"
    assert by.loc["SEE900000000002", "energietraeger"] == "Wind Onshore"
    assert by.loc["SEE900000000011", "energietraeger"] == "Photovoltaik"
    assert by.loc["SEE900000000031", "energietraeger"] == "Braunkohle"
    assert by.loc["SEE900000000036", "energietraeger"] == "Sonstige Konventionelle"  # Mineralölprodukte
    assert by.loc["SEE900000000037", "energietraeger"] == "Sonstige Konventionelle"  # unmapped fuel "Wasserstoff"
    assert bool(by.loc["SEE900000000037", "unmapped"]) is True
    assert bool(by.loc["SEE900000000052", "verworfen"]) is True  # Batterie
    assert by.loc["SEE900000000051", "energietraeger"] == "Pumpspeicher"


def test_mapping_fallback_rows_catch_null_lage_and_technologie(mapping):
    units = _raw({"einheit": "W", "tabelle": "EinheitenWind", "lage": None},
                 {"einheit": "S", "tabelle": "EinheitenStromSpeicher", "technologie": None})
    by = mastr.map_energietraeger(units, mapping).set_index("einheit")
    assert by.loc["W", "energietraeger"] == "Wind Onshore"
    assert bool(by.loc["W", "unmapped"]) is False
    assert bool(by.loc["S", "verworfen"]) is True
    assert bool(by.loc["S", "unmapped"]) is False


@pytest.mark.parametrize("line, message", [
    ("EinheitenSolar,*,Photovoltaik,Photovoltaik", "feld '\\*' verlangt wert '\\*'"),
    ("EinheitenSolar,lage,,Photovoltaik", "leere Zellen"),
    ("EinheitenSolar,*,*,", "leere Zellen"),
])
def test_load_mapping_rejects_invalid_rows(tmp_path, line, message):
    path = tmp_path / "mapping.csv"
    path.write_text(f"tabelle,feld,wert,energietraeger\nEinheitenWind,*,*,Wind Onshore\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        mastr.load_mapping(path)


def test_aggregate_rules(sqlite_path, units, mapping):
    seed, stats = mastr.aggregate(mastr.iter_units(sqlite_path, chunksize=10), CAL_START, CAL_END, mapping)
    assert list(seed.columns) == list(mastr.SEED_COLUMNS)
    row = seed.set_index(["jahr_monat", "bundesland_kuerzel", "energietraeger"])
    # SEE...021 (BY, Biomasse, 500 kW, in Betrieb 2015-06-17) -> Zubau 0.5 MW in 2015-06
    assert row.loc[("2015-06", "BY", "Biomasse"), "zubau_mw"] == pytest.approx(0.5)
    assert row.loc[("2015-06", "BY", "Biomasse"), "anzahl_zubau"] == 1
    # SEE...031 (NW, Braunkohle, 300000 kW, in Betrieb 1985, endgueltig stillgelegt 2024-03-31) -> Anfangsbestand + Abgang
    assert row.loc[("1990-01", "NW", "Braunkohle"), "anfangsbestand_mw"] == pytest.approx(300.0)
    assert row.loc[("2024-03", "NW", "Braunkohle"), "abgang_mw"] == pytest.approx(300.0)
    # SEE...032 (NW, Steinkohle, stillgelegt 1988-12-31, before the calendar) -> ignored entirely
    assert ("1990-01", "NW", "Steinkohle") not in row.index
    assert ("1988-12", "NW", "Steinkohle") not in row.index
    # SEE...013 (SN, Solar, 5 kW, In Betrieb without a date) -> Anfangsbestand in the first calendar month
    assert row.loc[("1990-01", "SN", "Photovoltaik"), "anfangsbestand_anzahl"] == 1
    assert row.loc[("1990-01", "SN", "Photovoltaik"), "anfangsbestand_mw"] == 0.005
    # SEE...005 (NI, Wind, 600 kW, 1998-05-20, endgueltig stillgelegt 2019-12-31) -> one Abgang, Zubau kept
    assert row.loc[("2019-12", "NI", "Wind Onshore"), "anzahl_abgang"] == 1
    assert row.loc[("2019-12", "NI", "Wind Onshore"), "abgang_mw"] == pytest.approx(0.6)
    assert row.loc[("1998-05", "NI", "Wind Onshore"), "anzahl_zubau"] == 1
    # SEE...010 (HE, Wind, 3300 kW, Vorübergehend stillgelegt with a Stilllegung date 2024-06-30) -> no Abgang
    assert units.loc[units["einheit"] == "SEE900000000010", "stilllegung"].notna().item()
    assert ("2024-06", "HE", "Wind Onshore") not in row.index
    assert row.loc[("2017-05", "HE", "Wind Onshore"), "zubau_mw"] == pytest.approx(3.3)
    assert int(row.xs(("HE", "Wind Onshore"), level=["bundesland_kuerzel", "energietraeger"])["anzahl_abgang"].sum()) == 0
    # SEE...001 offshore without Bundesland -> AWZ
    assert ("2020-04", "AWZ", "Wind Offshore") in row.index
    # SEE...012 (solar, Bundesland NULL, onshore table) -> UNB
    assert ("2021-09", "UNB", "Photovoltaik") in row.index
    assert stats["einheiten"] == 61
    assert stats["in_planung"] == 3
    assert stats["vor_kalender_abgang"] == 1
    assert stats["inbetriebnahme_fehlt"] == 2
    assert stats["verworfen"] == 2
    assert stats["unmapped"] == 1
    assert stats["datum_unplausibel"] == 0
    assert stats["netto_unplausibel"] == 0
    assert stats["nach_kalender"] == 0
    assert stats["stilllegung_ohne_datum"] == 0
    assert (seed[["zubau_mw", "abgang_mw", "anfangsbestand_mw"]].sum(axis=1) > 0).all()
    assert seed.equals(seed.sort_values(list(mastr.SEED_COLUMNS[:3])).reset_index(drop=True))


def test_aggregate_sums_unrounded_mw_before_rounding_the_cell(mapping):
    two = _raw({"netto_kw": "0.3"}, {"netto_kw": "0.6"})
    chunk = two.loc[two.index.repeat(100_000)].reset_index(drop=True)  # 100,000 x 0.3 kW + 100,000 x 0.6 kW
    seed, stats = mastr.aggregate([chunk], CAL_START, CAL_END, mapping)
    assert len(seed) == 1
    assert seed.loc[0, "zubau_mw"] == 90.0  # per-unit rounding would give 0.0 + 100.0
    assert seed.loc[0, "anzahl_zubau"] == 200_000
    split, split_stats = mastr.aggregate([chunk.iloc[:150_000], chunk.iloc[150_000:]], CAL_START, CAL_END, mapping)
    pd.testing.assert_frame_equal(split, seed)
    assert split_stats == stats


def test_aggregate_is_independent_of_chunking(sqlite_path, units, mapping):
    one, one_stats = mastr.aggregate([units], CAL_START, CAL_END, mapping)
    many, many_stats = mastr.aggregate(mastr.iter_units(sqlite_path, chunksize=3), CAL_START, CAL_END, mapping)
    pd.testing.assert_frame_equal(many, one)
    assert many_stats == one_stats


def test_aggregate_drops_nonpositive_capacity_and_months_after_calendar_end(mapping):
    units = _raw({"einheit": "N0", "netto_kw": "0"},
                 {"einheit": "N1", "netto_kw": "-5"},
                 {"einheit": "Z", "inbetriebnahme": "2031-02-01"},
                 {"einheit": "A", "netto_kw": "20", "status": ENDGUELTIG, "stilllegung": "2031-05-31"})
    seed, stats = mastr.aggregate([units], CAL_START, CAL_END, mapping)
    assert stats["netto_unplausibel"] == 2
    assert stats["nach_kalender"] == 2  # Zubau of Z, Abgang of A
    assert seed["jahr_monat"].tolist() == ["2020-05"]
    assert seed.loc[0, "zubau_mw"] == 0.02
    assert seed.loc[0, "anzahl_zubau"] == 1
    assert seed.loc[0, "anzahl_abgang"] == 0


def test_normalise_treats_implausible_dates_as_missing_and_counts_them(mapping):
    units = _raw({"einheit": "A", "inbetriebnahme": "2300-01-01"},  # beyond the datetime64[ns] limit
                 {"einheit": "B", "inbetriebnahme": "2150-05-05"},
                 {"einheit": "C", "inbetriebnahme": "1850-01-01"},
                 {"einheit": "D", "status": ENDGUELTIG, "stilllegung": "2999-12-31"},
                 {"einheit": "E"})
    assert units["inbetriebnahme"].dtype == "datetime64[ns]"
    assert units["inbetriebnahme"].isna().tolist() == [True, True, True, False, False]
    assert units["stilllegung"].isna().all()
    assert units.attrs["datum_unplausibel"] == 4
    _, stats = mastr.aggregate([units], CAL_START, CAL_END, mapping)
    assert stats["datum_unplausibel"] == 4
    assert stats["inbetriebnahme_fehlt"] == 3
    assert stats["stilllegung_ohne_datum"] == 1


def test_iter_units_passes_the_implausible_date_count_to_aggregate(tmp_path, mapping):
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "EinheitenSolar.csv").write_text(
        "EinheitMastrNummer,Bundesland,Nettonennleistung,Inbetriebnahmedatum,EinheitBetriebsstatus,"
        "DatumEndgueltigeStilllegung,Energietraeger\n"
        "S1,Bayern,10,2300-01-01,In Betrieb,,Solare Strahlungsenergie\n"
        "S2,Bayern,10,2020-05-01,In Betrieb,,Solare Strahlungsenergie\n", encoding="utf-8")
    db = mastr.sqlite_from_csv_dir(tables, tmp_path / "open-mastr.db")
    _, stats = mastr.aggregate(mastr.iter_units(db, chunksize=1), CAL_START, CAL_END, mapping)
    assert stats["datum_unplausibel"] == 1
    assert stats["inbetriebnahme_fehlt"] == 1


def test_aggregate_empty_input(mapping):
    seed, stats = mastr.aggregate([], CAL_START, CAL_END, mapping)
    assert list(seed.columns) == list(mastr.SEED_COLUMNS) and seed.empty
    assert stats == {"zeilen": 0}


def test_seed_roundtrip(tmp_path, sqlite_path, mapping):
    seed, stats = mastr.aggregate(mastr.iter_units(sqlite_path), CAL_START, CAL_END, mapping)
    path = tmp_path / "kapazitaet_monat.csv"
    mastr.write_seed(seed, path, stats, export_date=date(2026, 10, 25))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Datenquelle: Marktstammdatenregister der Bundesnetzagentur")
    assert "# Exportstand: 2026-10-25" in text
    assert "ohne Stilllegungsdatum bleibt im Bestand (stilllegung_ohne_datum)" in text
    back = mastr.read_seed(path)
    pd.testing.assert_frame_equal(back, seed, check_dtype=False)


@pytest.mark.xfail(strict=True, reason="fixture seed written in Task 3")
def test_committed_fixture_seed_is_current(sqlite_path, mapping):
    """data/fixtures/mastr/kapazitaet_monat.csv is generated by `ewmonitor seed-mastr --fixtures`; it must match."""
    seed, _ = mastr.aggregate(mastr.iter_units(sqlite_path), CAL_START, CAL_END, mapping)
    committed = mastr.read_seed(FIXTURE_TABLES.parent / "kapazitaet_monat.csv")
    pd.testing.assert_frame_equal(committed, seed, check_dtype=False)


def test_profile_lists_distinct_values(sqlite_path):
    text = mastr.profile(sqlite_path)
    assert "EinheitenWind" in text and "Windkraft auf See" in text and "Bundesland NULL" in text
