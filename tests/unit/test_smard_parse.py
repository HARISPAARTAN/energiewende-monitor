import math
from pathlib import Path

import pandas as pd

from ewmonitor.smard import STG_COLUMNS, chunk_name, parse_chunk, parse_chunk_file

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "smard"


def test_chunk_name():
    assert (
        chunk_name(410, "DE-LU", "quarterhour", 1760911200000) == "410_DE-LU_quarterhour_1760911200000.json"
    )


def test_parse_dst_week_has_676_quarter_hours():
    df = parse_chunk_file(FIXTURES / "410_DE-LU_quarterhour_1760911200000.json")
    assert list(df.columns) == STG_COLUMNS
    assert len(df) == 676
    assert df["ts_utc"].iloc[0] == pd.Timestamp("2025-10-19 22:00:00")
    assert df["ts_utc"].iloc[-1] == pd.Timestamp("2025-10-26 22:45:00")
    assert df["ts_utc"].dt.tz is None
    assert sorted(df["datum_key"].unique()) == [20251020 + i for i in range(7)]
    assert int((df["datum_key"] == 20251026).sum()) == 100
    assert df["filter_id"].unique().tolist() == [410]
    assert df["region"].unique().tolist() == ["DE-LU"]
    assert df["resolution"].unique().tolist() == ["quarterhour"]
    assert df["value"].dtype == "float64" and df["value"].notna().all()


def test_parse_price_week_has_169_hours_on_quarter_zero():
    df = parse_chunk_file(FIXTURES / "4169_DE-LU_hour_1760911200000.json")
    assert len(df) == 169
    assert set((df["zeit_key"] % 4).unique()) == {0}
    assert df["resolution"].unique().tolist() == ["hour"]


def test_parse_keeps_nulls_as_nan():
    payload = {"meta_data": {"version": 1}, "series": [[1760911200000, 1.5], [1760912100000, None]]}
    df = parse_chunk(payload, 4068, "DE-LU", "quarterhour")
    assert len(df) == 2
    assert df["value"].iloc[0] == 1.5 and math.isnan(df["value"].iloc[1])
    assert df["datum_key"].tolist() == [20251020, 20251020] and df["zeit_key"].tolist() == [0, 1]


def test_fixture_set_is_complete():
    names = sorted(p.name for p in FIXTURES.glob("*.json"))
    quarter = [n for n in names if "_quarterhour_" in n]
    hour = [n for n in names if "_hour_" in n]
    assert len(quarter) == 14 and hour == ["4169_DE-LU_hour_1760911200000.json"]
    assert "1224_DE-LU_quarterhour_1760911200000.json" not in names  # Kernenergie ended in 2023
