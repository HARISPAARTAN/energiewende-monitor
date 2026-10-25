import re

import typer
from typer.testing import CliRunner

from ewmonitor.cli import app

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
