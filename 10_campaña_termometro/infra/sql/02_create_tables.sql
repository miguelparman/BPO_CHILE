-- Esquema de prueba. Los tipos de dato son una estimación razonable basada en
-- cómo se usa cada columna en el .dtsx original (CAST/CONVERT, comparaciones,
-- longitudes de RUT chileno, etc.) y en lo confirmado vía INFORMATION_SCHEMA
-- contra el servidor real. Si en producción algún tipo es distinto (ej. un
-- nvarchar más corto, o Estado como char en vez de nvarchar), ajusta aquí --
-- este esquema es solo para pruebas locales, no reemplaza al real.

USE [CL_CAMPAÑAS];
GO

IF OBJECT_ID('dbo.TBL_CAMPAÑA_TERMOMETRO_SOURCE', 'U') IS NOT NULL DROP TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_SOURCE;
CREATE TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_SOURCE (
    RUT_DV       NVARCHAR(20)  NULL,
    NOMCLI       NVARCHAR(200) NULL,
    SEGME        NVARCHAR(100) NULL,
    SUB_SEGME    NVARCHAR(100) NULL,
    NOM_SM       NVARCHAR(200) NULL,
    NOM_SUP      NVARCHAR(200) NULL,
    PERIODO      INT           NULL,
    RUT          NVARCHAR(10)  NULL,
    RUT_SIN_DV   NVARCHAR(20)  NULL,
    [TENTA FO]   NVARCHAR(50)  NULL
);
GO

IF OBJECT_ID('dbo.TBL_CAMPAÑA_TERMOMETRO_DETRACTOR', 'U') IS NOT NULL DROP TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_DETRACTOR;
CREATE TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_DETRACTOR (
    PERIODO     NVARCHAR(10) NULL,
    RUT_SIN_DV  NVARCHAR(20) NULL
);
GO

IF OBJECT_ID('dbo.TBL_CAMPAÑA_TERMOMETRO_VALIDADOR_SM', 'U') IS NOT NULL DROP TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_VALIDADOR_SM;
CREATE TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_VALIDADOR_SM (
    PERIODO         NVARCHAR(10)  NULL,
    PLACE           NVARCHAR(50)  NULL,
    RUT_SM          NVARCHAR(20)  NULL,
    DNI             NVARCHAR(50)  NULL,
    NOM_SM          NVARCHAR(200) NULL,
    MAIL_SM         NVARCHAR(200) NULL,
    MAIL_FRACTALIA  NVARCHAR(200) NULL
);
GO

IF OBJECT_ID('dbo.TBL_CAMPAÑA_TERMOMETRO_SF_TEMP', 'U') IS NOT NULL DROP TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_SF_TEMP;
CREATE TABLE dbo.TBL_CAMPAÑA_TERMOMETRO_SF_TEMP (
    [No  identificación fiscal]                                    NVARCHAR(20)   NULL,
    [Fecha de la encuesta]                                          DATETIME2      NULL,
    [Promedio del termómetro]                                       DECIMAL(5,2)   NULL,
    [1. Oferta Comercial]                                           NVARCHAR(50)   NULL,
    [2. Instalación]                                                NVARCHAR(50)   NULL,
    [3. Facturación]                                                NVARCHAR(50)   NULL,
    [4. Cobranza]                                                   NVARCHAR(50)   NULL,
    [5. Soporte Técnico Fijo]                                       NVARCHAR(50)   NULL,
    [6. Soporte Técnico Móvil]                                      NVARCHAR(50)   NULL,
    [7. Recambio de equipo]                                         NVARCHAR(50)   NULL,
    [8. Atención postventa]                                         NVARCHAR(50)   NULL,
    [9. Cobertura móvil]                                            NVARCHAR(50)   NULL,
    [10. Canal de autoatención web]                                 NVARCHAR(50)   NULL,
    [11. Satisfacción general]                                      INT            NULL,
    [12. Expectativas]                                              NVARCHAR(50)   NULL,
    [13. Empresa Perfecta]                                          NVARCHAR(50)   NULL,
    [14. Probabilidad de recomendación]                             INT            NULL,
    [Comentarios]                                                   NVARCHAR(MAX)  NULL,
    [PERIODO]                                                       NVARCHAR(10)   NULL,
    [Estado]                                                        NVARCHAR(50)   NULL,
    [Peso]                                                          INT            NULL,
    [ISC (Índice de Satisfacción del Cliente): Ref.]                NVARCHAR(100)  NULL,
    [Plan de acción: Creado por]                                    NVARCHAR(200)  NULL,
    [ISC (Índice de Satisfacción del Cliente): Fecha de creación]   DATETIME2      NULL,
    [Plan de acción  Caso]                                          NVARCHAR(100)  NULL
);
GO

IF OBJECT_ID('dbo.TBL_CAMPAÑA_TERMOMETRO', 'U') IS NOT NULL DROP TABLE dbo.TBL_CAMPAÑA_TERMOMETRO;
CREATE TABLE dbo.TBL_CAMPAÑA_TERMOMETRO (
    RUT                                                NVARCHAR(10)  NULL,
    NOMCLI                                             NVARCHAR(200) NULL,
    SEGME                                              NVARCHAR(100) NULL,
    SUB_SEGME                                          NVARCHAR(100) NULL,
    NOM_SM                                             NVARCHAR(200) NULL,
    NOM_SUP                                            NVARCHAR(200) NULL,
    PERIODO                                            INT           NULL,
    [Fecha de la encuesta]                             DATETIME2     NULL,
    Estado                                             NVARCHAR(50)  NULL,
    [Prom 11.]                                         DECIMAL(5,2)  NULL,
    [Prom 14.]                                         DECIMAL(5,2)  NULL,
    NPS                                                NVARCHAR(20)  NULL,
    cod_dni                                            NVARCHAR(50)  NULL,
    Etiqueta                                           NVARCHAR(100) NULL,
    [Semana Fecha de la encuesta]                      NVARCHAR(20)  NULL,
    [Semana Fecha de la encuesta2]                     NVARCHAR(20)  NULL,
    RUT_SIN_DV                                         NVARCHAR(20)  NULL,
    [ESTADO GENERAL]                                   NVARCHAR(50)  NULL,
    [ESTADO EFECTIVO]                                  NVARCHAR(50)  NULL,
    ID_GENESYS_SM_TITULAR                              NVARCHAR(50)  NULL,
    [Plan de acción  Caso]                             NVARCHAR(100) NULL,
    [ISC (Índice de Satisfacción del Cliente): Ref.]   NVARCHAR(100) NULL,
    [TENTA FO]                                          NVARCHAR(50)  NULL,
    [ESTADO DETRACTOR]                                 NVARCHAR(20)  NULL
);
GO

USE [CL_CARTERA];
GO

IF OBJECT_ID('dbo.TBL_HISTORIAL_CARTERA', 'U') IS NOT NULL DROP TABLE dbo.TBL_HISTORIAL_CARTERA;
CREATE TABLE dbo.TBL_HISTORIAL_CARTERA (
    RUT_DV          NVARCHAR(20)  NULL,
    SUB_SEGME       NVARCHAR(100) NULL,
    NOMBRE_CLIENTE  NVARCHAR(200) NULL,
    SEGME           NVARCHAR(100) NULL,
    ID_GENESM       NVARCHAR(50)  NULL,
    NOM_SM          NVARCHAR(200) NULL,
    NOM_SUP         NVARCHAR(200) NULL,
    RUT_SM          NVARCHAR(20)  NULL,
    Etiqueta        NVARCHAR(100) NULL,
    cod_dni         NVARCHAR(50)  NULL,
    RUT_SIN_DV      NVARCHAR(20)  NULL,
    FECHA_INICIO    INT           NULL,  -- formato AAAAMMDD, ej. 20260101
    FECHA_FIN       INT           NULL   -- formato AAAAMMDD, ej. 20261231
);
GO
