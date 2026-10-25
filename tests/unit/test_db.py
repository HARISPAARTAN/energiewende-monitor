import math
from datetime import datetime

import pandas as pd

from ewmonitor.db import df_rows, split_batches


def test_split_batches_on_go_lines():
    sql = "CREATE TABLE a (x int);\nGO\n\nCREATE TABLE b (y int);\ngo\nSELECT 1\n"
    assert split_batches(sql) == ["CREATE TABLE a (x int);", "CREATE TABLE b (y int);", "SELECT 1"]


def test_split_batches_ignores_go_inside_text():
    sql = "SELECT 'GO' AS word;\nGO\nSELECT 'ALGORITHM';"
    assert split_batches(sql) == ["SELECT 'GO' AS word;", "SELECT 'ALGORITHM';"]


def test_df_rows_converts_nan_and_timestamps():
    df = pd.DataFrame({"ts": pd.to_datetime(["2025-10-19 22:00:00"]), "v": [math.nan], "k": [20251020]})
    rows = df_rows(df, ["ts", "v", "k"])
    assert rows == [(datetime(2025, 10, 19, 22, 0), None, 20251020)]
    assert type(rows[0][2]) is int
