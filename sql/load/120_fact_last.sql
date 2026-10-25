SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @from_key int = ?, @to_key int = ?;
DELETE FROM dw.fact_last WHERE datum_key BETWEEN @from_key AND @to_key;
INSERT INTO dw.fact_last (region_key, ts_utc, datum_key, zeit_key, aufloesung_min,
                          netzlast_mwh, residuallast_mwh, pumpspeicher_verbrauch_mwh)
SELECT r.region_key, s.ts_utc, s.datum_key, s.zeit_key,
       CASE s.resolution WHEN N'quarterhour' THEN 15 ELSE 60 END,
       CAST(MAX(CASE WHEN s.filter_id = 410  THEN s.value END) AS decimal(12,3)),
       CAST(MAX(CASE WHEN s.filter_id = 4359 THEN s.value END) AS decimal(12,3)),
       CAST(MAX(CASE WHEN s.filter_id = 4387 THEN s.value END) AS decimal(12,3))
FROM stg.smard_series s
JOIN dw.dim_region r ON r.smard_code = s.region
WHERE s.filter_id IN (410, 4359, 4387) AND s.datum_key BETWEEN @from_key AND @to_key
GROUP BY r.region_key, s.ts_utc, s.datum_key, s.zeit_key, s.resolution;
