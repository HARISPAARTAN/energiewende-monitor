# Changelog

## v0.1.0 (2026-10-25) Meilenstein 1

- SMARD-Client mit Cache und Wiederholungen, Wochen-Chunks als Fixture (Oktober 2025, Zeitumstellung).
- Star-Schema in SQL Server: `stg.smard_series`, `dw.dim_datum`, `dw.dim_zeit`, `dw.dim_energietraeger`,
  `dw.dim_region`, `dw.dim_bundesland`, `dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis`, Views `rpt.v_*`.
- CLI `ewmonitor` (ingest, load, check, all), Datenqualitätsprüfungen, GitHub-Actions-Workflow mit SQL-Server-Container.
