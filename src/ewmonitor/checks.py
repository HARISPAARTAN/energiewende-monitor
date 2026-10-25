"""Data-quality checks against the star schema. Each check judges a series only inside its own loaded span."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

Status = Literal["ok", "warn", "fail"]

# The SMARD filter IDs the load scripts pivot or select; tests/unit/test_filter_ids.py ties them to config.toml.
LAST_FILTER_IDS = (410, 4359, 4387)  # Netzlast, Residuallast, Pumpspeicher-Verbrauch
PREIS_FILTER_ID = 4169  # Day-Ahead-Preis


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str


def _val(con, sql: str, *params):
    return con.execute(sql, *params).fetchval()


def check_rows_per_day(con, from_key: int, to_key: int) -> CheckResult:
    sql = """
    WITH span AS (
        SELECT region_key, energietraeger_key, MIN(datum_key) AS von, MAX(datum_key) AS bis
        FROM dw.fact_erzeugung WHERE aufloesung_min = 15 AND datum_key BETWEEN ? AND ?
        GROUP BY region_key, energietraeger_key),
    tage AS (
        SELECT s.region_key, s.energietraeger_key, d.datum_key, d.viertelstunden
        FROM span s JOIN dw.dim_datum d ON d.datum_key BETWEEN s.von AND s.bis),
    ist AS (
        SELECT region_key, energietraeger_key, datum_key, COUNT(*) AS n
        FROM dw.fact_erzeugung WHERE aufloesung_min = 15 AND datum_key BETWEEN ? AND ?
        GROUP BY region_key, energietraeger_key, datum_key)
    SELECT COUNT(*) FROM tage t
    LEFT JOIN ist i ON i.region_key = t.region_key AND i.energietraeger_key = t.energietraeger_key
                   AND i.datum_key = t.datum_key
    WHERE ISNULL(i.n, 0) <> t.viertelstunden
    """
    bad = _val(con, sql, from_key, to_key, from_key, to_key)
    return CheckResult("viertelstunden_pro_tag", "ok" if bad == 0 else "fail",
                       f"{bad} Tag/Reihe-Kombinationen mit abweichender Zeilenzahl")


def check_null_values(con, from_key: int, to_key: int) -> CheckResult:
    n = _val(con, "SELECT COUNT(*) FROM dw.fact_erzeugung WHERE erzeugung_mwh IS NULL AND datum_key BETWEEN ? AND ?",
             from_key, to_key)
    return CheckResult("erzeugung_nullwerte", "ok" if n == 0 else "warn", f"{n} Viertelstunden ohne Wert (Quelle)")


def check_non_negative(con, from_key: int, to_key: int) -> CheckResult:
    n = _val(con, "SELECT COUNT(*) FROM dw.fact_erzeugung WHERE erzeugung_mwh < 0 AND datum_key BETWEEN ? AND ?",
             from_key, to_key)
    return CheckResult("erzeugung_nicht_negativ", "ok" if n == 0 else "fail", f"{n} negative Erzeugungswerte")


def check_price_range(con, from_key: int, to_key: int) -> CheckResult:
    n = _val(con, "SELECT COUNT(*) FROM dw.fact_preis WHERE (day_ahead_eur_mwh < -500 OR day_ahead_eur_mwh > 4000) "
                  "AND datum_key BETWEEN ? AND ?", from_key, to_key)
    return CheckResult("preis_plausibel", "ok" if n == 0 else "fail", f"{n} Preise außerhalb -500..4000 EUR/MWh")


def check_unmapped_staging(con, from_key: int, to_key: int) -> CheckResult:
    """Staging rows in the range whose region is not in dim_region, or whose filter is neither a load/price
    filter nor in dim_energietraeger."""
    known = ", ".join(str(i) for i in (*LAST_FILTER_IDS, PREIS_FILTER_ID))
    n = _val(con, f"""
        SELECT COUNT(*) FROM stg.smard_series s
        WHERE s.datum_key BETWEEN ? AND ?
          AND (NOT EXISTS (SELECT 1 FROM dw.dim_region r WHERE r.smard_code = s.region)
               OR (s.filter_id NOT IN ({known})
                   AND NOT EXISTS (SELECT 1 FROM dw.dim_energietraeger e WHERE e.smard_filter_id = s.filter_id)))
        """, from_key, to_key)
    return CheckResult("staging_zugeordnet", "ok" if n == 0 else "warn", f"{n} Staging-Zeilen ohne Dimension")


def check_incomplete_hours(con, from_key: int, to_key: int) -> CheckResult:
    """Hours of rpt.v_last_stunde in the range with fewer than four quarter-hour values for any fact_last
    measure; the view returns NULL for such a measure. These are gaps in the source data, mostly recent ones
    that SMARD may still fill: warn, never fail."""
    row = con.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN viertelstunden_netzlast_mwh < 4 OR viertelstunden_residuallast_mwh < 4
                          OR viertelstunden_pumpspeicher_verbrauch_mwh < 4 THEN 1 ELSE 0 END)
        FROM rpt.v_last_stunde WHERE datum_key BETWEEN ? AND ?
        """, from_key, to_key).fetchone()
    if row is None or row[1] is None:
        return CheckResult("unvollstaendige_stunden", "warn", "keine Lastdaten im Zeitraum")
    hours, incomplete = row
    return CheckResult("unvollstaendige_stunden", "ok" if incomplete == 0 else "warn",
                       f"{incomplete} von {hours} Stunden mit weniger als 4 Viertelstundenwerten je Messgröße")


def check_last_rows_per_day(con, from_key: int, to_key: int) -> CheckResult:
    """fact_last counterpart of viertelstunden_pro_tag: inside each region's loaded span, every day has as many
    quarter-hour rows as dim_datum.viertelstunden (92, 96 or 100)."""
    sql = """
    WITH span AS (
        SELECT region_key, MIN(datum_key) AS von, MAX(datum_key) AS bis
        FROM dw.fact_last WHERE aufloesung_min = 15 AND datum_key BETWEEN ? AND ?
        GROUP BY region_key),
    tage AS (
        SELECT s.region_key, d.datum_key, d.viertelstunden
        FROM span s JOIN dw.dim_datum d ON d.datum_key BETWEEN s.von AND s.bis),
    ist AS (
        SELECT region_key, datum_key, COUNT(*) AS n
        FROM dw.fact_last WHERE aufloesung_min = 15 AND datum_key BETWEEN ? AND ?
        GROUP BY region_key, datum_key)
    SELECT COUNT(*) FROM tage t
    LEFT JOIN ist i ON i.region_key = t.region_key AND i.datum_key = t.datum_key
    WHERE ISNULL(i.n, 0) <> t.viertelstunden
    """
    bad = _val(con, sql, from_key, to_key, from_key, to_key)
    return CheckResult("last_viertelstunden_pro_tag", "ok" if bad == 0 else "fail",
                       f"{bad} Tag/Region-Kombinationen mit abweichender Zeilenzahl")


def check_last_null_values(con, from_key: int, to_key: int) -> CheckResult:
    row = con.execute("""
        SELECT COUNT(*) - COUNT(netzlast_mwh), COUNT(*) - COUNT(residuallast_mwh),
               COUNT(*) - COUNT(pumpspeicher_verbrauch_mwh)
        FROM dw.fact_last WHERE datum_key BETWEEN ? AND ?
        """, from_key, to_key).fetchone()
    netz, rest, pump = (int(v or 0) for v in row)
    return CheckResult("last_nullwerte", "ok" if netz + rest + pump == 0 else "warn",
                       f"Viertelstunden ohne Wert (Quelle): Netzlast {netz}, Residuallast {rest}, Pumpspeicher {pump}")


def check_price_hours_per_day(con, from_key: int, to_key: int) -> CheckResult:
    """Every day inside each region's loaded price span has 23, 24 or 25 hourly prices."""
    sql = """
    WITH span AS (
        SELECT region_key, MIN(datum_key) AS von, MAX(datum_key) AS bis
        FROM dw.fact_preis WHERE datum_key BETWEEN ? AND ?
        GROUP BY region_key),
    ist AS (
        SELECT region_key, datum_key, COUNT(*) AS n
        FROM dw.fact_preis WHERE datum_key BETWEEN ? AND ?
        GROUP BY region_key, datum_key)
    SELECT COUNT(*) FROM span s
    JOIN dw.dim_datum d ON d.datum_key BETWEEN s.von AND s.bis
    LEFT JOIN ist i ON i.region_key = s.region_key AND i.datum_key = d.datum_key
    WHERE ISNULL(i.n, 0) NOT IN (23, 24, 25)
    """
    bad = _val(con, sql, from_key, to_key, from_key, to_key)
    return CheckResult("preis_stunden_pro_tag", "ok" if bad == 0 else "fail",
                       f"{bad} Tag/Region-Kombinationen ohne 23, 24 oder 25 Stundenpreise")


def check_facts_vs_staging(con, from_key: int, to_key: int) -> CheckResult:
    """Every fact row in the range comes from staging, and every staging row the load maps does arrive.

    The staging side mirrors the rules of sql/load/*.sql exactly:
    - fact_erzeugung: one row per staging row whose filter_id is in dim_energietraeger and whose region is in
      dim_region (null values included, the load keeps them).
    - fact_last: one row per distinct (region, ts_utc, datum_key, zeit_key, resolution) among the staging
      rows of the consumption filters LAST_FILTER_IDS with a mapped region (the load pivots three series
      into one row).
    - fact_preis: one row per staging row of PREIS_FILTER_ID at hourly resolution with a mapped region.
    """
    last_ids = ", ".join(str(i) for i in LAST_FILTER_IDS)
    row = con.execute(f"""
        SELECT
          (SELECT COUNT(*) FROM stg.smard_series s
             JOIN dw.dim_energietraeger e ON e.smard_filter_id = s.filter_id
             JOIN dw.dim_region r ON r.smard_code = s.region
            WHERE s.datum_key BETWEEN ? AND ?),
          (SELECT COUNT(*) FROM dw.fact_erzeugung WHERE datum_key BETWEEN ? AND ?),
          (SELECT COUNT(*) FROM (
              SELECT DISTINCT r.region_key, s.ts_utc, s.datum_key, s.zeit_key, s.resolution
              FROM stg.smard_series s JOIN dw.dim_region r ON r.smard_code = s.region
              WHERE s.filter_id IN ({last_ids}) AND s.datum_key BETWEEN ? AND ?) x),
          (SELECT COUNT(*) FROM dw.fact_last WHERE datum_key BETWEEN ? AND ?),
          (SELECT COUNT(*) FROM stg.smard_series s JOIN dw.dim_region r ON r.smard_code = s.region
            WHERE s.filter_id = {PREIS_FILTER_ID} AND s.resolution = N'hour' AND s.datum_key BETWEEN ? AND ?),
          (SELECT COUNT(*) FROM dw.fact_preis WHERE datum_key BETWEEN ? AND ?)
        """, *([from_key, to_key] * 6)).fetchone()
    pairs = {"erzeugung": (row[0], row[1]), "last": (row[2], row[3]), "preis": (row[4], row[5])}
    detail = "; ".join(f"{name}: Staging {stg}, Fakten {fact}" for name, (stg, fact) in pairs.items())
    ok = all(stg == fact for stg, fact in pairs.values())
    return CheckResult("fakten_vs_staging", "ok" if ok else "fail", detail)


def check_freshness(con, now: datetime | None = None, to_key: int | None = None) -> CheckResult:
    """Age of the newest Netzlast value that is not NULL, up to the end of the checked range (to_key): SMARD
    chunks carry the whole week with NULLs for quarter-hours not yet published, so the newest timestamp alone
    would hide a feed that stopped. `now` is naive UTC (all --fixtures passes the fixture week's end); a
    reference time before the newest value is reported as a warning, never as fresh."""
    latest = _val(con, "SELECT MAX(ts_utc) FROM dw.fact_last WHERE netzlast_mwh IS NOT NULL AND datum_key <= ?",
                  to_key if to_key is not None else 99991231)
    now = now or datetime.now(UTC).replace(tzinfo=None)
    if latest is None:
        return CheckResult("aktualitaet", "warn", "keine Netzlast-Werte geladen")
    age = now - latest
    if age < timedelta(0):
        return CheckResult("aktualitaet", "warn",
                           f"letzter Netzlast-Wert {latest:%Y-%m-%d %H:%M} UTC liegt nach der Referenzzeit "
                           f"{now:%Y-%m-%d %H:%M} UTC")
    return CheckResult("aktualitaet", "ok" if age <= timedelta(days=45) else "warn",
                       f"letzter Netzlast-Wert {latest:%Y-%m-%d %H:%M} UTC ({age.days} Tage alt)")


def run_checks(con, from_key: int, to_key: int, now: datetime | None = None) -> list[CheckResult]:
    return [
        check_rows_per_day(con, from_key, to_key),
        check_null_values(con, from_key, to_key),
        check_non_negative(con, from_key, to_key),
        check_last_rows_per_day(con, from_key, to_key),
        check_last_null_values(con, from_key, to_key),
        check_price_hours_per_day(con, from_key, to_key),
        check_price_range(con, from_key, to_key),
        check_unmapped_staging(con, from_key, to_key),
        check_facts_vs_staging(con, from_key, to_key),
        check_incomplete_hours(con, from_key, to_key),
        check_freshness(con, now, to_key),
    ]


def has_failures(results: list[CheckResult]) -> bool:
    return any(r.status == "fail" for r in results)


def format_results(results: list[CheckResult]) -> str:
    width = max(len(r.name) for r in results)
    return "\n".join(f"{r.name.ljust(width)}  {r.status.ljust(4)}  {r.detail}" for r in results)
