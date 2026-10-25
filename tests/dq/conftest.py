import os

import pytest

from ewmonitor import db
from ewmonitor.config import load_settings


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def con(settings):
    if not os.environ.get("MSSQL_SA_PASSWORD"):
        pytest.skip("MSSQL_SA_PASSWORD not set; database tests need the SQL Server container")
    connection = db.connect(settings.db)
    yield connection
    connection.close()
