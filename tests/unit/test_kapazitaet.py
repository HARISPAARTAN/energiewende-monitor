import pandas as pd

from ewmonitor.kapazitaet import write_stg_kapazitaet
from ewmonitor.mastr import SEED_COLUMNS


class _RecordingCon:
    """Records executed SQL, commits and rollbacks; cursor() returns itself."""

    def __init__(self):
        self.log = []
        self.fast_executemany = False

    def cursor(self):
        return self

    def execute(self, sql, *_params):
        self.log.append(("execute", sql))

    def executemany(self, sql, rows):
        self.log.append(("executemany", len(rows)))

    def commit(self):
        self.log.append(("commit",))

    def rollback(self):
        self.log.append(("rollback",))

    def close(self):
        pass


def test_empty_seed_still_commits_the_truncate():
    con = _RecordingCon()
    assert write_stg_kapazitaet(con, pd.DataFrame(columns=list(SEED_COLUMNS))) == 0
    assert con.log == [("execute", "TRUNCATE TABLE stg.mastr_kapazitaet"), ("commit",)]


def test_seed_rows_are_inserted_after_the_truncate_and_committed_once():
    seed = pd.DataFrame([["1990-01", "NW", "Braunkohle", 0.0, 0, 0.0, 0, 300.0, 1]], columns=list(SEED_COLUMNS))
    con = _RecordingCon()
    assert write_stg_kapazitaet(con, seed) == 1
    assert con.log == [("execute", "TRUNCATE TABLE stg.mastr_kapazitaet"), ("executemany", 1), ("commit",)]
