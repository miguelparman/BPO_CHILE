"""Sentencias T-SQL de la capa GOLD (las ejecuta cargar.py). Todo corre en el
servidor: los cruces con las dimensiones son set-based y no hace falta
traer las filas a Python. DDL de las tablas: infra/sql/03_gold.sql.

Gold lee SOLO de silver (TBL_CORREO_REGISTRO_SILVER y
TBL_CORREO_BANDEJAS_SILVER), nunca de bronze."""

from __future__ import annotations

from gold.mappings import (
    DESFASE_HORAS_LOCAL,
    ESQUEMA_GOLD,
    TABLA_DIM_ASUNTO_AGRUPADO,
    TABLA_DIM_BANDEJA,
    TABLA_DIM_FECHA,
    TABLA_DIM_JEFATURA,
    TABLA_DIM_TIPO,
    TABLA_FACT_MENSAJE,
)
from silver.mappings import COLUMNA_CONTROL_FECHA, COLUMNA_NUMERO_CASO, TABLA_BANDEJAS_SILVER, TABLA_REGISTRO_SILVER
from silver.mappings import ESQUEMA as ESQUEMA_SILVER

SILVER = f"[{ESQUEMA_SILVER}].[{TABLA_REGISTRO_SILVER}]"
# Valor de FACT_MENSAJE.TABLA_ORIGEN: la tabla silver de la que sale cada fila.
TABLA_ORIGEN_FACT = f"{ESQUEMA_SILVER}.{TABLA_REGISTRO_SILVER}"
BANDEJAS = f"[{ESQUEMA_SILVER}].[{TABLA_BANDEJAS_SILVER}]"
FACT = f"[{ESQUEMA_GOLD}].[{TABLA_FACT_MENSAJE}]"
DIM_FECHA = f"[{ESQUEMA_GOLD}].[{TABLA_DIM_FECHA}]"
DIM_BANDEJA = f"[{ESQUEMA_GOLD}].[{TABLA_DIM_BANDEJA}]"
DIM_TIPO = f"[{ESQUEMA_GOLD}].[{TABLA_DIM_TIPO}]"
DIM_ASUNTO = f"[{ESQUEMA_GOLD}].[{TABLA_DIM_ASUNTO_AGRUPADO}]"
DIM_JEFATURA = f"[{ESQUEMA_GOLD}].[{TABLA_DIM_JEFATURA}]"

# 'FechaHora' ya viene en hora local (serial de Excel), pero con artefactos
# de redondeo (ej. 09:37:13.999999): se redondea al segundo al pasar a
# DATETIME2(0) -- si no, 23:59:59.999999 caeria en el dia anterior. Si
# faltara, se deriva de la hora UTC con el desfase fijo.
_FECHA_HORA_LOCAL = (
    f"CAST(COALESCE(s.[FechaHora], DATEADD(HOUR, {DESFASE_HORAS_LOCAL}, s.[{COLUMNA_CONTROL_FECHA}])) AS DATETIME2(0))"
)

_WHERE_PERIODO_SILVER = f"s.[{COLUMNA_CONTROL_FECHA}] >= ? AND s.[{COLUMNA_CONTROL_FECHA}] < ?"


def rango_fechas_local(con_periodo: bool) -> str:
    sql = f"SELECT MIN(CAST({_FECHA_HORA_LOCAL} AS DATE)) AS DESDE, MAX(CAST({_FECHA_HORA_LOCAL} AS DATE)) AS HASTA FROM {SILVER} s"
    if con_periodo:
        sql += f" WHERE {_WHERE_PERIODO_SILVER}"
    return sql


# Calendario: inserta solo las fechas que faltan entre dos dias. Nombres en
# espanol con CHOOSE (no depende del SET LANGUAGE del login) y dia de semana
# calculado contra 1900-01-01 (lunes), sin depender de SET DATEFIRST.
COMPLETAR_DIM_FECHA = f"""
WITH dias AS (
    SELECT CAST(? AS DATE) AS F
    UNION ALL
    SELECT DATEADD(DAY, 1, F) FROM dias WHERE F < CAST(? AS DATE)
)
INSERT INTO {DIM_FECHA}
    (FECHA_KEY, FECHA, ANIO, TRIMESTRE, MES, NOMBRE_MES, ANIO_MES, DIA, DIA_SEMANA, NOMBRE_DIA, SEMANA_ISO, ES_FIN_DE_SEMANA)
SELECT
    CONVERT(INT, CONVERT(CHAR(8), d.F, 112)),
    d.F,
    YEAR(d.F),
    DATEPART(QUARTER, d.F),
    MONTH(d.F),
    CHOOSE(MONTH(d.F), N'Enero', N'Febrero', N'Marzo', N'Abril', N'Mayo', N'Junio', N'Julio',
           N'Agosto', N'Septiembre', N'Octubre', N'Noviembre', N'Diciembre'),
    CONVERT(CHAR(7), d.F, 126),
    DAY(d.F),
    ds.N,
    CHOOSE(ds.N, N'Lunes', N'Martes', N'Miércoles', N'Jueves', N'Viernes', N'Sábado', N'Domingo'),
    DATEPART(ISO_WEEK, d.F),
    CASE WHEN ds.N >= 6 THEN 1 ELSE 0 END
FROM dias d
CROSS APPLY (SELECT DATEDIFF(DAY, '19000101', d.F) % 7 + 1 AS N) ds
WHERE NOT EXISTS (SELECT 1 FROM {DIM_FECHA} x WHERE x.FECHA = d.F)
OPTION (MAXRECURSION 0);
"""

COMPLETAR_DIM_TIPO = f"""
INSERT INTO {DIM_TIPO} (TIPO)
SELECT DISTINCT s.[Tipo] FROM {SILVER} s
WHERE s.[Tipo] IS NOT NULL AND s.[Tipo] <> N''
  AND NOT EXISTS (SELECT 1 FROM {DIM_TIPO} d WHERE d.TIPO = s.[Tipo]);
"""


def completar_dim_asunto(cantidad_reglas: int) -> str:
    """Grupos de las reglas (asi existen aunque aun no haya mensajes) + los
    que aparezcan en silver."""
    valores = ", ".join("(?)" for _ in range(cantidad_reglas))
    return f"""
INSERT INTO {DIM_ASUNTO} (ASUNTO_AGRUPADO)
SELECT g.GRUPO FROM (
    SELECT GRUPO FROM (VALUES {valores}) AS r (GRUPO)
    UNION
    SELECT DISTINCT s.[ASUNTO_AGRUPADO] FROM {SILVER} s WHERE s.[ASUNTO_AGRUPADO] IS NOT NULL
) g
WHERE g.GRUPO <> N'' AND NOT EXISTS (SELECT 1 FROM {DIM_ASUNTO} d WHERE d.ASUNTO_AGRUPADO = g.GRUPO);
"""


COMPLETAR_DIM_JEFATURA = f"""
INSERT INTO {DIM_JEFATURA} (JEFATURA)
SELECT DISTINCT s.[JEFATURA] FROM {SILVER} s
WHERE s.[JEFATURA] IS NOT NULL AND s.[JEFATURA] <> N''
  AND NOT EXISTS (SELECT 1 FROM {DIM_JEFATURA} d WHERE d.JEFATURA = s.[JEFATURA]);
"""


# Origen de DIM_BANDEJA: TBL_CORREO_BANDEJAS_SILVER (estado actual,
# preferido) + bandejas que solo aparecen en los mensajes (su asesor/origen
# del mensaje mas reciente). ROW_NUMBER defensivo: el MERGE falla si una
# bandeja llega dos veces. COORDINADOR e ID_PLACE ya vienen calculados desde silver.
MERGE_DIM_BANDEJA = f"""
WITH desde_bandejas AS (
    SELECT b.Correo_Bandeja AS BANDEJA, b.ID_PLACE, b.Asesor AS ASESOR, b.COORDINADOR, b.ORIGEN,
           b.UltimaRevisionEntrada AS ENTRADA, b.UltimaRevisionSalida AS SALIDA,
           ROW_NUMBER() OVER (PARTITION BY b.Correo_Bandeja ORDER BY b.UltimaRevisionEntrada DESC, b.ORIGEN) AS RN
    FROM {BANDEJAS} b
    WHERE b.Correo_Bandeja IS NOT NULL AND b.Correo_Bandeja <> N''
),
desde_mensajes AS (
    SELECT s.[Bandeja] AS BANDEJA, s.[ID_PLACE], s.[Asesor] AS ASESOR, s.[COORDINADOR], s.[ORIGEN],
           CAST(NULL AS DATETIME2) AS ENTRADA, CAST(NULL AS DATETIME2) AS SALIDA,
           ROW_NUMBER() OVER (PARTITION BY s.[Bandeja] ORDER BY s.[{COLUMNA_CONTROL_FECHA}] DESC) AS RN
    FROM {SILVER} s
    WHERE s.[Bandeja] IS NOT NULL AND s.[Bandeja] <> N''
      AND NOT EXISTS (SELECT 1 FROM {BANDEJAS} b WHERE b.Correo_Bandeja = s.[Bandeja])
),
origen AS (
    SELECT * FROM desde_bandejas WHERE RN = 1
    UNION ALL
    SELECT * FROM desde_mensajes WHERE RN = 1
)
MERGE {DIM_BANDEJA} AS d
USING origen AS o ON d.BANDEJA = o.BANDEJA
WHEN MATCHED THEN UPDATE SET
    d.ID_PLACE = o.ID_PLACE,
    d.ASESOR = o.ASESOR,
    d.COORDINADOR = o.COORDINADOR,
    d.ORIGEN = o.ORIGEN,
    d.ULTIMA_REVISION_ENTRADA_UTC = o.ENTRADA,
    d.ULTIMA_REVISION_SALIDA_UTC = o.SALIDA
WHEN NOT MATCHED BY TARGET THEN INSERT
    (BANDEJA, ID_PLACE, ASESOR, COORDINADOR, ORIGEN, ULTIMA_REVISION_ENTRADA_UTC, ULTIMA_REVISION_SALIDA_UTC)
    VALUES (o.BANDEJA, o.ID_PLACE, o.ASESOR, o.COORDINADOR, o.ORIGEN, o.ENTRADA, o.SALIDA);
"""


def insert_fact(con_periodo: bool) -> str:
    """Silver -> FACT_MENSAJE. LEFT JOIN + ISNULL(..., 0): un valor NULL (o
    sin match) apunta al miembro vacio de clave 0 en vez de perder la fila.

    Parametros, en orden: TABLA_ORIGEN, PROCESO_CARGA, ID_EJECUCION,
    FECHA_CARGA (columnas de auditoria, ver cargar._params_auditoria) y, si
    con_periodo, inicio y fin del periodo."""
    sql = f"""
INSERT INTO {FACT}
    (FECHA_KEY, HORA_LOCAL, BANDEJA_KEY, TIPO_KEY, ASUNTO_AGRUPADO_KEY, JEFATURA_KEY,
     ID_MENSAJE, CONVERSATION_ID, NUMERO_CASO, ASUNTO, CONTACTO, FECHA_HORA_UTC, FECHA_HORA_LOCAL, CANTIDAD,
     TABLA_ORIGEN, PROCESO_CARGA, ID_EJECUCION, FECHA_CARGA)
SELECT
    CONVERT(INT, CONVERT(CHAR(8), CAST(l.FECHA_HORA_LOCAL AS DATE), 112)),
    DATEPART(HOUR, l.FECHA_HORA_LOCAL),
    ISNULL(b.BANDEJA_KEY, 0),
    ISNULL(t.TIPO_KEY, 0),
    ISNULL(a.ASUNTO_AGRUPADO_KEY, 0),
    ISNULL(j.JEFATURA_KEY, 0),
    s.[ID_Mensaje], s.[ConversationID], s.[{COLUMNA_NUMERO_CASO}], s.[Asunto], s.[Contacto],
    s.[{COLUMNA_CONTROL_FECHA}], l.FECHA_HORA_LOCAL, 1,
    ?, ?, ?, ?
FROM {SILVER} s
CROSS APPLY (SELECT {_FECHA_HORA_LOCAL} AS FECHA_HORA_LOCAL) l
LEFT JOIN {DIM_BANDEJA} b ON b.BANDEJA = s.[Bandeja]
LEFT JOIN {DIM_TIPO} t ON t.TIPO = s.[Tipo]
LEFT JOIN {DIM_ASUNTO} a ON a.ASUNTO_AGRUPADO = s.[ASUNTO_AGRUPADO]
LEFT JOIN {DIM_JEFATURA} j ON j.JEFATURA = s.[JEFATURA]
"""
    if con_periodo:
        sql += f"WHERE {_WHERE_PERIODO_SILVER}\n"
    return sql


# NUMERO_CASO de silver se recalcula en TODA la tabla en cada corrida (un
# caso puede abrirse despues del correo): se replica a los hechos de
# periodos que ya no se recargan. Es el mismo valor para toda la
# conversacion, por eso basta un valor por ConversationID.
ACTUALIZAR_NUMERO_CASO_FACT = f"""
UPDATE f SET f.NUMERO_CASO = c.NUMERO_CASO
FROM {FACT} f
LEFT JOIN (
    SELECT s.[ConversationID], MAX(s.[{COLUMNA_NUMERO_CASO}]) AS NUMERO_CASO
    FROM {SILVER} s
    WHERE s.[ConversationID] IS NOT NULL
    GROUP BY s.[ConversationID]
) c ON c.[ConversationID] = f.CONVERSATION_ID
WHERE ISNULL(f.NUMERO_CASO, '') <> ISNULL(c.NUMERO_CASO, '');
"""


DELETE_FACT_PERIODO = f"DELETE FROM {FACT} WHERE FECHA_HORA_UTC >= ? AND FECHA_HORA_UTC < ?"


def validar(con_periodo: bool) -> str:
    where_silver = f" WHERE {_WHERE_PERIODO_SILVER}" if con_periodo else ""
    where_fact = " WHERE FECHA_HORA_UTC >= ? AND FECHA_HORA_UTC < ?" if con_periodo else " WHERE 1 = 1"
    return f"""
SELECT
    (SELECT COUNT(*) FROM {SILVER} s{where_silver}) AS FILAS_SILVER,
    (SELECT COUNT(*) FROM {FACT}{where_fact}) AS FILAS_FACT,
    (SELECT COUNT(*) FROM {FACT}{where_fact} AND (BANDEJA_KEY = 0 OR TIPO_KEY = 0)) AS FILAS_SIN_BANDEJA_O_TIPO,
    (SELECT COUNT(*) FROM {FACT}{where_fact}
        AND (TABLA_ORIGEN IS NULL OR PROCESO_CARGA IS NULL OR ID_EJECUCION IS NULL OR FECHA_CARGA IS NULL)
    ) AS FILAS_SIN_AUDITORIA,
    (SELECT COUNT(*) FROM {FACT}{where_fact} AND JEFATURA_KEY = 0) AS FILAS_SIN_JEFATURA
"""
