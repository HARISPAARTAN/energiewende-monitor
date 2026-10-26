# Kennzahlen-Glossar

Die 35 Kennzahlen des Power-BI-Modells (Tabelle `Kennzahlen`), mit der DAX-Formel wie im TMDL
(`powerbi/EnergiewendeMonitor.SemanticModel/definition/tables/Kennzahlen.tmdl`). Die Formeln hier und im Modell
sind identisch; `tests/pbi/test_glossary.py` prüft das. Jede Kennzahl hat im Modell zusätzlich eine englische
Beschreibung. Der Abgleich mit dem Data Warehouse steht am Ende; die berechnete Spalte `Gruppe` hat einen eigenen Abschnitt.

Zeitstempel in SMARD-Daten sind UTC; Datum und Uhrzeit des Modells (`Datum`, `Zeit`) sind Ortszeit (Europe/Berlin).

## Kapazitäten und Grenzen

Gilt für Zubau, Installierte Leistung und Volllaststunden.

**Monatsendbestand.** `'Kapazität'[Bestand MW]` ist der Bestand am Monatsende (Anfangsbestand plus Zubau minus Abgang des Monats)
je Bundesland und Energieträger, mit lückenlosem Monatsraster ab Januar 1990. Summiert über Bundesländer ergibt das den
bundesweiten Bestand eines Monats; Summen über mehrere Monate wären sinnlos und kommen nicht vor.

**Letzter Monat mit Daten (LASTNONBLANK-Logik).** Installierte Leistung nimmt nicht den Bestand "des Zeitraums", sondern den des
letzten Monats mit Kapazitätszeilen, der am oder vor dem Ende des gewählten Datums liegt. Das Ende ist `MAX(Datum[Datum])` im
Kontext, die Auswahl `MAX('Kapazität'[Datum Key])` über alle Datumszeilen bis dahin (`REMOVEFILTERS(Datum)` plus Datumsvergleich).
Beispiele: Jahr 2024 ergibt den Bestand Dezember 2024; ein Jahr nach dem neuesten Monat oder ein Zeitraum ohne Filter ergibt den
neuesten Monat. Das entspricht der Logik von LASTNONBLANK und liefert auch dann einen Wert, wenn der Zeitraum
selbst keine Kapazitätszeile enthält (zum Beispiel ein einzelner Tag).

**Durchschnittsbestand bei den Volllaststunden.** Der Nenner ist der Durchschnitt der Monatsendbestände der Monate vom Monat des
ersten Erzeugungstags bis zum letzten Erzeugungstag im Kontext (`AVERAGEX` über die Monatsschlüssel). Würde der Endbestand
verwendet, sähen Energieträger mit starkem Zubau im Jahr (Photovoltaik) zu niedrige Volllaststunden aus, weil Anlagen
mitgezählt würden, die nur wenige Wochen liefen. Mit dem Durchschnitt stehen Erzeugung und Leistung zeitlich besser im Verhältnis.

**Netzreserve und Notstromaggregate sind im Bestand.** Im Marktstammdatenregister tragen 7,45 GW Steinkohle das Kennzeichen
`NetzreserveZugeordnet = 1`, 3,0 GW Mineralölprodukte und 0,6 GW Erdgas das Kennzeichen `Notstromaggregat = 1`. Diese Einheiten bleiben
in `Bestand MW` (Entscheidung in Meilenstein 3, kein weiterer Seed). Sie blähen die Kapazitätsbasis auf und drücken damit die
Volllaststunden dieser Energieträger (Steinkohle, Erdgas und Sonstige Konventionelle, wohin Mineralölprodukte fallen), weil sie praktisch keinen Strom am Markt erzeugen.
Volllaststunden von Wind und Photovoltaik sind davon nicht betroffen.

**Historie vor 2019 (Survivorship).** Das Register enthält nur Einheiten, die seit 2019 registriert wurden oder damals schon in
Betrieb waren; früher stillgelegte oder gelöschte Anlagen fehlen. Bestand und Zubau vor etwa 2019 zeigen darum den heute
registrierten Anlagenpark nach Inbetriebnahmedatum, nicht den damaligen Bestand (Kernenergie steht von 1990 bis Ende 2021
konstant bei 8,1 GW). Die Seite Datenqualität & Quellen nennt die Einschränkung.

**Der neueste Monat ist angebrochen.** Der Exportstand liegt mitten in einem Monat; Zubau und Abgang dieses Monats sind
unvollständig, und der Zubau der letzten zwei bis drei Monate fällt zu niedrig aus (verspätete Registrierung).

**Photovoltaik.** Die Nettonennleistung (Wechselrichter) liegt rund 11 % unter der Bruttoleistung der Module, die die
Bundesnetzagentur in ihren Zubauzahlen meldet.

## Anzeigetexte (KPI-Kennzahlen)

Gilt für `KPI Erzeugung`, `KPI EE-Anteil`, `KPI Day-Ahead Ø`, `KPI Negative Preisstunden` und `KPI Installierte Leistung` (die fünf Kennzahlenkacheln der Seite Überblick) und sinngemäß für `Datenstand Kopfzeile`.

**Warum Text.** Visuals formatieren Zahlen nach der Spracheinstellung des Betrachters, nicht nach der Kultur des Modells (de-DE). Auf dem Desktop des Besitzers stand auf einer Seite `92.87 €` neben `1.791`. Die KPI-Kennzahlen rufen deshalb `FORMAT` mit ausdrücklichem Gebietsschema `"de-DE"` auf und hängen die Einheit an; der Bericht zeigt so für jeden Betrachter deutsche Zahlen (zum Beispiel `439,3 TWh`, `89,32 €/MWh`, `303,7 GW`).

**Nur zur Anzeige.** Das Ergebnis ist Text und lässt sich nicht summieren, sortieren oder weiterverwenden. Keine Kennzahl greift auf diese Kennzahlen zu (ein Test prüft das). Tabellen und Achsen behalten die Zahlenkennzahlen und folgen weiter der Spracheinstellung des Betrachters.

## Energieträger-Gruppen (Spalte Gruppe)

Die berechnete Spalte `'Energieträger'[Gruppe]` faltet die zwölf Energieträger in acht Gruppen. Die drei Diagramme nach Energieträger (Überblick: Erzeugung je Monat; Erzeugung & Last: Erzeugung nach Energieträger; Ausbau: Zubau) färben und stapeln nach `Gruppe`, in der Reihenfolge der Tabelle (ausgeblendete Spalte `Gruppe Sortierung`):

| Reihenfolge | Gruppe | Energieträger |
|---|---|---|
| 1 | Biomasse | Biomasse |
| 2 | Wind | Wind Onshore, Wind Offshore |
| 3 | Photovoltaik | Photovoltaik |
| 4 | Wasserkraft | Wasserkraft |
| 5 | Erdgas | Erdgas |
| 6 | Steinkohle | Steinkohle |
| 7 | Braunkohle | Braunkohle |
| 8 | Sonstige | Kernenergie, Pumpspeicher, Sonstige Erneuerbare, Sonstige Konventionelle |

**Warum.** Ein Diagramm hält höchstens acht Farben auseinander; zwölf Energieträger wären nicht mehr zu unterscheiden. Sieben Farbgruppen und ein neutrales Grau (`Sonstige`) bleiben lesbar. In `Sonstige` stehen vier Energieträger: Kernenergie, Pumpspeicher, Sonstige Erneuerbare und Sonstige Konventionelle. Der Einzelwert je Energieträger bleibt in den Tabellen und Slicern (Slicer Energieträger und Tabelle Volllaststunden auf der Seite Ausbau); die Spalte `'Energieträger'[Energieträger]` ändert sich nicht.

**Formeln**

```dax
Gruppe =
SWITCH('Energieträger'[Energieträger], "Biomasse", "Biomasse", "Wind Onshore", "Wind", "Wind Offshore", "Wind", "Photovoltaik", "Photovoltaik", "Wasserkraft", "Wasserkraft", "Erdgas", "Erdgas", "Steinkohle", "Steinkohle", "Braunkohle", "Braunkohle", "Sonstige")

Gruppe Sortierung =
SWITCH('Energieträger'[Gruppe], "Biomasse", 1, "Wind", 2, "Photovoltaik", 3, "Wasserkraft", 4, "Erdgas", 5, "Steinkohle", 6, "Braunkohle", 7, 8)
```

## Erzeugung (MWh)

- **Definition:** Summe der Nettostromerzeugung im Filterkontext. SMARD liefert Viertelstundenwerte; die Summe über den gewählten Zeitraum, Energieträger und Region ergibt die Energie.
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`, Marktgebiet DE-LU
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Leere Viertelstunden (NULL) zählen nicht mit. Kernenergie endet in den Quelldaten am 2024-02-04.
  - Pumpspeicher-Verbrauch ist keine Erzeugung und steht nur in der Last.

**Formel**

```dax
Erzeugung (MWh) =
SUM(Erzeugung[Erzeugung MWh])
```

## Erzeugung Erneuerbar (MWh)

- **Definition:** Erzeugung der Energieträger mit der Kategorie Erneuerbar (Photovoltaik, Wind Onshore, Wind Offshore, Biomasse, Wasserkraft, sonstige Erneuerbare).
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`, Dimension `'Energieträger'[Kategorie]`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Pumpspeicher gehört in der Dimension `Energieträger` zur Kategorie Konventionell.
  - Ein äußerer Filter auf `'Energieträger'[Kategorie]` (Slicer Kategorie, Lesezeichen) bleibt wirksam (`KEEPFILTERS`): Bei Auswahl Konventionell ist die Kennzahl leer, der EE-Anteil 0 %.

**Formel**

```dax
Erzeugung Erneuerbar (MWh) =
CALCULATE([Erzeugung (MWh)], KEEPFILTERS('Energieträger'[Kategorie] = "Erneuerbar"))
```

## EE-Anteil %

- **Definition:** Anteil der erneuerbaren Erzeugung an der gesamten Nettoerzeugung. Bezugsgröße ist die Erzeugung, nicht der Verbrauch.
- **Einheit:** Anteil (angezeigt in %)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `0.0 %`
- **Hinweise:**
  - Weicht vom amtlichen Anteil am Bruttostromverbrauch ab: anderer Nenner, nur Marktgebiet DE-LU, keine Eigenversorgung außerhalb der Netze.
  - Im Kontext ohne Erzeugung: leer (DIVIDE).
  - Bei Auswahl Konventionell im Slicer Kategorie ist der Anteil 0 %, bei Erneuerbar 100 %; er übersteigt nie 100 %.

**Formel**

```dax
EE-Anteil % =
DIVIDE([Erzeugung Erneuerbar (MWh)], [Erzeugung (MWh)])
```

## Netzlast (MWh)

- **Definition:** Summe der Netzlast (SMARD-Reihe Gesamt (Netzlast): die aus dem Netz entnommene Energie). Der Pumpspeicher-Verbrauch ist eine eigene Reihe und nicht Teil dieser Kennzahl.
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Viertelstundenwerte; auf der Seite Erzeugung & Last je Tag oder je Uhrzeit summiert.

**Formel**

```dax
Netzlast (MWh) =
SUM(Last[Netzlast MWh])
```

## Residuallast (MWh)

- **Definition:** Netzlast abzüglich der Erzeugung aus Wind und Photovoltaik; der Teil der Last, den steuerbare Kraftwerke, Speicher und Importe decken müssen.
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Kann je Viertelstunde negativ werden, wenn Wind und Sonne die Last übersteigen.

**Formel**

```dax
Residuallast (MWh) =
SUM(Last[Residuallast MWh])
```

## Residuallast Minimum (MWh/15 min)

- **Definition:** Kleinster Viertelstundenwert der Residuallast im Filterkontext.
- **Einheit:** MWh je 15 min
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `#,0.0`
- **Hinweise:**
  - Die Einheit ist Energie je Viertelstunde, nicht Leistung; mal 4 ergibt MW.

**Formel**

```dax
Residuallast Minimum (MWh/15 min) =
MIN(Last[Residuallast MWh])
```

## Residuallast Ø (MWh/15 min)

- **Definition:** Mittelwert der Viertelstundenwerte der Residuallast im Filterkontext (Basis der Heatmap Tageszeit mal Wochentag).
- **Einheit:** MWh je 15 min
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `#,0.0`
- **Hinweise:**
  - Mittel über die vorhandenen Viertelstunden, nicht über Kalenderstunden.

**Formel**

```dax
Residuallast Ø (MWh/15 min) =
AVERAGE(Last[Residuallast MWh])
```

## Day-Ahead Ø (€/MWh)

- **Definition:** Arithmetisches Mittel der stündlichen Day-Ahead-Preise im Filterkontext.
- **Einheit:** EUR/MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`, Gebotszone DE-LU
- **Formatierung im Modell:** `#,0.00 "€"`
- **Hinweise:**
  - Nicht mengengewichtet: jede Stunde zählt gleich, unabhängig von Erzeugung oder Last.

**Formel**

```dax
Day-Ahead Ø (€/MWh) =
AVERAGE(Preis[Day-Ahead €/MWh])
```

## Day-Ahead Max (€/MWh)

- **Definition:** Höchster stündlicher Day-Ahead-Preis im Filterkontext.
- **Einheit:** EUR/MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `#,0.00 "€"`

**Formel**

```dax
Day-Ahead Max (€/MWh) =
MAX(Preis[Day-Ahead €/MWh])
```

## Day-Ahead Min (€/MWh)

- **Definition:** Niedrigster stündlicher Day-Ahead-Preis im Filterkontext.
- **Einheit:** EUR/MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `#,0.00 "€"`

**Formel**

```dax
Day-Ahead Min (€/MWh) =
MIN(Preis[Day-Ahead €/MWh])
```

## Negative Preisstunden

- **Definition:** Anzahl der Stunden mit negativem Day-Ahead-Preis (kleiner als 0).
- **Einheit:** Stunden
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Ein Preis von genau 0 zählt nicht.
  - Ein Tag hat 24 Preisstunden, am Tag der Zeitumstellung 23 oder 25.

**Formel**

```dax
Negative Preisstunden =
CALCULATE(COUNTROWS(Preis), Preis[Day-Ahead €/MWh] < 0)
```

## Preisstunden

- **Definition:** Anzahl der Stundenpreiszeilen im Filterkontext; Basis des Histogramms der Preisklassen.
- **Einheit:** Stunden
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Die Preisklasse ist `Preis[Preis Klasse (10 €)]`: der Preis wird mit INT auf ein Vielfaches von 10 abgerundet (-5,3 liegt in der Klasse -10, 7,9 in 0). Zeilen ohne Preis haben keine Klasse.

**Formel**

```dax
Preisstunden =
COUNTROWS(Preis)
```

## Erzeugung Vorjahr (MWh)

- **Definition:** Erzeugung im gleichen Zeitraum ein Jahr früher (SAMEPERIODLASTYEAR auf `Datum[Datum]`).
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Für 2023 gibt es kein Vorjahr: leer.
  - Wird ein angebrochenes Jahr als Ganzes gewählt, steht dem Teiljahr das volle Vorjahr gegenüber, weil der Kalender bis 2030 reicht. Für faire Vergleiche Monate wählen.

**Formel**

```dax
Erzeugung Vorjahr (MWh) =
CALCULATE([Erzeugung (MWh)], SAMEPERIODLASTYEAR(Datum[Datum]))
```

## Erzeugung Δ Vorjahr %

- **Definition:** Relative Veränderung der Erzeugung gegenüber dem gleichen Zeitraum des Vorjahres.
- **Einheit:** Prozent (vorzeichenbehaftet)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `+0.0 %;-0.0 %;0.0 %`
- **Hinweise:**
  - Leer, wenn das Vorjahr leer oder 0 ist.

**Formel**

```dax
Erzeugung Δ Vorjahr % =
DIVIDE([Erzeugung (MWh)] - [Erzeugung Vorjahr (MWh)], [Erzeugung Vorjahr (MWh)])
```

## EE-Anteil Vorjahr %

- **Definition:** Erneuerbarer Anteil an der Erzeugung im gleichen Zeitraum ein Jahr früher.
- **Einheit:** Anteil (angezeigt in %)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `0.0 %`
- **Hinweise:**
  - Für 2023 leer.

**Formel**

```dax
EE-Anteil Vorjahr % =
CALCULATE([EE-Anteil %], SAMEPERIODLASTYEAR(Datum[Datum]))
```

## EE-Anteil Δ Vorjahr (pp)

- **Definition:** Veränderung des erneuerbaren Anteils gegenüber dem Vorjahr in Prozentpunkten.
- **Einheit:** Prozentpunkte (vorzeichenbehaftet)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `+0.0 "pp";-0.0 "pp";0.0 "pp"`
- **Hinweise:**
  - Leer (BLANK), wenn der Vorjahresanteil leer ist, damit 2023 keinen künstlichen Anstieg von 0 zeigt.

**Formel**

```dax
EE-Anteil Δ Vorjahr (pp) =
IF(ISBLANK([EE-Anteil Vorjahr %]), BLANK(), ([EE-Anteil %] - [EE-Anteil Vorjahr %]) * 100)
```

## Netzlast Vormonat (MWh)

- **Definition:** Netzlast im gleichen Zeitraum einen Monat früher (DATEADD um -1 Monat).
- **Einheit:** MWh
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Beim ersten Monat der Daten (2023-01) leer.

**Formel**

```dax
Netzlast Vormonat (MWh) =
CALCULATE([Netzlast (MWh)], DATEADD(Datum[Datum], -1, MONTH))
```

## Netzlast Δ Vormonat %

- **Definition:** Relative Veränderung der Netzlast gegenüber dem Vormonat.
- **Einheit:** Prozent (vorzeichenbehaftet)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_last`
- **Formatierung im Modell:** `+0.0 %;-0.0 %;0.0 %`
- **Hinweise:**
  - Monate haben unterschiedlich viele Tage; der Wert ist nicht kalenderbereinigt.

**Formel**

```dax
Netzlast Δ Vormonat % =
DIVIDE([Netzlast (MWh)] - [Netzlast Vormonat (MWh)], [Netzlast Vormonat (MWh)])
```

## Zubau (MW)

- **Definition:** Summe der im Zeitraum in Betrieb genommenen Nettonennleistung (Marktstammdatenregister), je Monat, Bundesland und Energieträger.
- **Einheit:** MW
- **Quelle:** Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Der Zubau gehört zum Monat der Inbetriebnahme und liegt im Modell am Monatsersten; ein Tagesfilter zeigt ihn nur am 1.
  - Der Zubau der letzten zwei bis drei Monate ist zu niedrig, weil Anlagen oft erst Wochen nach der Inbetriebnahme registriert werden; der neueste Monat ist außerdem angebrochen.
  - Vor etwa 2019 unvollständig (siehe Abschnitt Kapazitäten und Grenzen).

**Formel**

```dax
Zubau (MW) =
SUM('Kapazität'[Zubau MW])
```

## Zubau YTD (MW)

- **Definition:** Zubau vom 1. Januar bis zum letzten Datum im Filterkontext (TOTALYTD).
- **Einheit:** MW
- **Quelle:** Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Gleiche Einschränkungen wie Zubau (MW).

**Formel**

```dax
Zubau YTD (MW) =
TOTALYTD([Zubau (MW)], Datum[Datum])
```

## Installierte Leistung (MW)

- **Definition:** Bestand der Nettonennleistung am Ende des letzten Monats mit Kapazitätsdaten, der am oder vor dem Ende des gewählten Zeitraums liegt. Der Monatsendbestand ist Anfangsbestand plus Zubau minus Abgang.
- **Einheit:** MW
- **Quelle:** Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Siehe Abschnitt Kapazitäten und Grenzen: Monatsendbestand, Auswahl des letzten Monats, Netzreserve, Notstromaggregate, Historie vor 2019.

**Formel**

```dax
Installierte Leistung (MW) =
VAR EndeDatum = MAX(Datum[Datum])
VAR LetzterMonat = CALCULATE(MAX('Kapazität'[Datum Key]), REMOVEFILTERS(Datum), Datum[Datum] <= EndeDatum)
RETURN CALCULATE(SUM('Kapazität'[Bestand MW]), REMOVEFILTERS(Datum), 'Kapazität'[Datum Key] = LetzterMonat)
```

## Volllaststunden (h)

- **Definition:** Erzeugung des Zeitraums geteilt durch den durchschnittlichen Monatsendbestand der installierten Leistung. Betrachtet werden die Monate vom Monat des ersten bis zum letzten Erzeugungstag im Kontext; Monate ohne Kapazitätszeile zählen nicht.
- **Einheit:** Stunden (h)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung` und Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Die Basis ist der Durchschnitt der Monatsendbestände, nicht der Endbestand: Bei starkem Zubau im Jahr vermeidet das zu niedrige Volllaststunden.
  - Ein unvollständiges Jahr wird nicht hochgerechnet: Erzeugung bis heute durch den Durchschnittsbestand bis heute.
  - Netzreserve und Notstromaggregate stehen in der Kapazitätsbasis (siehe unten) und drücken die Volllaststunden dieser Energieträger.
  - Nur bundesweit definiert: Die Erzeugung hat keine Beziehung zu `Bundesland`. Unter einer Bundesland-Auswahl (Balkendiagramm als Filter) oder der RLS-Rolle `Landesbehörde BW` ist die Kennzahl deshalb leer (Prüfung: gefiltert oder weniger als 18 sichtbare Zeilen, 16 Länder plus AWZ und Unbekannt), damit keine unmöglichen Werte über 8.760 Stunden entstehen.

**Formel**

```dax
Volllaststunden (h) =
IF(
ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18,
BLANK(),
VAR ErzStart = CALCULATE(MIN(Erzeugung[Datum Key]))
VAR ErzEnde = CALCULATE(MAX(Erzeugung[Datum Key]))
VAR MonatStart = INT(ErzStart / 100) * 100 + 1
VAR MonateMitBestand = CALCULATETABLE(VALUES('Kapazität'[Datum Key]), REMOVEFILTERS(Datum), 'Kapazität'[Datum Key] >= MonatStart && 'Kapazität'[Datum Key] <= ErzEnde)
VAR MittlererBestand = CALCULATE(AVERAGEX(MonateMitBestand, CALCULATE(SUM('Kapazität'[Bestand MW]))), REMOVEFILTERS(Datum))
RETURN DIVIDE([Erzeugung (MWh)], MittlererBestand)
)
```

## Anzahl Einheiten Zubau

- **Definition:** Anzahl der im Zeitraum in Betrieb genommenen Einheiten (Marktstammdatenregister).
- **Einheit:** Einheiten
- **Quelle:** Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Gleiche Einschränkungen wie Zubau (MW).

**Formel**

```dax
Anzahl Einheiten Zubau =
SUM('Kapazität'[Anzahl Zubau])
```

## Datenstand

- **Definition:** Neuester geladener SMARD-Zeitstempel in UTC, unabhängig von Filtern.
- **Einheit:** Text (dd.MM.yyyy HH:mm UTC)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `Text`

**Formel**

```dax
Datenstand =
FORMAT(CALCULATE(MAX(Erzeugung[Zeitstempel UTC]), REMOVEFILTERS()), "dd.MM.yyyy HH:mm") & " UTC"
```

## Zeilen

- **Definition:** Summe der Zeilen der vier Faktentabellen (Erzeugung, Last, Preis, 'Kapazität') im Filterkontext.
- **Einheit:** Zeilen
- **Quelle:** Alle vier Faktenansichten
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Ohne Filter gleich der Summe der Zeilen von `dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` und `dw.fact_kapazitaet`.

**Formel**

```dax
Zeilen =
COUNTROWS(Erzeugung) + COUNTROWS(Last) + COUNTROWS(Preis) + COUNTROWS('Kapazität')
```

## Datenstand MaStR

- **Definition:** Neuester Monat mit Kapazitätsdaten, unabhängig von Filtern, als JJJJ-MM-01.
- **Einheit:** Text (JJJJ-MM-TT)
- **Quelle:** Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `Text`
- **Hinweise:**
  - Der Monat ist angebrochen; der Exportstand steht im Dateinamen des Seeds und in der README.

**Formel**

```dax
Datenstand MaStR =
FORMAT(CALCULATE(MAX('Kapazität'[Datum Key]), REMOVEFILTERS()), "0000-00-00")
```

## KPI Erzeugung

- **Definition:** Anzeigetext für `Erzeugung (MWh)`: die Erzeugung in TWh mit einer Nachkommastelle und der Einheit, im Gebietsschema de-DE formatiert (Tausenderpunkt, Dezimalkomma).
- **Einheit:** Text (TWh)
- **Quelle:** wie `Erzeugung (MWh)`: SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `Text` (das Zahlenformat steht in der Formel)
- **Hinweise:**
  - Nur zur Anzeige (Abschnitt Anzeigetexte): Text im Gebietsschema de-DE statt in der Sprache des Betrachters; keine Berechnung verwendet diese Kennzahl.
  - Leer, wenn `Erzeugung (MWh)` leer ist.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): Jahr 2025 `439,3 TWh`, ohne Datumsfilter `1.707,1 TWh`.

**Formel**

```dax
KPI Erzeugung =
VAR Wert = DIVIDE([Erzeugung (MWh)], 1000000)
RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "#,0.0", "de-DE") & " TWh")
```

## KPI EE-Anteil

- **Definition:** Anzeigetext für `EE-Anteil %`: der Anteil mit einer Nachkommastelle und Prozentzeichen, im Gebietsschema de-DE formatiert (Dezimalkomma).
- **Einheit:** Text (%)
- **Quelle:** wie `EE-Anteil %`: SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`
- **Formatierung im Modell:** `Text` (das Zahlenformat steht in der Formel)
- **Hinweise:**
  - Nur zur Anzeige (Abschnitt Anzeigetexte): Text im Gebietsschema de-DE statt in der Sprache des Betrachters; keine Berechnung verwendet diese Kennzahl.
  - Leer, wenn `EE-Anteil %` leer ist (Kontext ohne Erzeugung).
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): Jahr 2025 `58,9 %`, ohne Datumsfilter `58,5 %`.

**Formel**

```dax
KPI EE-Anteil =
VAR Wert = [EE-Anteil %]
RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "0.0 %", "de-DE"))
```

## KPI Day-Ahead Ø

- **Definition:** Anzeigetext für `Day-Ahead Ø (€/MWh)`: der mittlere Stundenpreis mit zwei Nachkommastellen und der Einheit €/MWh, im Gebietsschema de-DE formatiert.
- **Einheit:** Text (€/MWh)
- **Quelle:** wie `Day-Ahead Ø (€/MWh)`: SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `Text` (das Zahlenformat steht in der Formel)
- **Hinweise:**
  - Nur zur Anzeige (Abschnitt Anzeigetexte): Text im Gebietsschema de-DE statt in der Sprache des Betrachters; keine Berechnung verwendet diese Kennzahl.
  - Leer, wenn `Day-Ahead Ø (€/MWh)` leer ist.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): Jahr 2025 `89,32 €/MWh`, ohne Datumsfilter `92,87 €/MWh`.

**Formel**

```dax
KPI Day-Ahead Ø =
VAR Wert = [Day-Ahead Ø (€/MWh)]
RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "#,0.00", "de-DE") & " €/MWh")
```

## KPI Negative Preisstunden

- **Definition:** Anzeigetext für `Negative Preisstunden`: die Anzahl der Stunden mit negativem Day-Ahead-Preis mit Tausenderpunkt und der Einheit h, im Gebietsschema de-DE formatiert.
- **Einheit:** Text (h)
- **Quelle:** wie `Negative Preisstunden`: SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_preis`
- **Formatierung im Modell:** `Text` (das Zahlenformat steht in der Formel)
- **Hinweise:**
  - Nur zur Anzeige (Abschnitt Anzeigetexte): Text im Gebietsschema de-DE statt in der Sprache des Betrachters; keine Berechnung verwendet diese Kennzahl.
  - Leer, wenn `Negative Preisstunden` leer ist.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): Jahr 2025 `573 h`, ohne Datumsfilter `1.791 h`.

**Formel**

```dax
KPI Negative Preisstunden =
VAR Wert = [Negative Preisstunden]
RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "#,0", "de-DE") & " h")
```

## KPI Installierte Leistung

- **Definition:** Anzeigetext für `Installierte Leistung (MW)`: der Bestand in GW (MW geteilt durch 1000) mit einer Nachkommastelle und der Einheit, im Gebietsschema de-DE formatiert.
- **Einheit:** Text (GW)
- **Quelle:** wie `Installierte Leistung (MW)`: Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `Text` (das Zahlenformat steht in der Formel)
- **Hinweise:**
  - Nur zur Anzeige (Abschnitt Anzeigetexte): Text im Gebietsschema de-DE statt in der Sprache des Betrachters; keine Berechnung verwendet diese Kennzahl.
  - Gleiche Einschränkungen wie `Installierte Leistung (MW)` (Abschnitt Kapazitäten und Grenzen).
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): ohne Datumsfilter `303,7 GW` (R5: 303.715 MW), Jahr 2025 `287,3 GW`.

**Formel**

```dax
KPI Installierte Leistung =
VAR Wert = DIVIDE([Installierte Leistung (MW)], 1000)
RETURN IF(ISBLANK(Wert), BLANK(), FORMAT(Wert, "#,0.0", "de-DE") & " GW")
```

## Zielerreichung Photovoltaik %

- **Definition:** Installierte Leistung (MW) der Photovoltaik am Ende des gewählten Zeitraums (letzter Monat mit Kapazitätsdaten am oder vor dem Periodenende) geteilt durch den gesetzlichen Wert für 2030 von 215 GW (215.000 MW). Die Zahl speist das Messinstrument auf der Seite Überblick.
- **Einheit:** Anteil (angezeigt in %)
- **Quelle:** Gesetzlicher Wert: § 4 Nr. 3 Buchst. d EEG 2023 (Solarenergie, 215 GW im Jahr 2030). Gesetzestext am 2026-10-26 auf gesetze-im-internet.de gelesen. Kapazität: Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `0 %`
- **Hinweise:**
  - Bezugswert ist das Ausbauziel für 2030. Der Anteil setzt den Bestand am Ende des gewählten Zeitraums ins Verhältnis zum Wert für 2030, nicht zum jährlichen Ausbaupfad des EEG: § 4 EEG 2023 nennt auch Werte für 2024, 2026 und 2028, die hier nicht verwendet werden.
  - Die Kapazität ist die im Marktstammdatenregister registrierte Nettonennleistung wie modelliert: Monatsendbestand mit Netzreserve und Notstromaggregaten, Historie vor 2019 unvollständig, angebrochener letzter Monat (Abschnitt Kapazitäten und Grenzen). Bei Photovoltaik liegt die Nettonennleistung rund 11 % unter der Bruttoleistung der Module.
  - Die amtliche Zielüberwachung der Bundesnetzagentur kann abweichen; dieser Anteil ist keine amtliche Zielerreichung.
  - Nur bundesweit: leer unter einer Bundesland-Auswahl und unter der RLS-Rolle `Landesbehörde BW`, weil das Ziel bundesweit gilt (dieselbe Prüfung wie bei `Volllaststunden (h)`: gefiltert oder weniger als 18 sichtbare Zeilen).
  - Ignoriert Filter auf Energieträger, Gruppe und Kategorie (REMOVEFILTERS auf die Tabelle Energieträger, Energieträger `Photovoltaik`); der Zeitraum wirkt wie bei `Installierte Leistung (MW)`. Der Anteil ist nicht auf 100 % begrenzt.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): ohne Datumsfilter 54 %, Jahr 2025 49 %, mit Bundesland Bayern leer; ein Filter auf Energieträger, Gruppe oder Kategorie ändert den Wert nicht.

**Formel**

```dax
Zielerreichung Photovoltaik % =
IF(
ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18,
BLANK(),
DIVIDE(CALCULATE([Installierte Leistung (MW)], REMOVEFILTERS('Energieträger'), 'Energieträger'[Energieträger] = "Photovoltaik"), 215000)
)
```

## Zielerreichung Wind an Land %

- **Definition:** Installierte Leistung (MW) der Windenergie an Land (Energieträger `Wind Onshore`) am Ende des gewählten Zeitraums geteilt durch den gesetzlichen Wert für 2030 von 115 GW (115.000 MW). Die Zahl speist das Messinstrument auf der Seite Überblick.
- **Einheit:** Anteil (angezeigt in %)
- **Quelle:** Gesetzlicher Wert: § 4 Nr. 1 Buchst. d EEG 2023 (Windenergie an Land, 115 GW im Jahr 2030). Gesetzestext am 2026-10-26 auf gesetze-im-internet.de gelesen. Kapazität: Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `0 %`
- **Hinweise:**
  - Bezugswert ist das Ausbauziel für 2030. Der Anteil setzt den Bestand am Ende des gewählten Zeitraums ins Verhältnis zum Wert für 2030, nicht zum jährlichen Ausbaupfad des EEG: § 4 EEG 2023 nennt auch Werte für 2024, 2026 und 2028, die hier nicht verwendet werden.
  - Die Kapazität ist die im Marktstammdatenregister registrierte Nettonennleistung wie modelliert: Monatsendbestand mit Netzreserve und Notstromaggregaten, Historie vor 2019 unvollständig, angebrochener letzter Monat (Abschnitt Kapazitäten und Grenzen).
  - Die amtliche Zielüberwachung der Bundesnetzagentur kann abweichen; dieser Anteil ist keine amtliche Zielerreichung.
  - Nur bundesweit: leer unter einer Bundesland-Auswahl und unter der RLS-Rolle `Landesbehörde BW`, weil das Ziel bundesweit gilt (dieselbe Prüfung wie bei `Volllaststunden (h)`: gefiltert oder weniger als 18 sichtbare Zeilen).
  - Ignoriert Filter auf Energieträger, Gruppe und Kategorie (REMOVEFILTERS auf die Tabelle Energieträger, Energieträger `Wind Onshore`); der Zeitraum wirkt wie bei `Installierte Leistung (MW)`. Der Anteil ist nicht auf 100 % begrenzt.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): ohne Datumsfilter 62 %.

**Formel**

```dax
Zielerreichung Wind an Land % =
IF(
ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18,
BLANK(),
DIVIDE(CALCULATE([Installierte Leistung (MW)], REMOVEFILTERS('Energieträger'), 'Energieträger'[Energieträger] = "Wind Onshore"), 115000)
)
```

## Zielerreichung Wind auf See %

- **Definition:** Installierte Leistung (MW) der Windenergie auf See (Energieträger `Wind Offshore`) am Ende des gewählten Zeitraums geteilt durch den gesetzlichen Mindestwert für 2030 von 30 GW (30.000 MW). Die Zahl speist das Messinstrument auf der Seite Überblick.
- **Einheit:** Anteil (angezeigt in %)
- **Quelle:** Gesetzlicher Wert: § 1 Abs. 2 WindSeeG (installierte Leistung von Windenergieanlagen auf See, die an das Netz angeschlossen werden: mindestens 30 GW bis 2030). Gesetzestext am 2026-10-26 auf gesetze-im-internet.de gelesen. Kapazität: Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `0 %`
- **Hinweise:**
  - Bezugswert ist das Mindestziel für 2030, kein jährlicher Pfad: Das WindSeeG nennt zusätzlich mindestens 40 GW bis 2035 und 70 GW bis 2045 (hier nicht verwendet). Das Gesetz zählt netzangeschlossene Anlagen, das Modell die im Register geführte Leistung.
  - Die Kapazität ist die im Marktstammdatenregister registrierte Nettonennleistung wie modelliert: Monatsendbestand mit Netzreserve und Notstromaggregaten, Historie vor 2019 unvollständig, angebrochener letzter Monat (Abschnitt Kapazitäten und Grenzen).
  - Die amtliche Zielüberwachung der Bundesnetzagentur kann abweichen; dieser Anteil ist keine amtliche Zielerreichung.
  - Nur bundesweit: leer unter einer Bundesland-Auswahl und unter der RLS-Rolle `Landesbehörde BW`, weil das Ziel bundesweit gilt (dieselbe Prüfung wie bei `Volllaststunden (h)`: gefiltert oder weniger als 18 sichtbare Zeilen).
  - Ignoriert Filter auf Energieträger, Gruppe und Kategorie (REMOVEFILTERS auf die Tabelle Energieträger, Energieträger `Wind Offshore`); der Zeitraum wirkt wie bei `Installierte Leistung (MW)`. Der Anteil ist nicht auf 100 % begrenzt.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): ohne Datumsfilter 39 %.

**Formel**

```dax
Zielerreichung Wind auf See % =
IF(
ISFILTERED(Bundesland[Bundesland]) || CALCULATE(COUNTROWS(Bundesland), REMOVEFILTERS(Bundesland)) < 18,
BLANK(),
DIVIDE(CALCULATE([Installierte Leistung (MW)], REMOVEFILTERS('Energieträger'), 'Energieträger'[Energieträger] = "Wind Offshore"), 30000)
)
```

## Datenstand Kopfzeile

- **Definition:** Eine Kopfzeile für jede Seite: das Datum der neuesten geladenen SMARD-Viertelstunde (UTC) und der Monat des MaStR-Bestands, unabhängig von Filtern, im deutschen Datumsformat (Gebietsschema de-DE).
- **Einheit:** Text (`Datenstand: SMARD TT.MM.JJJJ · MaStR Monat JJJJ`)
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung` und Marktstammdatenregister (Bundesnetzagentur, DL-DE-BY-2.0), Seed `data/seed/kapazitaet_monat.csv`, Ansicht `rpt.v_kapazitaet`
- **Formatierung im Modell:** `Text`
- **Hinweise:**
  - Anzeigetext im Gebietsschema de-DE, keine Berechnung verwendet ihn (Abschnitt Anzeigetexte). Die Seite Datenqualität & Quellen zeigt die beiden Stände weiter einzeln (`Datenstand`, `Datenstand MaStR`).
  - Das SMARD-Datum ist ein UTC-Datum; die Viertelstunde kann in Ortszeit schon auf den Folgetag fallen.
  - Der MaStR-Monat ist angebrochen (Exportstand mitten im Monat), siehe Abschnitt Kapazitäten und Grenzen.
  - Beispiel (Abfrage am 2026-10-26 gegen das geöffnete Modell): `Datenstand: SMARD 24.10.2026 · MaStR Oktober 2026`.

**Formel**

```dax
Datenstand Kopfzeile =
VAR Smard = CALCULATE(MAX(Erzeugung[Zeitstempel UTC]), REMOVEFILTERS())
VAR MastrKey = CALCULATE(MAX('Kapazität'[Datum Key]), REMOVEFILTERS())
RETURN
"Datenstand: SMARD " & FORMAT(Smard, "dd.MM.yyyy", "de-DE")
& " · MaStR " & FORMAT(DATE(INT(MastrKey / 10000), MOD(INT(MastrKey / 100), 100), 1), "MMMM yyyy", "de-DE")
```

## Abgleich mit dem Data Warehouse

Neun Kennzahlen werden gegen SQL geprüft: `sql/queries/reconcile_m3.sql` (Ausführung:
`uv run --env-file .env python -m tools.pbi.reconcile sql`) gegen die DAX-Abfragen in `tools/pbi/reconcile.py`
(`python -m tools.pbi.reconcile dax-queries` druckt sie für die DAX-Abfrageansicht von Power BI Desktop).
Mit geöffnetem Desktop vergleicht `uv run --env-file .env --group pbi pytest tests/pbi/test_reconcile.py -m live -q`.
Die R5 bis R8 folgen der DAX-Logik oben (letzter Monat bis zum Periodenende, Durchschnitt der Monatsendbestände).

### Abgleich am 2026-10-26

| Nr. | Kennzahl | Filter | SQL-Wert | DAX-Wert | Toleranz |
|---|---|---|---|---|---|
| R1 | Erzeugung (MWh) | Jahr 2025 | 439.280.977 | 439.280.977 | ± 0,5 |
| R2 | EE-Anteil % | Jahr 2025 | 0,5895 | 0,5895 | ± 0,0005 |
| R3 | Negative Preisstunden | Jahr 2025 | 573 | 573 | ± 0 |
| R4 | Day-Ahead Ø (€/MWh) | Jahr 2025 | 89,32 | 89,32 | ± 0,005 |
| R5 | Installierte Leistung (MW) | ohne Datumsfilter | 303.715 | 303.715 | ± 0,5 |
| R6 | Installierte Leistung (MW) | Jahr 2024 | 267.978 | 267.978 | ± 0,5 |
| R7 | Zubau (MW) | Jahr 2024, Photovoltaik | 15.193 | 15.193 | ± 0,5 |
| R8 | Volllaststunden (h) | Jahr 2025, Wind Onshore | 1.634 | 1.634 | ± 0,5 |
| R9 | Zeilen | ohne Filter | 1.737.824 | 1.737.824 | ± 0 |

Die SQL-Werte wurden am 2026-10-25 gegen die Datenbank `energiewende` gemessen (SMARD bis 2026-10-24, MaStR-Exportstand 2026-10-25)
und am 2026-10-26 unverändert erneut gelesen. Die DAX-Werte stammen aus Power BI Desktop (Microsoft-Store-Version) am 2026-10-26,
nach der Aktualisierung aus derselben Datenbank: `python -m tools.pbi.reconcile compare` und der Live-Test (9 von 9 bestanden).
Alle neun Kennzahlen liegen innerhalb der Toleranz und stimmen bei der gezeigten Rundung überein.

Zeilensicherheit am selben Tag: Mit der Rolle `Landesbehörde BW` zeigt das Modell nur Baden-Württemberg (installierte Leistung
29.578 MW statt 303.715 MW bundesweit); Volllaststunden bleiben unter der Rolle leer, weil die SMARD-Erzeugung nur bundesweit vorliegt.

Die neun neuen Kennzahlen (`KPI …`, `Zielerreichung …`, `Datenstand Kopfzeile`) und die Spalte `Gruppe` wurden am 2026-10-26 mit
schreibgeschützten DAX-Abfragen gegen das geöffnete Modell geprüft; die Objekte waren dabei nur in der Abfrage definiert, ins Modell
wurde nichts geschrieben. Ein SQL-Gegenwert besteht nur für die KPI-Texte, die dieselben Werte wie R1 bis R5 zeigen (Jahr 2025:
`439,3 TWh`, `58,9 %`, `89,32 €/MWh`, `573 h`; ohne Datumsfilter `303,7 GW`); die Zielerreichung, die Kopfzeile und die Gruppen haben keinen
SQL-Gegenwert und sind nur gegen das Modell geprüft.
