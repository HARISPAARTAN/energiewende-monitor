# Changelog

## v0.1.1 (2026-10-25) Korrekturen nach Review

- Faktenladen: Datenbankfehler werden nicht mehr verschluckt. `run_sql_file` liest alle Ergebnismengen vor dem
  Commit, die Ladeskripte laufen mit `SET NOCOUNT ON` und `SET XACT_ABORT ON`; vorher konnte ein fehlgeschlagener
  INSERT das DELETE festschreiben. `--from`/`--to` außerhalb des Kalenders werden abgelehnt.
- Neue Prüfung `fakten_vs_staging` (Staging gegen Fakten je Faktentabelle) sowie `last_viertelstunden_pro_tag`,
  `last_nullwerte`, `preis_stunden_pro_tag`; `stunden_aggregat` ersetzt durch `unvollstaendige_stunden` (Warnung).
- `rpt.v_last_stunde` liefert eine Messgröße nur bei vier Viertelstundenwerten, sonst NULL (unvollständige Stunden),
  und zählt die Werte in den neuen Spalten `viertelstunden_*`; `stunde_utc` ist jetzt `datetime2(0)` (vorher `datetime`).
- `rpt.v_negative_preisphasen` mit `start_datum_key`, exklusivem `ende_utc` und Ortszeit;
  `rpt.v_dim_bundesland` ohne aufgefülltes Kürzel.
- DQ-Tests in eigener Datenbank (`EWM_DQ_DB_NAME`, Standard `energiewende_dq`).
- SMARD-Client: Index-404 bedeutet keine Chunks (Warnung), abgebrochene Übertragungen werden wiederholt, Antworten
  ohne `series`-Liste werden nicht gecacht, `.part`-Dateien werden bei Schreibfehlern entfernt; eine Logzeile je
  heruntergeladenem Chunk und eine Zusammenfassung.
- Aktualität misst den letzten Netzlast-Wert ungleich NULL; neue Datenbanken im Wiederherstellungsmodell SIMPLE,
  Datenbankname geprüft; Verbindungen der CLI werden geschlossen.
- CI: `uv sync --locked`, `permissions: contents: read`.
- Nach v0.1.0 bereits auf `main`: CI-Runner auf ubuntu-24.04 fixiert (85d99c9); erster vollständiger Ladelauf
  dokumentiert, Datenstand 2026-10-25 (3a6640e).

## v0.1.0 (2026-10-25) Meilenstein 1

- SMARD-Client mit Cache und Wiederholungen, Wochen-Chunks als Fixture (Oktober 2025, Zeitumstellung).
- Star-Schema in SQL Server: `stg.smard_series`, `dw.dim_datum`, `dw.dim_zeit`, `dw.dim_energietraeger`,
  `dw.dim_region`, `dw.dim_bundesland`, `dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis`, Views `rpt.v_*`.
- CLI `ewmonitor` (ingest, load, check, all), Datenqualitätsprüfungen, GitHub-Actions-Workflow mit SQL-Server-Container.
