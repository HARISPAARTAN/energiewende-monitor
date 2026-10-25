# Energiewende-Monitor

[![CI](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml)

Deutsche Strommarktdaten (SMARD) als Star-Schema in SQL Server, Basis für ein öffentliches Power-BI-Modell.
English version: [README.en.md](README.en.md).

**Stand:** Meilenstein 1 (Datenpipeline, SQL-Schema, Tests, CI) ist fertig. Power-BI-Modell und Bericht folgen.

## Was der Monitor zeigt

- Stromerzeugung nach Energieträger, Netzlast, Residuallast und Pumpspeicher-Verbrauch im Marktgebiet DE-LU,
  viertelstündlich ab dem 1. Januar 2023.
- Day-Ahead-Preis DE-LU, stündlich.
- Später (Meilenstein 2): installierte Leistung je Bundesland aus dem Marktstammdatenregister.

## Architektur

SMARD-JSON (Wochen-Chunks, Cache in `data/raw/`) -> `stg.smard_series` -> T-SQL-Transformation ->
`dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` + Dimensionen `dw.dim_*` -> Views `rpt.v_*` -> Power BI.

Zeitstempel liegen in UTC (`ts_utc`). Die Schlüssel `datum_key` (JJJJMMTT) und `zeit_key` (0..95) sind
Europe/Berlin-Ortszeit und werden einmal in Python berechnet. Sommer- und Winterzeit werden so an einer Stelle
behandelt (92 bzw. 100 Viertelstunden am Umstellungstag).

## Schnellstart

Voraussetzungen: Docker Desktop, [uv](https://docs.astral.sh/uv/), Microsoft ODBC Driver 18 for SQL Server
(Windows: `winget install -e --id Microsoft.msodbcsql.18`).

```bash
cp .env.example .env            # MSSQL_SA_PASSWORD setzen
docker compose up -d            # SQL Server 2022 Developer, Port 1433
uv sync --dev
uv run --env-file .env ewmonitor all --fixtures   # Testwoche (Oktober 2025) laden und prüfen
uv run --env-file .env ewmonitor all              # ab 2023-01-01 bis gestern laden (ca. 15 Minuten)
```

Verbindung: `EWM_DB_SERVER` (Standard `127.0.0.1,1433`) und `EWM_DB_NAME` (Standard `energiewende`) aus der `.env`.

Befehle: `ewmonitor ingest`, `ewmonitor load`, `ewmonitor check`, `ewmonitor all`, jeweils mit `--from`, `--to`;
`ingest` und `all` zusätzlich mit `--regions` und `--refresh-days` (Standard 60: Chunks, die in den letzten 60 Tagen
enden, werden neu geladen, weil SMARD Wochen nachträglich neu veröffentlicht). `ewmonitor all --fixtures` arbeitet
ohne Netzwerk.

## Tests

- `uv run pytest tests/unit` (ohne Datenbank): Parser, Zeitzonen, Dimensionen, Client mit gemocktem HTTP.
- `uv run --env-file .env pytest tests/dq -m db`: Zeilen je Tag, Pivot, Stundenaggregat, Idempotenz der Ladeläufe.
- GitHub Actions führt beides gegen einen SQL-Server-Container aus (`.github/workflows/ci.yml`).

## Datenqualität

`ewmonitor check` prüft: Viertelstunden je Tag und Reihe (innerhalb der jeweils geladenen Spanne), Nullwerte,
keine negative Erzeugung, Preise zwischen -500 und 4000 EUR/MWh, Zuordnung aller Staging-Zeilen,
Stundenaggregat gegen Viertelstunden, Aktualität (Warnung ab 45 Tagen). Fehlende Viertelstunden je Monat liefert
die View `rpt.v_dq_luecken`.

## Datenquellen und Lizenzen

- SMARD, Bundesnetzagentur: Lizenz CC BY 4.0, Quellenangabe `Bundesnetzagentur | SMARD.de`.
  Filter: Erzeugung 1223, 1224, 1225, 1226, 1227, 1228, 4066, 4067, 4068, 4069, 4070, 4071; Verbrauch 410, 4359, 4387;
  Preis 4169. Kernenergie (1224) endet in den Quelldaten im Januar 2024.
- Marktstammdatenregister (ab Meilenstein 2): Datenlizenz Deutschland Namensnennung 2.0.

## Entscheidungen

Siehe `docs/decisions/` (SQL Server, Publish to web, Umfang, MaStR-Seed) und `docs/CHANGELOG.md`.

## Grenzen

Nur Marktgebiet DE-LU in Version 0.1; die Regelzonen folgen in Meilenstein 5. Keine Prognosen, keine
Redispatch-Daten. Die Rohdaten im Cache sind nicht Teil des Repositories.

## Lizenz

Code: MIT. Daten: siehe Datenquellen.
