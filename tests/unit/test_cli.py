import re
from datetime import date, datetime

import pytest
import typer
from typer.testing import CliRunner

from ewmonitor.cli import _range, app
from ewmonitor.config import load_settings

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _help(*args: str) -> str:
    """Help text without ANSI styling (Rich forces a terminal when GITHUB_ACTIONS is set)."""
    result = CliRunner().invoke(app, [*args, "--help"])
    assert result.exit_code == 0
    return _ANSI.sub("", result.output)


def test_cli_lists_commands():
    _help()
    names = {c.name for c in typer.main.get_command(app).commands.values()}
    assert names >= {"ingest", "load", "check", "all"}


def test_ingest_help_shows_refresh_and_regions():
    text = _help("ingest")
    assert "--refresh-days" in text and "--regions" in text


def test_all_help_shows_fixtures_option():
    text = _help("all")
    assert "--fixtures" in text and "--regions" in text


def test_range_rejects_from_before_the_scope_start():
    settings = load_settings()
    with pytest.raises(typer.BadParameter, match=r"vor dem Datenbeginn 2023-01-01.*2023-01-01 bis 2030-12-31"):
        _range(settings, datetime(2022, 12, 1), datetime(2023, 1, 31))


def test_range_rejects_to_after_the_calendar_end():
    settings = load_settings()
    with pytest.raises(typer.BadParameter, match=r"nach dem Kalenderende 2030-12-31.*2023-01-01 bis 2030-12-31"):
        _range(settings, datetime(2030, 12, 1), datetime(2031, 1, 1))


def test_range_accepts_the_calendar_bounds():
    settings = load_settings()
    assert _range(settings, datetime(2023, 1, 1), datetime(2030, 12, 31)) == (date(2023, 1, 1), date(2030, 12, 31))


def test_range_rejects_before_scope_start_even_though_calendar_is_older():
    settings = load_settings()
    with pytest.raises(typer.BadParameter, match="2023-01-01"):
        _range(settings, datetime(1995, 1, 1), None)


def test_seed_mastr_command_is_registered_and_fixtures_mode_writes_the_fixture_seed(tmp_path, monkeypatch):
    names = {c.name or c.callback.__name__.replace("_", "-") for c in app.registered_commands}
    assert "seed-mastr" in names
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "seed.csv").exists()
    assert "zeilen=" in result.output
