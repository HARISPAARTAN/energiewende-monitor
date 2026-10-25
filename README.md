# Energiewende-Monitor

[![CI](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/energiewende-monitor/actions/workflows/ci.yml)

Deutsche Strommarktdaten (SMARD) als Star-Schema in SQL Server, Basis für ein öffentliches Power-BI-Modell.
English version: [README.en.md](README.en.md).

**Stand:** Meilenstein 2 ist fertig: Datenpipeline, SQL-Schema, Tests, CI und installierte Leistung aus dem
Marktstammdatenregister. Power-BI-Modell und Bericht folgen.

Datenstand: SMARD 2026-10-25 (ab 2023-01-01, DE-LU; Ladezeit ca. 3 Minuten auf einem Laptop);
Marktstammdatenregister Exportstand 2026-10-25.

## Was der Monitor zeigt

- Stromerzeugung nach Energieträger, Netzlast, Residuallast und Pumpspeicher-Verbrauch im Marktgebiet DE-LU,
  viertelstündlich ab dem 1. Januar 2023.
- Day-Ahead-Preis DE-LU, stündlich.
- Installierte Leistung je Monat, Bundesland und Energieträger ab 1990 aus dem Marktstammdatenregister
  (Zubau, Abgang, Bestand), siehe [Kapazitäten (MaStR)](#kapazitäten-mastr).

## Architektur

SMARD-JSON (Wochen-Chunks, Cache in `data/raw/`) -> `stg.smard_series` -> T-SQL-Transformation ->
`dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` + Dimensionen `dw.dim_*` -> Views `rpt.v_*` -> Power BI.
MaStR-Seed `data/seed/kapazitaet_monat.csv` -> `stg.mastr_kapazitaet` -> `dw.fact_kapazitaet` -> `rpt.v_kapazitaet`.

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
uv run --env-file .env ewmonitor all              # ab 2023-01-01 bis gestern laden (ca. 3 Minuten)
```

Verbindung: `EWM_DB_SERVER` (Standard `127.0.0.1,1433`) und `EWM_DB_NAME` (Standard `energiewende`) aus der `.env`.

Befehle: `ewmonitor ingest`, `ewmonitor load`, `ewmonitor check`, `ewmonitor all`, jeweils mit `--from`, `--to`;
`ingest` und `all` zusätzlich mit `--regions` und `--refresh-days` (Standard 60: Chunks, die in den letzten 60 Tagen
enden, werden neu geladen, weil SMARD Wochen nachträglich neu veröffentlicht). `ewmonitor all --fixtures` arbeitet
ohne Netzwerk.

## Tests

- `uv run pytest tests/unit` (ohne Datenbank): Parser, Zeitzonen, Dimensionen, Client mit gemocktem HTTP,
  MaStR-Leser (SQLite und XML auf derselben synthetischen Fixture), Zuordnung und Aggregation.
- `uv run --env-file .env pytest tests/dq -m db`: Zeilen je Tag, Pivot, Stundenaggregat, Idempotenz der Ladeläufe,
  Fehler im Faktenladen. Die Suite arbeitet in einer eigenen Datenbank (`EWM_DQ_DB_NAME`, Standard `energiewende_dq`),
  leert dort Staging und Fakten und lädt die Testwoche; die Datenbank aus `EWM_DB_NAME` bleibt unberührt.
- GitHub Actions führt beides gegen einen SQL-Server-Container aus (`.github/workflows/ci.yml`).

## Fehlerbehandlung

HTTP-Fehler, die vorübergehend sein können (Verbindungsabbruch, Zeitüberschreitung, 429, 5xx, ungültiges JSON),
werden mit Wartezeit wiederholt (bis zu drei Versuche). Ein Chunk, der danach noch fehlschlägt, bricht den Lauf ab: Das Staging
wird je Reihe und Zeitraum ersetzt, ein übersprungener Chunk würde gute Zeilen dieser Woche löschen. Liefert SMARD
für eine konfigurierte Reihe keinen Index (404), hat sie keine Chunks; das wird als WARNING protokolliert.
Datenbankfehler brechen den Lauf ab und rollen den Schritt zurück; `--from`/`--to` außerhalb des Kalenders
(`scope.start` bis 2030-12-31) werden abgelehnt.

## Datenqualität

`ewmonitor check` prüft: Viertelstunden je Tag für Erzeugung und Last (innerhalb der jeweils geladenen Spanne),
Nullwerte in Erzeugung und Last, keine negative Erzeugung, 23, 24 oder 25 Stundenpreise je Tag, Preise zwischen
-500 und 4000 EUR/MWh, Zuordnung aller Staging-Zeilen, Abgleich Staging gegen Fakten je Faktentabelle,
unvollständige Stunden der Last (nur Warnung; Lücken in den Quelldaten, meist jüngere, die SMARD noch nachliefern kann) und Aktualität
(Warnung ab 45 Tagen). Fehlende Viertelstunden je Monat liefert die View `rpt.v_dq_luecken`.
Für die Kapazitäten: kein negativer Bestand, Staging gegen Fakten, lückenloses Monatsraster je Bundesland und
Energieträger und ein Plausibilitätsband für den bundesweiten Bestand im neuesten Monat (nur Warnung).

Die View `rpt.v_last_stunde` fasst die Last je UTC-Stunde zusammen. Eine Messgröße hat dort nur dann einen Wert,
wenn alle vier Viertelstunden der Stunde einen Wert haben, sonst NULL; die Spalten `viertelstunden_*` nennen die
Anzahl der vorhandenen Werte.

## Kapazitäten (MaStR)

Datenquelle: Marktstammdatenregister der Bundesnetzagentur, Datenlizenz Deutschland – Namensnennung – Version 2.0
(https://www.govdata.de/dl-de/by-2-0), Daten aggregiert.

Der Seed `data/seed/kapazitaet_monat.csv` (Exportstand 2026-10-25, 25.323 Zeilen, 1,1 MB) verdichtet 9.663.557
Einheiten aus acht Einheitentabellen zu Zubau, Abgang und Anfangsbestand je Monat, Bundesland und Energieträger.
`ewmonitor load` und `ewmonitor all` laden ihn nach `stg.mastr_kapazitaet` und bauen daraus `dw.fact_kapazitaet`
mit laufendem Bestand. Die View `rpt.v_kapazitaet` hat die Spalten `datum_key`, `jahr_monat`, `bundesland_key`,
`energietraeger_key`, `zubau_mw`, `anzahl_zubau`, `abgang_mw`, `anzahl_abgang`, `anfangsbestand_mw`,
`anfangsbestand_anzahl`, `bestand_mw`, `bestand_anzahl`.

Bestand im Oktober 2026 (Nettonennleistung): Photovoltaik 116,6 GW, Wind an Land 71,5 GW, Wind auf See 11,6 GW,
Erdgas 35,8 GW, Steinkohle 15,1 GW, Braunkohle 14,8 GW, Pumpspeicher 9,9 GW, Biomasse 8,8 GW, Wasserkraft 5,3 GW,
Kernenergie 0 (seit April 2023).

Regeln (Begründung in `docs/decisions/ADR-004-mastr-seed.md`):

- Es zählen Einheiten `In Betrieb`, `Vorübergehend stillgelegt` und `Endgültig stillgelegt`; `In Planung` nicht
  (75.731 Einheiten).
- Zubau im Monat der Inbetriebnahme, Abgang im Monat der endgültigen Stilllegung. Vorübergehend stillgelegte
  Einheiten bleiben im Bestand.
- Einheiten mit Inbetriebnahme vor 1990 oder ohne Datum gehen als Anfangsbestand in den Januar 1990 ein.
- Offshore-Wind in der Ausschließlichen Wirtschaftszone erhält das Bundesland `AWZ`. Ohne Bundesland steht
  `UNB` (Unbekannt): 74 Einheiten, vor allem Wasser- und Pumpspeicherkraftwerke in Luxemburg, Österreich und an der
  Schweizer Grenze, die in das deutsche Netz einspeisen.
- Batterien und andere Speicher außer Pumpspeichern sind ausgeschlossen (2.892.406 Einheiten): SMARD weist für sie
  keine Erzeugung aus.
- Die Zuordnung zu den SMARD-Energieträgern steht in `data/seed/mastr_energietraeger_mapping.csv`, die Wertelisten
  des Exports in `docs/mastr-profil.md`. Im Export 2026-10-25 bleibt kein Wert ohne Zuordnung.
- Photovoltaik: Die Nettonennleistung (Wechselrichter) liegt rund 11 % unter der Bruttoleistung der Module, die
  die Bundesnetzagentur in ihren Zubauzahlen meldet (Oktober 2026: 116,6 statt 131,7 GW).
- Aus dem Register gelöschte Einheiten fehlen auch in der Vergangenheit; frühe Jahre sind deshalb eine Untergrenze.

Seed neu erzeugen (nur auf dem Entwicklerrechner, nicht in CI):

```bash
uv sync --extra mastr
uv run ewmonitor seed-mastr --profile                   # Download mit open-mastr, dann Seed und Profil
uv run ewmonitor seed-mastr --skip-download --profile   # vorhandenen Zip verwenden (ca. 5 Minuten)
```

`--source xml` (Standard) liest den Gesamtdatenexport-Zip direkt: lxml streamt die UTF-16-XML-Dateien bei
konstantem Speicher und löst die Katalogwerte selbst auf. open-mastr 1.0 dient nur als Downloader, weil sein
SQLite-Import an allen 66 Solar-Dateien des Exports 2026-10-25 scheitert (Mehrfachwerte wie `710 3183` in einer
Ganzzahlspalte). `--source sqlite` liest die open-mastr-Datenbank als Rückfallebene. Der Exportstand im Seed kommt
aus dem Dateinamen des Zips oder aus `--date YYYYMMDD`. Platz: Zip 2,4 GB, SQLite-Datenbank von open-mastr 3,7 GB
(entsteht beim Download mit); Budget 15 GB. Laufzeit am 2026-10-25: Download 12 Minuten, open-mastr-Import
16 Minuten, XML-Leser 5 Minuten.

## Datenquellen und Lizenzen

- SMARD, Bundesnetzagentur: Lizenz CC BY 4.0, Quellenangabe `Bundesnetzagentur | SMARD.de`.
  Filter: Erzeugung 1223, 1224, 1225, 1226, 1227, 1228, 4066, 4067, 4068, 4069, 4070, 4071; Verbrauch 410, 4359, 4387;
  Preis 4169. Kernenergie (1224): letzte Erzeugung in der Viertelstunde ab 2023-04-15 23:45 Ortszeit, danach
  Nullwerte bis 2024-01-30 12:15, ab 2024-01-30 12:30 keine Werte mehr (NULL); die Reihe endet in den Quelldaten
  am 2024-02-04.
- Marktstammdatenregister, Bundesnetzagentur: Datenlizenz Deutschland – Namensnennung – Version 2.0, Quellenangabe
  siehe [Kapazitäten (MaStR)](#kapazitäten-mastr). Im Repository liegen nur aggregierte Werte.

## Entscheidungen

Siehe `docs/decisions/` (SQL Server, Publish to web, Umfang, MaStR-Seed) und `docs/CHANGELOG.md`.

## Grenzen

Erzeugung, Last und Preise nur für das Marktgebiet DE-LU; die Regelzonen folgen in Meilenstein 5. Keine
Prognosen, keine Redispatch-Daten. Der MaStR-Export und die Rohdaten im Cache sind nicht Teil des Repositories.

## Lizenz

Code: MIT. Daten: siehe Datenquellen.
