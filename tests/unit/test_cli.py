import dataclasses
import logging
import re
import shutil
from datetime import date, datetime

import pytest
import typer
from typer.testing import CliRunner

from ewmonitor import cli
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


def test_seed_mastr_command_is_registered_and_fixtures_mode_writes_the_fixture_seed(tmp_path):
    names = {c.name or c.callback.__name__.replace("_", "-") for c in app.registered_commands}
    assert "seed-mastr" in names
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "seed.csv").exists()
    assert "zeilen=" in result.output


@pytest.mark.parametrize("value", ["2026102", "202610250", "2026-10-25", "abcdefgh", "20261332", "20260230"])
def test_seed_mastr_rejects_a_malformed_or_impossible_date_before_any_work(tmp_path, value):
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--date", value, "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 2
    assert "--date" in _ANSI.sub("", result.output)
    assert not (tmp_path / "seed.csv").exists()


def test_seed_mastr_uses_a_valid_date_as_export_date(tmp_path):
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--date", "20251020", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert "# Exportstand: 2025-10-20" in (tmp_path / "seed.csv").read_text(encoding="utf-8")


def test_seed_mastr_rejects_an_unknown_source_before_any_work(tmp_path):
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--source", "csv", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 2
    assert "--source" in _ANSI.sub("", result.output)
    assert not (tmp_path / "seed.csv").exists()


def test_seed_mastr_reports_the_units_per_table(tmp_path):
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert "EinheitenSolar=9" in result.output and "EinheitenWind=10" in result.output


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    """Repository settings with root and MaStR output folder in tmp_path, so nothing in the repository is written."""
    settings = dataclasses.replace(load_settings(), root=tmp_path, mastr_output_dir=tmp_path / "mastr")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    return settings


def test_seed_mastr_fixture_profile_never_overwrites_the_real_profile(tmp_settings, tmp_path):
    result = CliRunner().invoke(app, ["seed-mastr", "--fixtures", "--profile", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert "profil: docs/mastr-profil-fixture.md" in result.output
    assert (tmp_path / "docs" / "mastr-profil-fixture.md").exists()
    assert not (tmp_path / "docs" / "mastr-profil.md").exists()


def _export_zip(settings, name="Gesamtdatenexport_20261025.zip"):
    folder = settings.mastr_output_dir / "data" / "xml_download"
    folder.mkdir(parents=True)
    shutil.copy(settings.fixtures_dir / "mastr" / "xml" / "Gesamtdatenexport_fixture.zip", folder / name)


def test_seed_mastr_xml_takes_the_export_date_from_the_zip_name(tmp_settings, tmp_path):
    _export_zip(tmp_settings)
    result = CliRunner().invoke(app, ["seed-mastr", "--skip-download", "--profile", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert "EinheitenSolar=9" in result.output and "unmapped=1" in result.output
    assert "# Exportstand: 2026-10-25" in (tmp_path / "seed.csv").read_text(encoding="utf-8")
    assert "Gesamtdatenexport_20261025.zip" in (tmp_path / "docs" / "mastr-profil.md").read_text(encoding="utf-8")


def test_seed_mastr_warns_when_date_differs_from_the_zip_name(tmp_settings, tmp_path, caplog):
    _export_zip(tmp_settings)
    caplog.set_level(logging.WARNING, logger="ewmonitor.cli")
    result = CliRunner().invoke(app, ["seed-mastr", "--skip-download", "--date", "20261020", "--out", str(tmp_path / "seed.csv")])
    assert result.exit_code == 0, result.output
    assert "# Exportstand: 2026-10-20" in (tmp_path / "seed.csv").read_text(encoding="utf-8")
    assert any("--date 2026-10-20 weicht vom Exportstand im Dateinamen 2026-10-25 ab" in r.getMessage()
               for r in caplog.records)
    caplog.clear()
    result = CliRunner().invoke(app, ["seed-mastr", "--skip-download", "--date", "20261025", "--out", str(tmp_path / "s2.csv")])
    assert result.exit_code == 0, result.output
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
