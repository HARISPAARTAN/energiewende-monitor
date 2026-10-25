import tomllib
from pathlib import Path

import ewmonitor

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_package_version_matches_pyproject():
    with open(PYPROJECT, "rb") as f:
        assert ewmonitor.__version__ == tomllib.load(f)["project"]["version"]
