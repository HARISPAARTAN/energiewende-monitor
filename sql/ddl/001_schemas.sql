IF SCHEMA_ID(N'stg') IS NULL EXEC(N'CREATE SCHEMA stg');
GO
IF SCHEMA_ID(N'dw') IS NULL EXEC(N'CREATE SCHEMA dw');
GO
IF SCHEMA_ID(N'rpt') IS NULL EXEC(N'CREATE SCHEMA rpt');
GO
IF OBJECT_ID(N'stg.smard_series') IS NULL
CREATE TABLE stg.smard_series (
    filter_id  int          NOT NULL,
    region     nvarchar(20) NOT NULL,
    resolution nvarchar(12) NOT NULL,
    ts_utc     datetime2(0) NOT NULL,
    value      float        NULL,
    datum_key  int          NOT NULL,
    zeit_key   smallint     NOT NULL,
    loaded_at  datetime2(0) NOT NULL CONSTRAINT df_smard_series_loaded_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT pk_smard_series PRIMARY KEY CLUSTERED (filter_id, region, resolution, ts_utc)
);
GO
