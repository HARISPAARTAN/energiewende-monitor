# Energiewende-Monitor

[![CI](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml)

German electricity-market data (SMARD) as a star schema in SQL Server, the basis for a public Power BI model.
German version: [README.md](README.md).

**Status:** milestone 2 is complete: data pipeline, SQL schema, tests, CI and installed capacity from the
Marktstammdatenregister. The Power BI model and report follow.

Data as of: SMARD 2026-10-25 (from 2023-01-01, DE-LU; load time about 3 minutes on a laptop);
Marktstammdatenregister export of 2026-10-25.

## What the monitor shows

- Generation by source, grid load, residual load and pumped-storage consumption for bidding zone DE-LU,
  quarter-hourly from 1 January 2023.
- Day-ahead price DE-LU, hourly.
- Installed capacity per month, federal state and energy source from the Marktstammdatenregister (additions,
  retirements, stock). The month grid starts in 1990; the stock is reliable only from about 2019, see
  [Capacity (MaStR)](#capacity-mastr).

## Architecture

SMARD JSON (weekly chunks, cached in `data/raw/`) -> `stg.smard_series` -> T-SQL transforms ->
`dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` plus dimensions `dw.dim_*` -> views `rpt.v_*` -> Power BI.
MaStR seed `data/seed/kapazitaet_monat.csv` -> `stg.mastr_kapazitaet` -> `dw.fact_kapazitaet` -> `rpt.v_kapazitaet`.

Timestamps are UTC (`ts_utc`). The keys `datum_key` (yyyymmdd) and `zeit_key` (0..95) are Europe/Berlin local
time, computed once in Python, so daylight-saving days (92 or 100 quarter-hours) are handled in one place.

## Quick start

Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/), Microsoft ODBC Driver 18 for SQL Server
(Windows: `winget install -e --id Microsoft.msodbcsql.18`).

```bash
cp .env.example .env            # set MSSQL_SA_PASSWORD
docker compose up -d            # SQL Server 2022 Developer on port 1433
uv sync --dev
uv run --env-file .env ewmonitor all --fixtures   # load and check the October 2025 test week
uv run --env-file .env ewmonitor all              # load 2023-01-01 to yesterday (about 3 minutes)
```

Connection: `EWM_DB_SERVER` (default `127.0.0.1,1433`) and `EWM_DB_NAME` (default `energiewende`) from `.env`.

Commands: `ewmonitor ingest`, `ewmonitor load`, `ewmonitor check`, `ewmonitor all`, each with `--from`, `--to`;
`ingest` and `all` also take `--regions` and `--refresh-days` (default 60: chunks that ended within the last 60 days
are downloaded again, because SMARD republishes past weeks). `ewmonitor all --fixtures` runs without network access.

## Tests

- `uv run pytest tests/unit` (no database): parser, time zones, dimensions, client with mocked HTTP, MaStR
  readers (SQLite and XML on the same synthetic fixture), mapping and aggregation.
- `uv run --env-file .env pytest tests/dq -m db`: rows per day, pivot, hourly aggregate, idempotent loads, errors
  in the fact loads. The suite works in its own database (`EWM_DQ_DB_NAME`, default `energiewende_dq`), empties
  staging and facts there and loads the test week; the database from `EWM_DB_NAME` is left untouched.
  For capacity: running stock after additions and retirements, a gap-free month grid up to the last month,
  AWZ and UNB rows, the four capacity checks on the fixture seed and idempotent `dw.fact_kapazitaet` loads.
- GitHub Actions runs both against a SQL Server container (`.github/workflows/ci.yml`).

## Error handling

HTTP failures that may be transient (connection drops, timeouts, 429, 5xx, invalid JSON) are retried with a
backoff (up to three attempts). A chunk that still fails stops the run: staging is replaced per series and time range, so a
skipped chunk would delete that week's good rows. When SMARD has no index (404) for a configured series, the
series has no chunks and a WARNING is logged. Database errors stop the run and roll the step back; `--from`/`--to`
outside the calendar (`scope.start` to 2030-12-31) are rejected.

## Data quality

`ewmonitor check` verifies quarter-hours per day for generation and load (inside each series' loaded span), null
values in generation and load, no negative generation, 23, 24 or 25 hourly prices per day, prices between -500 and
4000 EUR/MWh, mapping of every staging row, staging reconciled with facts per fact table, incomplete load hours
(warning only; gaps in the source data, mostly recent ones that SMARD may still fill) and freshness (warning after 45 days). Missing quarter-hours
per month come from the view `rpt.v_dq_luecken`.
For capacity: no negative stock, staging reconciled with facts, a gap-free month grid per federal state and
energy source, and a plausibility band for the national stock in the newest month (warning only).

The view `rpt.v_last_stunde` aggregates the load per UTC hour. A measure has a value there only when all four
quarter-hours of the hour have one, otherwise NULL; the `viertelstunden_*` columns give the number of values present.

## Capacity (MaStR)

Datenquelle: Marktstammdatenregister der Bundesnetzagentur, Datenlizenz Deutschland – Namensnennung – Version 2.0
(https://www.govdata.de/dl-de/by-2-0), Daten aggregiert.

The seed `data/seed/kapazitaet_monat.csv` (export of 2026-10-25, 25,323 rows, 1.1 MB) condenses 9,663,557 units
from eight unit tables into additions, retirements and opening stock per month, federal state and energy source.
`ewmonitor load` and `ewmonitor all` stage it in `stg.mastr_kapazitaet` and build `dw.fact_kapazitaet` with running
stock totals. The view `rpt.v_kapazitaet` has the columns `datum_key`, `jahr_monat`, `bundesland_key`,
`energietraeger_key`, `zubau_mw`, `anzahl_zubau`, `abgang_mw`, `anzahl_abgang`, `anfangsbestand_mw`,
`anfangsbestand_anzahl`, `bestand_mw`, `bestand_anzahl`. `bestand_mw` is the end-of-month value after the month's
additions and retirements. The newest month is partial, and because units are often registered weeks after
commissioning, additions in the last two to three months are too low.

Stock in October 2026 (net rated power): solar PV 116.6 GW, wind onshore 71.5 GW, wind offshore 11.6 GW, natural gas
35.8 GW, hard coal 15.1 GW, lignite 14.8 GW, pumped storage 9.9 GW, biomass 8.8 GW, hydro 5.3 GW, nuclear 0
(since April 2023).

Rules (reasoning in `docs/decisions/ADR-004-mastr-seed.md`):

- Units `In Betrieb`, `Vorübergehend stillgelegt` and `Endgültig stillgelegt` count; `In Planung` does not
  (75,731 units).
- Addition in the month of commissioning, retirement in the month of final decommissioning. Temporarily
  decommissioned units stay in the stock.
- Units commissioned before 1990 or without a date enter as opening stock in January 1990.
- Offshore wind in the exclusive economic zone gets the federal state `AWZ`. Units without a federal state get
  `UNB` (unknown): 74 units, mostly hydro and pumped-storage plants in Luxembourg, Austria and on the Swiss border
  that feed into the German grid.
- Batteries and other storage except pumped storage are excluded (2,892,406 units): SMARD reports no generation
  for them.
- The mapping to the SMARD energy sources lives in `data/seed/mastr_energietraeger_mapping.csv`, the value lists of
  the export in `docs/mastr-profil.md`. No value of the 2026-10-25 export is left unmapped.
- Solar PV: net rated power (inverter) is about 11 % below the gross module power that the Bundesnetzagentur
  reports in its expansion figures (October 2026: 116.6 instead of 131.7 GW).
- **History before 2019 is incomplete.** The register holds only units registered since it started in 2019,
  plus the units in operation at that time; plants decommissioned or deleted earlier are missing. Stock and
  additions before about 2019 therefore show today's registered fleet by commissioning date, not the stock of
  the time. Examples: nuclear stays flat at 8.1 GW from 1990 to the end of 2021 (about 20.5 GW were online in
  2010); wind onshore shows 24.0 GW at the end of 2010 instead of about 27 GW.
- Emergency generators and grid-reserve plants stay in the stock in milestone 2: 3.0 GW of petroleum products
  and 0.6 GW of natural gas carry `Notstromaggregat = 1`, 7.45 GW of hard coal `NetzreserveZugeordnet = 1`.
  Whether to exclude them is decided in milestone 3.

Regenerating the seed (developer machine only, not in CI):

```bash
uv sync --extra mastr
uv run ewmonitor seed-mastr --profile                   # download with open-mastr, then seed and profile
uv run ewmonitor seed-mastr --skip-download --profile   # reuse the existing zip (about 5 minutes)
```

`--source xml` (default) reads the Gesamtdatenexport zip directly: lxml streams the UTF-16 XML files with flat
memory and resolves the catalog values itself. open-mastr 1.0 serves as the downloader only, because its SQLite
import fails on all 66 solar files of the 2026-10-25 export (multi-values such as `710 3183` in an integer column).
`--source sqlite` reads the open-mastr database; for the 2026-10-25 export it lacks `EinheitenSolar` and
`EinheitenVerbrennung` entirely, so the SQLite reader serves tests and comparisons, not as a fallback for the real
seed. The export date in the seed comes from the zip's file name; a differing `--date YYYYMMDD` wins with a
warning. `seed-mastr --fixtures --profile` writes `docs/mastr-profil-fixture.md` and leaves the real profile alone. Disk: zip 2.4 GB, open-mastr SQLite database 3.7 GB (built during the
download); budget 15 GB. Runtime on 2026-10-25: download 12 minutes, open-mastr import 16 minutes, XML reader
5 minutes.

Note: `ewmonitor all --fixtures` replaces the capacity data of the developer database (`EWM_DB_NAME`) with the
fixture seed. Run `ewmonitor load` again before a Power BI refresh.

## Data sources and licences

- SMARD, Bundesnetzagentur: CC BY 4.0, attribution `Bundesnetzagentur | SMARD.de`.
  Filters: generation 1223, 1224, 1225, 1226, 1227, 1228, 4066, 4067, 4068, 4069, 4070, 4071; consumption 410, 4359, 4387;
  price 4169. Nuclear (1224): last generation in the quarter-hour from 2023-04-15 23:45 local time, then zeros
  until 2024-01-30 12:15, no values (NULL) from 2024-01-30 12:30; the series ends in the source data on 2024-02-04.
- Marktstammdatenregister, Bundesnetzagentur: Datenlizenz Deutschland – Namensnennung – Version 2.0, attribution
  see [Capacity (MaStR)](#capacity-mastr). The repository holds aggregated values only.

## Decisions

See `docs/decisions/` (SQL Server, Publish to web, scope, MaStR seed) and `docs/CHANGELOG.md`.

## Limits

Generation, load and prices for bidding zone DE-LU only; the four control areas follow in milestone 5. No
forecasts, no Redispatch data. The MaStR export and the raw cache are not part of the repository.

## Licence

Code: MIT. Data: see data sources.
