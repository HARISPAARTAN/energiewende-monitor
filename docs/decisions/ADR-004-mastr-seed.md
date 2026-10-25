# ADR-004: Marktstammdatenregister als aggregierter Seed

Datum: 2026-10-25 · Status: angenommen (überarbeitet mit Meilenstein 2, Exportstand 2026-10-25)

## Entscheidung

Der MaStR-Gesamtdatenexport (ein Zip mit 2,4 GB und 231 UTF-16-XML-Dateien, entpackt 48 GB, davon 33 GB
Einheitentabellen) wird einmal lokal gelesen und zu `data/seed/kapazitaet_monat.csv` verdichtet: Zubau, Abgang
und Anfangsbestand je Monat, Bundesland und Energieträger. Nur dieser Seed (1,1 MB, 25.323 Zeilen) liegt im
Repository; CI und `ewmonitor load` laden ihn, ohne Download und ohne die Einzelanlagen.

## Herunterladen und Lesen

- **open-mastr 1.0 lädt herunter** (optionales Extra `mastr`, Massendownload mit den deutschen Tabellennamen;
  die API-Variante braucht ein Konto und ist für 10 Millionen Einheiten zu langsam).
- **Der Seed liest den Zip selbst** (`mastr.iter_units_xml`, Standard `--source xml`). open-mastr 1.0 schreibt
  den Export zusätzlich in eine SQLite-Datenbank (3,7 GB, 16 Minuten), scheitert dabei aber an allen
  66 Dateien `EinheitenSolar_*.xml` des Exports 2026-10-25: Felder mit mehreren Katalogwerten wie `710 3183`
  passen nicht in die Ganzzahlspalte, die open-mastr anlegt. `EinheitenSolar` bliebe leer, und Photovoltaik ist
  der größte Bestand. Der eigene Leser streamt jede Datei mit lxml `iterparse`, behält nur die zehn benötigten
  Felder und löst die Katalog-IDs über `Katalogwerte.xml` auf (die IDs sind global eindeutig; ein Wert, der keine
  ID ist, bleibt unverändert). Der ganze Export läuft so in rund fünf Minuten bei konstantem Speicher, ohne
  etwas auf die Platte zu entpacken (9.663.557 Einheiten, davon 6.598.819 Solar).
- Der SQLite-Leser (`--source sqlite`) bleibt für Tests und Vergleiche, ist aber keine Rückfallebene für den
  echten Seed: Für den Export 2026-10-25 fehlen in der open-mastr-Datenbank `EinheitenSolar` und
  `EinheitenVerbrennung` ganz (der Import scheitert an allen Solar-Dateien und an der einen
  Verbrennungs-Datei). Beide Leser liefern
  denselben normalisierten Rahmen; ein Unit-Test prüft das auf der synthetischen Fixture (61 Einheiten, als
  SQLite-Tabellen und als Export-Zip).
- `seed-mastr` ohne `--skip-download` ruft weiter open-mastr auf und baut damit auch die SQLite-Datenbank
  (am 2026-10-25 zusammen 28 Minuten: 12 Minuten Download, 16 Minuten Import). Mit vorhandenem Zip genügt
  `--skip-download`; der Exportstand kommt aus dem Dateinamen.

## Regeln

- Es zählen Einheiten mit Status `In Betrieb`, `Vorübergehend stillgelegt` und `Endgültig stillgelegt`;
  `In Planung` ist ausgeschlossen.
- Zubau im Monat des Inbetriebnahmedatums; Abgang im Monat der endgültigen Stilllegung, nur bei Status
  `Endgültig stillgelegt` mit Datum. Eine vorübergehend stillgelegte Einheit bleibt im Bestand.
- **Kalender ab 1990 mit Anfangsbestand.** Einheiten mit Inbetriebnahme vor dem 1990-01-01 oder ohne Datum gehen
  als Anfangsbestand in den ersten Kalendermonat; wer vor 1990 endgültig stillgelegt wurde, entfällt.
- Leistung = Nettonennleistung in kW / 1000, je Zelle nach dem Summieren auf drei Nachkommastellen gerundet.
  Bei Photovoltaik liegt die Nettonennleistung (Wechselrichter, AC) unter der Modulleistung (kWp), die die
  Bundesnetzagentur in ihren Zubauzahlen meldet; der Seed weist deshalb rund 11 % weniger PV-Leistung aus
  (Oktober 2026: 116,6 GW netto, 131,7 GW brutto).
- **Bundesland.** Offshore-Anlagen außerhalb der Zwölfmeilenzone tragen im Export den Wert
  `Ausschließliche Wirtschaftszone` (nie NULL); er wird zum Kürzel `AWZ`. Offshore-Anlagen im Küstenmeer behalten
  ihr Bundesland (Niedersachsen, Schleswig-Holstein, Mecklenburg-Vorpommern) und zählen trotzdem als Wind
  Offshore. Ein fehlendes Bundesland wird bei `WindAnLandOderAufSee = Windenergie auf See` zu `AWZ`, sonst zu
  `Unbekannt` (`UNB`). Im Export 2026-10-25 betrifft das 74 gezählte Einheiten, darunter 30 Pumpspeicher- und
  30 Wasserkraft-Einheiten im Ausland, die an das deutsche Netz angeschlossen sind und deshalb im Register stehen:
  Vianden in Luxemburg, die Illwerke in Vorarlberg, Kühtai und Silz in Tirol, Laufenburg und Rheinfelden an der
  Schweizer Grenze. Sie bleiben als `UNB` im Bestand.
- **Speicher.** Pumpspeicher zählen als `Pumpspeicher`. Batterien, Wasserstoffspeicher, Druckluft- und
  Schwungradspeicher sowie Speicher ohne Technologie werden verworfen: SMARD weist für sie keine Erzeugung aus.
- **Historie vor 2019.** Das Register enthält nur Einheiten, die seit seinem Start 2019 registriert wurden, und
  die damals in Betrieb waren; vorher stillgelegte und gelöschte Einheiten fehlen, ihre Historie lässt sich nicht
  rekonstruieren. Bestand und Zubau vor etwa 2019 zeigen deshalb den heute registrierten Anlagenpark nach
  Inbetriebnahmedatum und sind deutlich unvollständig: Kernenergie steht von 1990 bis Ende 2021 konstant bei
  8,1 GW (2010 rund 20,5 GW am Netz), Wind an Land hat Ende 2010 24,0 GW statt rund 27 GW. Das Monatsraster
  beginnt trotzdem 1990, damit die laufenden Summen den Anfangsbestand enthalten.
- **Bestand** (`bestand_mw`) ist der Wert am Monatsende nach Zubau und Abgang des Monats. Der neueste Monat ist
  angebrochen; wegen des Registrierungsverzugs fällt der Zubau der letzten zwei bis drei Monate zu niedrig aus.
- **Notstrom und Netzreserve** bleiben in Meilenstein 2 im Bestand: 3,0 GW Mineralölprodukte und 0,6 GW Erdgas
  tragen `Notstromaggregat = 1`. Ebenso 7,45 GW Steinkohle mit `NetzreserveZugeordnet = 1`, die nicht am Markt
  erzeugen. Beides entscheidet Meilenstein 3.

## Zuordnung zu den SMARD-Energieträgern

Die Zuordnung steht in `data/seed/mastr_energietraeger_mapping.csv` (erste passende Zeile je Tabelle gewinnt;
nicht zugeordnete Werte werden `Sonstige Konventionelle` und als `unmapped` gezählt). Entscheidungen nach dem
Profil des Exports 2026-10-25 (`docs/mastr-profil.md`):

| MaStR-Tabelle | Feld = Wert | Energieträger | Begründung |
|---|---|---|---|
| Wind | Bundesland = Ausschließliche Wirtschaftszone | Wind Offshore | AWZ liegt immer auf See |
| Wind | WindAnLandOderAufSee = Windenergie auf See / an Land | Wind Offshore / Onshore | Das Feld heißt im Export so; eine Spalte `Lage` gibt es nicht |
| Biomasse | Hauptbrennstoff = Klärgas, Deponiegas | Sonstige Erneuerbare | SMARD zählt Klär- und Deponiegas zu den sonstigen Erneuerbaren |
| Verbrennung | Hauptbrennstoff = Grubengas | Sonstige Erneuerbare | wie Grubengas in der GSGK-Tabelle |
| Verbrennung | Energieträger = Erdgas, Steinkohle, Braunkohle | gleichnamig | eigene SMARD-Reihen |
| Verbrennung | Energieträger = Mineralölprodukte, andere Gase, nicht biogener Abfall, Wärme, Wasserstoff | Sonstige Konventionelle | keine eigene SMARD-Reihe |
| Verbrennung | Energieträger = Speicher | Sonstige Konventionelle | eine falsch erfasste Verbrennungseinheit |
| GSGK | Energieträger = Geothermie, Grubengas, Solarthermie, Druck aus Wasserleitungen | Sonstige Erneuerbare | SMARD führt Geothermie und Grubengas unter den sonstigen Erneuerbaren; Solarthermie und Wasserdruck sind erneuerbar ohne eigene Reihe |
| GSGK | Energieträger = Druck aus Gasleitungen, Klärschlamm | Sonstige Konventionelle | Gasdruck stammt aus fossiler Verdichtung; Klärschlamm wird wie Abfall verbrannt |
| Stromspeicher | Technologie = Pumpspeicher | Pumpspeicher | eigene SMARD-Reihe |
| Stromspeicher | jede andere Technologie, NULL | verworfen | keine Erzeugung bei SMARD |

Solar, Wasser und Kernkraft werden tabellenweise zugeordnet (Photovoltaik, Wasserkraft, Kernenergie).

## Folgen

Reproduzierbar ohne Download, Exportstand und Statistik im Kopf des Seeds, keine Einzelanlagen im Repository.
Ein neuer Export braucht `seed-mastr --skip-download --profile`; neue MaStR-Werte erscheinen im Profil und als
`unmapped` in der Statistik und werden dann in der Mapping-Datei ergänzt. Speicherbedarf lokal: Zip 2,4 GB,
SQLite von open-mastr 3,7 GB; Budget 15 GB.
