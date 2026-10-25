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
IF OBJECT_ID(N'stg.mastr_kapazitaet') IS NULL
CREATE TABLE stg.mastr_kapazitaet (
    jahr_monat            char(7)       NOT NULL,
    bundesland_kuerzel    nvarchar(3)   NOT NULL,
    energietraeger        nvarchar(40)  NOT NULL,
    zubau_mw              decimal(12,3) NOT NULL,
    anzahl_zubau          int           NOT NULL,
    abgang_mw             decimal(12,3) NOT NULL,
    anzahl_abgang         int           NOT NULL,
    anfangsbestand_mw     decimal(14,3) NOT NULL,
    anfangsbestand_anzahl int           NOT NULL,
    loaded_at             datetime2(0)  NOT NULL CONSTRAINT df_mastr_kapazitaet_loaded_at DEFAULT SYSUTCDATETIME(),
    CONSTRAINT pk_mastr_kapazitaet PRIMARY KEY CLUSTERED (jahr_monat, bundesland_kuerzel, energietraeger)
);
GO
