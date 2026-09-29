"""Sentencias T-SQL del proceso.

1) Execute SQL Tasks de CL_Proc_EPA_WSP.dtsx: cada archivo de scripts_sql/
   es una copia LITERAL (byte a byte) de la propiedad SqlStatementSource de
   la tarea -- no se reescribio ni se "corrigio" nada. La prueba
   tests/equivalencia/test_equivalencia_dtsx.py verifica que siguen siendo
   identicos al .dtsx.

2) Sentencias que vivian dentro de los scripts .py (102_calidad/) o que
   introduce la migracion (ventana por periodo, decision (a) del plan).
"""

from __future__ import annotations

from pathlib import Path

import mappings

_DIR = Path(__file__).resolve().parent / "scripts_sql"


def _leer(nombre: str) -> str:
    return (_DIR / nombre).read_text(encoding="utf-8")


# Tarea del .dtsx (refId)                                           -> script
LOG_INICIO = _leer("00_log_inicio.sql")  # Package\Log_Inicio  (162.BBDD_GENERAL)
TRUNCATE_WSP_MEDALLIA = _leer("10_truncate_tbl_encuestas_wsp_medallia.sql")  # Package\WSP\TRUNCATE ...  (162.CL_TEMPORALES_INDICADORES)
TRUNCATE_ENCUESTAS_CHILE = _leer("20_truncate_tbl_encuestas_chile.sql")  # Package\EPA_ISN\TRUNCATE ...  (162.CL_TEMPORALES_INDICADORES)
SP_EPA_ISN_CHILE = _leer("30_sp_epa_isn_chile.sql")  # Package\SP_EPA_ISN_CHILE  (162.CL_CALIDAD)
SP_PROCESO_ENCUESTAS_MEDALLIA = _leer("40_sp_proceso_encuestas_medallia.sql")  # Package\MEDALIA\SP_...  (162.CL_CALIDAD)
LOG_FIN = _leer("99_log_fin.sql")  # Package\Log_Fin  (162.BBDD_GENERAL)

# CL_Carga_de_encuestas_MEDALLIA.py: cursor.execute("TRUNCATE TABLE [TBL_ENCUESTAS_MEDALLIA]")
TRUNCATE_ENCUESTAS_MEDALLIA = f"TRUNCATE TABLE [{mappings.MEDALLIA.tabla}]"


def delete_ventana(traslado: mappings.Traslado, n_periodos: int) -> str:
    """Reemplaza al TRUNCATE de la tabla temporal (decision (a) del plan):
    el CSV de SharePoint trae solo los ultimos 2 meses de [Externos_Frac], asi
    que se borran SOLO esos periodos y se conserva el historico que el
    script original copiaba completo (ENCUESTA >= 202601, WS_MEDALLIA_2 entera)
    y que SP.EPA_ISN_CHILE sigue leyendo (p.ej. RETENCIONES >= 202401)."""
    marcas = ", ".join("?" for _ in range(n_periodos))
    return f"DELETE FROM [{mappings.SCHEMA}].[{traslado.tabla}] WHERE [{traslado.columna_periodo}] IN ({marcas})"


def delete_anteriores(traslado: mappings.Traslado) -> str:
    """Filtro 'WHERE periodo_evento >= 202601' del traslado EPA_ISN: la tabla
    nunca debe contener periodos anteriores (con TRUNCATE era implicito)."""
    col = f"[{traslado.columna_periodo}]"
    return f"DELETE FROM [{mappings.SCHEMA}].[{traslado.tabla}] WHERE TRY_CAST({col} AS int) < ? OR {col} IS NULL"
