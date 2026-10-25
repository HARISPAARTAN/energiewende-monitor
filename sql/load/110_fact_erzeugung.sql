SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @from_key int = ?, @to_key int = ?;
DELETE FROM dw.fact_erzeugung WHERE datum_key BETWEEN @from_key AND @to_key;
INSERT INTO dw.fact_erzeugung (region_key, energietraeger_key, ts_utc, datum_key, zeit_key, aufloesung_min, erzeugung_mwh)
SELECT r.region_key, e.energietraeger_key, s.ts_utc, s.datum_key, s.zeit_key,
       CASE s.resolution WHEN N'quarterhour' THEN 15 ELSE 60 END,
       CAST(s.value AS decimal(12,3))
FROM stg.smard_series s
JOIN dw.dim_energietraeger e ON e.smard_filter_id = s.filter_id
JOIN dw.dim_region r ON r.smard_code = s.region
WHERE s.datum_key BETWEEN @from_key AND @to_key;
