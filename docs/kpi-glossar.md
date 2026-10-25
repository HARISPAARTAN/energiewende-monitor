# Kennzahlen-Glossar

Die 26 Kennzahlen des Power-BI-Modells (Tabelle `Kennzahlen`), mit der DAX-Formel wie im TMDL
(`powerbi/EnergiewendeMonitor.SemanticModel/definition/tables/Kennzahlen.tmdl`). Die Formeln hier und im Modell
sind identisch; `tests/pbi/test_glossary.py` prüft das. Jede Kennzahl hat im Modell zusätzlich eine englische
Beschreibung. Der Abgleich mit dem Data Warehouse steht am Ende.

Zeitstempel in SMARD-Daten sind UTC; Datum und Uhrzeit des Modells (`Datum`, `Zeit`) sind Ortszeit (Europe/Berlin).

## Kapazitäten und Grenzen

Gilt für Zubau, Installierte Leistung und Volllaststunden.

**Monatsendbestand.** `Kapazität[Bestand MW]` ist der Bestand am Monatsende (Anfangsbestand plus Zubau minus Abgang des Monats)
je Bundesland und Energieträger, mit lückenlosem Monatsraster ab Januar 1990. Summiert über Bundesländer ergibt das den
bundesweiten Bestand eines Monats; Summen über mehrere Monate wären sinnlos und kommen nicht vor.

**Letzter Monat mit Daten (LASTNONBLANK-Logik).** Installierte Leistung nimmt nicht den Bestand "des Zeitraums", sondern den des
letzten Monats mit Kapazitätszeilen, der am oder vor dem Ende des gewählten Datums liegt. Das Ende ist `MAX(Datum[Datum])` im
Kontext, die Auswahl `MAX(Kapazität[Datum Key])` über alle Datumszeilen bis dahin (`REMOVEFILTERS(Datum)` plus Datumsvergleich).
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
- **Quelle:** SMARD (Bundesnetzagentur | SMARD.de, CC BY 4.0), Ansicht `rpt.v_erzeugung`, Dimension `Energieträger[Kategorie]`
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Pumpspeicher gehört in der Dimension `Energieträger` zur Kategorie Konventionell.
  - Ein äußerer Filter auf `Energieträger[Kategorie]` (Slicer Kategorie, Lesezeichen) bleibt wirksam (`KEEPFILTERS`): Bei Auswahl Konventionell ist die Kennzahl leer, der EE-Anteil 0 %.

**Formel**

```dax
Erzeugung Erneuerbar (MWh) =
CALCULATE([Erzeugung (MWh)], KEEPFILTERS(Energieträger[Kategorie] = "Erneuerbar"))
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
SUM(Kapazität[Zubau MW])
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
VAR LetzterMonat = CALCULATE(MAX(Kapazität[Datum Key]), REMOVEFILTERS(Datum), Datum[Datum] <= EndeDatum)
RETURN CALCULATE(SUM(Kapazität[Bestand MW]), REMOVEFILTERS(Datum), Kapazität[Datum Key] = LetzterMonat)
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
VAR MonateMitBestand = CALCULATETABLE(VALUES(Kapazität[Datum Key]), REMOVEFILTERS(Datum), Kapazität[Datum Key] >= MonatStart && Kapazität[Datum Key] <= ErzEnde)
VAR MittlererBestand = CALCULATE(AVERAGEX(MonateMitBestand, CALCULATE(SUM(Kapazität[Bestand MW]))), REMOVEFILTERS(Datum))
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
SUM(Kapazität[Anzahl Zubau])
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

- **Definition:** Summe der Zeilen der vier Faktentabellen (Erzeugung, Last, Preis, Kapazität) im Filterkontext.
- **Einheit:** Zeilen
- **Quelle:** Alle vier Faktenansichten
- **Formatierung im Modell:** `#,0`
- **Hinweise:**
  - Ohne Filter gleich der Summe der Zeilen von `dw.fact_erzeugung`, `dw.fact_last`, `dw.fact_preis` und `dw.fact_kapazitaet`.

**Formel**

```dax
Zeilen =
COUNTROWS(Erzeugung) + COUNTROWS(Last) + COUNTROWS(Preis) + COUNTROWS(Kapazität)
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
FORMAT(CALCULATE(MAX(Kapazität[Datum Key]), REMOVEFILTERS()), "0000-00-00")
```

## Abgleich mit dem Data Warehouse

Neun Kennzahlen werden gegen SQL geprüft: `sql/queries/reconcile_m3.sql` (Ausführung:
`uv run --env-file .env python -m tools.pbi.reconcile sql`) gegen die DAX-Abfragen in `tools/pbi/reconcile.py`
(`python -m tools.pbi.reconcile dax-queries` druckt sie für die DAX-Abfrageansicht von Power BI Desktop).
Mit geöffnetem Desktop vergleicht `uv run --env-file .env --group pbi pytest tests/pbi/test_reconcile.py -m live -q`.
Die R5 bis R8 folgen der DAX-Logik oben (letzter Monat bis zum Periodenende, Durchschnitt der Monatsendbestände).

### Abgleich am 2026-10-25: SQL-Seite

| Nr. | Kennzahl | Filter | SQL-Wert | DAX-Wert | Toleranz |
|---|---|---|---|---|---|
| R1 | Erzeugung (MWh) | Jahr 2025 | 439.280.977 | offen (Desktop-Sitzung) | ± 0,5 |
| R2 | EE-Anteil % | Jahr 2025 | 0,5895 | offen (Desktop-Sitzung) | ± 0,0005 |
| R3 | Negative Preisstunden | Jahr 2025 | 573 | offen (Desktop-Sitzung) | ± 0 |
| R4 | Day-Ahead Ø (€/MWh) | Jahr 2025 | 89,32 | offen (Desktop-Sitzung) | ± 0,005 |
| R5 | Installierte Leistung (MW) | ohne Datumsfilter | 303.715 | offen (Desktop-Sitzung) | ± 0,5 |
| R6 | Installierte Leistung (MW) | Jahr 2024 | 267.978 | offen (Desktop-Sitzung) | ± 0,5 |
| R7 | Zubau (MW) | Jahr 2024, Photovoltaik | 15.193 | offen (Desktop-Sitzung) | ± 0,5 |
| R8 | Volllaststunden (h) | Jahr 2025, Wind Onshore | 1.634 | offen (Desktop-Sitzung) | ± 0,5 |
| R9 | Zeilen | ohne Filter | 1.737.824 | offen (Desktop-Sitzung) | ± 0 |

Die SQL-Werte wurden am 2026-10-25 gegen die Datenbank `energiewende` gemessen (SMARD bis 2026-10-24, MaStR-Exportstand 2026-10-25).
Die DAX-Spalte wird in der Validierungssitzung mit Power BI Desktop gefüllt; weicht ein Wert über die Toleranz ab, ist das ein
Befund für den Bericht.
