"""Typed settings: config.toml for the data scope, environment variables for the database."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _odbc_quote(value: str) -> str:
    """Brace-quote an ODBC connection-string value so ';', '=' and braces in it are taken literally."""
    return "{" + value.replace("}", "}}") + "}"


@dataclass(frozen=True)
class SmardConfig:
    base_url: str
    generation: tuple[int, ...]
    consumption: tuple[int, ...]
    price: int
    price_regions: tuple[str, ...]

    @property
    def quarterhour_filters(self) -> tuple[int, ...]:
        return self.generation + self.consumption


@dataclass(frozen=True)
class DbConfig:
    server: str
    database: str
    user: str
    password: str = field(repr=False)
    driver: str

    def connection_string(self, database: str | None = None) -> str:
        if not self.password:
            raise ValueError("MSSQL_SA_PASSWORD fehlt")
        return (
            f"DRIVER={{{self.driver}}};SERVER={self.server};DATABASE={database or self.database};"
            f"UID={_odbc_quote(self.user)};PWD={_odbc_quote(self.password)};"
            "Encrypt=yes;TrustServerCertificate=yes"
        )


@dataclass(frozen=True)
class Settings:
    root: Path
    start: str
    regions: tuple[str, ...]
    smard: SmardConfig
    db: DbConfig
    raw_dir: Path
    seed_dir: Path
    fixtures_dir: Path


def _toml_list(data: dict, section: str, key: str) -> list:
    """A list value from config.toml; a bare string would otherwise become a tuple of its characters."""
    value = data[section][key]
    if not isinstance(value, list):
        raise ValueError(f"config.toml: [{section}] {key} muss eine Liste sein, nicht {type(value).__name__}")
    return value


def load_settings(root: Path | None = None) -> Settings:
    """Read config.toml under `root` (default: the repository root) and the EWM_*/MSSQL_* variables.

    A missing MSSQL_SA_PASSWORD is not an error here; DbConfig.connection_string raises when it is needed.
    """
    root = (root or Path(__file__).resolve().parents[2]).resolve()
    data = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
    scope, smard, paths = data["scope"], data["smard"], data["paths"]
    db = DbConfig(
        server=os.environ.get("EWM_DB_SERVER", "localhost,1433"),
        database=os.environ.get("EWM_DB_NAME", "energiewende"),
        user=os.environ.get("EWM_DB_USER", "sa"),
        password=os.environ.get("MSSQL_SA_PASSWORD", ""),
        driver=os.environ.get("EWM_DB_DRIVER", "ODBC Driver 18 for SQL Server"),
    )
    return Settings(
        root=root,
        start=str(scope["start"]),
        regions=tuple(_toml_list(data, "scope", "regions")),
        smard=SmardConfig(
            base_url=smard["base_url"],
            generation=tuple(int(x) for x in _toml_list(data, "smard", "generation")),
            consumption=tuple(int(x) for x in _toml_list(data, "smard", "consumption")),
            price=int(smard["price"]),
            price_regions=tuple(_toml_list(data, "smard", "price_regions")),
        ),
        db=db,
        raw_dir=root / paths["raw"],
        seed_dir=root / paths["seed"],
        fixtures_dir=root / paths["fixtures"],
    )
