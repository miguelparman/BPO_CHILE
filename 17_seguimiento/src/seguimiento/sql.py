"""Sentencias T-SQL del proceso.

Cada archivo de scripts_sql/pXX/ es una copia LITERAL (byte a byte) de la
propiedad SqlStatementSource de la Execute SQL Task correspondiente del
.dtsx -- no se reescribio ni se "corrigio" nada. La prueba
tests/equivalencia/test_equivalencia_dtsx.py verifica que siguen identicos.

Al ejecutarse, a_temporal() redirige las staging de CL_TEMPORALES que se
reemplazan por #temporales de la sesion del paquete (mappings.TABLAS_TEMPORALES):
'[CL_TEMPORALES].[dbo].[TBL_X]' -> '#TBL_X'. Es la UNICA modificacion.

Tareas del .dtsx que NO se ejecutan (ver docs/EQUIVALENCIA.md):
  - redundantes con la migracion: los TRUNCATE de staging que pasan a
    #temporales, y 'Agrega Nombre de Contacto' (cruce en Python);
  - 02 'ACTUALIZA CASOS OTRO PAIS': excluida por decision del usuario
    (DELETE en PE_SALESFORCE_ACTUAL; SQL en docs/no_migrado/);
  - 02 'ACTUALIZA TIFICIACIONES' y 07 'BK': deshabilitadas en el paquete.
"""

from __future__ import annotations

from pathlib import Path

from mappings import BD_STAGING, ESQUEMA, TABLAS_TEMPORALES, FlujoSpec

_DIR = Path(__file__).resolve().parent / "scripts_sql"


def leer(paquete: str, nombre: str) -> str:
    """Texto literal de scripts_sql/<paquete>/<nombre>."""
    with open(_DIR / paquete / nombre, encoding="utf-8", newline="") as f:
        return f.read()


def nombre_staging(tabla: str) -> str:
    return f"[{BD_STAGING}].[{ESQUEMA}].[{tabla}]"


def a_temporal(sql: str) -> str:
    """Redirige las staging reemplazadas a sus #temporales. El espacio final
    cubre los casos en que el .dtsx pega el alias al nombre ('...]X0')."""
    for tabla in TABLAS_TEMPORALES:
        sql = sql.replace(nombre_staging(tabla), f"#{tabla} ")
    return sql


def crear_temporal(tabla: str, tipos: tuple[tuple[str, str], ...] = ()) -> str:
    """#temporal con la estructura exacta de la staging permanente (molde:
    mismos tipos, anchos y collation; no lee ni escribe sus filas), salvo las
    columnas de 'tipos' (FlujoSpec.tipos_temporal)."""
    alteraciones = "".join(f" ALTER TABLE #{tabla} ALTER COLUMN [{c}] {t} NULL;" for c, t in tipos)
    return f"DROP TABLE IF EXISTS #{tabla}; SELECT TOP 0 * INTO #{tabla} FROM {nombre_staging(tabla)};{alteraciones}"


def insert_temporal(flujo: FlujoSpec) -> str:
    """Equivalente al fast load del OLE DB Destination, sobre la #temporal
    (tempdb: carga minimamente registrada, sin TABLOCK que pedir)."""
    columnas = flujo.columnas_insert
    return (
        f"INSERT INTO #{flujo.tabla} ("
        + ", ".join(f"[{c}]" for c in columnas)
        + ") VALUES ("
        + ", ".join("?" for _ in columnas)
        + ")"
    )


def insert_tabla(tabla: str, columnas: tuple[str, ...]) -> str:
    """INSERT parametrizado en una tabla permanente de CL_TEMPORALES
    (equivalente a DataFrame.to_sql(if_exists='append'))."""
    return (
        f"INSERT INTO {nombre_staging(tabla)} ("
        + ", ".join(f"[{c}]" for c in columnas)
        + ") VALUES ("
        + ", ".join("?" for _ in columnas)
        + ")"
    )
