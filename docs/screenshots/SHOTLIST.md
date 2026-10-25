# Screenshot-Liste

Aufnahme in der Validierungssitzung mit Power BI Desktop (Schritt 7 der Klickfolge). Die PNG-Dateien liegen in diesem
Ordner und werden von `README.md` und `README.en.md` eingebunden.

## Vorbereitung

- Desktop-Fenster maximiert, Bericht im Berichtsansicht-Modus (linke Leiste, erstes Symbol), Seitenansicht
  "Tatsächliche Größe" oder "An Seite anpassen" so, dass die Seite das Fenster ausfüllt.
- Datenstand: nach `ewmonitor load` mit den echten Daten (nicht `--fixtures`), alle Filter zurückgesetzt.
- Aufnahme mit Win+Shift+S, Fenster-Ausschnitt; Breite **1280 px** (Seitenbreite des Berichts), Höhe 720 px für die Seiten.
- Format PNG, keine Bearbeitung außer dem Zuschneiden auf 1280 px Breite; keine Zugangsdaten, keine Benutzernamen im Bild.

## Aufnahmen

| Datei | Inhalt | Zustand |
|---|---|---|
| `01-ueberblick.png` | Seite Überblick | Jahr 2025, kein Monat, Kategorie leer, Kennzahl-Auswahl "Erzeugung (MWh)" |
| `02-erzeugung-last.png` | Seite Erzeugung & Last | Datumsfilter auf einen Monat mit Daten (zum Beispiel Oktober 2025) |
| `03-preise.png` | Seite Preise | Jahr 2025; Histogramm, negative Stunden je Monat, Streudiagramm und Top-10-Preisphasen sichtbar |
| `04-ausbau.png` | Seite Ausbau | Alle Energieträger, Jahr 2025 |
| `05-datenqualitaet.png` | Seite Datenqualität & Quellen | ohne Filter; Datenstand SMARD und MaStR, Quellen und Lizenzen sichtbar |
| `06-modell.png` | Modellansicht (dritte Leiste) | Sternschema mit Fakten- und Dimensionstabellen, Beziehungen sichtbar, Tabellen so angeordnet, dass keine Linien durch Tabellen laufen |
| `07-kennzahl-auswahl.png` | Überblick mit dem Feldparameter-Slicer in Aktion | Kennzahl-Auswahl auf "Day-Ahead Ø (€/MWh)"; das Liniendiagramm unten rechts zeigt die Preise |

## Nachbereitung

- Dateinamen exakt wie in der Tabelle, Kleinbuchstaben, ohne Leerzeichen.
- Die Bilder zeigen den Stand nach der ersten Aktualisierung; wenn sich Zahlen ändern, werden sie neu aufgenommen.
- Reihenfolge der README: 01 bis 05 unter "Bericht", 06 und 07 darunter bei "Modell".
