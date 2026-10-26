# Validierungssitzung mit Power BI Desktop (Meilenstein 3)

Die einzige Sitzung mit Desktop, etwa 20 bis 30 Minuten. Vorher sind alle Offline-Tests grün, `powerbi/` enthält keine
`.pbi/cache.abf`, und der SQL-Server-Container läuft (`docker compose ps`, Dienst `ewm-mssql` healthy; Daten geladen mit
`uv run --env-file .env ewmonitor load`). Das Kennwort wird nur von Hand in Desktop eingegeben, nie in einen Chat oder eine Datei.

Vor der Sitzung (Agent, Pflichtbefehl, kein Test): `uv run python tools/pbi/build_report.py` gefolgt von `git status --short powerbi`
darf nichts ausgeben, sonst weicht der Bericht von `tools/pbi/pages.json` ab.

## Quelle der Wahrheit für den Bericht

- **Bis zur Sitzung** erzeugen `tools/pbi/pages.json` und `tools/pbi/build_report.py` die Berichtsdateien (Seiten, Visuals, Lesezeichen,
  Themaregistrierung). Änderungen gehören dorthin; danach wird neu erzeugt. Erzeugte Dateien werden nicht von Hand geändert.
- **Nach der Sitzung** sind die PBIR-Dateien, die Desktop gespeichert hat, die Quelle. `build_report.py` wird nicht mehr ausgeführt: Es würde
  die Normalisierung von Desktop (Zeilenenden, Eigenschaftsreihenfolge, `$schema`-Versionen) und jede Korrektur aus der Sitzung überschreiben.
  Spätere Berichtsänderungen erfolgen in Desktop oder direkt in den PBIR-Dateien.
- Die Lint-Tests (`tests/pbi`) laufen unverändert weiter, jetzt auf den von Desktop gespeicherten Dateien. Die Prüfung "Neuerzeugung
  hinterlässt einen sauberen Baum" ist der Pflichtbefehl oben und gilt nur vor der Sitzung; es gibt dafür keinen Test.

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
   "Trust server certificate" ankreuzen. Warten, bis die Aktualisierung fertig ist. Meldet die erste Aktualisierung nach dem Öffnen
   "A cyclic reference was encountered during evaluation" bei einer beliebigen Tabelle (am 2026-10-26 bei `Zeit`, `Erzeugung` und `Datum`), den Dialog
   schließen und ein zweites Mal aktualisieren; das zweite Mal lud jedes Mal alle Tabellen. Schlägt eine Tabelle auch dann fehl, den Fehlertext an
   den Agenten geben.
5. Modellansicht (drittes Symbol links): Die Beziehungen zwischen Fakten und Dimensionen sind gezeichnet; `Datum`, Tabellentools, prüfen, dass
   "Als Datumstabelle markieren" auf `Datum[Datum]` gesetzt ist.
6. **Abgleich sofort nach der Aktualisierung**, vor allen Screenshots: Desktop offen lassen und dem Agenten "Desktop ist offen" sagen. Der Agent führt
   `uv run --env-file .env --group pbi pytest tests/pbi/test_reconcile.py -m live -q` aus (einmalig zuvor
   `uv run python tools/pbi/fetch_adomd.py`). Fehlt ADOMD, führt der Owner die neun DAX-Abfragen aus
   `uv run python -m tools.pbi.reconcile dax-queries` in der DAX-Abfrageansicht von Desktop (viertes Symbol links) aus und gibt die Ergebnisse
   an den Agenten; dieser füllt die Tabelle in `docs/kpi-glossar.md` (Abschnitt "Abgleich"). Weicht ein Wert ab, wird zuerst die DAX-Kennzahl
   korrigiert und neu abgeglichen; Screenshots entstehen erst danach.
7. Berichtsansicht, alle fünf Seiten öffnen (`Überblick`, `Erzeugung & Last`, `Preise`, `Ausbau`, `Datenqualität & Quellen`). Kein Visual darf
   "Visual kann nicht angezeigt werden" oder ein rotes Fehlersymbol zeigen; sonst "Details anzeigen" und den Text an den Agenten geben.
   Die Seiten tragen das dunkle Thema `Energiewende Leitstand` mit Seitenleiste links und Kopfzeile oben (kein rotes Säulendiagramm, kein
   mintfarbener Hintergrund auf der Seite Preise). Dann prüfen:
   - Navigation und Kopfzeile: Die fünf Schaltflächen der Seitenleiste wechseln die Seite (in Desktop mit Strg+Klick); die Schaltfläche der aktuellen
     Seite ist hervorgehoben (Fläche `#0F3442`, Text cyan und fett, auch beim Überfahren mit der Maus). Der Text jeder Schaltfläche beginnt nicht
     am linken Rand, sondern eingerückt (`leftMargin` 20, im Bericht als ganze Zahl `20L` geschrieben); klebt er am Rand, hat Desktop die
     Eigenschaft nicht übernommen. Die Kopfzeile zeigt den Seitentitel und rechts auf einer Zeile, ohne abgeschnittenes Ende,
     `Datenstand: SMARD TT.MM.JJJJ · MaStR Monat JJJJ`.
   - Kennzahlenkacheln auf Überblick: deutsches Zahlenformat mit Einheit, nirgends `92.87 €` neben `1.791`; die Werte stehen vollständig in der Kachel
     (am breitesten `92,87 €/MWh`) und in der halbfetten Schrift des Themas. Erwartete Werte laut Abfragen vom 2026-10-26 (Erzeugung, EE-Anteil,
     Day-Ahead Ø, negative Preisstunden, installierte Leistung): Jahr 2025 `439,3 TWh`, `58,9 %`, `89,32 €/MWh`, `573 h`, `287,3 GW`;
     ohne Datumsfilter `1.707,1 TWh`, `58,5 %`, `92,87 €/MWh`, `1.791 h`, `303,7 GW`.
   - Messinstrumente auf Überblick: Photovoltaik, Wind an Land und Wind auf See zeigen den Anteil am Ziel 2030 (ohne Datumsfilter laut Abfrage vom
     2026-10-26 etwa 54 %, 62 % und 39 %); unter der RLS-Rolle (Punkt "RLS" unten) sind sie leer.
   - Feldparameter: Der Slicer `Kennzahl-Auswahl` ändert das Liniendiagramm unten rechts auf Überblick; alle vier Einträge zeigen eine Linie
     (nicht leer, nicht "Anzahl von ..."). Er wählt genau einen Eintrag, ohne "Alle auswählen"; ohne Auswahl steht er auf `Erzeugung (MWh)`.
     Fallback: Feld im Bereich Y entfernen, den Parameter `Kennzahl-Auswahl` hineinziehen, speichern und die Form dem Agenten zeigen.
   - Energieträgerfarben: Die drei gestapelten Diagramme (Überblick, Erzeugung & Last, Ausbau) zeigen je Gruppe die Farbe der Palette aus
     `tools/pbi/pages.json` (Biomasse grün, Wind blau, Photovoltaik gelb, Wasserkraft türkisgrün, Erdgas orange, Steinkohle violett, Braunkohle rot,
     Sonstige grau); die Legende zeigt alle acht Einträge in dieser Reihenfolge, ohne Blätterpfeil und ohne gekürzte Namen (Überblick unten in
     8 pt, die beiden Säulendiagramme rechts). Fallback: Format, Datenfarben, je Gruppe von Hand. Nicht "fx": das
     bietet Desktop mit Legende und bei Flächendiagrammen nicht an.
   - Der Slicer `Kategorie` (Überblick) ist horizontal, mit zwei Kacheln und ohne "Alle auswählen". Fallback: Format, Slicer-Einstellungen,
     Ausrichtung, Horizontal.
   - Zeitachsen und Zeiträume: Die fünf Monatsdiagramme (Flächendiagramm, EE-Anteil, Kennzahl-Auswahl, negative Preisstunden, Zubau) zeigen alle
     Monate ohne Bildlaufleiste. Die Jahresfilter bieten nur Jahre mit Daten an (Überblick und Preise 2023 bis 2026, Ausbau 1990 bis 2026), der
     Datumsbereich auf Erzeugung & Last reicht vom 01.01.2023 bis zum Datenstand, die Linien auf "EE-Anteil vs. Vorjahr" enden am Datenstand, der
     Zubau beginnt 2019, und "Volllaststunden nach Energieträger und Jahr" zeigt nur 2023 bis 2026 mit allen fünf Spalten.
   - Texte ohne Links: Seitenleiste unten und die Karten auf Datenqualität & Quellen zeigen die Adressen als normalen Text (Desktop zeichnet Links in
     Textfeldern immer dunkelblau); kein Text klebt am Rand einer Karte, und keine Kachel zeigt einen englischen Untertitel wie "… by …".
   - Lesezeichen: Slicer `Kategorie` zurücksetzen, dann Ansicht, Lesezeichen, `Erneuerbar` und `Konventionell` wählen. Lesezeichen erfassen den
     Seitenfilter, nicht den Zustand des Slicers; steht der Slicer auf Konventionell und wird `Erneuerbar` angewendet, ist die Seite leer. Fallback:
     beide Lesezeichen in Desktop neu aufnehmen (Slicer leer, Filter setzen, Lesezeichen aktualisieren).
   - EE-Anteil: Slicer `Kategorie` auf Konventionell: die Kachel EE-Anteil zeigt `0,0 %` (nie mehr als 100 %), auf Erneuerbar `100,0 %`.
   - Drillthrough: auf Überblick Rechtsklick auf einen Monat im Flächendiagramm, Drillthrough, Erzeugung & Last. Der Monatsfilter bleibt gesetzt;
     zurück geht es über die Seitenregister.
   - Preise: Die Tabelle "Längste negative Preisphasen" zeigt genau zehn Zeilen (je Jahr können bei gleichem Rang mehr erscheinen; Fallback:
     Filterbereich, Erste N, 10, nach Stunden). Das Histogramm hat die Klasse -10. Die Diagrammfarben folgen dem Thema.
   - Heatmap auf Erzeugung & Last: Die Zellwerte sind auf dem hellsten Blau der Skala (`#256ABF`) lesbar. Fallback: Format, Zellelemente, Schriftfarbe.
   - Ausbau: Ein Klick auf einen Balken (Bundesland) filtert die Tabelle "Volllaststunden nach Energieträger und Jahr": die Spalte Volllaststunden ist
     dann leer, nie über 8.760 Stunden. Ohne Auswahl liegen die Werte unter 8.760 Stunden (Wind Onshore 2025: 1.634).
   - RLS: Modellierung, Anzeigen als, `Landesbehörde BW` ankreuzen, OK. Ausbau zeigt nur Baden-Württemberg, Volllaststunden sind leer, die
     Messinstrumente auf Überblick sind leer; danach "Anzeige beenden".
8. Screenshots zuletzt, nach `docs/screenshots/SHOTLIST.md`: Fenster maximiert, jede Seite 1280 px breit (Win+Shift+S, Fenster-Ausschnitt), als PNG in
   `E:\GITGUB\energiewende-monitor\docs\screenshots\` mit den dort genannten Dateinamen. Slicer und Filter vorher zurücksetzen.
9. Datei, Speichern (Strg+S), Desktop schließen. Desktop normalisiert beim ersten Speichern Dateien: CRLF-Zeilenenden, Reihenfolge der
   Eigenschaften und der `lineageTag`, die Sprachmetadaten in `cultures/de-DE.tmdl`, `diagramLayout.json`, `.pbi/`-Dateien und möglicherweise
   neuere `$schema`-Versionen. Die normalisierten Dateien werden übernommen und sind ab jetzt die Quelle (siehe oben).
   Danach `git status`: Es darf keine `.pbi/`-Datei zur Übernahme anstehen (`cache.abf`, `localSettings.json`, `editorSettings.json` und
   `unappliedChanges.json` sind git-ignoriert); erscheint dort eine andere, gehört sie in die `.gitignore`, nicht in den Commit.

## Fehlerschleife (wiederholen, bis Desktop öffnet, aktualisiert und ohne Fehler rendert)

Gilt bis zum ersten Speichern in Desktop, solange `build_report.py` noch die Quelle ist.

1. Der Owner gibt den Fehlertext von Desktop unverändert weiter.
2. Der Agent findet Datei und Zeile, behebt die Ursache (`tools/pbi/pages.json` oder `tools/pbi/build_report.py` für Berichtsdateien mit
   anschließender Neuerzeugung, die TMDL-Dateien direkt für das Modell; erzeugte Berichtsdateien werden nicht von Hand geändert). Hat Desktop
   den Bericht bereits gespeichert, wird stattdessen die gespeicherte PBIR-Datei direkt korrigiert und `build_report.py` nicht mehr ausgeführt.
3. Der Agent führt `uv run pytest tests/pbi -m "pbi and not live" -q` und `uv run --group pbi pytest tests/pbi/test_tmdl_tom.py -q` aus und ergänzt
   eine Regressionsprüfung im passenden Lint-Test, wenn die Fehlerklasse neu ist.
4. Der Owner öffnet das Projekt neu (oder wählt "Externe Änderungen übernehmen" im Hinweisband von Desktop) und macht an der gescheiterten Stelle weiter.
   Nach drei Runden ohne Fortschritt beim selben Fehler wird abgebrochen und mit den Fehlertexten gemeldet.

## Nach der Sitzung (Agent)

1. Zuerst `git status`: Keine `.pbi/`-Datei darf zur Übernahme anstehen (`powerbi/**/.pbi/unappliedChanges.json` ist in der `.gitignore`).
   Dann `git diff` der Desktop-Normalisierung prüfen: Nur Formatierung und Desktop-Metadaten dürfen sich ändern; jede inhaltliche Änderung
   (umbenannte Objekte, entfernte Visuals, geänderte DAX) ist ein Befund.
2. Offline-Tests auf den normalisierten Dateien wiederholen. Schreibt Desktop eine neuere `$schema`-Version: ist sie in microsoft/json-schemas
   veröffentlicht, in `tools/pbi/vendor_schemas.py` aufnehmen, neu vendoren und `schema_versions.json` aktualisieren; sonst die URL in
   `schema_versions.json` unter `unpublished` eintragen. `build_report.py` wird nicht mehr ausgeführt.
3. Die Lesezugriffe der Lint-Tests nur an die Formatierung anpassen, nie die Absicht eines Tests abschwächen.
4. Committen: `chore(pbi): files as normalised by Power BI Desktop; screenshots and reconciliation` (mit `docs/screenshots/*.png` und der gefüllten
   Abgleichstabelle), pushen, `gh run watch --exit-status`.
5. Tag setzen: `git tag -a v0.3.0 -m "Meilenstein 3: Semantikmodell und Bericht"` und `git push origin v0.3.0`.
