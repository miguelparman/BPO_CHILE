"""Capa SILVER de la estructura medallion de 11_correos:

- Bronze: TBL_CORREO_REGISTRO -- los 'Registro' de los .xlsx tal cual (+ ORIGEN),
  cargada por bronze/cargar.py.
- Silver (se construye LEYENDO bronze, nunca los .xlsx):
  - TBL_CORREO_REGISTRO_SILVER: sin las columnas calculadas por el Excel que
    no son confiables (silver/mappings.COLUMNAS_EXCLUIDAS_SILVER), y con
    columnas derivadas: ASUNTO_AGRUPADO (ver
    silver/mappings.REGLAS_ASUNTO_AGRUPADO), COORDINADOR, ID_PLACE y
    JEFATURA (cruce con silver/mappings.TABLA_PERSONAL por ID_PLACE + mes)
    y NUMERO_CASO (cruce con silver/mappings.TABLA_SEGUIMIENTO por
    ConversationID; se recalcula sobre toda la tabla en cada corrida).
  - TBL_CORREO_BANDEJAS_SILVER: TBL_CORREO_BANDEJAS + COORDINADOR + ID_PLACE.
- Gold: modelo estrella en el esquema 'gold', lee SOLO de silver -- ver
  gold/cargar.py.

Registro: misma estrategia de carga que bronze, por periodo (DELETE + INSERT
del rango sobre FechaHora_UTC_Texto), o completa (TRUNCATE + INSERT de todo
bronze) para la carga inicial / una reconstruccion. Bandejas: siempre
completa, igual que en bronze.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime

import pandas as pd

from bronze.mappings import COLUMNA_CONTROL_FECHA, COLUMNA_ORIGEN, TABLA_BANDEJAS, TABLA_REGISTRO
from bronze.mappings import ESQUEMA as ESQUEMA_BRONZE
from comun.logging_setup import NOMBRE_LOGGER
from silver.mappings import (
    COLUMNA_ASUNTO_AGRUPADO,
    COLUMNA_COORDINADOR,
    COLUMNA_ID_PLACE,
    COLUMNA_JEFATURA,
    COLUMNA_NUMERO_CASO,
    COLUMNAS_BANDEJAS_SILVER_DESDE_BRONZE,
    COLUMNAS_SILVER_DESDE_BRONZE,
    BASE_ID_PLACE,
    CAMPO_ASUNTO,
    CAMPO_CONTACTO,
    ESQUEMA,
    PATRON_BANDEJA_ID_PLACE,
    REGLAS_ASUNTO_AGRUPADO,
    SEPARADOR_CASOS,
    TABLA_BANDEJAS_SILVER,
    TABLA_PERSONAL,
    TABLA_REGISTRO_SILVER,
    TABLA_SEGUIMIENTO,
)

_PREFIJO_ORIGEN = "registro_"
_PATRON_ID_PLACE = re.compile(PATRON_BANDEJA_ID_PLACE, re.IGNORECASE)

logger = logging.getLogger(NOMBRE_LOGGER)


def _normalizar(texto: str) -> str:
    """Minusculas y sin tildes ('Presentación' -> 'presentacion'), para que
    las reglas no dependan de como se escribio el asunto."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return sin_tildes.casefold()


def _patron(textos: list[str], palabra_completa: bool) -> re.Pattern[str]:
    """Una regex por regla de asunto. Con palabra_completa, el texto no puede
    tener una letra/digito pegado antes ni despues ('presentacion' calza en
    '[Presentación]' pero no en 'representación')."""
    alternativas = "|".join(re.escape(_normalizar(t)) for t in textos)
    if palabra_completa:
        return re.compile(rf"(?<!\w)(?:{alternativas})(?!\w)")
    return re.compile(alternativas)


def _correos(contacto: object) -> set[str]:
    """Correos de 'Contacto' normalizados (puede traer varios separados por ';')."""
    if not isinstance(contacto, str):
        return set()
    return {_normalizar(c.strip()) for c in contacto.split(";") if c.strip()}


# Por regla: patron del asunto (CAMPO_ASUNTO) o conjunto de correos (CAMPO_CONTACTO).
_REGLAS_COMPILADAS = [
    (
        regla,
        _patron(regla.textos, regla.palabra_completa) if regla.campo == CAMPO_ASUNTO else None,
        {_normalizar(t) for t in regla.textos} if regla.campo == CAMPO_CONTACTO else None,
    )
    for regla in REGLAS_ASUNTO_AGRUPADO
]


def agrupar_asunto(asunto: object, contacto: object = None, tipo: object = None) -> str | None:
    """Devuelve el grupo de la primera regla que calza con el mensaje (asunto,
    contacto y tipo), o None si ninguna calza."""
    asunto_normalizado = _normalizar(asunto) if isinstance(asunto, str) and asunto.strip() else None
    correos = _correos(contacto)
    for regla, patron, correos_regla in _REGLAS_COMPILADAS:
        if regla.tipo is not None and tipo != regla.tipo:
            continue
        if patron is not None and asunto_normalizado is not None and patron.search(asunto_normalizado):
            return regla.grupo
        if correos_regla is not None and correos & correos_regla:
            return regla.grupo
    return None


def coordinador_desde_origen(origen: object) -> str | None:
    """Nombre del coordinador a partir del nombre del .xlsx: sin el prefijo
    'Registro_' (sin distinguir mayusculas), sin extension y con '_' -> ' '.
    'Registro_JHON_MORALES_PENA.xlsx' -> 'JHON MORALES PENA'. None si vacio."""
    if not isinstance(origen, str) or not origen.strip():
        return None
    nombre = origen.strip()
    if nombre.casefold().startswith(_PREFIJO_ORIGEN):
        nombre = nombre[len(_PREFIJO_ORIGEN) :]
    if "." in nombre:
        nombre = nombre.rsplit(".", 1)[0]
    nombre = nombre.replace("_", " ").strip()
    return nombre or None


def id_place_desde_bandeja(bandeja: object) -> int | None:
    """ID Place a partir de la bandeja: 'SM<n>@movistar.cl' -> BASE_ID_PLACE + n
    (sin distinguir mayusculas, ignorando espacios alrededor).
    'SM68@movistar.cl' -> 51030068. None si vacio o no calza el patron."""
    if not isinstance(bandeja, str):
        return None
    coincidencia = _PATRON_ID_PLACE.match(bandeja.strip())
    if coincidencia is None:
        return None
    return BASE_ID_PLACE + int(coincidencia.group(1))


def _con_id_place(df: pd.DataFrame, columna_bandeja: str) -> pd.DataFrame:
    # dtype 'Int64' (entero con NULL): con float, pyodbc mandaria 51030068.0.
    df[COLUMNA_ID_PLACE] = df[columna_bandeja].map(id_place_desde_bandeja).astype("Int64")
    sin_id = df.loc[df[COLUMNA_ID_PLACE].isna(), columna_bandeja]
    if not sin_id.empty:
        logger.warning(
            "  %s fila(s) sin %s (bandeja fuera del patron %s): %s",
            len(sin_id),
            COLUMNA_ID_PLACE,
            PATRON_BANDEJA_ID_PLACE,
            sorted(sin_id.fillna("(vacia)").astype(str).unique()),
        )
    return df


def construir_silver(bronze_df: pd.DataFrame) -> pd.DataFrame:
    df = bronze_df.copy()
    df[COLUMNA_ASUNTO_AGRUPADO] = [
        agrupar_asunto(asunto, contacto, tipo)
        for asunto, contacto, tipo in zip(df[CAMPO_ASUNTO], df[CAMPO_CONTACTO], df["Tipo"])
    ]
    df[COLUMNA_COORDINADOR] = df[COLUMNA_ORIGEN].map(coordinador_desde_origen)
    return _con_id_place(df, "Bandeja")


def periodo_desde_utc(fechas: pd.Series) -> pd.Series:
    """Periodo AAAAMM (entero, como [Periodo] de TABLA_PERSONAL) de cada
    FechaHora_UTC_Texto: 2026-09-30 23:10 UTC -> 202609. NULL si no hay fecha."""
    fechas = pd.to_datetime(fechas, errors="coerce")
    return (fechas.dt.year * 100 + fechas.dt.month).astype("Int64")


def jefatura_por_place_periodo(personal_df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (ID_PLACE, PERIODO) con su JEFATURA. [ID Place] es texto en
    el origen (trae valores como '-'): lo que no es numerico se descarta. Si un
    par tiene mas de una jefatura se toma la mas frecuente (empate: la primera
    alfabetica) y se avisa en el log."""
    df = pd.DataFrame(
        {
            COLUMNA_ID_PLACE: pd.to_numeric(personal_df["ID_PLACE"].astype(str).str.strip(), errors="coerce"),
            "PERIODO": pd.to_numeric(personal_df["PERIODO"], errors="coerce"),
            COLUMNA_JEFATURA: personal_df["JEFATURA"].where(personal_df["JEFATURA"].notna()).str.strip(),
        }
    ).dropna()
    df = df[df[COLUMNA_JEFATURA] != ""].astype({COLUMNA_ID_PLACE: "Int64", "PERIODO": "Int64"})

    claves = [COLUMNA_ID_PLACE, "PERIODO"]
    conteo = df.groupby([*claves, COLUMNA_JEFATURA]).size().reset_index(name="N")
    ambiguos = conteo.groupby(claves).size()
    ambiguos = ambiguos[ambiguos > 1]
    if not ambiguos.empty:
        logger.warning(
            "  %s par(es) ID_PLACE/periodo con mas de una jefatura en %s; se toma la mas frecuente: %s",
            len(ambiguos),
            TABLA_PERSONAL,
            [(int(i), int(p)) for i, p in ambiguos.index],
        )
    conteo = conteo.sort_values([*claves, "N", COLUMNA_JEFATURA], ascending=[True, True, False, True])
    return conteo.drop_duplicates(claves)[[*claves, COLUMNA_JEFATURA]].reset_index(drop=True)


def agregar_jefatura(silver_df: pd.DataFrame, jefaturas_df: pd.DataFrame) -> pd.DataFrame:
    """Left join de silver con jefatura_por_place_periodo() por ID_PLACE + mes
    UTC. No cambia la cantidad de filas (las claves de jefaturas_df son unicas)."""
    df = silver_df.copy()
    df["PERIODO"] = periodo_desde_utc(df[COLUMNA_CONTROL_FECHA])
    df = df.merge(jefaturas_df, how="left", on=[COLUMNA_ID_PLACE, "PERIODO"], validate="many_to_one")
    df[COLUMNA_JEFATURA] = df[COLUMNA_JEFATURA].astype(object).where(df[COLUMNA_JEFATURA].notna(), None)

    sin_jefatura = df[df[COLUMNA_JEFATURA].isna()]
    if not sin_jefatura.empty:
        pares = sin_jefatura.groupby([COLUMNA_ID_PLACE, "PERIODO"], dropna=False).size()
        logger.warning(
            "  %s fila(s) sin %s (ID_PLACE/periodo sin fila en %s): %s",
            len(sin_jefatura),
            COLUMNA_JEFATURA,
            TABLA_PERSONAL,
            [(str(i), str(p), int(n)) for (i, p), n in pares.items()],
        )
    return df.drop(columns="PERIODO")


def _con_jefatura(gateway, silver_df: pd.DataFrame) -> pd.DataFrame:
    """Lee de TABLA_PERSONAL solo los meses presentes en silver_df y cruza."""
    periodos = sorted(int(p) for p in periodo_desde_utc(silver_df[COLUMNA_CONTROL_FECHA]).dropna().unique())
    if not periodos:
        return silver_df.assign(**{COLUMNA_JEFATURA: None})
    placeholders = ", ".join("?" for _ in periodos)
    personal_df = gateway.fetch_dataframe(
        f"SELECT [ID Place] AS ID_PLACE, [Periodo] AS PERIODO, [Jefatura] AS JEFATURA FROM {TABLA_PERSONAL} "
        f"WHERE [Periodo] IN ({placeholders}) AND [Jefatura] IS NOT NULL",
        periodos,
    )
    logger.info("%s fila(s) leidas de %s para los periodos %s.", len(personal_df), TABLA_PERSONAL, periodos)
    if personal_df.empty:
        personal_df = pd.DataFrame(columns=["ID_PLACE", "PERIODO", "JEFATURA"])
    df = agregar_jefatura(silver_df, jefatura_por_place_periodo(personal_df))
    for jefatura, cantidad in df[COLUMNA_JEFATURA].fillna("(sin jefatura)").value_counts().items():
        logger.info("  %s = %s: %s fila(s)", COLUMNA_JEFATURA, jefatura, cantidad)
    return df


# Casos por ConversationID: [To Addres] normalizado (sin espacios, en
# mayusculas) = ConversationID normalizado. Solo se consideran los [To Addres]
# con forma de ConversationID (32 caracteres hexadecimales): el resto son
# correos y nunca calzan. Todos los casos de la conversacion, por apertura.
# Solo actualiza las filas cuyo valor cambia (incluye volver a NULL).
ACTUALIZAR_NUMERO_CASO = f"""
WITH casos AS (
    SELECT
        UPPER(LTRIM(RTRIM(t.[To Addres]))) AS CONVERSATION_ID,
        STRING_AGG(CAST(LTRIM(RTRIM(t.[Número del caso])) AS VARCHAR(MAX)), '{SEPARADOR_CASOS}')
            WITHIN GROUP (ORDER BY t.[Fecha/Hora de apertura], t.[Número del caso]) AS {COLUMNA_NUMERO_CASO}
    FROM {TABLA_SEGUIMIENTO} t
    WHERE LEN(LTRIM(RTRIM(t.[To Addres]))) = 32
      AND LTRIM(RTRIM(t.[To Addres])) NOT LIKE '%[^0-9A-Fa-f]%'
      AND t.[Número del caso] IS NOT NULL
    GROUP BY UPPER(LTRIM(RTRIM(t.[To Addres])))
)
UPDATE s SET s.[{COLUMNA_NUMERO_CASO}] = c.{COLUMNA_NUMERO_CASO}
FROM [{ESQUEMA}].[{TABLA_REGISTRO_SILVER}] s
LEFT JOIN casos c ON c.CONVERSATION_ID = UPPER(LTRIM(RTRIM(s.[ConversationID])))
WHERE ISNULL(s.[{COLUMNA_NUMERO_CASO}], '') <> ISNULL(c.{COLUMNA_NUMERO_CASO}, '');
"""

CONTAR_NUMERO_CASO = (
    f"SELECT COUNT(*) AS FILAS, COUNT(s.[{COLUMNA_NUMERO_CASO}]) AS CON_CASO "
    f"FROM [{ESQUEMA}].[{TABLA_REGISTRO_SILVER}] s"
)


def actualizar_numero_caso(gateway) -> int:
    """Recalcula NUMERO_CASO en TODA la tabla silver (no solo el periodo):
    un caso puede abrirse dias despues del correo. Devuelve filas cambiadas."""
    cambiadas = gateway.execute_script_rowcount(ACTUALIZAR_NUMERO_CASO)
    conteo = gateway.fetch_dataframe(CONTAR_NUMERO_CASO)
    if not conteo.empty:
        filas, con_caso = int(conteo.iloc[0]["FILAS"]), int(conteo.iloc[0]["CON_CASO"])
        logger.info(
            "%s: %s fila(s) cambiadas; %s de %s fila(s) de [%s].[%s] con caso (%s).",
            COLUMNA_NUMERO_CASO,
            cambiadas,
            con_caso,
            filas,
            ESQUEMA,
            TABLA_REGISTRO_SILVER,
            TABLA_SEGUIMIENTO,
        )
    return cambiadas


def construir_bandejas_silver(bronze_df: pd.DataFrame) -> pd.DataFrame:
    df = bronze_df.copy()
    df[COLUMNA_COORDINADOR] = df[COLUMNA_ORIGEN].map(coordinador_desde_origen)
    return _con_id_place(df, "Correo_Bandeja")


def _select_bronze(con_periodo: bool) -> str:
    columnas_sql = ", ".join(f"[{c}]" for c in COLUMNAS_SILVER_DESDE_BRONZE)
    sql = f"SELECT {columnas_sql} FROM [{ESQUEMA_BRONZE}].[{TABLA_REGISTRO}]"
    if con_periodo:
        sql += f" WHERE [{COLUMNA_CONTROL_FECHA}] >= ? AND [{COLUMNA_CONTROL_FECHA}] < ?"
    return sql


def _log_reparto(silver_df: pd.DataFrame) -> None:
    reparto = silver_df[COLUMNA_ASUNTO_AGRUPADO].fillna("(sin grupo)").value_counts()
    for grupo, cantidad in reparto.items():
        logger.info("  %s = %s: %s fila(s)", COLUMNA_ASUNTO_AGRUPADO, grupo, cantidad)


def cargar_periodo_silver(gateway, fecha_inicio: datetime, fecha_fin: datetime) -> tuple[int, int]:
    """Reconstruye en silver solo el periodo [fecha_inicio, fecha_fin) desde
    bronze. Devuelve (filas_eliminadas, filas_insertadas)."""
    bronze_df = gateway.fetch_dataframe(_select_bronze(con_periodo=True), (fecha_inicio, fecha_fin))
    logger.info(
        "%s fila(s) leidas de [%s].[%s] (bronze) para el periodo [%s, %s).",
        len(bronze_df),
        ESQUEMA_BRONZE,
        TABLA_REGISTRO,
        fecha_inicio,
        fecha_fin,
    )
    silver_df = _con_jefatura(gateway, construir_silver(bronze_df))
    _log_reparto(silver_df)

    eliminadas = gateway.execute_script_rowcount(
        f"DELETE FROM [{ESQUEMA}].[{TABLA_REGISTRO_SILVER}] "
        f"WHERE [{COLUMNA_CONTROL_FECHA}] >= ? AND [{COLUMNA_CONTROL_FECHA}] < ?",
        (fecha_inicio, fecha_fin),
    )
    logger.info("%s fila(s) eliminadas de [%s].[%s] para el periodo.", eliminadas, ESQUEMA, TABLA_REGISTRO_SILVER)
    insertadas = gateway.bulk_insert(TABLA_REGISTRO_SILVER, silver_df, schema=ESQUEMA)
    actualizar_numero_caso(gateway)
    return eliminadas, insertadas


def recargar_silver_completo(gateway) -> int:
    """Reconstruye silver completa desde TODO bronze (carga inicial, o tras
    cambiar las reglas). Devuelve filas insertadas."""
    bronze_df = gateway.fetch_dataframe(_select_bronze(con_periodo=False))
    logger.info("%s fila(s) leidas de [%s].[%s] (bronze, completo).", len(bronze_df), ESQUEMA_BRONZE, TABLA_REGISTRO)
    silver_df = _con_jefatura(gateway, construir_silver(bronze_df))
    _log_reparto(silver_df)

    gateway.truncate_table(TABLA_REGISTRO_SILVER, schema=ESQUEMA)
    insertadas = gateway.bulk_insert(TABLA_REGISTRO_SILVER, silver_df, schema=ESQUEMA)
    actualizar_numero_caso(gateway)
    return insertadas


def cargar_bandejas_silver(gateway) -> int:
    """TBL_CORREO_BANDEJAS (bronze) -> TBL_CORREO_BANDEJAS_SILVER, siempre
    completa: bronze tambien la reemplaza entera en cada corrida (es el
    estado actual de cada bandeja, no tiene periodo). Devuelve filas
    insertadas."""
    columnas_sql = ", ".join(f"[{c}]" for c in COLUMNAS_BANDEJAS_SILVER_DESDE_BRONZE)
    bronze_df = gateway.fetch_dataframe(f"SELECT {columnas_sql} FROM [{ESQUEMA_BRONZE}].[{TABLA_BANDEJAS}]")
    logger.info("%s fila(s) leidas de [%s].[%s] (bronze).", len(bronze_df), ESQUEMA_BRONZE, TABLA_BANDEJAS)
    silver_df = construir_bandejas_silver(bronze_df)

    gateway.truncate_table(TABLA_BANDEJAS_SILVER, schema=ESQUEMA)
    return gateway.bulk_insert(TABLA_BANDEJAS_SILVER, silver_df, schema=ESQUEMA)
