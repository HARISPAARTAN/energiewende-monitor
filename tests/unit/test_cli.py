from typer.testing import CliRunner

from ewmonitor.cli import app


def test_cli_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["ingest", "load", "check", "all"]:
        assert command in result.output


def test_all_help_shows_fixtures_option():
    result = CliRunner().invoke(app, ["all", "--help"])
    assert result.exit_code == 0 and "--fixtures" in result.output and "--regions" in result.output
