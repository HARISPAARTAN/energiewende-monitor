from datetime import date, time
from pathlib import Path

import pandas as pd

from ewmonitor.dims import DIM_DATUM_COLUMNS, DIM_ZEIT_COLUMNS, build_dim_datum, build_dim_zeit

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"


def test_dim_datum_rows_and_dst_quarter_hours():
    df = build_dim_datum(date(2025, 1, 1), date(2025, 12, 31))
    assert list(df.columns) == DIM_DATUM_COLUMNS
    assert len(df) == 365
    assert df.loc[df["datum_key"] == 20250330, "viertelstunden"].item() == 92
    assert df.loc[df["datum_key"] == 20251026, "viertelstunden"].item() == 100
    assert int(df["viertelstunden"].sum()) == 365 * 96


def test_dim_datum_names_iso_week_and_season():
    df = build_dim_datum(date(2024, 12, 30), date(2025, 1, 5))
    row = df[df["datum_key"] == 20250101].iloc[0]
    assert row["monat_name_de"] == "Januar" and row["monat_name_en"] == "January"
    assert row["wochentag_de"] == "Mittwoch" and row["wochentag_nr"] == 3
    assert row["iso_jahr"] == 2025 and row["iso_woche"] == 1
    assert row["jahr_monat"] == "2025-01" and row["quartal"] == 1 and row["saison_de"] == "Winter"
    assert int(row["ist_wochenende"]) == 0
    assert df[df["datum_key"] == 20241230].iloc[0]["iso_jahr"] == 2025
    assert int(df[df["datum_key"] == 20250104].iloc[0]["ist_wochenende"]) == 1


def test_dim_zeit():
    df = build_dim_zeit()
    assert list(df.columns) == DIM_ZEIT_COLUMNS
    assert len(df) == 96 and df["zeit_key"].tolist() == list(range(96))
    row = df[df["zeit_key"] == 50].iloc[0]
    assert row["uhrzeit"] == time(12, 30) and row["stunde"] == 12 and row["viertelstunde"] == 2
    assert row["tageszeit_de"] == "Mittag" and row["tageszeit_en"] == "Midday"
    assert df[df["zeit_key"] == 95].iloc[0]["tageszeit_de"] == "Abend"
    assert df[df["zeit_key"] == 0].iloc[0]["tageszeit_de"] == "Nacht"


def test_seed_files_are_consistent():
    et = pd.read_csv(SEED / "dim_energietraeger.csv")
    assert len(et) == 12 and et["smard_filter_id"].is_unique and et["energietraeger_key"].tolist() == list(range(1, 13))
    assert set(et["kategorie_de"]) == {"Erneuerbar", "Konventionell"}
    assert et["farbe_hex"].str.match(r"^#[0-9A-F]{6}$").all()
    region = pd.read_csv(SEED / "dim_region.csv")
    assert region["smard_code"].tolist() == ["DE-LU", "50Hertz", "Amprion", "TenneT", "TransnetBW"]
    bl = pd.read_csv(SEED / "dim_bundesland.csv")
    assert len(bl) == 17 and bl["kuerzel"].is_unique and int(bl["ist_awz"].sum()) == 1
