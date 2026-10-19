-- 16_Gerencia: amplia las 2 columnas que truncaban datos reales (decision del
-- usuario 2026-10-19: ampliar la columna en vez de truncar).
--   TBL_VOLUMETRIA_ESCALAMIENTO.[Cargo]          varchar(30) -> varchar(255)  (max. real 48)
--   TBL_VOLUMETRIA_CLOSE_THE_LOOP.[Causa Raiz]   varchar(30) -> varchar(255)  (max. real 33)
-- 255 = ancho con el que el Excel Source entrega el texto (DT_WSTR 255).
-- Sin vistas/SP/estadisticas dependientes (sys.sql_expression_dependencies).
-- Idempotente: se puede volver a ejecutar.

IF COL_LENGTH('dbo.TBL_VOLUMETRIA_ESCALAMIENTO', 'Cargo') < 255
    ALTER TABLE [dbo].[TBL_VOLUMETRIA_ESCALAMIENTO]
        ALTER COLUMN [Cargo] varchar(255) COLLATE Modern_Spanish_CI_AS NULL;

IF COL_LENGTH('dbo.TBL_VOLUMETRIA_CLOSE_THE_LOOP', 'Causa Raiz') < 255
    ALTER TABLE [dbo].[TBL_VOLUMETRIA_CLOSE_THE_LOOP]
        ALTER COLUMN [Causa Raiz] varchar(255) COLLATE Modern_Spanish_CI_AS NULL;
