import typer
from typer.testing import CliRunner

from ewmonitor.cli import app


def test_cli_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    names = {c.name for c in typer.main.get_command(app).commands.values()}
    assert names >= {"ingest", "load", "check", "all"}


def test_ingest_help_shows_refresh_and_regions():
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0 and "--refresh-days" in result.output and "--regions" in result.output


def test_all_help_shows_fixtures_option():
    result = CliRunner().invoke(app, ["all", "--help"])
    assert result.exit_code == 0 and "--fixtures" in result.output and "--regions" in result.output
