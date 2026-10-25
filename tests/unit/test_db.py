import math
from datetime import datetime

import pandas as pd
import pytest

from ewmonitor.db import bulk_insert, df_rows, run_sql_file, split_batches
from ewmonitor.load import write_stg


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


class _FakeCursor:
    """Cursor double: executemany raises on call number fail_executemany_on (1-based); records into the parent."""

    def __init__(self, con):
        self.con = con
        self.fast_executemany = False

    def execute(self, sql, *params):
        self.con.calls.append(("execute", sql, params))

    def executemany(self, sql, rows):
        self.con.calls.append(("executemany", sql, len(rows)))
        self.con.executemany_count += 1
        if self.con.executemany_count == self.con.fail_executemany_on:
            raise RuntimeError("insert failed")

    def close(self):
        self.con.calls.append(("close",))


class _FakeCursorConnection:
    def __init__(self, fail_executemany_on: int):
        self.fail_executemany_on = fail_executemany_on
        self.executemany_count = 0
        self.calls: list[tuple] = []

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.calls.append(("commit",))

    def rollback(self):
        self.calls.append(("rollback",))


def test_bulk_insert_rolls_back_and_closes_cursor_when_second_chunk_fails():
    con = _FakeCursorConnection(fail_executemany_on=2)

    with pytest.raises(RuntimeError, match="insert failed"):
        bulk_insert(con, "t", ["a"], [(1,), (2,), (3,)], chunk=2)

    assert [c[0] for c in con.calls] == ["executemany", "executemany", "rollback", "close"]
    assert ("commit",) not in con.calls


def test_write_stg_failed_insert_rolls_back_deletes_without_committing():
    ts = pd.to_datetime(["2025-10-19 22:00:00", "2025-10-19 22:15:00"])
    df = pd.DataFrame({
        "filter_id": [1, 1], "region": ["DE", "DE"], "resolution": ["quarterhour", "quarterhour"],
        "ts_utc": ts, "datum_key": [20251020, 20251020], "zeit_key": [0, 15], "value": [1.0, 2.0],
    })
    con = _FakeCursorConnection(fail_executemany_on=1)

    with pytest.raises(RuntimeError, match="insert failed"):
        write_stg(con, df)

    kinds = [c[0] for c in con.calls]
    assert kinds.index("execute") < kinds.index("executemany")
    assert "DELETE FROM stg.smard_series" in con.calls[kinds.index("execute")][1]
    assert kinds[-1] == "close" and "rollback" in kinds
    assert "commit" not in kinds
