-- Reconciliation of the Power BI measures against the warehouse (milestone 3).
-- Every statement returns (id, wert); the DAX side lives in tools/pbi/reconcile.py with the same ids.
-- Run: uv run --env-file .env python -m tools.pbi.reconcile sql
-- R5 to R8 follow the DAX of Kennzahlen.tmdl exactly (see docs/kpi-glossar.md).

-- R1 Erzeugung gesamt 2025 (MWh)           -> [Erzeugung (MWh)] with Datum[Jahr] = 2025
SELECT 'R1' AS id, SUM(erzeugung_mwh) AS wert FROM dw.fact_erzeugung f JOIN dw.dim_datum d ON d.datum_key = f.datum_key WHERE f.aufloesung_min = 15 AND d.jahr = 2025;

-- R2 EE-Anteil 2025                        -> [EE-Anteil %] with Datum[Jahr] = 2025 (ratio, 4 decimals)
SELECT 'R2', SUM(CASE WHEN e.kategorie_de = N'Erneuerbar' THEN f.erzeugung_mwh END) / SUM(f.erzeugung_mwh)
FROM dw.fact_erzeugung f JOIN dw.dim_datum d ON d.datum_key = f.datum_key JOIN dw.dim_energietraeger e ON e.energietraeger_key = f.energietraeger_key
WHERE f.aufloesung_min = 15 AND d.jahr = 2025;

-- R3 Negative Preisstunden 2025            -> [Negative Preisstunden] with Datum[Jahr] = 2025
SELECT 'R3', COUNT(*) FROM dw.fact_preis p JOIN dw.dim_datum d ON d.datum_key = p.datum_key WHERE d.jahr = 2025 AND p.day_ahead_eur_mwh < 0;

-- R4 Day-Ahead Ø 2025                      -> [Day-Ahead Ø (€/MWh)] with Datum[Jahr] = 2025 (2 decimals)
SELECT 'R4', AVG(p.day_ahead_eur_mwh) FROM dw.fact_preis p JOIN dw.dim_datum d ON d.datum_key = p.datum_key WHERE d.jahr = 2025;

-- R5 Installierte Leistung, newest month   -> [Installierte Leistung (MW)] with no date filter
SELECT 'R5', SUM(bestand_mw) FROM dw.fact_kapazitaet WHERE datum_key = (SELECT MAX(datum_key) FROM dw.fact_kapazitaet);

-- R6 Installierte Leistung end of 2024     -> [Installierte Leistung (MW)] with Datum[Jahr] = 2024
-- (the stock of the last month with capacity data on or before 2024-12-31)
SELECT 'R6', SUM(bestand_mw) FROM dw.fact_kapazitaet WHERE datum_key = (SELECT MAX(datum_key) FROM dw.fact_kapazitaet WHERE datum_key <= 20241231);

-- R7 Zubau 2024 Photovoltaik               -> [Zubau (MW)] with Datum[Jahr] = 2024 and Energieträger = Photovoltaik
SELECT 'R7', SUM(k.zubau_mw) FROM dw.fact_kapazitaet k JOIN dw.dim_datum d ON d.datum_key = k.datum_key JOIN dw.dim_energietraeger e ON e.energietraeger_key = k.energietraeger_key
WHERE d.jahr = 2024 AND e.name_de = N'Photovoltaik';

-- R8 Volllaststunden Wind Onshore 2025     -> [Volllaststunden (h)] with Datum[Jahr] = 2025 and Energieträger = Wind Onshore (0 decimals)
-- Generation of the year divided by the average month-end stock over the months from the first month with
-- generation data to the last generation day (the VAR ErzStart / ErzEnde / MonatStart logic of the measure).
WITH erz AS (SELECT SUM(f.erzeugung_mwh) AS mwh, MIN(f.datum_key) AS von, MAX(f.datum_key) AS bis
             FROM dw.fact_erzeugung f JOIN dw.dim_datum d ON d.datum_key = f.datum_key JOIN dw.dim_energietraeger e ON e.energietraeger_key = f.energietraeger_key
             WHERE f.aufloesung_min = 15 AND d.jahr = 2025 AND e.name_de = N'Wind Onshore'),
     kap AS (SELECT AVG(m.mw) AS mw FROM (SELECT k.datum_key, SUM(k.bestand_mw) AS mw FROM dw.fact_kapazitaet k JOIN dw.dim_energietraeger e ON e.energietraeger_key = k.energietraeger_key
             WHERE k.datum_key BETWEEN (SELECT von / 100 * 100 + 1 FROM erz) AND (SELECT bis FROM erz) AND e.name_de = N'Wind Onshore' GROUP BY k.datum_key) m)
SELECT 'R8', erz.mwh / kap.mw FROM erz, kap;

-- R9 Zeilen gesamt                          -> [Zeilen] with no filter
SELECT 'R9', (SELECT COUNT(*) FROM dw.fact_erzeugung) + (SELECT COUNT(*) FROM dw.fact_last) + (SELECT COUNT(*) FROM dw.fact_preis) + (SELECT COUNT(*) FROM dw.fact_kapazitaet);
