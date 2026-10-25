"""pyodbc access to SQL Server: connections, GO-batched scripts, fast bulk inserts."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import pyodbc

from .config import DbConfig

log = logging.getLogger(__name__)
_GO = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE | re.MULTILINE)


def split_batches(sql: str) -> list[str]:
    """Split a T-SQL script on lines that contain only GO (sqlcmd convention)."""
    return [batch.strip() for batch in _GO.split(sql) if batch.strip()]


def connect(cfg: DbConfig, database: str | None = None, autocommit: bool = False) -> pyodbc.Connection:
    return pyodbc.connect(cfg.connection_string(database), autocommit=autocommit)


def ensure_database(cfg: DbConfig) -> None:
    """CREATE DATABASE cannot run inside a transaction, hence autocommit against master."""
    with connect(cfg, database="master", autocommit=True) as con:
        con.execute(f"IF DB_ID(N'{cfg.database}') IS NULL CREATE DATABASE [{cfg.database}];")
    log.info("database %s ready", cfg.database)


def run_sql_file(con: pyodbc.Connection, path: Path, *params) -> None:
    """Execute every GO batch of a script in one transaction; params apply to each batch (use them only in
    single-batch scripts). On any failure the transaction is rolled back and the error re-raised.

    pyodbc returns from execute() after the first result of a batch (a row count, unless SET NOCOUNT ON), so
    an error raised by a later statement only surfaces when the remaining results are read. Every batch is
    therefore drained with nextset() before the commit.
    """
    batches = split_batches(Path(path).read_text(encoding="utf-8"))
    cur = con.cursor()  # not "with": pyodbc's Cursor.__exit__ commits
    try:
        for batch in batches:
            cur.execute(batch, *params)
            while cur.nextset():
                pass
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
    log.info("ran %s", Path(path).name)


def run_ddl(con: pyodbc.Connection, sql_dir: Path) -> None:
    for path in sorted((Path(sql_dir) / "ddl").glob("*.sql")):
        run_sql_file(con, path)


def _py(value):
    if value is None:
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):  # NaN, NaT, NA
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):  # numpy scalars
        return value.item()
    return value


def df_rows(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    return [tuple(_py(v) for v in row) for row in df[columns].itertuples(index=False, name=None)]


def bulk_insert(
    con: pyodbc.Connection, table: str, columns: list[str], rows: list[tuple], chunk: int = 50_000
) -> int:
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cur = con.cursor()
    try:
        cur.fast_executemany = True
        for i in range(0, len(rows), chunk):
            cur.executemany(sql, rows[i : i + chunk])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
    log.info("inserted %d rows into %s", len(rows), table)
    return len(rows)
