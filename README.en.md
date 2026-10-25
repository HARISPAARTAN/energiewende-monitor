# Energiewende-Monitor

[![CI](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml)

German electricity-market data (SMARD) as a star schema in SQL Server, the basis for a public Power BI model.
German version: [README.md](README.md).

**Status:** milestone 1 (data pipeline, SQL schema, tests, CI) is complete. The Power BI model and report follow.

## What the monitor shows

- Generation by source, grid load, residual load and pumped-storage consumption for bidding zone DE-LU,
  quarter-hourly from 1 January 2023.
- Day-ahead price DE-LU, hourly.
- Later (milestone 2): installed capacity per federal state from the Marktstammdatenregister.

## Architecture

SMARD JSON (weekly chunks, cached in `data/raw/`) -> `stg.smard_series` -> T-SQL transforms ->
`dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` plus dimensions `dw.dim_*` -> views `rpt.v_*` -> Power BI.

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
uv run --env-file .env ewmonitor all              # load 2023-01-01 to yesterday (about 15 minutes)
```

Connection: `EWM_DB_SERVER` (default `127.0.0.1,1433`) and `EWM_DB_NAME` (default `energiewende`) from `.env`.

Commands: `ewmonitor ingest`, `ewmonitor load`, `ewmonitor check`, `ewmonitor all`, each with `--from`, `--to`;
`ingest` and `all` also take `--regions` and `--refresh-days` (default 60: chunks that ended within the last 60 days
are downloaded again, because SMARD republishes past weeks). `ewmonitor all --fixtures` runs without network access.

## Tests

- `uv run pytest tests/unit` (no database): parser, time zones, dimensions, client with mocked HTTP.
- `uv run --env-file .env pytest tests/dq -m db`: rows per day, pivot, hourly aggregate, idempotent loads.
- GitHub Actions runs both against a SQL Server container (`.github/workflows/ci.yml`).

## Data quality

`ewmonitor check` verifies quarter-hours per day and series (inside each series' loaded span), null values,
no negative generation, prices between -500 and 4000 EUR/MWh, mapping of every staging row, the hourly aggregate
against quarter-hours, and freshness (warning after 45 days). Missing quarter-hours per month come from the view
`rpt.v_dq_luecken`.

## Data sources and licences

- SMARD, Bundesnetzagentur: CC BY 4.0, attribution `Bundesnetzagentur | SMARD.de`.
  Filters: generation 1223, 1224, 1225, 1226, 1227, 1228, 4066, 4067, 4068, 4069, 4070, 4071; consumption 410, 4359, 4387;
  price 4169. Nuclear (1224) ends in the source data in January 2024.
- Marktstammdatenregister (from milestone 2): Datenlizenz Deutschland Namensnennung 2.0.

## Decisions

See `docs/decisions/` (SQL Server, Publish to web, scope, MaStR seed) and `docs/CHANGELOG.md`.

## Limits

Bidding zone DE-LU only in version 0.1; the four control areas follow in milestone 5. No forecasts, no
Redispatch data. The raw cache is not part of the repository.

## Licence

Code: MIT. Data: see data sources.
