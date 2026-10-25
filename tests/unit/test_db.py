import math
from datetime import datetime

import pandas as pd
import pytest

from ewmonitor import db
from ewmonitor.config import DbConfig
from ewmonitor.db import bulk_insert, df_rows, ensure_database, quote_name, run_sql_file, split_batches
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


class _FakeBatchCursor:
    """Cursor double for run_sql_file: each batch yields `results` result sets; execute raises on the batch
    whose index equals fail_on, nextset raises while draining the batch whose index equals fail_drain_on."""

    def __init__(self, con):
        self.con = con
        self.batch = -1
        self.pending = 0

    def execute(self, sql, *params):
        self.batch += 1
        self.con.calls.append(("execute", sql, params))
        if self.batch == self.con.fail_on:
            raise RuntimeError("batch failed")
        self.pending = self.con.results - 1

    def nextset(self):
        self.con.calls.append(("nextset",))
        if self.batch == self.con.fail_drain_on:
            raise RuntimeError("later statement failed")
        if self.pending > 0:
            self.pending -= 1
            return True
        return False

    def close(self):
        self.con.calls.append(("close",))


class _FakeConnection:
    def __init__(self, fail_on: int = -1, fail_drain_on: int = -1, results: int = 1):
        self.fail_on = fail_on
        self.fail_drain_on = fail_drain_on
        self.results = results
        self.calls: list[tuple] = []

    def cursor(self):
        return _FakeBatchCursor(self)

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

    assert [c[0] for c in con.calls] == ["execute", "nextset", "execute", "rollback", "close"]
    assert con.calls[0][1:] == ("DELETE FROM t;", (7,))
    assert ("commit",) not in con.calls


def test_run_sql_file_drains_every_result_set_before_committing(tmp_path):
    script = tmp_path / "one_batch.sql"
    script.write_text("DELETE FROM t; INSERT INTO t VALUES (1);\n", encoding="utf-8")
    con = _FakeConnection(results=2)

    run_sql_file(con, script)

    assert [c[0] for c in con.calls] == ["execute", "nextset", "nextset", "commit", "close"]


def test_run_sql_file_rolls_back_when_a_later_statement_fails_while_draining(tmp_path):
    script = tmp_path / "one_batch.sql"
    script.write_text("DELETE FROM t; INSERT INTO t VALUES (1), (1);\n", encoding="utf-8")
    con = _FakeConnection(fail_drain_on=0, results=2)

    with pytest.raises(RuntimeError, match="later statement failed"):
        run_sql_file(con, script)

    assert [c[0] for c in con.calls] == ["execute", "nextset", "rollback", "close"]


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


def test_quote_name_brackets_valid_names_and_rejects_others():
    assert quote_name("energiewende_dq") == "[energiewende_dq]"
    for bad in ["", "energie wende", "x]; DROP DATABASE y; --", "dq-test", "ä"]:
        with pytest.raises(ValueError, match="ungültig"):
            quote_name(bad)


class _MasterConnection:
    def __init__(self, db_id):
        self.db_id = db_id
        self.sql: list[str] = []
        self.closed = False

    def execute(self, sql, *params):
        self.sql.append(sql)
        return self

    def fetchval(self):
        return self.db_id

    def close(self):
        self.closed = True


def _cfg(name="energiewende_dq"):
    return DbConfig(server="s", database=name, user="u", password="p", driver="d")


def test_ensure_database_creates_in_simple_recovery_and_closes(monkeypatch):
    master = _MasterConnection(db_id=None)
    monkeypatch.setattr(db, "connect", lambda cfg, database=None, autocommit=False: master)
    ensure_database(_cfg())
    assert master.sql[1:] == ["CREATE DATABASE [energiewende_dq];",
                              "ALTER DATABASE [energiewende_dq] SET RECOVERY SIMPLE;"]
    assert master.closed


def test_ensure_database_leaves_an_existing_database_alone(monkeypatch):
    master = _MasterConnection(db_id=7)
    monkeypatch.setattr(db, "connect", lambda cfg, database=None, autocommit=False: master)
    ensure_database(_cfg())
    assert len(master.sql) == 1 and master.closed


def test_ensure_database_rejects_an_unsafe_name_before_connecting(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("connected")

    monkeypatch.setattr(db, "connect", fail)
    with pytest.raises(ValueError):
        ensure_database(_cfg("x]; DROP DATABASE energiewende; --"))
