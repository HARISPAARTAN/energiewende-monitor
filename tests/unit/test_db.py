import math
from datetime import datetime

import pandas as pd
import pytest

from ewmonitor.db import df_rows, run_sql_file, split_batches


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


def test_df_rows_converts_nat_and_na_to_none():
    df = pd.DataFrame({
        "ts": pd.Series([pd.NaT, pd.Timestamp("2025-10-19 22:00:00")], dtype="datetime64[ns]"),
        "n": pd.array([pd.NA, 7], dtype="Int64"),
    })
    assert df_rows(df, ["ts", "n"]) == [(None, None), (datetime(2025, 10, 19, 22, 0), 7)]


class _FakeConnection:
    """Records execute/commit/rollback calls and raises on the batch whose index equals fail_on."""

    def __init__(self, fail_on: int):
        self.fail_on = fail_on
        self.calls: list[tuple] = []

    def execute(self, sql, *params):
        index = sum(1 for call in self.calls if call[0] == "execute")
        self.calls.append(("execute", sql, params))
        if index == self.fail_on:
            raise RuntimeError("batch failed")

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


def test_run_sql_file_rolls_back_and_reraises_when_a_later_batch_fails(tmp_path):
    script = tmp_path / "two_batches.sql"
    script.write_text("DELETE FROM t;\nGO\nINSERT INTO t VALUES (1);\n", encoding="utf-8")
    con = _FakeConnection(fail_on=1)

    with pytest.raises(RuntimeError, match="batch failed"):
        run_sql_file(con, script, 7)

    assert [c[0] for c in con.calls] == ["execute", "execute", "rollback"]
    assert con.calls[0][1:] == ("DELETE FROM t;", (7,))
    assert ("commit",) not in con.calls
