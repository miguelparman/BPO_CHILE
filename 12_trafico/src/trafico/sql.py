"""Sentencias T-SQL de las Execute SQL Tasks de CL_Proc_Trafico_01.dtsx.

Cada archivo de scripts_sql/ es una copia LITERAL (byte a byte) de la
propiedad SqlStatementSource de la tarea correspondiente -- no se reescribio
ni se "corrigio" nada, para preservar la logica funcional. La prueba
tests/equivalencia/test_equivalencia_dtsx.py verifica que siguen siendo
identicos al .dtsx.

Las tareas cruzan varias bases del mismo servidor con nombres de 3 partes
(CL_DATA, CL_CARTERA, CL_ANALISIS, CL_PLANTA, BBDD_GENERAL), por eso se
ejecutan en SQL Server y no se trasladaron a pandas.
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent / "scripts_sql"


def _leer(nombre: str) -> str:
    return (_DIR / nombre).read_text(encoding="utf-8")


# Tarea del .dtsx (refId)                                      -> script
LOG_INICIO = _leer("00_log_inicio.sql")  # Package\Log Inicio
TEMPORALES_TRUNCA_TABLAS = _leer("10_temporales_trunca_tablas.sql")  # Package\TEMPORALES\TRUNCA TABLAS
TEMPORALES_UPDATE = _leer("11_temporales_update.sql")  # Package\TEMPORALES\UPDATE
LIMPIA_FORMATEANDO_ANI = _leer("20_limpia_formateando_ani.sql")  # Package\LIMPIA TEMPORALES\FORMATEANDO ANI
LIMPIA_UPDATE_RUT = _leer("21_limpia_update_rut.sql")  # Package\LIMPIA TEMPORALES\UPDATE RUT
LIMPIA_UPDATE_COD_DNI = _leer("22_limpia_update_cod_dni.sql")  # Package\LIMPIA TEMPORALES\UPDATE COD_DNI
LIMPIA_UPDATE_SEGMENTO = _leer("23_limpia_update_segmento.sql")  # ...\UPDATE SEGMENTO - UPDATE SUBSEGMENTO
LIMPIA_SEGMENTO_COLA = _leer("24_limpia_segmento_cola.sql")  # Package\LIMPIA TEMPORALES\SEGMENTO COLA
LIMPIA_LLAMA_CCAA = _leer("25_limpia_llama_ccaa.sql")  # Package\LIMPIA TEMPORALES\LLAMA CCAA?
CL_TRAFICO_DELETE_PERIODO = _leer("30_cl_trafico_delete_periodo.sql")  # Package\CL_TRAFICO\DELETE PERIODO (? = User::Periodo)
CL_TRAFICO_UPDATE_WSP = _leer("31_cl_trafico_update_wsp.sql")  # Package\CL_TRAFICO\UPDATE_WSP
LOG_FIN = _leer("99_log_fin.sql")  # Package\Log Fin

# Secuencia 'LIMPIA TEMPORALES' en el orden de sus Precedence Constraints.
LIMPIA_TEMPORALES = (
    ("FORMATEANDO ANI", LIMPIA_FORMATEANDO_ANI),
    ("UPDATE RUT", LIMPIA_UPDATE_RUT),
    ("UPDATE COD_DNI", LIMPIA_UPDATE_COD_DNI),
    ("UPDATE SEGMENTO - UPDATE SUBSEGMENTO", LIMPIA_UPDATE_SEGMENTO),
    ("SEGMENTO COLA", LIMPIA_SEGMENTO_COLA),
    ("LLAMA CCAA?", LIMPIA_LLAMA_CCAA),
)
