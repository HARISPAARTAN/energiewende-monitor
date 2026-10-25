SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @from_key int = ?, @to_key int = ?;  -- accepted for uniformity; the capacity fact is rebuilt in full from the seed
DELETE FROM dw.fact_kapazitaet;
WITH stg_keys AS (
    SELECT s.jahr_monat, b.bundesland_key, e.energietraeger_key, s.zubau_mw, s.anzahl_zubau, s.abgang_mw, s.anzahl_abgang,
           s.anfangsbestand_mw, s.anfangsbestand_anzahl
    FROM stg.mastr_kapazitaet s
    JOIN dw.dim_bundesland b ON b.kuerzel = s.bundesland_kuerzel
    JOIN dw.dim_energietraeger e ON e.name_de = s.energietraeger),
paare AS (
    SELECT bundesland_key, energietraeger_key, MIN(jahr_monat) AS erster_monat FROM stg_keys
    GROUP BY bundesland_key, energietraeger_key),
letzter AS (SELECT MAX(jahr_monat) AS jahr_monat FROM stg.mastr_kapazitaet),
raster AS (
    SELECT d.datum_key, d.jahr_monat, p.bundesland_key, p.energietraeger_key
    FROM paare p CROSS JOIN letzter l
    JOIN dw.dim_datum d ON d.tag = 1 AND d.jahr_monat BETWEEN p.erster_monat AND l.jahr_monat),
werte AS (
    SELECT r.datum_key, r.bundesland_key, r.energietraeger_key,
           COALESCE(s.zubau_mw, 0) AS zubau_mw, COALESCE(s.anzahl_zubau, 0) AS anzahl_zubau,
           COALESCE(s.abgang_mw, 0) AS abgang_mw, COALESCE(s.anzahl_abgang, 0) AS anzahl_abgang,
           COALESCE(s.anfangsbestand_mw, 0) AS anfangsbestand_mw, COALESCE(s.anfangsbestand_anzahl, 0) AS anfangsbestand_anzahl
    FROM raster r
    LEFT JOIN stg_keys s ON s.jahr_monat = r.jahr_monat AND s.bundesland_key = r.bundesland_key AND s.energietraeger_key = r.energietraeger_key)
INSERT INTO dw.fact_kapazitaet (datum_key, bundesland_key, energietraeger_key, zubau_mw, anzahl_zubau, abgang_mw, anzahl_abgang,
                                anfangsbestand_mw, anfangsbestand_anzahl, bestand_mw, bestand_anzahl)
SELECT datum_key, bundesland_key, energietraeger_key, zubau_mw, anzahl_zubau, abgang_mw, anzahl_abgang, anfangsbestand_mw, anfangsbestand_anzahl,
       SUM(anfangsbestand_mw + zubau_mw - abgang_mw) OVER (PARTITION BY bundesland_key, energietraeger_key ORDER BY datum_key ROWS UNBOUNDED PRECEDING),
       SUM(anfangsbestand_anzahl + anzahl_zubau - anzahl_abgang) OVER (PARTITION BY bundesland_key, energietraeger_key ORDER BY datum_key ROWS UNBOUNDED PRECEDING)
FROM werte;
