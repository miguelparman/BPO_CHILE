"""Capa SILVER de la estructura medallion de 11_correos:

- Bronze: TBL_CORREO_REGISTRO -- los 'Registro' de los .xlsx tal cual (+ ORIGEN),
  cargada por bronze/cargar.py.
- Silver (se construye LEYENDO bronze, nunca los .xlsx):
  - TBL_CORREO_REGISTRO_SILVER: sin las columnas calculadas por el Excel que
    no son confiables (silver/mappings.COLUMNAS_EXCLUIDAS_SILVER), y con
    columnas derivadas: ASUNTO_AGRUPADO (ver
    silver/mappings.REGLAS_ASUNTO_AGRUPADO), COORDINADOR, ID_PLACE y
    JEFATURA (cruce con silver/mappings.TABLA_HISTORICO_PLACES por ID_PLACE +
    dia UTC, o la foto anterior mas reciente)
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
    JEFATURA_TRIADAS,
    PATRON_BANDEJA_ID_PLACE,
    REGLAS_ASUNTO_AGRUPADO,
    SEPARADOR_CASOS,
    ReglaAgrupacion,
    TABLA_BANDEJAS_SILVER,
    TABLA_HISTORICO_PLACES,
    TABLA_REGISTRO_SILVER,
    TABLA_SEGUIMIENTO,
    TIPO_CASO_SEGUIMIENTO,
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


def _usa_patron(regla: ReglaAgrupacion) -> bool:
    """Reglas que buscan texto (asunto, o contacto con contiene=True)."""
    return regla.campo == CAMPO_ASUNTO or regla.contiene


# Por regla: patron de texto (asunto, o contacto con contiene=True) o
# conjunto de correos (contacto exacto).
_REGLAS_COMPILADAS = [
    (
        regla,
        _patron(regla.textos, regla.palabra_completa) if _usa_patron(regla) else None,
        {_normalizar(t) for t in regla.textos} if not _usa_patron(regla) else None,
    )
    for regla in REGLAS_ASUNTO_AGRUPADO
]


def agrupar_asunto(asunto: object, contacto: object = None, tipo: object = None) -> str | None:
    """Devuelve el grupo de la primera regla que calza con el mensaje (asunto,
    contacto y tipo), o None si ninguna calza."""
    textos = {
        CAMPO_ASUNTO: _normalizar(asunto) if isinstance(asunto, str) and asunto.strip() else None,
        CAMPO_CONTACTO: _normalizar(contacto) if isinstance(contacto, str) and contacto.strip() else None,
    }
    correos = _correos(contacto)
    for regla, patron, correos_regla in _REGLAS_COMPILADAS:
        if regla.tipo is not None and tipo != regla.tipo:
            continue
        texto = textos[regla.campo]
        if patron is not None and texto is not None and patron.search(texto):
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


def fecha_desde_utc(fechas: pd.Series) -> pd.Series:
    """Dia (sin hora, en UTC) de cada FechaHora_UTC_Texto, para cruzar con
    [Fecha Impacto]: 2026-09-30 23:10 UTC -> 2026-09-30. NaT si no hay fecha."""
    return pd.to_datetime(fechas, errors="coerce").dt.normalize()


def normalizar_plataforma(plataforma: object) -> str | None:
    """[Plataforma] -> JEFATURA: todo lo que contenga 'triada' (sin distinguir
    mayusculas) -> JEFATURA_TRIADAS; lo que venga en MAYUSCULAS se capitaliza
    (CARTERIZADOS -> Carterizados), el resto queda tal cual. None si vacio."""
    if not isinstance(plataforma, str) or not plataforma.strip():
        return None
    valor = plataforma.strip()
    if "triada" in valor.casefold():
        return JEFATURA_TRIADAS
    if valor.isupper():
        return valor.capitalize()
    return valor


def jefatura_por_place_fecha(places_df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (ID_PLACE, FECHA) con su JEFATURA (ya normalizada). [ID] es
    texto en el origen: lo que no es numerico se descarta, igual que las fotos
    sin plataforma. Si un par tiene mas de una jefatura se toma la mas
    frecuente (empate: la primera alfabetica) y se avisa en el log."""
    df = pd.DataFrame(
        {
            COLUMNA_ID_PLACE: pd.to_numeric(places_df["ID_PLACE"].astype(str).str.strip(), errors="coerce"),
            "FECHA": pd.to_datetime(places_df["FECHA"], errors="coerce"),
            COLUMNA_JEFATURA: places_df["PLATAFORMA"].map(normalizar_plataforma),
        }
    ).dropna()
    df = df.astype({COLUMNA_ID_PLACE: "Int64"})

    claves = [COLUMNA_ID_PLACE, "FECHA"]
    conteo = df.groupby([*claves, COLUMNA_JEFATURA]).size().reset_index(name="N")
    ambiguos = conteo.groupby(claves).size()
    ambiguos = ambiguos[ambiguos > 1]
    if not ambiguos.empty:
        logger.warning(
            "  %s par(es) ID_PLACE/fecha con mas de una jefatura en %s; se toma la mas frecuente: %s",
            len(ambiguos),
            TABLA_HISTORICO_PLACES,
            [(int(i), f.date().isoformat()) for i, f in ambiguos.index],
        )
    conteo = conteo.sort_values([*claves, "N", COLUMNA_JEFATURA], ascending=[True, True, False, True])
    return conteo.drop_duplicates(claves)[[*claves, COLUMNA_JEFATURA]].reset_index(drop=True)


def agregar_jefatura(silver_df: pd.DataFrame, jefaturas_df: pd.DataFrame) -> pd.DataFrame:
    """Cruza silver con jefatura_por_place_fecha() por ID_PLACE + dia UTC: la
    foto de ese dia o, si no hay, la mas reciente anterior de ese ID
    (merge_asof 'backward'). No cambia la cantidad ni el orden de las filas."""
    df = silver_df.copy()
    df["FECHA"] = fecha_desde_utc(df[COLUMNA_CONTROL_FECHA])
    df["_FILA"] = range(len(df))

    cruzables = df[df[COLUMNA_ID_PLACE].notna() & df["FECHA"].notna()].copy()
    cruzables[COLUMNA_ID_PLACE] = cruzables[COLUMNA_ID_PLACE].astype("int64")
    fotos = jefaturas_df.rename(columns={"FECHA": "FECHA_FOTO"}).copy()
    fotos[COLUMNA_ID_PLACE] = fotos[COLUMNA_ID_PLACE].astype("int64")
    fotos["FECHA_FOTO"] = pd.to_datetime(fotos["FECHA_FOTO"]).astype(cruzables["FECHA"].dtype)
    cruzadas = pd.merge_asof(
        cruzables[["_FILA", COLUMNA_ID_PLACE, "FECHA"]].sort_values("FECHA"),
        fotos.sort_values("FECHA_FOTO"),
        left_on="FECHA",
        right_on="FECHA_FOTO",
        by=COLUMNA_ID_PLACE,
        direction="backward",
    )
    df = df.merge(cruzadas[["_FILA", "FECHA_FOTO", COLUMNA_JEFATURA]], how="left", on="_FILA", validate="one_to_one")
    df = df.sort_values("_FILA").reset_index(drop=True)
    df[COLUMNA_JEFATURA] = df[COLUMNA_JEFATURA].astype(object).where(df[COLUMNA_JEFATURA].notna(), None)

    con_foto_anterior = df[df[COLUMNA_JEFATURA].notna() & (df["FECHA_FOTO"] < df["FECHA"])]
    if not con_foto_anterior.empty:
        logger.info(
            "  %s fila(s) con %s tomada de una foto anterior (sin foto del dia en %s).",
            len(con_foto_anterior),
            COLUMNA_JEFATURA,
            TABLA_HISTORICO_PLACES,
        )
    sin_jefatura = df[df[COLUMNA_JEFATURA].isna()]
    if not sin_jefatura.empty:
        por_place = sin_jefatura.groupby(COLUMNA_ID_PLACE, dropna=False).size()
        logger.warning(
            "  %s fila(s) sin %s (ID_PLACE sin foto con plataforma en %s hasta la fecha del mensaje): %s",
            len(sin_jefatura),
            COLUMNA_JEFATURA,
            TABLA_HISTORICO_PLACES,
            [(str(i), int(n)) for i, n in por_place.items()],
        )
    return df.drop(columns=["FECHA", "_FILA", "FECHA_FOTO"])


# Fotos de places para el rango [?, ?] de dias de los mensajes, mas la ultima
# foto anterior al rango de cada ID (para los que no tengan foto en el rango).
# Solo fotos con plataforma.
SELECT_HISTORICO_PLACES = f"""
SELECT [ID] AS ID_PLACE, [Fecha Impacto] AS FECHA, [Plataforma] AS PLATAFORMA
FROM {TABLA_HISTORICO_PLACES}
WHERE [Fecha Impacto] >= ? AND [Fecha Impacto] <= ? AND NULLIF(LTRIM(RTRIM([Plataforma])), '') IS NOT NULL
UNION ALL
SELECT ID_PLACE, FECHA, PLATAFORMA FROM (
    SELECT [ID] AS ID_PLACE, [Fecha Impacto] AS FECHA, [Plataforma] AS PLATAFORMA,
           ROW_NUMBER() OVER (PARTITION BY [ID] ORDER BY [Fecha Impacto] DESC) AS RN
    FROM {TABLA_HISTORICO_PLACES}
    WHERE [Fecha Impacto] < ? AND NULLIF(LTRIM(RTRIM([Plataforma])), '') IS NOT NULL
) anteriores
WHERE RN = 1
"""


def _con_jefatura(gateway, silver_df: pd.DataFrame) -> pd.DataFrame:
    """Lee de TABLA_HISTORICO_PLACES solo los dias presentes en silver_df (mas
    la ultima foto anterior de cada ID) y cruza."""
    fechas = fecha_desde_utc(silver_df[COLUMNA_CONTROL_FECHA]).dropna()
    if fechas.empty:
        return silver_df.assign(**{COLUMNA_JEFATURA: None})
    desde, hasta = fechas.min().date(), fechas.max().date()
    places_df = gateway.fetch_dataframe(SELECT_HISTORICO_PLACES, (desde, hasta, desde))
    logger.info("%s fila(s) leidas de %s para los dias %s a %s.", len(places_df), TABLA_HISTORICO_PLACES, desde, hasta)
    if places_df.empty:
        places_df = pd.DataFrame(columns=["ID_PLACE", "FECHA", "PLATAFORMA"])
    df = agregar_jefatura(silver_df, jefatura_por_place_fecha(places_df))
    for jefatura, cantidad in df[COLUMNA_JEFATURA].fillna("(sin jefatura)").value_counts().items():
        logger.info("  %s = %s: %s fila(s)", COLUMNA_JEFATURA, jefatura, cantidad)
    return df


# Casos por ConversationID: [To Addres] normalizado (sin espacios, en
# mayusculas) = ConversationID normalizado. Solo se consideran los [To Addres]
# con forma de ConversationID (32 caracteres hexadecimales): el resto son
# correos y nunca calzan. Solo casos de tipo TIPO_CASO_SEGUIMIENTO. Todos
# los casos de la conversacion, por apertura.
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
      AND t.[Tipo del caso] = '{TIPO_CASO_SEGUIMIENTO}'
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
