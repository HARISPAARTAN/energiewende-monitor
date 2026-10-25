# Validierungssitzung mit Power BI Desktop (Meilenstein 3)

Die einzige Sitzung mit Desktop, etwa 20 bis 30 Minuten. Vorher sind alle Offline-Tests grün, `powerbi/` enthält keine
`.pbi/cache.abf`, und der SQL-Server-Container läuft (`docker compose ps`, Dienst `ewm-mssql` healthy; Daten geladen mit
`uv run --env-file .env ewmonitor load`). Das Kennwort wird nur von Hand in Desktop eingegeben, nie in einen Chat oder eine Datei.

## Klickfolge

1. Alle Power-BI-Desktop-Fenster schließen. Im Explorer `E:\GITGUB\energiewende-monitor\powerbi\EnergiewendeMonitor.pbip`
   doppelklicken, oder in Desktop Datei, Öffnen, Auf diesem Gerät suchen und die Datei wählen.
2. Meldet Desktop, dass das Projekt eine Vorschaufunktion braucht: Datei, Optionen und Einstellungen, Optionen, Vorschaufeatures,
   `Power BI Project (.pbip) save option` und `Store semantic model using TMDL format` ankreuzen, OK, Desktop neu starten, zurück zu Punkt 1.
3. Erscheint ein Fehlerdialog (zum Beispiel "Unable to open document", "TMDL Format Error" oder ein PBIR-Schemafehler mit
   Dateiname): mit "Details kopieren" oder durch Markieren den Text unverändert an den Agenten geben, Desktop ohne Speichern schließen und die
   Fehlerschleife unten ausführen.
4. Der Bericht öffnet ohne Daten (kein Cache). Start, Aktualisieren. Im Dialog für `127.0.0.1,1433;energiewende` den Reiter **Datenbank**
   wählen, Benutzer `sa` und das Kennwort aus der `.env` eingeben, bei "Select which level to apply these settings to" `127.0.0.1,1433`
   wählen, Verbinden. Fragt Desktop nach der Verschlüsselung ("unable to connect using an encrypted connection"), OK wählen oder, falls angeboten,
   "Trust server certificate" ankreuzen. Warten, bis die Aktualisierung fertig ist. Schlägt eine Tabelle fehl, den Fehlertext an den Agenten geben.
5. Modellansicht (drittes Symbol links): Die Beziehungen zwischen Fakten und Dimensionen sind gezeichnet; `Datum`, Tabellentools, prüfen, dass
   "Als Datumstabelle markieren" auf `Datum[Datum]` gesetzt ist.
6. Berichtsansicht, alle fünf Seiten öffnen (`Überblick`, `Erzeugung & Last`, `Preise`, `Ausbau`, `Datenqualität & Quellen`). Kein Visual darf
   "Visual kann nicht angezeigt werden" oder ein rotes Fehlersymbol zeigen; sonst "Details anzeigen" und den Text an den Agenten geben. Dann prüfen:
   - Drillthrough: auf Überblick Rechtsklick auf einen Monat im Flächendiagramm, Drillthrough, Erzeugung & Last.
   - Lesezeichen: Ansicht, Lesezeichen, `Erneuerbar` und `Konventionell` wählen.
   - Der Slicer `Kennzahl-Auswahl` ändert das Liniendiagramm unten rechts; der Slicer `Kategorie` filtert die Seite Überblick.
   - Die Energieträgerfarben. Ignorieren die beiden gestapelten Diagramme die Spalte `Farbe`: Format, Datenfarben, fx, Feldwert
     `Energieträger[Farbe]` einmal setzen.
   - RLS: Modellierung, Anzeigen als, `Landesbehörde BW` ankreuzen, OK. Ausbau zeigt nur Baden-Württemberg; danach "Anzeige beenden".
7. Screenshots nach `docs/screenshots/SHOTLIST.md`: Fenster maximiert, jede Seite 1280 px breit (Win+Shift+S, Fenster-Ausschnitt), als PNG in
   `E:\GITGUB\energiewende-monitor\docs\screenshots\` mit den dort genannten Dateinamen.
8. Desktop offen lassen und dem Agenten "Desktop ist offen" sagen. Der Agent führt
   `uv run --env-file .env --group pbi pytest tests/pbi/test_reconcile.py -m live -q` aus (einmalig zuvor
   `uv run python tools/pbi/fetch_adomd.py`). Fehlt ADOMD, führt der Owner die neun DAX-Abfragen aus
   `uv run python -m tools.pbi.reconcile dax-queries` in der DAX-Abfrageansicht von Desktop (viertes Symbol links) aus und gibt die Ergebnisse
   an den Agenten; dieser füllt die Tabelle in `docs/kpi-glossar.md` (Abschnitt "Abgleich").
9. Datei, Speichern (Strg+S), Desktop schließen. Desktop normalisiert beim ersten Speichern Dateien: CRLF-Zeilenenden, Reihenfolge der
   Eigenschaften und der `lineageTag`, die Sprachmetadaten in `cultures/de-DE.tmdl`, `diagramLayout.json`, `.pbi/`-Dateien und möglicherweise
   neuere `$schema`-Versionen. Die normalisierten Dateien werden übernommen.

## Fehlerschleife (wiederholen, bis Desktop öffnet, aktualisiert und ohne Fehler rendert)

1. Der Owner gibt den Fehlertext von Desktop unverändert weiter.
2. Der Agent findet Datei und Zeile, behebt die Ursache (`tools/pbi/pages.json` oder `tools/pbi/build_report.py` für Berichtsdateien mit
   anschließender Neuerzeugung, die TMDL-Dateien direkt für das Modell; erzeugte Berichtsdateien werden nicht von Hand geändert).
3. Der Agent führt `uv run pytest tests/pbi -m "pbi and not live" -q` und `uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q` aus und ergänzt
   eine Regressionsprüfung im passenden Lint-Test, wenn die Fehlerklasse neu ist.
4. Der Owner öffnet das Projekt neu (oder wählt "Externe Änderungen übernehmen" im Hinweisband von Desktop) und macht an der gescheiterten Stelle weiter.
   Nach drei Runden ohne Fortschritt beim selben Fehler wird abgebrochen und mit den Fehlertexten gemeldet.

## Nach der Sitzung (Agent)

1. `git diff` der Desktop-Normalisierung prüfen: Nur Formatierung und Desktop-Metadaten dürfen sich ändern; jede inhaltliche Änderung
   (umbenannte Objekte, entfernte Visuals, geänderte DAX) ist ein Befund.
2. Offline-Tests auf den normalisierten Dateien wiederholen. Schreibt Desktop eine neuere `$schema`-Version: ist sie in microsoft/json-schemas
   veröffentlicht, in `tools/pbi/vendor_schemas.py` aufnehmen, neu vendoren und `schema_versions.json` aktualisieren; sonst die URL in
   `schema_versions.json` unter `unpublished` eintragen.
3. Die Lesezugriffe der Lint-Tests nur an die Formatierung anpassen, nie die Absicht eines Tests abschwächen.
4. Committen: `chore(pbi): files as normalised by Power BI Desktop; screenshots and reconciliation` (mit `docs/screenshots/*.png` und der gefüllten
   Abgleichstabelle), pushen, `gh run watch --exit-status`.
5. Tag setzen: `git tag -a v0.3.0 -m "Meilenstein 3: Semantikmodell und Bericht"` und `git push origin v0.3.0`.
