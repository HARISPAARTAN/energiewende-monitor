IF OBJECT_ID(N'dw.fact_erzeugung') IS NULL
BEGIN
    CREATE TABLE dw.fact_erzeugung (
        region_key         smallint      NOT NULL,
        energietraeger_key smallint      NOT NULL,
        ts_utc             datetime2(0)  NOT NULL,
        datum_key          int           NOT NULL,
        zeit_key           smallint      NOT NULL,
        aufloesung_min     tinyint       NOT NULL,
        erzeugung_mwh      decimal(12,3) NULL,
        CONSTRAINT pk_fact_erzeugung PRIMARY KEY CLUSTERED (region_key, energietraeger_key, ts_utc),
        CONSTRAINT fk_fact_erzeugung_datum FOREIGN KEY (datum_key) REFERENCES dw.dim_datum (datum_key),
        CONSTRAINT fk_fact_erzeugung_zeit FOREIGN KEY (zeit_key) REFERENCES dw.dim_zeit (zeit_key),
        CONSTRAINT fk_fact_erzeugung_region FOREIGN KEY (region_key) REFERENCES dw.dim_region (region_key),
        CONSTRAINT fk_fact_erzeugung_et FOREIGN KEY (energietraeger_key) REFERENCES dw.dim_energietraeger (energietraeger_key)
    );
    CREATE INDEX ix_fact_erzeugung_datum ON dw.fact_erzeugung (datum_key) INCLUDE (erzeugung_mwh);
END
GO
IF OBJECT_ID(N'dw.fact_last') IS NULL
BEGIN
    CREATE TABLE dw.fact_last (
        region_key                 smallint      NOT NULL,
        ts_utc                     datetime2(0)  NOT NULL,
        datum_key                  int           NOT NULL,
        zeit_key                   smallint      NOT NULL,
        aufloesung_min             tinyint       NOT NULL,
        netzlast_mwh               decimal(12,3) NULL,
        residuallast_mwh           decimal(12,3) NULL,
        pumpspeicher_verbrauch_mwh decimal(12,3) NULL,
        CONSTRAINT pk_fact_last PRIMARY KEY CLUSTERED (region_key, ts_utc),
        CONSTRAINT fk_fact_last_datum FOREIGN KEY (datum_key) REFERENCES dw.dim_datum (datum_key),
        CONSTRAINT fk_fact_last_zeit FOREIGN KEY (zeit_key) REFERENCES dw.dim_zeit (zeit_key),
        CONSTRAINT fk_fact_last_region FOREIGN KEY (region_key) REFERENCES dw.dim_region (region_key)
    );
    CREATE INDEX ix_fact_last_datum ON dw.fact_last (datum_key) INCLUDE (netzlast_mwh, residuallast_mwh);
END
GO
IF OBJECT_ID(N'dw.fact_preis') IS NULL
BEGIN
    CREATE TABLE dw.fact_preis (
        region_key        smallint     NOT NULL,
        ts_utc            datetime2(0) NOT NULL,
        datum_key         int          NOT NULL,
        zeit_key          smallint     NOT NULL,
        day_ahead_eur_mwh decimal(9,2) NULL,
        CONSTRAINT pk_fact_preis PRIMARY KEY CLUSTERED (region_key, ts_utc),
        CONSTRAINT fk_fact_preis_datum FOREIGN KEY (datum_key) REFERENCES dw.dim_datum (datum_key),
        CONSTRAINT fk_fact_preis_zeit FOREIGN KEY (zeit_key) REFERENCES dw.dim_zeit (zeit_key),
        CONSTRAINT fk_fact_preis_region FOREIGN KEY (region_key) REFERENCES dw.dim_region (region_key)
    );
    CREATE INDEX ix_fact_preis_datum ON dw.fact_preis (datum_key) INCLUDE (day_ahead_eur_mwh);
END
GO
IF OBJECT_ID(N'dw.fact_kapazitaet') IS NULL
BEGIN
    CREATE TABLE dw.fact_kapazitaet (
        datum_key             int           NOT NULL,
        bundesland_key        smallint      NOT NULL,
        energietraeger_key    smallint      NOT NULL,
        zubau_mw              decimal(12,3) NOT NULL,
        anzahl_zubau          int           NOT NULL,
        abgang_mw             decimal(12,3) NOT NULL,
        anzahl_abgang         int           NOT NULL,
        anfangsbestand_mw     decimal(14,3) NOT NULL,
        anfangsbestand_anzahl int           NOT NULL,
        bestand_mw            decimal(14,3) NOT NULL,
        bestand_anzahl        int           NOT NULL,
        CONSTRAINT pk_fact_kapazitaet PRIMARY KEY CLUSTERED (datum_key, bundesland_key, energietraeger_key),
        CONSTRAINT fk_fact_kapazitaet_datum FOREIGN KEY (datum_key) REFERENCES dw.dim_datum (datum_key),
        CONSTRAINT fk_fact_kapazitaet_bl FOREIGN KEY (bundesland_key) REFERENCES dw.dim_bundesland (bundesland_key),
        CONSTRAINT fk_fact_kapazitaet_et FOREIGN KEY (energietraeger_key) REFERENCES dw.dim_energietraeger (energietraeger_key)
    );
END
GO
