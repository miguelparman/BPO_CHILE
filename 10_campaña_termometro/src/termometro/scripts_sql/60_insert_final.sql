-- Reemplaza el Execute SQL Task "TBL_CAMPAÑA_TERMOMETRO"
-- Se mantiene como SQL de conjunto (no se reimplementa en pandas) porque usa
-- ROW_NUMBER() particionado y varios joins condicionados por fecha: hacerlo en
-- SQL Server es más simple, más rápido y de mucho menor riesgo que replicar la
-- misma lógica en memoria con pandas.
--
-- Parámetros: fecha_evaluacion, fecha_fin_evaluacion, periodo

INSERT INTO [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO]
    (
    [RUT]
    ,[NOMCLI]
    ,[SEGME]
    ,[SUB_SEGME]
    ,[NOM_SM]
    ,[NOM_SUP]
    ,[PERIODO]
    ,[Fecha de la encuesta]
    ,[Estado]
    ,[Prom 11.]
    ,[Prom 14.]
    ,[NPS]
    ,[cod_dni]
    ,[Etiqueta]
    ,[Semana Fecha de la encuesta]
    ,[Semana Fecha de la encuesta2]
    ,[RUT_SIN_DV]
    ,[ESTADO GENERAL]
    ,[ESTADO EFECTIVO]
    ,[ID_GENESYS_SM_TITULAR]
    ,[Plan de acción  Caso]
    ,[ISC (Índice de Satisfacción del Cliente): Ref.]
    ,[TENTA FO]
    ,[ESTADO DETRACTOR]
    )
SELECT
     X0.[RUT]
    ,X0.[NOMCLI]
    ,X0.[SEGME]
    ,X0.[SUB_SEGME]
    ,X0.[NOM_SM]
    ,X0.[NOM_SUP]
    ,X0.[PERIODO]
    ,X0.[Fecha de la encuesta]
    ,X0.[Estado]
    ,X0.[Prom 11.]
    ,X0.[Prom 14.]
    ,X0.[NPS]
    ,X0.[cod_dni]
    ,X0.[Etiqueta]
    ,X0.[Semana Fecha de la encuesta]
    ,X0.[Semana Fecha de la encuesta2]
    ,X0.[RUT_SIN_DV]
    ,CASE WHEN X0.Estado = 'NO RECORRIDO' THEN 'NO RECORRIDO' ELSE 'RECORRIDO' END [ESTADO GENERAL]
    ,CASE WHEN X0.Estado IN ('NO RECORRIDO', 'SIN CONTACTO') THEN 'NO CONTACTADO' ELSE 'CONTACTADO' END [ESTADO EFECTIVO]
    ,X0.[ID_GENESYS_SM_TITULAR]
    ,X0.[Plan de acción  Caso]
    ,X0.[ISC (Índice de Satisfacción del Cliente): Ref.]
    ,X0.[TENTA FO]
    ,X0.[ESTADO DETRACTOR]
FROM
(
    SELECT
        X0.[RUT]
        ,X4.NOMBRE_CLIENTE [NOMCLI]
        ,X4.SEGMENTO [SEGME]
        ,X4.SUB_SEGMENTO [SUB_SEGME]
        ,X4.[ID_GENESYS_SM_TITULAR]
        ,X4.[NOM_SM]
        ,X4.[NOM_SUP]
        ,X0.[PERIODO]
        ,X1.[Fecha de la encuesta]
        ,CASE WHEN X1.Estado IS NULL THEN 'NO RECORRIDO' ELSE X1.Estado END [Estado]
        ,X2.[Prom 11.]
        ,X3.[Prom 14.]
        ,X3.[NPS]
        ,X4.[cod_dni]
        ,X4.[Etiqueta]
        ,CASE
            WHEN X1.[Fecha de la encuesta] IS NULL THEN NULL
            WHEN DAY(X1.[Fecha de la encuesta]) <= 7 THEN 'Semana 01'
            WHEN DAY(X1.[Fecha de la encuesta]) <= 14 THEN 'Semana 02'
            WHEN DAY(X1.[Fecha de la encuesta]) <= 21 THEN 'Semana 03'
            ELSE 'Semana 04'
        END [Semana Fecha de la encuesta]
        ,CASE
            WHEN X1.[Fecha de la encuesta] IS NULL THEN NULL
            ELSE CONCAT('Semana 0', DATEPART(WEEK, X1.[Fecha de la encuesta]) - DATEPART(WEEK, DATEADD(DD, -DAY(X1.[Fecha de la encuesta]) + 1, X1.[Fecha de la encuesta])) + 1)
        END [Semana Fecha de la encuesta2]
        ,X0.[RUT_SIN_DV]
        ,X1.[Plan de acción  Caso]
        ,X1.[ISC (Índice de Satisfacción del Cliente): Ref.]
        ,X0.[TENTA FO]
        ,CASE WHEN X5.RUT_SIN_DV IS NOT NULL THEN 'DETRACTOR' ELSE '-' END [ESTADO DETRACTOR]
    FROM
        [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SOURCE] X0 WITH(NOLOCK)
    -- ESTADO TERMÓMETRO (última encuesta del periodo por cliente)
    LEFT JOIN
        (
            SELECT
                 X0.[No  identificación fiscal]
                ,X0.[PERIODO]
                ,X0.[Fecha de la encuesta]
                ,X0.[Estado]
                ,X0.[Plan de acción  Caso]
                ,X0.[ISC (Índice de Satisfacción del Cliente): Ref.]
            FROM
            (
                SELECT
                    [No  identificación fiscal]
                    ,[PERIODO]
                    ,[Fecha de la encuesta]
                    ,[Estado]
                    ,[Peso]
                    ,[Plan de acción  Caso]
                    ,[ISC (Índice de Satisfacción del Cliente): Ref.]
                    -- Desempate agregado 2026-10-07 (no estaba en el .dtsx): con misma Fecha y Peso,
                    -- 1) la encuesta con Plan de acción Caso, 2) la ISC más reciente (Ref. correlativa).
                    -- Sin esto, SQL Server elegía una al azar en cada corrida.
                    ,ROW_NUMBER() OVER(
                        PARTITION BY [No  identificación fiscal]
                        ORDER BY
                            [No  identificación fiscal]
                            ,[Peso]
                            ,[Fecha de la encuesta] DESC
                            ,CASE WHEN [Plan de acción  Caso] IS NOT NULL THEN 0 ELSE 1 END
                            ,TRY_CAST(REPLACE([ISC (Índice de Satisfacción del Cliente): Ref.], 'ISC - ', '') AS INT) DESC
                    ) [Orden]
                FROM
                    [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP] WITH(NOLOCK)
                WHERE
                    [Fecha de la encuesta] BETWEEN :fecha_evaluacion AND :fecha_fin_evaluacion
                    AND PERIODO = :periodo
            ) X0
            WHERE X0.[Orden] = 1
        ) X1
    ON
        X1.[No  identificación fiscal] = X0.[RUT_SIN_DV]
    -- PROMEDIO NOTA TERMOMETRO 11
    LEFT JOIN
        (
        SELECT
            [No  identificación fiscal]
            ,ROUND(CONVERT(DECIMAL(5,2), AVG(CONVERT(DECIMAL(5,2), [11. Satisfacción general]))), 2) [Prom 11.]
        FROM
            [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP] WITH(NOLOCK)
        WHERE
            [11. Satisfacción general] IS NOT NULL
            AND [Fecha de la encuesta] BETWEEN :fecha_evaluacion AND :fecha_fin_evaluacion
            AND PERIODO = :periodo
        GROUP BY
            [No  identificación fiscal]
        ) X2
    ON
        X2.[No  identificación fiscal] = X0.[RUT_SIN_DV]
    -- PROMEDIO NOTA 14 (NPS)
    LEFT JOIN
        (
        SELECT
            [No  identificación fiscal]
            ,ROUND(CONVERT(DECIMAL(5,2), AVG(CONVERT(DECIMAL(5,2), [14. Probabilidad de recomendación]))), 2) [Prom 14.]
            ,CASE
                WHEN AVG(CONVERT(DECIMAL(5,2), [14. Probabilidad de recomendación])) <= 6 THEN 'Detractor'
                WHEN AVG(CONVERT(DECIMAL(5,2), [14. Probabilidad de recomendación])) <= 8 THEN 'Neutro'
                ELSE 'Promotor'
            END [NPS]
        FROM
            [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_SF_TEMP] WITH(NOLOCK)
        WHERE
            [14. Probabilidad de recomendación] IS NOT NULL
            AND [Fecha de la encuesta] BETWEEN :fecha_evaluacion AND :fecha_fin_evaluacion
            AND PERIODO = :periodo
        GROUP BY
            [No  identificación fiscal]
        ) X3
    ON
        X3.[No  identificación fiscal] = X0.[RUT_SIN_DV]
    -- CARTERA VIGENTE A LA FECHA DE EVALUACIÓN
    LEFT JOIN
        (
            SELECT
                RIGHT('000' + LEFT(REPLACE(X0.[RUT_DV], '-', ''), LEN(REPLACE(X0.[RUT_DV], '-', '')) - 1), 10) [RUT]
                ,[SUB_SEGME] SUB_SEGMENTO
                ,NOMBRE_CLIENTE
                ,[SEGME] SEGMENTO
                ,[ID_GENESM] [ID_GENESYS_SM_TITULAR]
                ,[NOM_SM]
                ,[NOM_SUP]
                ,[RUT_SM] RUT_SM_TITULAR
                ,Etiqueta
                ,cod_dni
                ,RUT_SIN_DV
            FROM
                [CL_CARTERA].[dbo].[TBL_HISTORIAL_CARTERA] X0 WITH(NOLOCK)
            WHERE
                CAST(CONVERT(VARCHAR(8), CAST(:fecha_evaluacion AS DATE), 112) AS INT) BETWEEN FECHA_INICIO AND FECHA_FIN
        ) X4
    ON
        X4.[RUT_SIN_DV] = X0.[RUT_SIN_DV]
    -- MARCA DE DETRACTOR
    LEFT JOIN
        (
        SELECT
            [PERIODO]
            ,[RUT_SIN_DV]
        FROM
            [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO_DETRACTOR]
        ) X5
    ON
        X5.RUT_SIN_DV = X0.RUT_SIN_DV
) X0;
