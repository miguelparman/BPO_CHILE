"""Carga.

- Log_Inicio / Log_Fin: [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
  (Nombre='Update_Chile_Calidad_Epa'), en autocommit como en SSIS.
- WSP / EPA_ISN: en vez de 'TRUNCATE' (Execute SQL Task) + INSERT de toda la
  tabla (script .py), DELETE de los periodos que trae el CSV + INSERT, en UNA
  transaccion (decision (a) del plan: el CSV solo trae 2 meses y el
  historico debe conservarse). En SSIS eran dos tareas separadas: si el
  script fallaba, la tabla quedaba vacia y SP.EPA_ISN_CHILE corria igual
  (reconstruyendo TBL_CALIDAD_RETENCIONES vacia); aqui un fallo deja la tabla
  como estaba.
- MEDALLIA: TRUNCATE + INSERT (la tabla es de paso: SP_PROCESO_ENCUESTAS_MEDALLIA
  la vacia al terminar). Primero un INSERT masivo transaccional; si falla, se
  repite fila a fila omitiendo las que fallan, como el script original.
- SP_EPA_ISN_CHILE / SP_PROCESO_ENCUESTAS_MEDALLIA: EXEC literal del .dtsx,
  en autocommit (semantica OLE DB de SSIS).
"""

from __future__ import annotations

import logging

import pandas as pd

import mappings
import sql
from mappings import Traslado

logger = logging.getLogger("epa_wsp")


def registrar_inicio(db_general) -> None:
    """Package\\Log_Inicio."""
    db_general.execute_autocommit(sql.LOG_INICIO)


def registrar_fin(db_general) -> None:
    """Package\\Log_Fin."""
    db_general.execute_autocommit(sql.LOG_FIN)


def _param_periodo(traslado: Traslado, periodo: int):
    # periodo_evento es nvarchar(10) en TBL_ENCUESTAS_CHILE: se compara como
    # texto (un parametro int forzaria CONVERT de toda la columna).
    return str(periodo) if traslado.tipo_periodo in ("nvarchar", "varchar") else int(periodo)


def cargar_ventana(
    db_indicadores, traslado: Traslado, df: pd.DataFrame, periodos: list[int], periodo_desde: int | None = None
) -> int:
    """DELETE de los periodos del CSV (+ los anteriores a periodo_desde) e
    INSERT, todo o nada."""
    with db_indicadores.transaccion():
        if periodo_desde is not None:
            db_indicadores.execute_script(sql.delete_anteriores(traslado), (int(periodo_desde),))
        db_indicadores.execute_script(
            sql.delete_ventana(traslado, len(periodos)), [_param_periodo(traslado, p) for p in periodos]
        )
        logger.info("  %s: DELETE %s IN %s", traslado.tabla, traslado.columna_periodo, periodos)
        return db_indicadores.bulk_insert(traslado.tabla, df, mappings.SCHEMA, esquema=traslado.esquema)


def cargar_medallia(db_indicadores, df: pd.DataFrame, traslado: Traslado = mappings.MEDALLIA) -> tuple[int, list]:
    """TRUNCATE TABLE [TBL_ENCUESTAS_MEDALLIA] + INSERT. Devuelve
    (filas insertadas, [(fila, error)])."""
    try:
        with db_indicadores.transaccion():
            db_indicadores.execute_script(sql.TRUNCATE_ENCUESTAS_MEDALLIA)
            insertadas = db_indicadores.bulk_insert(traslado.tabla, df, mappings.SCHEMA, esquema=traslado.esquema)
        return insertadas, []
    except Exception as exc:  # noqa: BLE001 - se reintenta fila a fila
        logger.warning("  %s: el INSERT masivo fallo (%s); se reintenta fila a fila.", traslado.tabla, exc)

    db_indicadores.execute_script(sql.TRUNCATE_ENCUESTAS_MEDALLIA)
    insertadas, errores = db_indicadores.insert_tolerante(traslado.tabla, df, mappings.SCHEMA)
    for fila, error in errores[:20]:
        logger.error("  %s: error en fila %s: %s", traslado.tabla, fila, error)
    return insertadas, errores


def ejecutar_sp(db_calidad, script: str) -> None:
    """Package\\SP_EPA_ISN_CHILE y Package\\MEDALIA\\SP_PROCESO_ENCUESTAS_MEDALLIA."""
    db_calidad.execute_autocommit(script)
