"""
Orquestación de SSIS_CL_ISN.dtsx. Reproduce el árbol de PrecedenceConstraint
completo (todas "on Success", sin expresiones -- ver el README para el
diagrama del árbol original):

  Contenedor de secuencias (4 ramas EN PARALELO; las de aux_contacto y aux_cliente estan APAGADAS por defecto,
  ver config.isn_cargar_aux_contacto / isn_cargar_aux_cliente -> quedan 2)
      -> SECUENCIA NUEVA (SF -> Contenedor de secuencias -> TBL_ISN_PRE -> Contenedor de secuencias 1, secuencial)
          -> fan-out EN PARALELO: rama TBL_ISN | rama TBL_ISN_CALIDAD

Igual que en 10_campaña_termometro/pipeline.py: las ramas paralelas se
lanzan con ThreadPoolExecutor y, si cualquiera falla, el paso siguiente NO
se ejecuta -- así se comporta un contenedor SSIS cuyos hijos alimentan a un
mismo sucesor "on Success".
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common.sql_loader import load_dataframe, truncate_table
from config import settings
from db import run_sql_file
from isn import columns as isn_columns
from isn.extractors import aux_cliente_extractor, aux_contacto_extractor, isn_extractor
from isn.loaders.csv_writer import archivar_isn_csv, exportar_isn_csv
from isn.transformers.envios_consolidado import transform_envios_consolidado
from isn.validators.aux_validator import validar_no_vacio
from isn.validators.envios_validator import validar_envios_consolidado

logger = logging.getLogger(__name__)

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_ISN = settings.db_database_isn
_CALIDAD = settings.db_database_calidad


def _correr_ramas_paralelas(ramas: dict, etiqueta: str) -> None:
    logger.info("[%s] ejecutando %d ramas en paralelo: %s", etiqueta, len(ramas), list(ramas))
    with ThreadPoolExecutor(max_workers=len(ramas)) as executor:
        futures = {executor.submit(fn): name for name, fn in ramas.items()}
        errores = []
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 - se agrega el nombre de rama y se relanza más abajo
                logger.exception("[%s] la rama '%s' falló", etiqueta, name)
                errores.append((name, exc))
    if errores:
        raise RuntimeError(
            f"[{etiqueta}] se detuvo: fallaron las ramas {[n for n, _ in errores]}. "
            "El paso siguiente no se ejecuta (igual que las Precedence Constraints originales)."
        )


# --- Contenedor de secuencias (4 ramas en paralelo) ---------------------------------


def _rama_delete_envios_consolidado_local() -> None:
    run_sql_file(_ISN, _SQL_DIR / "delete_envios_consolidado_local.sql")


def _rama_tbls_auxiliares() -> None:
    run_sql_file(_ISN, _SQL_DIR / "tbls_auxiliares.sql")


def _rama_aux_contacto() -> None:
    # Se lee/valida el CSV ANTES de truncar: si el archivo no existe o falla
    # la validación, TBL_ISN_SF_AUX_CONTACTO no se toca en vez de quedar vacía.
    df = aux_contacto_extractor.leer_aux_contacto()
    validar_no_vacio(df, isn_columns.TABLA_AUX_CONTACTO, isn_columns.COLUMNAS_AUX_CONTACTO)
    truncate_table(_ISN, isn_columns.TABLA_AUX_CONTACTO)
    load_dataframe(_ISN, df, isn_columns.TABLA_AUX_CONTACTO)


def _rama_aux_cliente() -> None:
    df = aux_cliente_extractor.leer_aux_cliente()
    validar_no_vacio(df, isn_columns.TABLA_AUX_CLIENTE, isn_columns.COLUMNAS_AUX_CLIENTE)
    truncate_table(_ISN, isn_columns.TABLA_AUX_CLIENTE)
    load_dataframe(_ISN, df, isn_columns.TABLA_AUX_CLIENTE)


def _contenedor_de_secuencias() -> None:
    ramas = {
        "delete_envios_consolidado_local": _rama_delete_envios_consolidado_local,
        "tbls_auxiliares": _rama_tbls_auxiliares,
    }
    # Ramas de aux_contacto / aux_cliente: APAGADAS por defecto (sus columnas solo llegan a TBL_ISN_SF, que nadie lee,
    # y no pasan al isn.csv). Cada una se reactiva con su variable de entorno (ver config.py).
    opcionales = (
        ("aux_contacto", settings.isn_cargar_aux_contacto, _rama_aux_contacto, "ISN_CARGAR_AUX_CONTACTO",
         "Reporte_isn_aux_contacto.csv", "TBL_ISN_SF_AUX_CONTACTO"),
        ("aux_cliente", settings.isn_cargar_aux_cliente, _rama_aux_cliente, "ISN_CARGAR_AUX_CLIENTE",
         "Reporte_isn_aux_cliente.csv", "TBL_ISN_SF_AUX_CLIENTE"),
    )
    for nombre, activa, rama, variable, archivo, tabla in opcionales:
        if activa:
            ramas[nombre] = rama
        else:
            logger.info(
                "[Contenedor de secuencias] rama '%s' APAGADA (%s=false): no se descarga %s ni se toca %s (queda congelada).",
                nombre, variable, archivo, tabla,
            )
    _correr_ramas_paralelas(ramas, "Contenedor de secuencias")


# --- SECUENCIA NUEVA (secuencial) ---------------------------------------------------


def _secuencia_nueva(fecha_inicio: str, fecha_fin: str) -> None:
    logger.info("[SECUENCIA NUEVA] inicio (fecha_inicio=%s, fecha_fin=%s)", fecha_inicio, fecha_fin)

    # SF: DROP -> TBL_ISN_SF
    run_sql_file(_ISN, _SQL_DIR / "drop_tbl_isn_sf.sql")
    run_sql_file(
        _ISN,
        _SQL_DIR / "select_into_tbl_isn_sf.sql",
        {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
    )

    # Contenedor de secuencias: DELETE -> INSERT (TBL_ISN_SF_CONSOLIDADO)
    run_sql_file(_ISN, _SQL_DIR / "delete_tbl_isn_sf_consolidado.sql")
    run_sql_file(_ISN, _SQL_DIR / "insert_tbl_isn_sf_consolidado.sql")

    # TBL_ISN_PRE: DROP -> TBL_ISN_PRE
    run_sql_file(_ISN, _SQL_DIR / "drop_tbl_isn_pre.sql")
    run_sql_file(_ISN, _SQL_DIR / "select_into_tbl_isn_pre.sql")

    # Contenedor de secuencias 1: DELETE -> INSERT (TBL_ISN_PRE_CONSOLIDADO)
    run_sql_file(_ISN, _SQL_DIR / "delete_tbl_isn_pre_consolidado.sql")
    run_sql_file(_ISN, _SQL_DIR / "insert_tbl_isn_pre_consolidado.sql")

    logger.info("[SECUENCIA NUEVA] fin")


# --- Fan-out final: TBL_ISN | TBL_ISN_CALIDAD ---------------------------------------


def _rama_tbl_isn() -> None:
    logger.info("[TBL_ISN] inicio")
    run_sql_file(_ISN, _SQL_DIR / "drop_tbl_isn.sql")
    run_sql_file(_ISN, _SQL_DIR / "select_into_tbl_isn.sql")

    df = isn_extractor.leer_tbl_isn_para_export()
    exportar_isn_csv(df)
    archivar_isn_csv()
    logger.info("[TBL_ISN] fin (%d filas exportadas)", len(df))


def _rama_tbl_isn_calidad() -> None:
    logger.info("[TBL_ISN_CALIDAD] inicio")
    run_sql_file(_ISN, _SQL_DIR / "drop_tbl_isn_calidad.sql")
    run_sql_file(_ISN, _SQL_DIR / "select_into_tbl_isn_calidad.sql")

    # ACTUALIZACION SERVIDOR: DELETE -> Data Flow -> UPDATE, todo en CL_CALIDAD.
    run_sql_file(_CALIDAD, _SQL_DIR / "delete_envios_consolidado_calidad.sql")

    df = isn_extractor.leer_tbl_isn_calidad()
    validar_envios_consolidado(df)
    df = transform_envios_consolidado(df)
    load_dataframe(_CALIDAD, df, isn_columns.TABLA_ENVIOS_CONSOLIDADO)

    run_sql_file(_CALIDAD, _SQL_DIR / "update_envios_consolidado_calidad.sql")
    logger.info("[TBL_ISN_CALIDAD] fin (%d filas)", len(df))


def run(fecha_inicio: str | None = None, fecha_fin: str | None = None) -> None:
    fecha_inicio = fecha_inicio or settings.fecha_inicio
    fecha_fin = fecha_fin or settings.fecha_fin

    logger.info("[isn] inicio")
    _contenedor_de_secuencias()
    _secuencia_nueva(fecha_inicio, fecha_fin)
    _correr_ramas_paralelas(
        {"TBL_ISN": _rama_tbl_isn, "TBL_ISN_CALIDAD": _rama_tbl_isn_calidad},
        "fan-out final",
    )
    logger.info("[isn] fin")
