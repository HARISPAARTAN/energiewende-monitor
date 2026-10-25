IF OBJECT_ID(N'dw.dim_datum') IS NULL
CREATE TABLE dw.dim_datum (
    datum_key      int          NOT NULL CONSTRAINT pk_dim_datum PRIMARY KEY CLUSTERED,
    datum          date         NOT NULL,
    jahr           smallint     NOT NULL,
    quartal        tinyint      NOT NULL,
    monat          tinyint      NOT NULL,
    monat_name_de  nvarchar(12) NOT NULL,
    monat_name_en  nvarchar(12) NOT NULL,
    jahr_monat     char(7)      NOT NULL,
    iso_jahr       smallint     NOT NULL,
    iso_woche      tinyint      NOT NULL,
    tag            tinyint      NOT NULL,
    wochentag_nr   tinyint      NOT NULL,
    wochentag_de   nvarchar(12) NOT NULL,
    wochentag_en   nvarchar(12) NOT NULL,
    ist_wochenende bit          NOT NULL,
    saison_de      nvarchar(10) NOT NULL,
    viertelstunden tinyint      NOT NULL
);
GO
IF OBJECT_ID(N'dw.dim_zeit') IS NULL
CREATE TABLE dw.dim_zeit (
    zeit_key      smallint     NOT NULL CONSTRAINT pk_dim_zeit PRIMARY KEY CLUSTERED,
    uhrzeit       time(0)      NOT NULL,
    stunde        tinyint      NOT NULL,
    viertelstunde tinyint      NOT NULL,
    tageszeit_de  nvarchar(10) NOT NULL,
    tageszeit_en  nvarchar(10) NOT NULL
);
GO
IF OBJECT_ID(N'dw.dim_energietraeger') IS NULL
CREATE TABLE dw.dim_energietraeger (
    energietraeger_key smallint     NOT NULL CONSTRAINT pk_dim_energietraeger PRIMARY KEY CLUSTERED,
    smard_filter_id    int          NOT NULL CONSTRAINT uq_dim_energietraeger_filter UNIQUE,
    name_de            nvarchar(40) NOT NULL,
    name_en            nvarchar(40) NOT NULL,
    kategorie_de       nvarchar(20) NOT NULL,
    kategorie_en       nvarchar(20) NOT NULL,
    sortierung         tinyint      NOT NULL,
    farbe_hex          char(7)      NOT NULL
);
GO
IF OBJECT_ID(N'dw.dim_region') IS NULL
CREATE TABLE dw.dim_region (
    region_key smallint     NOT NULL CONSTRAINT pk_dim_region PRIMARY KEY CLUSTERED,
    smard_code nvarchar(20) NOT NULL CONSTRAINT uq_dim_region_code UNIQUE,
    name_de    nvarchar(60) NOT NULL,
    name_en    nvarchar(60) NOT NULL,
    typ_de     nvarchar(20) NOT NULL,
    typ_en     nvarchar(20) NOT NULL
);
GO
IF OBJECT_ID(N'dw.dim_bundesland') IS NULL
CREATE TABLE dw.dim_bundesland (
    bundesland_key smallint     NOT NULL CONSTRAINT pk_dim_bundesland PRIMARY KEY CLUSTERED,
    name_de        nvarchar(40) NOT NULL,
    kuerzel        char(3)      NOT NULL CONSTRAINT uq_dim_bundesland_kuerzel UNIQUE,
    ist_awz        bit          NOT NULL
);
GO
