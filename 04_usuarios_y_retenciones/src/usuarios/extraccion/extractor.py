"""Extraccion: un extraer_xxx() por cada Origen OLE DB de los 5 paquetes
USUARIOS_*.dtsx.

Todos los origenes que apuntaban a Externos_Frac migraron de una consulta
SQL a un CSV publicado en SharePoint via Microsoft Graph -- mismo patron ya
usado en 30_parque (ver sharepoint/reader.py, mappings.py). Las consultas
SQL originales quedan documentadas en sql.py como referencia literal de la
logica de negocio que aqui se replica en pandas: filtros 'WHERE' se vuelven
mascaras booleanas, JOINs se vuelven pd.merge, CTEs con ROW_NUMBER()/dedup
se vuelven sort_values + duplicated(), CAST/TRY_CAST se vuelven
_cast_int_estricto/_cast_int_tolerante (ver abajo).

El unico Origen que leia CL_USUARIOS/CL_DATA (no Externos_Frac), 'CARGA DE
USUARIOS RETENCIONES SERVIDOR CHILE', se dio de baja junto con su Data Flow
completo por ser un trabajo obsoleto -- ver pipeline.py."""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import pandas as pd

import mappings
from exceptions import ExtraccionError
from models import Periodo
from sharepoint.reader import SharePointCsvReader

logger = logging.getLogger("usuarios")


# ===========================================================================
# Utilidades comunes de casteo/validacion (equivalentes a CAST/TRY_CAST y a
# la comprobacion de columnas esperadas de un Origen OLE DB).
# ===========================================================================


def _validar_columnas(df: pd.DataFrame, columnas: Sequence[str], archivo: str) -> None:
    faltantes = [c for c in columnas if c not in df.columns]
    if faltantes:
        raise ExtraccionError(f"Faltan columnas esperadas en '{archivo}': {faltantes}")


def _cast_int_estricto(serie: pd.Series, columna: str, contexto: str) -> pd.Series:
    """Equivalente a CAST(... AS int): un valor no numerico aborta toda la
    extraccion, igual que abortaria la consulta SQL original. Una celda
    vacia (NULL de origen) no es un error, CAST(NULL AS int) tambien es
    NULL."""
    convertido = pd.to_numeric(serie, errors="coerce")
    invalidos = convertido.isna() & serie.notna()
    if invalidos.any():
        filas = serie.index[invalidos].tolist()
        raise ExtraccionError(
            f"[{contexto}] La columna '{columna}' tiene valores no numericos en las filas {filas} "
            "(CAST AS int aborta la consulta en el origen original)."
        )
    return convertido.astype("Int64")


def _cast_int_tolerante(serie: pd.Series) -> pd.Series:
    """Equivalente a TRY_CAST(... AS int): un valor no numerico no aborta,
    queda NULL."""
    return pd.to_numeric(serie, errors="coerce").astype("Int64")


def _filtrar_periodo_gte(df: pd.DataFrame, columna_periodo: pd.Series, umbral: int) -> pd.DataFrame:
    """Equivalente a 'WHERE <col> >= ?': una columna nula no cumple la
    condicion (NULL >= x es NULL en T-SQL, la fila no se incluye), igual que
    'fillna(False)' aqui evita el error de pandas al indexar con una mascara
    booleana que contenga <NA>."""
    mascara = (columna_periodo >= umbral).fillna(False)
    return df[mascara]


def _limpiar_texto_null(serie: pd.Series) -> pd.Series:
    """Equivalente a replace(columna,'NULL','')."""
    return serie.astype("string").str.replace("NULL", "", regex=False)


def _periodo_mes_anterior(periodo: Periodo) -> int:
    """Equivalente a FORMAT(DATEADD(MONTH,-1,CAST(?+'01' AS date)),'yyyyMM')."""
    anio, mes = divmod(periodo.como_int, 100)
    mes -= 1
    if mes == 0:
        mes, anio = 12, anio - 1
    return anio * 100 + mes


def _periodo_siguiente(periodo_int: int) -> int:
    """Equivalente al CASE de 'ultimo_parque' (202312->202401, 202412->202501,
    202512->202601, ELSE periodo+1) generalizado: cualquier periodo que
    termina en diciembre avanza a enero del anio siguiente -- los 3 casos
    hardcodeados del .dtsx original son instancias de esta misma formula."""
    anio, mes = divmod(periodo_int, 100)
    if mes == 12:
        return (anio + 1) * 100 + 1
    return periodo_int + 1


# ===========================================================================
# USUARIOS_0101 Parque.dtsx -- Origen '55_PARQUE' del Data Flow 'PARQUE'
# ===========================================================================


def extraer_parque(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Reemplaza sql.PARQUE_SELECT (UNION ALL fijo+movil, LEFT JOIN con
    RUT_marca_cartera, GROUP BY, y la proyeccion 'ultimo_parque' al periodo
    siguiente) por su equivalente en pandas."""
    try:
        df_fijo = reader.leer_csv(mappings.PARQUE_FIJO_ARCHIVO)
        df_movil = reader.leer_csv(mappings.PARQUE_MOVIL_ARCHIVO)
        df_marca = reader.leer_csv(mappings.RUT_MARCA_CARTERA_ARCHIVO)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen '55_PARQUE': {exc}") from exc
    return _construir_parque(df_fijo, df_movil, df_marca, periodo)


def _mapear_segme(serie: pd.Series) -> pd.Series:
    mapa = {
        "Mediana Empresa": "MEDIANA",
        "Mediana": "MEDIANA",
        "Peque?a": "PEQUEÑA",
        "Peque?a Empresa": "PEQUEÑA",
        "Pequeña": "PEQUEÑA",
        "Pequeña Empresa": "PEQUEÑA",
        "Micro": "MICRO",
    }
    return serie.map(mapa)


def _mapear_tpo_prod_fijo(tpo_prod: pd.Series, tecnologia: pd.Series) -> pd.Series:
    condiciones = [
        (tpo_prod == "BAF") & tecnologia.isin(["ADSL", "LTE", "SAT", "VDSL"]),
        (tpo_prod == "BAF") & (tecnologia == "FIBER"),
        (tpo_prod == "TV") & tecnologia.isin(["DTH", "IPTV"]),
        (tpo_prod == "VOZ") & tecnologia.isin(["FWT", "PSTN", "TDM", "TOIP", "SIN TEC"]),
        (tpo_prod == "MTV") & tecnologia.isin(["IPTV"]),
    ]
    resultados = ["CO", "FO", "TV", "STB", "TV"]
    return pd.Series(np.select(condiciones, resultados, default=None), index=tpo_prod.index, dtype="object")


def _mapear_servicio(marca: pd.Series) -> pd.Series:
    """Equivalente a CASE sobre COALESCE(m.marca,3): (1,4)->CARTERIZADOS,
    cualquier otro valor (incluido el default 3) -> TRIADAS."""
    marca_num = pd.to_numeric(marca, errors="coerce").fillna(3)
    return pd.Series(np.where(marca_num.isin([1, 4]), "CARTERIZADOS", "TRIADAS"), index=marca.index)


def _preparar_parque_fijo(df: pd.DataFrame, df_marca: pd.DataFrame, piso: int) -> pd.DataFrame:
    _validar_columnas(df, ["periodo", "segme", "q_casos", "tpo_prod", "tecnologia", "rut"], mappings.PARQUE_FIJO_ARCHIVO)
    _validar_columnas(df_marca, ["rutcli", "marca"], mappings.RUT_MARCA_CARTERA_ARCHIVO)
    df = df.copy()
    df["periodo"] = _cast_int_estricto(df["periodo"], "periodo", mappings.PARQUE_FIJO_ARCHIVO)
    df = _filtrar_periodo_gte(df, df["periodo"], piso)

    df = df.copy()
    df["_rutcli_join"] = df["rut"].astype("string").str.slice(0, -1)
    marca = df_marca.rename(columns={"rutcli": "_rutcli_join"})[["_rutcli_join", "marca"]]
    df = df.merge(marca, on="_rutcli_join", how="left")

    resultado = pd.DataFrame(index=df.index)
    resultado["periodo"] = df["periodo"]
    resultado["segme"] = _mapear_segme(df["segme"])
    resultado["pqe"] = _cast_int_estricto(df["q_casos"], "q_casos", mappings.PARQUE_FIJO_ARCHIVO)
    resultado["tpo_prod"] = _mapear_tpo_prod_fijo(df["tpo_prod"], df["tecnologia"])
    resultado["tipo"] = "FIJO"
    resultado["SERVICIO"] = _mapear_servicio(df["marca"])
    return resultado


def _preparar_parque_movil(df: pd.DataFrame, df_marca: pd.DataFrame, piso: int) -> pd.DataFrame:
    _validar_columnas(df, ["periodo", "segme", "tpo_prod", "rutcli"], mappings.PARQUE_MOVIL_ARCHIVO)
    _validar_columnas(df_marca, ["rutcli", "marca"], mappings.RUT_MARCA_CARTERA_ARCHIVO)
    df = df.copy()
    df["periodo"] = _cast_int_estricto(df["periodo"], "periodo", mappings.PARQUE_MOVIL_ARCHIVO)
    df = _filtrar_periodo_gte(df, df["periodo"], piso)

    df = df.copy()
    marca = df_marca[["rutcli", "marca"]]
    df = df.merge(marca, on="rutcli", how="left")

    resultado = pd.DataFrame(index=df.index)
    resultado["periodo"] = df["periodo"]
    resultado["segme"] = _mapear_segme(df["segme"])
    resultado["pqe"] = pd.array([1] * len(df), dtype="Int64")
    resultado["tpo_prod"] = df["tpo_prod"]
    resultado["tipo"] = "MOVIL"
    resultado["SERVICIO"] = _mapear_servicio(df["marca"])
    return resultado


def _construir_parque(
    df_fijo: pd.DataFrame, df_movil: pd.DataFrame, df_marca: pd.DataFrame, periodo: Periodo
) -> pd.DataFrame:
    piso = _periodo_mes_anterior(periodo)

    cte_parques = pd.concat(
        [_preparar_parque_fijo(df_fijo, df_marca, piso), _preparar_parque_movil(df_movil, df_marca, piso)],
        ignore_index=True,
    )

    cte2 = cte_parques.groupby(["periodo", "segme", "tpo_prod", "tipo", "SERVICIO"], dropna=False, as_index=False)[
        "pqe"
    ].sum()

    periodo_maximo = cte2["periodo"].max()
    ultimo_parque = cte2[cte2["periodo"] == periodo_maximo].copy()
    ultimo_parque["periodo"] = ultimo_parque["periodo"].apply(_periodo_siguiente).astype("Int64")

    resultado = pd.concat([ultimo_parque, cte2], ignore_index=True)
    # 'cast(periodo as varchar(6))+segme+tpo_prod+tipo+SERVICIO': el '+' de
    # T-SQL propaga NULL (a diferencia de CONCAT); el dtype nullable
    # 'string' de pandas tiene el mismo comportamiento al sumarse.
    resultado["PQE_llave"] = (
        resultado["periodo"].astype("string")
        + resultado["segme"].astype("string")
        + resultado["tpo_prod"].astype("string")
        + resultado["tipo"].astype("string")
        + resultado["SERVICIO"].astype("string")
    )
    resultado = resultado.sort_values("periodo", ascending=False, kind="mergesort").reset_index(drop=True)
    return resultado[["periodo", "segme", "tpo_prod", "tipo", "SERVICIO", "pqe", "PQE_llave"]]


# ===========================================================================
# USUARIOS_0201 SSIS_CL_Retenciones.dtsx
# ===========================================================================


def _extraer_csv_simple(
    reader: SharePointCsvReader,
    archivo: str,
    columnas: Sequence[str],
    columna_periodo: str,
    periodo: Periodo,
    nombre_origen: str,
) -> pd.DataFrame:
    """Origenes sin transformaciones mas alla de 'CAST(<columna_periodo> AS
    int) >= ?': copia 1:1 de las columnas declaradas, igual que el Origen OLE
    DB original (ver sql.py para la consulta que reemplaza cada uno)."""
    try:
        df = reader.leer_csv(archivo)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen '{nombre_origen}': {exc}") from exc
    _validar_columnas(df, columnas, archivo)
    df = df[list(columnas)].copy()
    periodo_num = _cast_int_estricto(df[columna_periodo], columna_periodo, archivo)
    return _filtrar_periodo_gte(df, periodo_num, periodo.como_int).reset_index(drop=True)


_BAJAS_FRAUDE_COLUMNAS = (
    "PERIODO", "REPORT_DATE", "RUT_CLIENTE", "NOMBRE_CLIENTE", "SUBSEGMENTO", "SUBSCRIBER_KEY",
    "LINEA", "TIPO_PRODUCTO", "tipobaja", "q_movimiento", "MANAGEMENT_INITIAL", "AGENT_DESC_INITIAL",
    "AGENT_BAJA", "subgerente_atencion", "jefe_atencion", "service_manager", "gerente",
    "SUBGERENTE_COMERCIAL", "JEFE_COMERCIAL", "ACCOUNT_MANAGER", "SALES_CHANNEL_NAME",
    "SALES_CHANNEL_NAME_INITIAL", "SALES_SUBCHANNEL_NAME_INITIAL", "SITE_NAME_INITIAL",
    "REFERENCE_NUMBER", "DESC_MOVIMIENTO", "ORDER_ACTION_REASON_DESC",
)

_BAJAS_POR_ALTA_COLUMNAS = (
    "PARK_EFFECT_DESC", "PARK_EFFECT_VALUE", "SUBSCRIBER_KEY", "ACCESS_ID", "RUT",
    "MAIN_PRODUCT_FAMILY", "SERVICE_TYPE", "SUBSEGMENTO", "PERIODO", "combinacion origen", "MODELO",
)

_BAJAS_FIJO_COLUMNAS = (
    "CLOSE_DATE", "MOVEMENT_TYPE_DESC", "CNT_IDENTIFICATION_DOC_NUMBER", "SUBSCRIBER_KEY",
    "SERVICE_ID", "MAIN_PRODUCT_FAMILY", "SERVICE_TYPE", "CUSTOMER_SUB_TYPE_DESC", "YEAR_MONTH",
    "MOVEMENT_DESC",
)

_BAJAS_MOVIL_COLUMNAS = (
    "LLAVE", "FECHA_BAJA", "PERIODO", "RUT_CLIENTE", "RAZON_SOCIAL", "SEGMENTO_CG",
    "NUMERO_TELEFONO", "TIPO_PRODUCTO", "TIPOBAJA", "Q_MOVIMIENTO", "GERENTE_COMERCIAL",
    "SUBGERENTE_COMERCIAL", "JEFE_COMERCIAL", "ACCOUNT_MANAGER", "SUBGERENTE_POSTVENTA",
    "JEFE_POSTVENTA", "SERVICE_MANAGER", "RECEPTORA",
)


def extraer_bajas_fraude(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen 'BAJAS_FRAUDE 233' del Data Flow 'TBL_SERVCH_BAJAS_FRAUDE'
    (USUARIOS_0201 SSIS_CL_Retenciones.dtsx)."""
    return _extraer_csv_simple(
        reader, mappings.RETENCIONES_BAJAS_FRAUDE_ARCHIVO, _BAJAS_FRAUDE_COLUMNAS, "PERIODO", periodo, "BAJAS_FRAUDE 233"
    )


def extraer_bajas_por_alta(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen '223_BAJAS_POR_ALTA_FO' del Data Flow
    'TBL_SERVCH_BAJAS_POR_ALTA_FO' (USUARIOS_0201 SSIS_CL_Retenciones.dtsx)."""
    return _extraer_csv_simple(
        reader,
        mappings.RETENCIONES_BAJAS_POR_ALTA_ARCHIVO,
        _BAJAS_POR_ALTA_COLUMNAS,
        "PERIODO",
        periodo,
        "223_BAJAS_POR_ALTA_FO",
    )


_BD_RETEN_COLUMNAS_ORIGEN = (
    "periodo", "rut", "nomcli", "segme", "nom_sm", "nom_sup", "sub_segme", "tpo_serv", "tpo_prod",
    "tpo_tecno", "q_parque", "q_riesgo", "q_baja_v", "q_baja_p", "q_baja_m", "motivo", "submotivo",
    "submotivo2", "canal_ing", "subcan_ing", "canal_res", "subcan_res", "cargo_res", "canal_hres",
    "fecha_ultima_actualizacion", "cons_estados",
)


def extraer_bd_reten(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen 'BD_RETEN_V2 (223)' + componente 'Data Conversion' del Data
    Flow 'BD_RETEN' (USUARIOS_0201 SSIS_CL_Retenciones.dtsx). Reemplaza
    sql.RETENCIONES_BD_RETEN_SELECT (CTE con dedup ROW_NUMBER + piso fijo
    'periodo >= 202601') por su equivalente en pandas."""
    try:
        df = reader.leer_csv(mappings.RETENCIONES_BD_RETEN_ARCHIVO)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen 'BD_RETEN_V2 (223)': {exc}") from exc
    df = _construir_bd_reten(df, periodo)
    return _aplicar_conversion_bd_reten(df)


def _extraer_case_idnum(cons_estados) -> str:
    """Equivalente a: CASE WHEN cons_estados='NULL' THEN '' ELSE
    SUBSTRING(cons_estados, CHARINDEX('{',cons_estados)+1,
    CHARINDEX(':',cons_estados)-CHARINDEX('{',cons_estados)-1) END."""
    if pd.isna(cons_estados) or cons_estados == "NULL":
        return ""
    inicio = cons_estados.find("{")
    fin = cons_estados.find(":")
    if inicio == -1 or fin == -1 or fin <= inicio:
        return ""
    return cons_estados[inicio + 1 : fin]


def _construir_bd_reten(df: pd.DataFrame, periodo: Periodo) -> pd.DataFrame:
    _validar_columnas(df, _BD_RETEN_COLUMNAS_ORIGEN, mappings.RETENCIONES_BD_RETEN_ARCHIVO)
    df = df.copy()

    # Piso fijo 'periodo >= 202601' del CTE original, aplicado ANTES del dedup.
    periodo_crudo_num = pd.to_numeric(df["periodo"], errors="coerce")
    df = _filtrar_periodo_gte(df, periodo_crudo_num, 202601)

    # ROW_NUMBER() OVER(PARTITION BY periodo,rut,tpo_serv,tpo_prod,tpo_tecno,
    # submotivo ORDER BY periodo): el ORDER BY es sobre una columna que forma
    # parte del propio PARTITION BY, por lo que no desempata nada -- igual
    # que en SQL Server, que fila "gana" ROWNO=1 dentro de un grupo empatado
    # no esta definido por la consulta original. Aqui se preserva el orden
    # de aparicion en el CSV (sort_values estable) como criterio de desempate.
    claves = ["periodo", "rut", "tpo_serv", "tpo_prod", "tpo_tecno", "submotivo"]
    df = df.sort_values(claves, kind="mergesort")
    df = df[~df.duplicated(subset=claves, keep="first")].copy()

    resultado = pd.DataFrame(index=df.index)
    resultado["ROWNO"] = 1
    resultado["periodo"] = _cast_int_tolerante(df["periodo"])
    resultado["rut"] = _limpiar_texto_null(df["rut"])

    rut_para_rutcli = _limpiar_texto_null(df["rut"]).str.replace("-", "", regex=False).str.replace(
        "k", "", regex=False
    )
    largo_original = df["rut"].astype("string").str.len()
    rut_recortado = pd.Series(
        [
            texto[: largo - 1] if pd.notna(texto) and pd.notna(largo) and largo >= 1 else pd.NA
            for texto, largo in zip(rut_para_rutcli, largo_original)
        ],
        index=df.index,
        dtype="object",
    )
    resultado["rutcli"] = _cast_int_tolerante(rut_recortado)

    for columna in ("nomcli", "segme", "nom_sm", "nom_sup", "sub_segme"):
        resultado[columna] = _limpiar_texto_null(df[columna])
    resultado["tpo_serv"] = df["tpo_serv"]
    resultado["tpo_prod"] = df["tpo_prod"]
    resultado["tpo_tecno"] = df["tpo_tecno"]
    for columna in ("q_parque", "q_riesgo", "q_baja_v", "q_baja_p", "q_baja_m"):
        resultado[columna] = _cast_int_estricto(df[columna], columna, mappings.RETENCIONES_BD_RETEN_ARCHIVO)
    for columna in (
        "motivo", "submotivo", "submotivo2", "canal_ing", "subcan_ing",
        "canal_res", "subcan_res", "cargo_res", "canal_hres",
    ):
        resultado[columna] = _limpiar_texto_null(df[columna])
    resultado["last_modified"] = df["fecha_ultima_actualizacion"].to_numpy()
    resultado["case_idnum"] = df["cons_estados"].apply(_extraer_case_idnum)
    resultado["Evaluacion"] = 1
    resultado["LLAVE"] = (
        resultado["periodo"].astype("string")
        + resultado["rutcli"].astype("string")
        + resultado["tpo_serv"].astype("string")
        + resultado["tpo_prod"].astype("string")
        + resultado["tpo_tecno"].astype("string")
    )

    resultado = _filtrar_periodo_gte(resultado, resultado["periodo"], periodo.como_int)
    return resultado.reset_index(drop=True)


def _aplicar_conversion_bd_reten(df: pd.DataFrame) -> pd.DataFrame:
    # Componente 'Data Conversion': 'ROWNO' (solo usado en el WHERE ROWNO=1
    # de la consulta) y 'motivo' (seleccionado en el CTE pero sin columna de
    # salida "Copy of ...") no llegan al destino.
    df = df.drop(columns=list(mappings.BD_RETEN_COLUMNAS_DESCARTADAS), errors="ignore").copy()

    # 'Evaluacion' llega como literal entero 1 (desde el CTE) y el
    # componente lo convierte a string(5).
    df["Evaluacion"] = df["Evaluacion"].astype(str)
    # 'last_modified' (alias de fecha_ultima_actualizacion) se convierte de
    # datetime a date (sin componente de hora). En el origen SQL original
    # era una columna datetime real (nunca pasaba por REPLACE(...,'NULL','')
    # como el resto de las columnas de texto); en el CSV, un valor faltante
    # llega igual que en cualquier otra columna de texto: el literal 'NULL'.
    valores_last_modified = df["last_modified"].replace("NULL", None)
    df["last_modified"] = pd.to_datetime(valores_last_modified).dt.date

    # errorRowDisposition="FailComponent" (comportamiento por defecto, igual
    # que en 08_cartera): un valor que excede el ancho debe abortar la
    # extraccion, no truncarse en silencio.
    for columna, largo in mappings.BD_RETEN_TRUNCATION_LENGTHS.items():
        valores = df[columna].astype("string")
        excede = valores.str.len() > largo
        if excede.any():
            filas = df.index[excede].tolist()
            raise ExtraccionError(
                f"La columna '{columna}' excede el ancho de truncamiento ({largo} caracteres) "
                f"en las filas {filas} del Data Flow 'BD_RETEN' (Data Conversion, "
                "errorRowDisposition=FailComponent)."
            )
        df[columna] = valores.str.slice(0, largo)
    return df


# ===========================================================================
# USUARIOS_0300 ETL_INTENCIONES.dtsx
# ===========================================================================


def extraer_bajas_fijo(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen del pipe 'BAJAS_FIJO' del Data Flow 'TBL_CH_BAJAS'
    (USUARIOS_0300 ETL_INTENCIONES.dtsx)."""
    return _extraer_csv_simple(
        reader, mappings.INTENCIONES_BAJAS_FIJO_ARCHIVO, _BAJAS_FIJO_COLUMNAS, "YEAR_MONTH", periodo, "BAJAS_FIJO"
    )


def extraer_bajas_movil(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen del pipe 'BAJAS_MOVIL' del Data Flow 'TBL_CH_BAJAS'
    (USUARIOS_0300 ETL_INTENCIONES.dtsx)."""
    return _extraer_csv_simple(
        reader, mappings.INTENCIONES_BAJAS_MOVIL_ARCHIVO, _BAJAS_MOVIL_COLUMNAS, "PERIODO", periodo, "BAJAS_MOVIL"
    )


def extraer_intenciones_v2(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen + componente 'Data Conversion 1' del Data Flow 'INTENCIONES'
    (USUARIOS_0300 ETL_INTENCIONES.dtsx). El filtro original
    ('YEAR(CASE_OPEN_TIME)*100+MONTH(CASE_OPEN_TIME) >= ?') se deriva de una
    fecha, no de una columna de periodo plana."""
    try:
        df = reader.leer_csv(mappings.INTENCIONES_V2_ARCHIVO)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen de 'INTENCIONES': {exc}") from exc

    columnas = ("CASE_ID_NUMBER", "CASE_OPEN_TIME", "CASE_NOTE")
    _validar_columnas(df, columnas, mappings.INTENCIONES_V2_ARCHIVO)
    df = df[list(columnas)].copy()

    try:
        fechas = pd.to_datetime(df["CASE_OPEN_TIME"], errors="raise")
    except Exception as exc:
        raise ExtraccionError(
            f"No se pudo parsear 'CASE_OPEN_TIME' en '{mappings.INTENCIONES_V2_ARCHIVO}': {exc}"
        ) from exc
    anio_mes = fechas.dt.year * 100 + fechas.dt.month
    df = _filtrar_periodo_gte(df, anio_mes, periodo.como_int).reset_index(drop=True)

    return _aplicar_conversion_intenciones_v2(df)


def _aplicar_conversion_intenciones_v2(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for columna, largo in mappings.INTENCIONES_V2_TRUNCATION_LENGTHS.items():
        valores = df[columna].astype("string")
        excede = valores.str.len() > largo
        if excede.any():
            filas = df.index[excede].tolist()
            raise ExtraccionError(
                f"La columna '{columna}' excede el ancho de truncamiento ({largo} caracteres) "
                f"en las filas {filas} del Data Flow 'INTENCIONES' (Data Conversion 1, "
                "errorRowDisposition=FailComponent)."
            )
        df[columna] = valores.str.slice(0, largo)
    return df


# ===========================================================================
# USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx -- Data Flow 'INTEN_AMDOCS'
# ===========================================================================

_ITEM_AMDOCS_COLUMNAS_ORIGEN = (
    "rut", "case_idnum", "type1", "type2", "sub_motivo", "case_desc", "case_resol", "case_optim",
    "agent_orig", "agent_reso", "canal_ing", "subcan_ing", "case_cltim", "segmento", "subtype",
    "line_buss", "motivo", "servicio", "cantidad", "prod_type", "ser_stat_r", "periodo", "tpo_serv",
    "rutcli", "pqe_stb", "pqe_baf", "pqe_tv", "pqe_voz", "pqe_bam", "tecno_stb", "tecno_baf",
    "tecno_tv", "tpo_t_stb", "tpo_t_baf", "tpo_t_tv", "origen", "canal_res", "subcan_res",
    "cargo_res", "canal_hres",
)

_MESES_ORACLE = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def extraer_item_amdocs(reader: SharePointCsvReader, periodo: Periodo) -> pd.DataFrame:
    """Origen + componente 'Data Conversion' del Data Flow 'INTEN_AMDOCS'
    (USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx). Reemplaza sql.ITEM_AMDOCS_SELECT
    (CTE con dedup ROW_NUMBER por case_idnum + piso fijo 'periodo >= 202601')
    por su equivalente en pandas."""
    try:
        df = reader.leer_csv(mappings.ITEM_AMDOCS_ARCHIVO)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen de 'INTEN_AMDOCS': {exc}") from exc
    df = _construir_item_amdocs(df, periodo)
    return _aplicar_conversion_item_amdocs(df)


def _parsear_case_cltim(valor):
    """Equivalente a: CASE WHEN case_cltim='' THEN NULL ELSE TRY_CONVERT(
    datetime, CONCAT('20',SUBSTRING(case_cltim,8,2),'-',<mes>,'-',
    SUBSTRING(case_cltim,1,2),' ',REPLACE(SUBSTRING(case_cltim,11,8),'.',':'),
    RIGHT(case_cltim,3))) END. Formato origen deducido de los indices de
    SUBSTRING/RIGHT del .dtsx original: 'DD-MON-YY:HH.MI.SS.mmm AM/PM'.
    TRY_CONVERT nunca aborta -- un texto que no matchea el formato queda
    NULL, igual que el resto de este Data Flow (IgnoreFailure)."""
    if pd.isna(valor) or valor == "":
        return pd.NaT
    texto = str(valor)
    try:
        dia = texto[0:2]
        mes = _MESES_ORACLE[texto[3:6].upper()]
        anio = texto[7:9]
        hora = texto[10:18].replace(".", ":")
        ampm = texto[-3:]
        return pd.to_datetime(f"20{anio}-{mes}-{dia} {hora}{ampm}", errors="raise")
    except Exception:
        return pd.NaT


def _construir_item_amdocs(df: pd.DataFrame, periodo: Periodo) -> pd.DataFrame:
    _validar_columnas(df, _ITEM_AMDOCS_COLUMNAS_ORIGEN, mappings.ITEM_AMDOCS_ARCHIVO)
    df = df.copy()

    # 'case_idnum NOT IN (\'\',\'0\') AND case_idnum IS NOT NULL AND periodo
    # >= 202601', aplicado ANTES del dedup.
    case_idnum_texto = df["case_idnum"].astype("string")
    periodo_crudo_num = pd.to_numeric(df["periodo"], errors="coerce")
    piso = (
        case_idnum_texto.notna()
        & ~case_idnum_texto.isin(["", "0"])
        & (periodo_crudo_num >= 202601).fillna(False)
    )
    df = df[piso].copy()

    # ROW_NUMBER() OVER(PARTITION BY case_idnum ORDER BY case_optim): a
    # diferencia de BD_RETEN, aqui el ORDER BY si desempata de forma
    # determinista (case_optim no forma parte del PARTITION BY).
    df["_case_optim_orden"] = pd.to_datetime(df["case_optim"], errors="coerce")
    df = df.sort_values(["case_idnum", "_case_optim_orden"], kind="mergesort")
    df = df[~df.duplicated(subset=["case_idnum"], keep="first")].copy()

    resultado = pd.DataFrame(index=df.index)
    resultado["ROWNO"] = 1
    rut_recortado = (
        df["rut"].astype("string").str.slice(0, -1).str.replace("-", "", regex=False).str.replace(
            ".", "", regex=False
        )
    )
    resultado["rut"] = _cast_int_estricto(rut_recortado, "rut", mappings.ITEM_AMDOCS_ARCHIVO)
    resultado["case_idnum"] = _cast_int_estricto(df["case_idnum"], "case_idnum", mappings.ITEM_AMDOCS_ARCHIVO)
    for columna in ("type1", "type2", "sub_motivo", "case_desc", "case_resol"):
        resultado[columna] = df[columna]
    resultado["case_optim"] = df["_case_optim_orden"]
    resultado["agent_orig"] = _cast_int_estricto(df["agent_orig"], "agent_orig", mappings.ITEM_AMDOCS_ARCHIVO)
    resultado["agent_reso"] = _cast_int_tolerante(df["agent_reso"])
    resultado["canal_ing"] = df["canal_ing"]
    resultado["subcan_ing"] = df["subcan_ing"]
    resultado["case_cltim"] = df["case_cltim"].apply(_parsear_case_cltim)
    for columna in ("segmento", "subtype", "line_buss", "motivo", "servicio", "cantidad", "prod_type", "ser_stat_r"):
        resultado[columna] = df[columna]
    resultado["periodo"] = _cast_int_estricto(df["periodo"], "periodo", mappings.ITEM_AMDOCS_ARCHIVO)
    resultado["tpo_serv"] = df["tpo_serv"]
    resultado["rutcli"] = df["rutcli"]
    for columna in (
        "pqe_stb", "pqe_baf", "pqe_tv", "pqe_voz", "pqe_bam", "tecno_stb", "tecno_baf", "tecno_tv",
        "tpo_t_stb", "tpo_t_baf", "tpo_t_tv", "origen", "canal_res", "subcan_res", "cargo_res", "canal_hres",
    ):
        resultado[columna] = df[columna]
    resultado["ValidFrom"] = pd.Timestamp.now()

    resultado = _filtrar_periodo_gte(resultado, resultado["periodo"], periodo.como_int)
    return resultado.reset_index(drop=True)


def _aplicar_conversion_item_amdocs(df: pd.DataFrame) -> pd.DataFrame:
    # 'rutcli' se convierte pero nunca se mapea al destino; 'ROWNO' (siempre
    # 1, dado el filtro ROWNO=1 del origen) se mapea a la columna 'Evaluacion'.
    df = df.drop(columns=list(mappings.ITEM_AMDOCS_COLUMNAS_DESCARTADAS), errors="ignore").copy()
    df = df.rename(columns=mappings.ITEM_AMDOCS_RENOMBRES)

    # errorRowDisposition="IgnoreFailure": un valor que no castea no aborta
    # la fila, queda NULL -- a diferencia de BD_RETEN/INTENCIONES_V2.
    for columna in mappings.ITEM_AMDOCS_INT_COLUMNS:
        df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int64")
    for columna in mappings.ITEM_AMDOCS_DATETIME_COLUMNS:
        df[columna] = pd.to_datetime(df[columna], errors="coerce")
    for columna, largo in mappings.ITEM_AMDOCS_TRUNCATION_LENGTHS.items():
        df[columna] = df[columna].astype("string").str.slice(0, largo)
    return df


# ===========================================================================
# USUARIOS_0302 ETL_BASE_SAIP.dtsx -- Data Flow 'SAIP'
# ===========================================================================

_SAIP_COLUMNAS_ORIGEN = (
    "rut_ej", "dv_ej", "nombres", "ap_pat", "ap_mat", "sexo", "fec_ingr", "rut_empr", "dv_empr",
    "desc_empr", "desc_tip", "desc_unida", "desc_estad", "desc_esta1", "desc_suc", "desc_subge",
    "desc_geren", "desc_cargo", "desc_funci", "posicion_f", "fec_saip_a", "fec_saip_b", "autentica",
    "siscel", "rrss", "red", "citrix", "id_genesys", "comuna_pto",
)


def extraer_saip(reader: SharePointCsvReader) -> pd.DataFrame:
    """Origen '223 SAIP' + componente 'Conversion de datos' del Data Flow
    'SAIP' (USUARIOS_0302 ETL_BASE_SAIP.dtsx). Sin parametros -- unico de los
    5 paquetes sin variable de periodo."""
    try:
        df = reader.leer_csv(mappings.SAIP_ARCHIVO)
    except Exception as exc:
        raise ExtraccionError(f"Fallo el Origen '223 SAIP': {exc}") from exc
    _validar_columnas(df, _SAIP_COLUMNAS_ORIGEN, mappings.SAIP_ARCHIVO)
    df = df[list(_SAIP_COLUMNAS_ORIGEN)].copy()

    # WHERE [fec_saip_a] IS NULL OR FORMAT(CONVERT(DATE,[fec_saip_a],3),
    # 'dd/MM/yyyy') >= '2022-01-01': el .dtsx original comparaba el texto
    # 'dd/MM/yyyy' contra un literal ISO ('yyyy-mm-dd'), lo que excluia los
    # dias 01-20 de CUALQUIER mes/anio sin relacion con la fecha real (bug
    # de comparacion lexicografica de formatos distintos). A pedido, aqui se
    # corrige a una comparacion de FECHAS real: se parsea 'fec_saip_a' una
    # sola vez y se compara contra 2022-01-01 como fecha, no como texto.
    fecha_saip_a = pd.to_datetime(df["fec_saip_a"], errors="coerce", dayfirst=True)
    condicion = df["fec_saip_a"].isna() | (fecha_saip_a >= pd.Timestamp("2022-01-01"))
    df = df[condicion].copy()
    df["FECHA"] = fecha_saip_a[condicion].dt.strftime("%d/%m/%Y")
    df = df.reset_index(drop=True)

    return _aplicar_conversion_saip(df)


def _aplicar_conversion_saip(df: pd.DataFrame) -> pd.DataFrame:
    # 'fec_saip_a'/'fec_saip_b' se seleccionan pero nunca llegan al destino.
    df = df.drop(columns=list(mappings.SAIP_COLUMNAS_DESCARTADAS), errors="ignore").copy()
    try:
        # 'fec_ingr' es la fecha nativa del origen. 'FECHA' llega como texto
        # 'dd/MM/yyyy' (formateada asi en extraer_saip, replicando
        # sql.SAIP_SELECT) -- cada una necesita su propio parseo para no ser
        # ambigua.
        df["fec_ingr"] = pd.to_datetime(df["fec_ingr"]).dt.date
        df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True).dt.date
    except Exception as exc:
        raise ExtraccionError(
            f"No se pudieron convertir a fecha las columnas ('fec_ingr', 'FECHA') "
            f"del Data Flow 'SAIP' (Conversion de datos): {exc}"
        ) from exc
    return df
