"""Write the synthetic MaStR fixture: eight CSV tables with open-mastr 1.0 table and column names, 61 units.

Usage: uv run python tools/make_mastr_fixture.py
Writes data/fixtures/mastr/tables/<Tabelle>.csv. Deterministic, no randomness: the units below are the
whole fixture. tests/unit/test_mastr.py depends on them; the statistics the tests assert come from
(aggregated with calendar 1990-01-01 .. 2030-12-31):

- in_planung = 3            SEE900000000003 (Wind), SEE900000000019 (Solar), SEE900000000079 (Geothermie)
- vor_kalender_abgang = 1   SEE900000000032 (NW Steinkohle, stillgelegt 1988-12-31; no row at all)
- inbetriebnahme_fehlt = 2  SEE900000000013 (SN Solar, 5 kW), SEE900000000067 (Wasser); both In Betrieb, no date
- verworfen = 2             SEE900000000052, SEE900000000053 (Batterie; 053 also has no date)
- unmapped = 1              SEE900000000037 (Energietraeger "Wasserstoff")
- datum_unplausibel = 0, netto_unplausibel = 0, nach_kalender = 0, stilllegung_ohne_datum = 0

Rule units the tests check by cell:
- SEE900000000005 (NI Wind, endgueltig stillgelegt 2019-12-31): Zubau 1998-05 and one Abgang 2019-12
- SEE900000000010 (HE Wind, Vorübergehend stillgelegt with a DatumEndgueltigeStilllegung 2024-06-30):
  Zubau 2017-05, no Abgang, because only Endgültig stillgelegt units leave the stock

Every other unit maps cleanly: all Wind units have a Lage, all Verbrennung and GSGK fuels are in the
mapping, all other storage units are Pumpspeicher, no other unit has an empty Inbetriebnahmedatum, and
every other endgueltig stillgelegte unit has a Stilllegung on or after 1990-01-01.
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "mastr" / "tables"

BASE_COLUMNS = ["EinheitMastrNummer", "Bundesland", "Nettonennleistung", "Bruttoleistung", "Inbetriebnahmedatum",
                "EinheitBetriebsstatus", "DatumEndgueltigeStilllegung", "Energietraeger"]
TABLE_EXTRA_COLUMNS = {  # open-mastr 1.0: Technologie is absent from Solar and Wasser
    "EinheitenWind": ["Technologie", "Lage"],
    "EinheitenSolar": [],
    "EinheitenBiomasse": ["Technologie", "Hauptbrennstoff"],
    "EinheitenWasser": [],
    "EinheitenGeothermieGrubengasDruckentspannung": ["Technologie"],
    "EinheitenVerbrennung": ["Technologie", "Hauptbrennstoff"],
    "EinheitenKernkraft": ["Technologie"],
    "EinheitenStromSpeicher": ["Technologie"],
}

B = "In Betrieb"
V = "Vorübergehend stillgelegt"
E = "Endgültig stillgelegt"
P = "In Planung"

# Columns of every row:
#   EinheitMastrNummer, Bundesland, Netto kW, Brutto kW, Inbetriebnahme, Status, Stilllegung, Energietraeger,
#   Technologie, Hauptbrennstoff, Lage
# "" is an empty (NULL) value; Technologie, Hauptbrennstoff and Lage are written only where the table has them.
UNITS = {
    "EinheitenWind": [
        ("SEE900000000001", "", "8000", "8000", "2020-04-15", B, "", "Wind", "Horizontalläufer", "", "Windkraft auf See"),
        ("SEE900000000002", "Niedersachsen", "3000", "3050", "2012-11-02", B, "", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000003", "Brandenburg", "2000", "2000", "", P, "", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000004", "Schleswig-Holstein", "2300", "2350", "2016-08-10", B, "", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000005", "Niedersachsen", "600", "600", "1998-05-20", E, "2019-12-31", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000006", "Mecklenburg-Vorpommern", "6000", "6150", "2023-11-30", B, "", "Wind", "Horizontalläufer", "", "Windkraft auf See"),
        ("SEE900000000007", "", "9500", "9500", "2024-02-01", B, "", "Wind", "Horizontalläufer", "", "Windkraft auf See"),
        ("SEE900000000008", "Sachsen-Anhalt", "1500", "1500", "2005-03-15", V, "", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000009", "Brandenburg", "4200", "4200", "2025-07-01", B, "", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
        ("SEE900000000010", "Hessen", "3300", "3400", "2017-05-12", V, "2024-06-30", "Wind", "Horizontalläufer", "", "Windkraft an Land"),
    ],
    "EinheitenSolar": [
        ("SEE900000000011", "Bayern", "9.9", "10.5", "2019-03-01", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000012", "", "30", "32", "2021-09-20", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000013", "Sachsen", "5", "5", "", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000014", "Baden-Württemberg", "7.2", "7.8", "2009-06-30", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000015", "Bayern", "750", "800", "2011-12-15", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000016", "Nordrhein-Westfalen", "10.5", "11", "2022-04-04", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000017", "Brandenburg", "20000", "21500", "2023-08-01", B, "", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000018", "Hessen", "4.5", "4.5", "2004-10-01", E, "2024-10-01", "Solare Strahlungsenergie", "", "", ""),
        ("SEE900000000019", "Berlin", "12", "12", "", P, "", "Solare Strahlungsenergie", "", "", ""),
    ],
    "EinheitenBiomasse": [
        ("SEE900000000021", "Bayern", "500", "526", "2015-06-17", B, "", "Biomasse", "Verbrennungsmotor", "Biogas", ""),
        ("SEE900000000022", "Niedersachsen", "750", "780", "2007-09-01", B, "", "Biomasse", "Verbrennungsmotor", "Biogas", ""),
        ("SEE900000000023", "Schleswig-Holstein", "250", "265", "2012-03-10", V, "", "Biomasse", "Verbrennungsmotor", "Biogas", ""),
        ("SEE900000000024", "Bayern", "1000", "1050", "1995-01-01", E, "2020-12-31", "Biomasse", "Dampfturbine", "Holz", ""),
        ("SEE900000000025", "Thüringen", "20000", "21000", "2003-04-01", B, "", "Biomasse", "Dampfturbine", "Holz", ""),
        ("SEE900000000026", "Mecklenburg-Vorpommern", "550", "570", "2018-06-01", B, "", "Biomasse", "Verbrennungsmotor", "Biomethan", ""),
        ("SEE900000000027", "Rheinland-Pfalz", "75", "75", "2016-02-01", B, "", "Biomasse", "Verbrennungsmotor", "Biogas", ""),
    ],
    "EinheitenVerbrennung": [
        ("SEE900000000031", "Nordrhein-Westfalen", "300000", "320000", "1985-01-01", E, "2024-03-31", "Braunkohle", "Dampfturbine", "Rohbraunkohle", ""),
        ("SEE900000000032", "Nordrhein-Westfalen", "50000", "54000", "1975-01-01", E, "1988-12-31", "Steinkohle", "Dampfturbine", "Steinkohle", ""),
        ("SEE900000000033", "Hessen", "400000", "415000", "2005-05-05", B, "", "Erdgas", "Gasturbine mit Abhitzekessel", "Erdgas", ""),
        ("SEE900000000034", "Sachsen", "900000", "950000", "2012-08-01", B, "", "Braunkohle", "Dampfturbine", "Rohbraunkohle", ""),
        ("SEE900000000035", "Saarland", "180000", "190000", "1989-06-01", E, "2022-10-31", "Steinkohle", "Dampfturbine", "Steinkohle", ""),
        ("SEE900000000036", "Hamburg", "1000", "1050", "2010-01-01", B, "", "Mineralölprodukte", "Verbrennungsmotor", "Heizöl", ""),
        ("SEE900000000037", "Hamburg", "1000", "1000", "2024-07-01", B, "", "Wasserstoff", "Brennstoffzelle", "Wasserstoff", ""),
        ("SEE900000000038", "Bremen", "25000", "26000", "1999-11-01", V, "", "andere Gase", "Gasturbine ohne Abhitzekessel", "Gichtgas", ""),
        ("SEE900000000039", "Sachsen-Anhalt", "30000", "32000", "2001-01-01", B, "", "nicht biogener Abfall", "Dampfturbine", "Hausmüll", ""),
    ],
    "EinheitenKernkraft": [
        ("SEE900000000041", "Bayern", "1400000", "1485000", "1988-01-01", E, "2023-04-15", "Kernenergie", "Druckwasserreaktor", "", ""),
        ("SEE900000000042", "Niedersachsen", "1360000", "1430000", "1988-06-01", E, "2023-04-15", "Kernenergie", "Druckwasserreaktor", "", ""),
        ("SEE900000000043", "Baden-Württemberg", "1310000", "1400000", "1989-04-01", E, "2023-04-15", "Kernenergie", "Druckwasserreaktor", "", ""),
        ("SEE900000000044", "Schleswig-Holstein", "1400000", "1480000", "1986-09-01", E, "2021-12-31", "Kernenergie", "Druckwasserreaktor", "", ""),
        ("SEE900000000045", "Hessen", "1167000", "1225000", "1974-08-25", E, "2011-08-06", "Kernenergie", "Druckwasserreaktor", "", ""),
    ],
    "EinheitenStromSpeicher": [
        ("SEE900000000051", "Thüringen", "1060000", "1060000", "2003-01-01", B, "", "Speicher", "Pumpspeicher", "", ""),
        ("SEE900000000052", "Berlin", "100", "100", "2022-01-01", B, "", "Speicher", "Batterie", "", ""),
        ("SEE900000000053", "Berlin", "50", "50", "", B, "", "Speicher", "Batterie", "", ""),
        ("SEE900000000054", "Baden-Württemberg", "160000", "165000", "1975-01-01", B, "", "Speicher", "Pumpspeicher", "", ""),
        ("SEE900000000055", "Sachsen", "80000", "80000", "1990-03-01", V, "", "Speicher", "Pumpspeicher", "", ""),
        ("SEE900000000056", "Nordrhein-Westfalen", "140000", "145000", "1969-01-01", E, "2025-01-31", "Speicher", "Pumpspeicher", "", ""),
    ],
    "EinheitenWasser": [
        ("SEE900000000061", "Baden-Württemberg", "1200", "1250", "1950-01-01", B, "", "Wasser", "", "", ""),
        ("SEE900000000062", "Bayern", "25000", "26000", "1955-01-01", B, "", "Wasser", "", "", ""),
        ("SEE900000000063", "Bayern", "300", "310", "2014-05-01", B, "", "Wasser", "", "", ""),
        ("SEE900000000064", "Rheinland-Pfalz", "45", "45", "1992-07-01", E, "2018-12-31", "Wasser", "", "", ""),
        ("SEE900000000065", "Sachsen", "150", "155", "2009-04-01", V, "", "Wasser", "", "", ""),
        ("SEE900000000066", "Hessen", "900", "920", "2020-10-01", B, "", "Wasser", "", "", ""),
        ("SEE900000000067", "Thüringen", "80", "80", "", B, "", "Wasser", "", "", ""),
    ],
    "EinheitenGeothermieGrubengasDruckentspannung": [
        ("SEE900000000071", "Bayern", "3000", "3400", "2008-01-01", B, "", "Geothermie", "ORC-Anlage", "", ""),
        ("SEE900000000072", "Bayern", "5500", "6000", "2013-09-01", B, "", "Geothermie", "ORC-Anlage", "", ""),
        ("SEE900000000073", "Baden-Württemberg", "4300", "4800", "2010-11-01", B, "", "Geothermie", "Kalina-Anlage", "", ""),
        ("SEE900000000074", "Saarland", "1350", "1400", "2002-02-01", B, "", "Grubengas", "Verbrennungsmotor", "", ""),
        ("SEE900000000075", "Nordrhein-Westfalen", "2000", "2050", "1997-06-01", E, "2021-06-30", "Grubengas", "Verbrennungsmotor", "", ""),
        ("SEE900000000076", "Nordrhein-Westfalen", "1500", "1550", "2004-12-01", V, "", "Grubengas", "Verbrennungsmotor", "", ""),
        ("SEE900000000077", "Hessen", "600", "620", "2016-03-01", B, "", "Druckentspannung", "Druckentspannungsturbine", "", ""),
        ("SEE900000000079", "Bayern", "4000", "4500", "", P, "", "Geothermie", "ORC-Anlage", "", ""),
    ],
}

ROW_FIELDS = BASE_COLUMNS + ["Technologie", "Hauptbrennstoff", "Lage"]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for table, rows in UNITS.items():
        columns = BASE_COLUMNS + TABLE_EXTRA_COLUMNS[table]
        path = OUT_DIR / f"{table}.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(columns)
            for row in rows:
                record = dict(zip(ROW_FIELDS, row, strict=True))
                writer.writerow([record[c] for c in columns])
        total += len(rows)
        print(f"{path.relative_to(OUT_DIR.parents[3])}: {len(rows)} Einheiten")
    print(f"insgesamt {total} Einheiten")


if __name__ == "__main__":
    main()
