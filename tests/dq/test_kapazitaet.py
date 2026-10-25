import pytest

pytestmark = pytest.mark.db


def _bestand(con, kuerzel, name, jahr_monat):
    return con.execute("""
        SELECT k.bestand_mw, k.bestand_anzahl FROM rpt.v_kapazitaet k
        JOIN dw.dim_bundesland b ON b.bundesland_key = k.bundesland_key
        JOIN dw.dim_energietraeger e ON e.energietraeger_key = k.energietraeger_key
        WHERE b.kuerzel = ? AND e.name_de = ? AND k.jahr_monat = ?""", kuerzel, name, jahr_monat).fetchone()


def test_running_totals_follow_zubau_and_abgang(con):
    assert tuple(_bestand(con, "NW", "Braunkohle", "1990-01")) == (300.0, 1)   # Anfangsbestand
    assert tuple(_bestand(con, "NW", "Braunkohle", "2024-02")) == (300.0, 1)   # still there the month before
    assert tuple(_bestand(con, "NW", "Braunkohle", "2024-03")) == (0.0, 0)     # Abgang month
    # BY Biomasse: Zubau 1.0 MW in 1995-01 and 0.5 MW in 2015-06 (fixture seed)
    assert tuple(_bestand(con, "BY", "Biomasse", "2015-05")) == (1.0, 1)
    assert tuple(_bestand(con, "BY", "Biomasse", "2015-06")) == (1.5, 2)


def test_month_grid_is_dense_until_the_last_seed_month(con):
    last = con.execute("SELECT MAX(jahr_monat) FROM stg.mastr_kapazitaet").fetchval()
    n = con.execute("""
        SELECT COUNT(*) FROM rpt.v_kapazitaet k JOIN dw.dim_bundesland b ON b.bundesland_key = k.bundesland_key
        JOIN dw.dim_energietraeger e ON e.energietraeger_key = k.energietraeger_key
        WHERE b.kuerzel = 'NW' AND e.name_de = 'Braunkohle'""").fetchval()
    first_year, first_month = 1990, 1
    last_year, last_month = int(last[:4]), int(last[5:])
    assert n == (last_year - first_year) * 12 + (last_month - first_month) + 1


def test_awz_and_unbekannt_rows_exist(con):
    rows = con.execute("""
        SELECT DISTINCT b.kuerzel FROM dw.fact_kapazitaet k JOIN dw.dim_bundesland b ON b.bundesland_key = k.bundesland_key""").fetchall()
    assert {"AWZ", "UNB"} <= {r[0].strip() for r in rows}


def test_capacity_checks_on_the_fixture(con):
    from ewmonitor.checks import run_checks
    by = {r.name: r for r in run_checks(con, 20251020, 20251026)}
    assert by["kapazitaet_bestand_nicht_negativ"].status == "ok"
    assert by["kapazitaet_vs_staging"].status == "ok"
    assert by["kapazitaet_monatsraster"].status == "ok"
    assert by["kapazitaet_plausibel"].status == "warn"
