-- Capa SILVER de la estructura medallion (ver src/correos/silver/cargar.py):
-- las tablas de bronze (ver 01_bronze.sql) limpias + columnas derivadas. La
-- llena main.py (etapa silver) leyendo bronze, nunca los .xlsx directamente.
-- Gold lee SOLO de estas tablas.
--
-- Usa IF OBJECT_ID(...) IS NULL (nunca DROP): 172.17.0.162 es el servidor
-- real -- volver a correrlo no toca la tabla ni sus datos.

USE [CL_MOVIL];
GO

IF OBJECT_ID('dbo.TBL_CORREO_REGISTRO_SILVER', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.TBL_CORREO_REGISTRO_SILVER (
        Bandeja                          NVARCHAR(255)  NULL,
        Tipo                              NVARCHAR(20)   NULL,
        FechaHora_UTC_Texto               DATETIME2(7)   NULL,  -- campo de control de periodo, igual que en bronze
        FechaHora                        DATETIME2(7)   NULL,
        Contacto                          NVARCHAR(MAX)  NULL,
        Asunto                            NVARCHAR(MAX)  NULL,
        ID_Mensaje                        NVARCHAR(200)  NULL,
        ConversationID                    NVARCHAR(200)  NULL,
        Asesor                            NVARCHAR(200)  NULL,
        ORIGEN                            NVARCHAR(400)  NULL,
        ASUNTO_AGRUPADO                   NVARCHAR(50)   NULL,  -- REBOTE / PRESENTACIÓN / PRUEBA / PROMO; NULL si ninguna regla calza (ver silver/mappings.REGLAS_ASUNTO_AGRUPADO)
        COORDINADOR                       NVARCHAR(400)  NULL,  -- ORIGEN sin 'Registro_' ni extension, '_' -> ' ' (ver silver/cargar.coordinador_desde_origen)
        ID_PLACE                          INT            NULL,  -- 'SM<n>@movistar.cl' -> 51030000 + n (ver silver/cargar.id_place_desde_bandeja)
        JEFATURA                          NVARCHAR(50)   NULL   -- [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO] por ID_PLACE + mes UTC (ver silver/cargar.agregar_jefatura)
    );

    CREATE INDEX IX_TBL_CORREO_REGISTRO_SILVER_FechaHoraUTC ON dbo.TBL_CORREO_REGISTRO_SILVER (FechaHora_UTC_Texto);
END
GO

-- Migracion: la primera version de silver copiaba de bronze los calculos de
-- la macro del Excel (EsPrimeraEntrada, TieneRespuesta, Tiempo_*_Horas,
-- Estado). No son confiables: se quitan de silver y quedan solo en bronze
-- (ver silver/mappings.COLUMNAS_EXCLUIDAS_SILVER).
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'EsPrimeraEntrada') IS NOT NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER DROP COLUMN EsPrimeraEntrada;
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'TieneRespuesta') IS NOT NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER DROP COLUMN TieneRespuesta;
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'Tiempo_Primera_Respuesta_Horas') IS NOT NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER DROP COLUMN Tiempo_Primera_Respuesta_Horas;
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'Estado') IS NOT NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER DROP COLUMN Estado;
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'Tiempo_Respuesta_Horas') IS NOT NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER DROP COLUMN Tiempo_Respuesta_Horas;
GO

-- Migracion: COORDINADOR se derivaba en gold (T-SQL sobre ORIGEN); ahora es
-- una columna derivada de silver. Queda NULL hasta la siguiente carga de
-- silver (main.py --desde silver --completo la llena para todo).
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'COORDINADOR') IS NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER ADD COORDINADOR NVARCHAR(400) NULL;
GO

-- Estado actual de cada bandeja (TBL_CORREO_BANDEJAS de bronze) + COORDINADOR + ID_PLACE.
-- Se reemplaza completa en cada corrida, igual que en bronze. Es el origen
-- de gold.DIM_BANDEJA.
IF OBJECT_ID('dbo.TBL_CORREO_BANDEJAS_SILVER', 'U') IS NULL
    CREATE TABLE dbo.TBL_CORREO_BANDEJAS_SILVER (
        Correo_Bandeja           NVARCHAR(255)  NULL,
        Asesor                    NVARCHAR(200)  NULL,
        UltimaRevisionEntrada     DATETIME2(7)   NULL,
        UltimaRevisionSalida      DATETIME2(7)   NULL,
        ORIGEN                    NVARCHAR(400)  NULL,
        COORDINADOR               NVARCHAR(400)  NULL,
        ID_PLACE                  INT            NULL   -- igual que en TBL_CORREO_REGISTRO_SILVER, desde Correo_Bandeja
    );
GO

-- Migracion: ID_PLACE (derivado de la bandeja) en las dos tablas silver.
-- Primero se llamo [ID PLACE] (con espacio): si existe se renombra, si no
-- se agrega. Una columna agregada queda NULL hasta la siguiente carga de
-- silver (main.py --desde silver --completo la llena para todo).
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'ID PLACE') IS NOT NULL
   AND COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'ID_PLACE') IS NULL
    EXEC sp_rename 'dbo.TBL_CORREO_REGISTRO_SILVER.[ID PLACE]', 'ID_PLACE', 'COLUMN';
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'ID_PLACE') IS NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER ADD ID_PLACE INT NULL;
IF COL_LENGTH('dbo.TBL_CORREO_BANDEJAS_SILVER', 'ID PLACE') IS NOT NULL
   AND COL_LENGTH('dbo.TBL_CORREO_BANDEJAS_SILVER', 'ID_PLACE') IS NULL
    EXEC sp_rename 'dbo.TBL_CORREO_BANDEJAS_SILVER.[ID PLACE]', 'ID_PLACE', 'COLUMN';
IF COL_LENGTH('dbo.TBL_CORREO_BANDEJAS_SILVER', 'ID_PLACE') IS NULL
    ALTER TABLE dbo.TBL_CORREO_BANDEJAS_SILVER ADD ID_PLACE INT NULL;
GO

-- Migracion: JEFATURA (cruce con la base de personal). Mismo ancho que
-- [Jefatura] en el origen. Queda NULL hasta la siguiente carga de silver.
IF COL_LENGTH('dbo.TBL_CORREO_REGISTRO_SILVER', 'JEFATURA') IS NULL
    ALTER TABLE dbo.TBL_CORREO_REGISTRO_SILVER ADD JEFATURA NVARCHAR(50) NULL;
GO
