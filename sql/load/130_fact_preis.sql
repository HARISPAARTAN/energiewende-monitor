SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @from_key int = ?, @to_key int = ?;
DELETE FROM dw.fact_preis WHERE datum_key BETWEEN @from_key AND @to_key;
INSERT INTO dw.fact_preis (region_key, ts_utc, datum_key, zeit_key, day_ahead_eur_mwh)
SELECT r.region_key, s.ts_utc, s.datum_key, s.zeit_key, CAST(s.value AS decimal(9,2))
FROM stg.smard_series s
JOIN dw.dim_region r ON r.smard_code = s.region
WHERE s.filter_id = 4169 AND s.resolution = N'hour' AND s.datum_key BETWEEN @from_key AND @to_key;
