"""Sentencias T-SQL de CL_Proc_Trafico_FCR_02.dtsx.

Cada archivo de scripts_sql/ es una copia LITERAL (byte a byte) de la
propiedad SqlStatementSource de la tarea correspondiente; la prueba
tests/equivalencia/test_equivalencia_dtsx.py verifica que siguen siendo
identicos al .dtsx.

- Log Inicio, Limpia Tabla y Log Fin se ejecutan tal cual.
- Alimenta Tabla NO se ejecuta en el pipeline: su logica (5 bases, LEAD,
  14 indicadores FCR y TRAMO_QUIEBRE) esta separada en extraccion ->
  transformacion -> carga. El literal se conserva como ORACULO: la
  herramienta tools/equivalencia.py lo corre (redirigido a una tabla #temp,
  sin escribir en TBL_FCR) para comparar su resultado con el de Python.
"""

from __future__ import annotations

from pathlib import Path

import mappings

_DIR = Path(__file__).resolve().parent / "scripts_sql"


def _leer(nombre: str) -> str:
    return (_DIR / nombre).read_text(encoding="utf-8")


# Tarea del .dtsx (refId)                                        -> script
LOG_INICIO = _leer("00_log_inicio.sql")  # Package\Log Inicio
LIMPIA_TABLA = _leer("10_limpia_tabla.sql")  # Package\Proceso Carga Tabla\Limpia Tabla (? = User::Periodo)
ALIMENTA_TABLA = _leer("11_alimenta_tabla.sql")  # Package\Proceso Carga Tabla\Alimenta Tabla (? = User::Periodo)
LOG_FIN = _leer("99_log_fin.sql")  # Package\Log Fin


def extraccion_base(base: mappings.BaseFCR) -> str:
    """SELECT de origen del bloque 'XA' de una base de Alimenta Tabla, con el
    MISMO filtro (misma expresion, evaluada por SQL Server con la collation
    del servidor). Solo se leen las columnas crudas; FECHA, HORA, BASE y
    [FECHA/HORA] se derivan en transformacion/. El parametro reemplaza a
    '@PERIODO INT = ?'. El SERVICIO es una constante de mappings.py, no una
    entrada externa: se escribe literal, igual que en el original."""
    c = mappings.COLUMNA_INICIO
    return (
        f"SELECT [{c}], ANI, SERVICIO, LOGINID\n"
        f"FROM [CL_TRAFICO].[{mappings.SCHEMA}].[{base.tabla_origen}]\n"
        f"WHERE CONVERT(VARCHAR(6),[{c}],112)>=CAST(? AS INT) AND SERVICIO IN ('{base.servicio}')"
    )


CONTAR_PERIODO = (
    f"SELECT COUNT(*) FROM [CL_TRAFICO].[{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}] "
    "WHERE YEAR(FECHA)*100+MONTH(FECHA)>=?"
)

# --------------------------------------------------------------------------- #
# Oraculo (solo tools/equivalencia.py)
# --------------------------------------------------------------------------- #
TABLA_ORACULO = "#TBL_FCR_ORACULO"
_INSERT_ORIGINAL = "INSERT INTO [CL_TRAFICO].[dbo].[TBL_FCR]"
_DROP_GLOBAL = "DROP TABLE IF EXISTS  ##TBL_TMP_FCR;"


def alimenta_tabla_oraculo() -> str:
    """Alimenta Tabla con UN solo cambio de destino: inserta en una tabla
    #temp de la sesion con la misma estructura que TBL_FCR (SELECT TOP 0 *
    INTO), en lugar de TBL_FCR. Asi se obtiene lo que SSIS insertaria, con las
    mismas conversiones implicitas, sin escribir en produccion. Tambien se
    quitan los 'DROP TABLE IF EXISTS ##TBL_TMP_FCR' (tabla GLOBAL que el script
    nunca crea): para que la verificacion no pueda afectar a otra sesion."""
    if ALIMENTA_TABLA.count(_INSERT_ORIGINAL) != 1 or ALIMENTA_TABLA.count(_DROP_GLOBAL) != 2:
        raise ValueError("El T-SQL de Alimenta Tabla no tiene la forma esperada para el oraculo.")
    cuerpo = ALIMENTA_TABLA.replace(_INSERT_ORIGINAL, f"INSERT INTO {TABLA_ORACULO}").replace(_DROP_GLOBAL, "")
    return (
        "SET NOCOUNT ON;\n"
        f"DROP TABLE IF EXISTS {TABLA_ORACULO};\n"
        f"SELECT TOP 0 * INTO {TABLA_ORACULO} FROM [CL_TRAFICO].[dbo].[TBL_FCR];\n" + cuerpo
    )
