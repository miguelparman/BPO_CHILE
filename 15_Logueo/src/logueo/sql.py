"""Sentencias T-SQL del proceso.

Cada archivo de scripts_sql/ es una copia LITERAL (byte a byte) de la
propiedad SqlStatementSource de la tarea (o SqlCommand del Lookup) en
Cl_Proc_Logueo.dtsx -- no se reescribio ni se "corrigio" nada. La prueba
tests/equivalencia/test_equivalencia_dtsx.py verifica que siguen identicos.

La tarea 'BK' (BACKUP DATABASE) esta DESHABILITADA en el paquete y no se
migra; su SQL queda como referencia en docs/BK_deshabilitado_no_migrado.sql.
"""

from __future__ import annotations

from pathlib import Path

import mappings

_DIR = Path(__file__).resolve().parent / "scripts_sql"


def _leer(nombre: str) -> str:
    with open(_DIR / nombre, encoding="utf-8", newline="") as f:
        return f.read()


# Tarea del .dtsx (refId)                                   -> script
LOG_INICIO = _leer("00_log_inicio.sql")  # Package\Log Inicio
LOOKUP_REFERENCIA = _leer("10_lookup_referencia.sql")  # Package\LOGUEO CHILE\CARGA TABLA\Busqueda (SqlCommand)
AGREGA_DNI = _leer("20_agrega_dni.sql")  # Package\LOGUEO CHILE\AGREGA DNI  (? = User::Periodo)
LOG_FIN = _leer("30_log_fin.sql")  # Package\Log Fin
SP_LOGUEO = _leer("40_sp_logueo.sql")  # Package\SP

# Fast load del 'Destino de OLE DB' (AccessMode 3, TABLOCK, CHECK_CONSTRAINTS):
# INSERT parametrizado por lotes dentro de UNA transaccion
# (FastLoadMaxInsertCommitSize = 2147483647 -> un solo commit).
INSERT_DESTINO = (
    f"INSERT INTO [{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}] WITH (TABLOCK) ("
    + ", ".join(f"[{c}]" for c in mappings.COLUMNAS_INSERT)
    + ") VALUES ("
    + ", ".join("?" for _ in mappings.COLUMNAS_INSERT)
    + ")"
)
