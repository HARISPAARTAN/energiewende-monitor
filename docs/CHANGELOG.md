# Changelog

## v0.3.0 (2026-10-25) Meilenstein 3 Modell und Bericht

Stand: Dateien und Prüfungen sind fertig; die erste Validierung in Power BI Desktop (Aktualisieren, Seiten, Screenshots,
Abgleich der DAX-Seite) steht noch aus, danach folgt der Tag.

- Power-BI-Projekt als PBIP (`powerbi/EnergiewendeMonitor.pbip`): Semantikmodell als TMDL, Bericht als PBIR, beide code-first
  erzeugt (`tools/pbi/`). Schemas von Microsoft sind vendort (`tools/pbi/schemas/`, `schema_versions.json`), die Visualvorlagen
  stammen aus microsoft/fabric-toolbox (MIT, `tools/pbi/templates/`). Quelle des Modells: `Sql.Database("127.0.0.1,1433",
  "energiewende")` auf den `rpt`-Ansichten, Importmodus, SQL-Anmeldung nur in Desktop.
- Modell: 14 Tabellen (Erzeugung, Last, Preis, Kapazität, `Last Stunde`, `Preisphasen`, `Datenlücken`, Datum als Datumstabelle, Zeit,
  Energieträger, Region, Bundesland, `Kennzahlen`, Feldparameter `Kennzahl-Auswahl`), 26 Kennzahlen mit englischer Beschreibung und
  Formatzeichenfolge, Rolle `Landesbehörde BW`, Kultur de-DE. Berechnete Spalten `Preis Klasse (10 €)` (Abrunden mit INT, BLANK-sicher)
  und `Tageszeit Nr`.
- Kapazitätskennzahlen: `Installierte Leistung (MW)` nimmt den Bestand des letzten Monats mit Daten am oder vor dem Periodenende;
  `Volllaststunden (h)` teilt die Erzeugung durch den durchschnittlichen Monatsendbestand der Monate mit Erzeugungsdaten. Netzreserve
  und Notstromaggregate bleiben im Bestand und sind im Glossar vermerkt. Dazu `Preisstunden` und `Datenstand MaStR`.
- Bericht: fünf Seiten (`Überblick`, `Erzeugung & Last`, `Preise`, `Ausbau`, `Datenqualität & Quellen`, 1280 mal 720), Thema
  `Energiewende`, Drillthrough von Überblick nach Erzeugung & Last, Lesezeichen `Erneuerbar` und `Konventionell` sowie ein Slicer
  `Kategorie` (Lesezeichen sind im veröffentlichten Bericht nicht erreichbar), TopN-10-Filter auf den Preisphasen,
  Feldparameter-Liniendiagramm, Heatmap, Histogramm der Preisklassen.
- Tests `tests/pbi/` (offline, Marker `pbi`): Schemaprüfung aller TMDL- und PBIR-Dateien, Lint von Modell, Kennzahlen, Beziehungen,
  Rolle und Seiten, optionaler Parse mit Microsofts TOM (`test_tmdl_tom.py`, `tools/pbi/fetch_tom.py`).
- Abgleich Modell und Warehouse: `sql/queries/reconcile_m3.sql` (R1 bis R9, R5 bis R8 folgen der DAX-Logik), DAX-Abfragen und
  ADOMD-Zugriff in `tools/pbi/reconcile.py` (`python -m tools.pbi.reconcile sql|dax-queries|compare`), Live-Test
  `tests/pbi/test_reconcile.py` (Marker `live`, überspringt ohne geöffnetes Desktop oder ADOMD), `tools/pbi/fetch_adomd.py`
  für den ADOMD-Client ohne Systeminstallation. Die SQL-Werte stehen mit Datum in `docs/kpi-glossar.md`.
- `tools/pbi/make_public_variant.py`: Kopie des Projekts ohne Rolle als `EnergiewendeMonitor (öffentlich)` für "Im Web veröffentlichen".
- `docs/kpi-glossar.md`: Definition, Formel, Einheit, Quelle und Hinweise für alle 26 Kennzahlen; `docs/screenshots/SHOTLIST.md`.
- README und README.en: Abschnitte Bericht und Entwicklung (`uv sync --extra mastr`). CI: `lint-and-unit` führt zusätzlich
  `pytest tests/pbi -m "pbi and not live"` aus. Version 0.3.0 (`pyproject.toml`, `ewmonitor.__version__`).

## v0.2.0 (2026-10-25) Meilenstein 2 Kapazitäten

- Kalender aus `config.toml` (`[calendar]`, 1990-01-01 bis 2030-12-31); `dim_datum` deckt die MaStR-Historie ab,
  SMARD-Befehle lehnen `--from` vor `[scope] start` weiter ab. Neues Bundesland `Unbekannt` (`UNB`).
- `ewmonitor.mastr`: Einheiten lesen und normalisieren, Zuordnung zu den SMARD-Energieträgern über
  `data/seed/mastr_energietraeger_mapping.csv`, monatliche Aggregation von Zubau, Abgang und Anfangsbestand je
  Bundesland und Energieträger (MW erst je Zelle gerundet, unplausible Daten gezählt), Seed-CSV mit Quellenangabe
  nach DL-DE-BY-2.0. Synthetische Fixture mit 61 Einheiten (`tools/make_mastr_fixture.py`).
- Neuer Befehl `ewmonitor seed-mastr` (`--date`, `--skip-download`, `--fixtures`, `--profile`, `--out`,
  `--source xml|sqlite`).
- `stg.mastr_kapazitaet`, `dw.fact_kapazitaet` mit laufendem Bestand über ein lückenloses Monatsraster,
  `rpt.v_kapazitaet`; `load` und `all` laden den Seed. Neue Prüfungen `kapazitaet_bestand_nicht_negativ`,
  `kapazitaet_vs_staging`, `kapazitaet_monatsraster` und `kapazitaet_plausibel` (Warnung).
- XML-Leser für den Gesamtdatenexport (`--source xml`, Standard): open-mastr 1.0 scheitert beim SQLite-Import an
  allen Solar-Dateien des Exports 2026-10-25; der eigene Leser streamt den Zip mit lxml in rund fünf Minuten.
  Beide Leser liefern auf der Fixture denselben Rahmen. lxml ist neue Abhängigkeit.
- Zuordnung nach dem echten Profil: Offshore-Wind über `WindAnLandOderAufSee` und das Bundesland
  `Ausschließliche Wirtschaftszone` (`AWZ`); Wasserstoff, Klärschlamm, Druck aus Gasleitungen als sonstige
  Konventionelle; Klärgas, Deponiegas, Grubengas, Solarthermie, Druck aus Wasserleitungen als sonstige Erneuerbare.
- Echter Seed, Exportstand 2026-10-25: 9.663.557 Einheiten, 25.323 Zeilen, keine nicht zugeordneten Werte;
  Wertelisten in `docs/mastr-profil.md`, Entscheidungen in ADR-004.
- Nach dem Review: `kapazitaet_plausibel` warnt auch bei fehlendem Energieträger und begrenzt zusätzlich
  Wasserkraft und sonstige Konventionelle; `kapazitaet_monatsraster` scheitert, wenn ein Paar vor dem letzten
  Monat endet; `kapazitaet_vs_staging` vergleicht zusätzlich den Endbestand je Bundesland und Energieträger;
  Toleranz für negativen Bestand eine Rundungseinheit. `seed-mastr --fixtures --profile` schreibt
  `docs/mastr-profil-fixture.md`; ein `--date`, das vom Zip-Namen abweicht, wird gemeldet.
  `ewmonitor.__version__` = 0.2.0.
- Bekannte Grenze: Die Kapazitätshistorie vor etwa 2019 ist unvollständig (nur heute registrierte Einheiten),
  siehe README und ADR-004.

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
