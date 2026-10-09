"""Transformacion: emula el componente 'Conversión de datos' (Data Convert)
de cada Data Flow -- selecciona/renombra columnas al nombre fisico de
destino y castea numericos/fechas (coerce a NULL, o levanta ValidacionError,
segun ColumnaSpec.estricto -- ver validacion.py) -- y las tareas 'Execute
SQL' que corren sobre el mismo servidor despues de cargar cada tabla."""

from __future__ import annotations

import logging
import re
from datetime import date

import pandas as pd

import mappings
import sql
from db import DatabaseGateway
from exceptions import ValidacionError
from models import ColumnaSpec

logger = logging.getLogger("ventas")

# Formato de un RUT chileno: 6 a 9 digitos, guion opcional, digito
# verificador (0-9 o K/k). Usado para detectar filas reales (produccion,
# 2026-09) donde la persona cargo 'RUT DE LA EMPRESA'/'NOMBRE EMPRESA' al
# reves en el formulario -- ver corregir_rut_nombre_invertidos.
_PATRON_RUT = re.compile(r"^\d{6,9}-?[\dkK]$")


def seleccionar_columnas(df: pd.DataFrame, columnas: tuple[str, ...]) -> pd.DataFrame:
    """Selecciona solo las columnas esperadas, descartando cualquier otra.
    Los workbooks de Excel de origen (baseV2/Hoja1 de Base Carta Meta.xlsx)
    tienen columnas adicionales sin usar que el .dtsx original tampoco
    conectaba en el Origen Excel (el Data Flow original solo 've' las
    columnas que uno explicitamente mapea) -- si no se filtran aqui,
    terminan viajando hasta el INSERT y SQL Server lo rechaza por columnas
    que no existen en la tabla destino (visto en produccion, 2026-09)."""
    return df[list(columnas)]


_PATRON_FECHA_ISO = r"^\d{4}-\d{2}-\d{2}"


def _parsear_fechas(original: pd.Series) -> pd.Series:
    """Parsea una columna de fechas que puede traer dos formatos:

    - ISO ('2026-09-30 00:00:00'): celdas que en Excel son fechas reales
      (pd.read_excel con dtype=str las devuelve asi). Se leen con
      format='ISO8601', SIN 'dayfirst'.
    - Texto chileno/es-CL ('22/7/2026', dia/mes/anio, igual que el
      LocaleID=10250 del .dtsx original): se leen con 'dayfirst=True' --
      sin ese hint pandas asume mes/dia y deja NaT en muchas filas reales
      (visto en produccion, 2026-09).

    No se usa un solo pd.to_datetime(..., dayfirst=True) para todo: pandas
    infiere UN formato a partir del primer valor, y con dayfirst=True un
    ISO cuyo dia es <=12 ('2026-10-02') se infiere como '%Y-%d-%m' -- todas
    las filas con dia >12 quedan NaT y las de dia <=12 se leen con dia y mes
    invertidos (visto en produccion, 2026-10-02, 'Fecha Ingreso' de baseV2:
    14.791 filas rechazadas desde que las primeras filas pasaron a octubre)."""
    texto = original.astype("string").str.strip()
    es_iso = texto.str.match(_PATRON_FECHA_ISO, na=False)
    iso = pd.to_datetime(texto.where(es_iso), errors="coerce", format="ISO8601")
    local = pd.to_datetime(original.where(~es_iso), errors="coerce", dayfirst=True)
    return iso.where(es_iso, local)


def convertir_tipos(df: pd.DataFrame, columnas: tuple[ColumnaSpec, ...]) -> pd.DataFrame:
    """Data Convert generico: para columnas tipo='numero'/'entero'/'fecha',
    castea con pandas y, si 'estricto=True' (FailComponent), levanta
    ValidacionError ante un valor que no parsea; si 'estricto=False'
    (IgnoreFailure), el valor invalido queda NULL sin abortar. 'numero' emula
    un destino DT_R8 (float, con decimales); 'entero' emula un destino DT_I4
    (redondea y castea a 'Int64' nullable, sin decimales) -- ver
    ColumnaSpec.tipo. Para columnas tipo='texto' con 'estricto=False',
    trunca en silencio al ancho declarado (el caso 'estricto=True' ya fue
    validado por validacion.validar_longitudes antes de llegar aqui, ver
    README)."""
    df = df.copy()
    for columna in columnas:
        if columna.tipo == "numero":
            original = df[columna.nombre]
            convertido = pd.to_numeric(original, errors="coerce")
            if columna.estricto:
                invalidos = convertido.isna() & original.notna()
                if invalidos.any():
                    raise ValidacionError(
                        f"La columna '{columna.nombre}' tiene valores no numericos en las filas "
                        f"{df.index[invalidos].tolist()} (FailComponent)."
                    )
            df[columna.nombre] = convertido
        elif columna.tipo == "entero":
            # Emula el Data Convert casteando a DT_I4 (no DT_R8): sin este
            # redondeo/cast a entero, la columna queda float64 y viaja con
            # decimales al INSERT -- antes (via SSIS) siempre llegaba como
            # entero, asi que un valor real con parte fraccionaria (p.ej.
            # 'TOTAL INGRESADO' con centavos de un calculo previo) se veia
            # sin decimales en meses anteriores y con decimales aqui (visto
            # en produccion, 2026-09). 'Int64' (nullable) preserva NULL para
            # IgnoreFailure sin volver la columna float.
            original = df[columna.nombre]
            convertido = pd.to_numeric(original, errors="coerce")
            if columna.estricto:
                invalidos = convertido.isna() & original.notna()
                if invalidos.any():
                    raise ValidacionError(
                        f"La columna '{columna.nombre}' tiene valores no numericos en las filas "
                        f"{df.index[invalidos].tolist()} (FailComponent)."
                    )
            df[columna.nombre] = convertido.round().astype("Int64")
        elif columna.tipo == "fecha":
            original = df[columna.nombre]
            convertido = _parsear_fechas(original)
            if columna.estricto:
                invalidos = convertido.isna() & original.notna()
                if invalidos.any():
                    raise ValidacionError(
                        f"La columna '{columna.nombre}' tiene fechas invalidas en las filas "
                        f"{df.index[invalidos].tolist()} (FailComponent)."
                    )
            # Las columnas destino son SQL Server 'date' (sin hora, DT_DBDATE
            # en el .dtsx original) -- se descarta la hora antes de insertar.
            # Bindear un Timestamp con hora contra una columna 'date' via
            # ODBC lanza 'Datetime field overflow' (visto en produccion, 2026-09).
            df[columna.nombre] = convertido.dt.date
        elif columna.tipo == "texto":
            # Siempre se castea a string, no solo cuando hay que truncar
            # (estricto=False): si el origen quedo con dtype numerico (p.ej.
            # un DNI/RUT sin dtype=str forzado en la lectura), este cast es
            # la unica proteccion contra que el valor viaje como float y
            # llegue a SQL Server con un '.0' agregado (ver
            # SharePointExcelReader.leer_hoja para la causa raiz).
            valores = df[columna.nombre].astype("string")
            if not columna.estricto and columna.longitud_max > 0:
                excede = valores.str.len() > columna.longitud_max
                if excede.any():
                    logger.warning(
                        "%s valor(es) de '%s' exceden %s caracteres, se truncan a ese ancho (IgnoreFailure): filas %s",
                        int(excede.sum()),
                        columna.nombre,
                        columna.longitud_max,
                        df.index[excede].tolist(),
                    )
                valores = valores.str.slice(0, columna.longitud_max)
            df[columna.nombre] = valores
    return df


# ---------------------------------------------------------------------------
# CROSS 0101 SSIS_CL_Senalizaciones.dtsx
# ---------------------------------------------------------------------------


def seleccionar_y_renombrar_senhalizaciones(df: pd.DataFrame) -> pd.DataFrame:
    """Data Convert de 'TBL_FUNNEL_SENHALIZACIONES': selecciona las 35
    columnas mapeadas (descarta 'TOTAL INGRESADO', 'Dia', 'MES' final y
    'OPORTUNDAD MOVIL (CHI-XXXXXX)', que se leen pero no siguen en el
    .dtsx original) y las renombra al nombre fisico de la tabla destino."""
    columnas_origen = [origen for origen, _destino in mappings.MAPEO_SENHALIZACIONES]
    renombre = dict(mappings.MAPEO_SENHALIZACIONES)
    return df[columnas_origen].rename(columns=renombre)


def corregir_rut_nombre_invertidos(df: pd.DataFrame) -> pd.DataFrame:
    """Corrige un error real de captura visto en produccion (2026-09): la
    persona cargo 'RUT DE LA EMPRESA' y 'NOMBRE EMPRESA' al reves en el
    formulario. Si 'NOMBRE EMPRESA' tiene forma de RUT chileno (_PATRON_RUT)
    y 'RUT DE LA EMPRESA' no, se intercambian los dos valores -- no es logica
    del .dtsx original, es una limpieza agregada sobre datos reales (ver
    README, 'Notas de fidelidad')."""
    df = df.copy()
    rut = df["RUT DE LA EMPRESA"].astype("string")
    nombre = df["NOMBRE EMPRESA"].astype("string")
    rut_parece_rut = rut.str.match(_PATRON_RUT, na=False)
    nombre_parece_rut = nombre.str.match(_PATRON_RUT, na=False)
    invertidas = nombre_parece_rut & ~rut_parece_rut
    if invertidas.any():
        logger.warning(
            "[senalizaciones] %s fila(s) con 'RUT DE LA EMPRESA'/'NOMBRE EMPRESA' invertidos, corregidas: %s",
            int(invertidas.sum()),
            df.index[invertidas].tolist(),
        )
        columnas = ["RUT DE LA EMPRESA", "NOMBRE EMPRESA"]
        df.loc[invertidas, columnas] = df.loc[invertidas, columnas[::-1]].values
    return df


def vaciar_valores_que_excedan_ancho(df: pd.DataFrame, columnas: tuple[ColumnaSpec, ...], contexto: str) -> pd.DataFrame:
    """Solo para columnas de texto 'estricto=True' (FailComponent en el
    .dtsx original): cuando un valor excede su ancho maximo (y no se pudo
    recuperar con una limpieza especifica como corregir_rut_nombre_invertidos),
    se deja vacio (None) en esa columna en vez de descartar la fila completa
    o abortar toda la carga -- el resto de la fila sigue siendo valida y se
    carga igual. A pedido del usuario tras revisar datos reales del
    formulario: reemplaza, para este proyecto, el aborto estricto que tenia
    el .dtsx original ante un valor demasiado largo (ver README, 'Notas de
    fidelidad'; validacion.validar_longitudes documenta el comportamiento
    original y sigue disponible/testeada, pero ya no se usa como gate).

    Las columnas 'estricto=False' (IgnoreFailure) NO pasan por aqui: se
    dejan intactas para que convertir_tipos() las trunque al ancho
    declarado (en vez de vaciarlas) -- esa es la disposicion de truncamiento
    real del .dtsx original para esas columnas, y vaciarlas aqui tambien
    perdia datos reales sin necesidad (visto en produccion, 2026-09, con
    'SEÑALIZACION // EJECUTIVO DE VENTAS': el Excel de origen trae valores
    mas largos que los 15 caracteres declarados, y deben cargarse truncados,
    no vacios)."""
    df = df.copy()
    for columna in columnas:
        if columna.tipo != "texto" or columna.longitud_max <= 0 or not columna.estricto:
            continue
        valores = df[columna.nombre].astype("string")
        excede = valores.str.len() > columna.longitud_max
        if excede.any():
            logger.warning(
                "[%s] %s valor(es) de '%s' exceden %s caracteres, se dejan vacios: filas %s",
                contexto,
                int(excede.sum()),
                columna.nombre,
                columna.longitud_max,
                df.index[excede].tolist(),
            )
            df.loc[excede, columna.nombre] = None
    return df


def corregir_dni_cero_perdido(db: DatabaseGateway) -> None:
    """Execute SQL Task 'UPDATE' (outer, nivel 'Contenedor de secuencias 1'):
    corrige 'TU DNI' para los 19 pares literales de mappings.CORRECCIONES_DNI_CEROS
    (el .dtsx original los enviaba como 19 sentencias separadas por 'GO' --
    aqui se ejecutan como UPDATEs parametrizados independientes, ver
    sql.SQL_CORREGIR_DNI_CERO_PERDIDO y README, 'Notas de fidelidad')."""
    for dni_correcto, dni_incorrecto in mappings.CORRECCIONES_DNI_CEROS:
        db.execute_script(sql.SQL_CORREGIR_DNI_CERO_PERDIDO, params=(dni_correcto, dni_incorrecto))
    logger.info("[senalizaciones] %s correcciones de 'TU DNI' (cero perdido) aplicadas.", len(mappings.CORRECCIONES_DNI_CEROS))


def corregir_dni_desde_tabla_dni(db: DatabaseGateway) -> None:
    """Execute SQL Task 'UPDATE' (interno, dentro de 'Contenedor de
    secuencias'): aplica a TBL_FUNNEL_SENHALIZACIONES.[TU DNI] la correccion
    cargada en TBL_FUNNEL_SENHALIZACIONES_DNI."""
    db.execute_script(sql.SQL_CORREGIR_DNI_DESDE_TABLA_DNI)


def ejecutar_sp_funnel_senhalizaciones(db: DatabaseGateway) -> None:
    """Execute SQL Task 'SP_FUNNEL_SENHALIZACIONES'."""
    db.execute_script(sql.SQL_EXEC_SP_FUNNEL_SENHALIZACIONES)


# ---------------------------------------------------------------------------
# CROSS 0102 SSIS_CL_Ventas.dtsx
# ---------------------------------------------------------------------------


def agregar_columnas_post_carga_basev2(df: pd.DataFrame) -> pd.DataFrame:
    """El Data Flow 'TBL_FUNNEL_VENTAS_basev2_temp' no llena
    'DNI SUPERVISOR'/'DNI ESPECIALISTA'/'COD_DNI'/'FECHA DE EVALUACION' (se
    completan despues via Execute SQL Task, ver limpiar_y_completar_basev2/
    completar_dni_sup_esp_cod) -- se agregan aqui como NULL para que
    bulk_insert inserte la fila completa con esas 4 columnas en NULL."""
    df = df.copy()
    for columna in mappings.COLUMNAS_VENTAS_BASEV2_POST_CARGA:
        df[columna] = None
    return df


def limpiar_y_completar_basev2(db: DatabaseGateway) -> None:
    """Execute SQL Task 'BaseV2\\Tarea Ejecutar SQL': limpieza de
    basev2_temp (DELETE de filas sin 'Fecha Ingreso', TRIM/UPPER, recorte de
    'Rut Empresa', y calculo de 'FECHA DE EVALUACION') -- 5 sentencias
    ejecutadas en orden (ver sql.SQL_LIMPIEZA_VENTAS_BASEV2)."""
    for sentencia in sql.SQL_LIMPIEZA_VENTAS_BASEV2:
        db.execute_script(sentencia)


def actualizar_rut_ejecutivo_desde_tabla_dni(db: DatabaseGateway) -> None:
    """Execute SQL Task 'BaseV2\\update DNI'."""
    db.execute_script(sql.SQL_ACTUALIZAR_RUT_EJECUTIVO_DESDE_TABLA_DNI)


def completar_dni_sup_esp_cod(db: DatabaseGateway) -> None:
    """Execute SQL Task 'Contenedor de secuencias 1\\UPDATE': completa
    'DNI SUPERVISOR'/'DNI ESPECIALISTA' cruzando con Sup_temp/Esp_temp, y
    copia 'RUT EJECUTIVO' a 'COD_DNI' -- 3 sentencias ejecutadas en orden
    (ver sql.SQL_COMPLETAR_DNI_SUP_ESP_COD)."""
    for sentencia in sql.SQL_COMPLETAR_DNI_SUP_ESP_COD:
        db.execute_script(sentencia)


def convertir_tipos_metas(df: pd.DataFrame) -> pd.DataFrame:
    """Data Convert parcial de 'METAS_COMISIONES': castea las columnas de
    texto (mappings.COLUMNAS_VENTAS_METAS_TEXTO) via convertir_tipos(), y
    castea a entero 'Fibra'/'Voz'/'Total'/'PERIODO' y la renombrada
    'Señalizacion Total' -> 'SEÑALIZACIONES TOTAL' -- estas 4 NO pasan por
    el Data Convert en el .dtsx original (van directo Origen -> Destino),
    pero la tabla destino las declara 'int': el .dtsx original no tiene
    ninguna disposicion de error configurada para ellas, asi que un valor no
    numerico haria fallar el INSERT completo contra SQL Server -- se replica
    aqui como estricto (ValidacionError), no como coerce silencioso (ver
    README, 'Notas de fidelidad')."""
    df = convertir_tipos(df, mappings.COLUMNAS_VENTAS_METAS_TEXTO)

    def _castear_entero_estricto(serie: pd.Series, nombre: str) -> pd.Series:
        convertido = pd.to_numeric(serie, errors="coerce")
        invalidos = convertido.isna() & serie.notna()
        if invalidos.any():
            raise ValidacionError(
                f"La columna '{nombre}' de METAS_COMISIONES tiene valores no numericos en las filas "
                f"{df.index[invalidos].tolist()} (la tabla destino la declara 'int', sin disposicion "
                "de error configurada en el .dtsx original -- el INSERT fallaria)."
            )
        return convertido

    for columna in mappings.COLUMNAS_VENTAS_METAS_NUMERICAS:
        df[columna] = _castear_entero_estricto(df[columna], columna)

    origen, destino = mappings.COLUMNA_VENTAS_METAS_SENALIZACION_TOTAL
    df[destino] = _castear_entero_estricto(df[origen], origen)
    if origen != destino:
        df = df.drop(columns=[origen])
    return df


def renombrar_basev2_a_temp(df: pd.DataFrame) -> pd.DataFrame:
    """Data Flow 'LOCAL\\TBL_FUNNEL_VENTAS_Temp': copia basev2_temp a Temp
    sin transformacion intermedia, salvo el renombre de columnas de
    mappings.RENOMBRE_VENTAS_BASEV2_A_TEMP y el descarte de 'Tramo Ingreso'
    (se lee de basev2_temp pero no se mapea al destino en el .dtsx original)."""
    df = df.drop(columns=["Tramo Ingreso"], errors="ignore")
    return df.rename(columns=mappings.RENOMBRE_VENTAS_BASEV2_A_TEMP)


def borrar_temp_anterior_a_fecha(db: DatabaseGateway, fecha: date) -> int:
    """Execute SQL Task 'LOCAL\\DELETE TEMP <'."""
    filas = db.execute_script_rowcount(sql.SQL_LOCAL_DELETE_TEMP_MENOR_A_FECHA, params=(fecha,))
    logger.info("[ventas] LOCAL/DELETE TEMP <: %s filas purgadas de TBL_FUNNEL_VENTAS_Temp (fecha=%s).", filas, fecha)
    return filas


def borrar_ventas2_desde_fecha(db: DatabaseGateway, fecha: date) -> int:
    """Execute SQL Task 'LOCAL\\DELETE VENTAS2 >'."""
    filas = db.execute_script_rowcount(sql.SQL_LOCAL_DELETE_VENTAS2_MAYOR_IGUAL_FECHA, params=(fecha,))
    logger.info("[ventas] LOCAL/DELETE VENTAS2 >=: %s filas purgadas de TBL_FUNNEL_VENTAS2 (fecha=%s).", filas, fecha)
    return filas


def insertar_ventas2_desde_temp(db: DatabaseGateway) -> int:
    """Execute SQL Task 'LOCAL\\INSERT VENAS2'."""
    filas = db.execute_script_rowcount(sql.SQL_LOCAL_INSERT_VENTAS2)
    logger.info("[ventas] LOCAL/INSERT VENAS2: %s filas insertadas en TBL_FUNNEL_VENTAS2 desde TBL_FUNNEL_VENTAS_Temp.", filas)
    return filas
