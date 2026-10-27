"""Sentencias T-SQL del proceso (scripts_sql/).

  sla/        TRUNCA TABLA y UPDATE: copia LITERAL (byte a byte) de la propiedad
              SqlStatementSource de la Execute SQL Task del .dtsx. Lo unico que
              cambia al ejecutarse es el nombre de la tabla (modo prueba usa
              TBL_SLA_PY): para_sla(). tests/equivalencia verifica que sigan
              identicos al .dtsx.
  puntualidad/ la tarea PUNTUALIDAD, reescrita (ver docs/EQUIVALENCIA.md). El
              original, literal, esta en docs/referencia_sql/p2_PUNTUALIDAD.sql y
              es contra lo que se prueba la equivalencia (equivalencia/).
  prueba/     solo modo prueba: crea TBL_SLA_PY.
  ajustes/    cambios deliberados respecto del .dtsx: SLA pasa de int a decimal(10,2).

Los scripts de puntualidad/ llevan marcas {{TBL_SLA}}, {{TBL_PUNTUALIDAD}},
{{FUENTE}} y {{FECHA_DESDE}} que se reemplazan por los valores del Destino.
"""

from __future__ import annotations

from pathlib import Path

from mappings import TBL_SLA_REAL, Destino

_DIR = Path(__file__).resolve().parent / "scripts_sql"

# Nombre de la tabla en los scripts literales del .dtsx.
_TBL_SLA_DTSX = "[CL_ANALISIS].[dbo].[TBL_SLA]"

# VIEW_SLA_4TIP / 3TIP / 1TIP (su definicion, como tabla derivada sobre {{TBL_SLA}}), con el desempate
# 'Vigente' primero. Se usan en 20_base.sql y en la prueba de equivalencia (comparador.py).
VISTAS_SLA = {
    '4TIP': "(\n\t\tSELECT [Línea de Negocio], [Motivo de contacto], Tipología, Subtipología, [SLA], [Día/Hora], [Calendario/Laboral], [Estado]\n\t\t\t,ROW_NUMBER() OVER (PARTITION BY [Línea de Negocio],[Motivo de contacto],[Tipología],[Subtipología] ORDER BY [Línea de Negocio],[Motivo de contacto],[Tipología],[Subtipología], CASE WHEN [Estado] = 'Vigente' THEN 0 ELSE 1 END) [indice]\n\t\tFROM {{TBL_SLA}}\n\t\tWHERE [Línea de Negocio] <> ''\n\t)",
    '3TIP': "(\n\t\tSELECT x0.[Motivo de contacto], x0.[Tipología], x0.[Subtipología], x0.[SLA], x0.[Día/Hora], x0.[Calendario/Laboral], x0.[Estado]\n\t\tFROM (\n\t\t\tSELECT [Motivo de contacto], [Tipología], [Subtipología], [SLA], [Día/Hora], [Calendario/Laboral], [Estado]\n\t\t\t\t,ROW_NUMBER() OVER (PARTITION BY [Motivo de contacto],[Tipología],[Subtipología] ORDER BY [Motivo de contacto],[Tipología],[Subtipología], CASE WHEN [Estado] = 'Vigente' THEN 0 ELSE 1 END) [Indice]\n\t\t\tFROM {{TBL_SLA}}\n\t\t\tWHERE [Línea de Negocio] = ''\n\t\t) x0\n\t\tWHERE indice = 1\n\t)",
    '1TIP': "(\n\t\tSELECT x0.[Motivo de contacto], x0.[SLA], x0.[Día/Hora], x0.[Calendario/Laboral], x0.[Estado]\n\t\tFROM (\n\t\t\tSELECT [Motivo de contacto], [SLA], [Día/Hora], [Calendario/Laboral], [Estado]\n\t\t\t\t,ROW_NUMBER() OVER (PARTITION BY [Línea de Negocio],[Motivo de contacto],[Tipología],[Subtipología] ORDER BY [Línea de Negocio],[Motivo de contacto],[Tipología],[Subtipología], CASE WHEN [Estado] = 'Vigente' THEN 0 ELSE 1 END) [indice]\n\t\t\tFROM {{TBL_SLA}}\n\t\t\tWHERE [Tipología] = '' AND [Subtipología] = ''\n\t\t) x0\n\t\tWHERE x0.[indice] = 1\n\t)",
}


def leer(carpeta: str, nombre: str) -> str:
    """Texto literal de scripts_sql/<carpeta>/<nombre>."""
    with open(_DIR / carpeta / nombre, encoding="utf-8", newline="") as f:
        return f.read()


def para_sla(sql: str, destino: Destino) -> str:
    """Scripts literales del .dtsx: solo se redirige el nombre de TBL_SLA."""
    return sql.replace(_TBL_SLA_DTSX, destino.tbl_sla)


def con_marcas(sql: str, destino: Destino, fuente: str | None = None) -> str:
    """Reemplaza las marcas {{...}} de los scripts propios."""
    for nombre, bloque in VISTAS_SLA.items():
        sql = sql.replace("{{SLA_" + nombre + "}}", bloque)
    sql = (
        sql.replace("{{TBL_SLA_REAL}}", TBL_SLA_REAL)
        .replace("{{TBL_SLA}}", destino.tbl_sla)
        .replace("{{TBL_PUNTUALIDAD}}", destino.tbl_puntualidad)
        .replace("{{FUENTE}}", fuente or destino.fuente)
        .replace("{{FECHA_DESDE}}", destino.fecha_desde)
    )
    if "{{" in sql:
        raise ValueError("Quedaron marcas {{...}} sin reemplazar en el script T-SQL.")
    return sql


# --------------------------------------------------------------------------- #
# Paquete 1: SLA PRUEBA
# --------------------------------------------------------------------------- #
def scripts_antes_sla(destino: Destino) -> list[str]:
    """TRUNCA TABLA (y, en prueba, crear TBL_SLA_PY si no existe)."""
    scripts = []
    if destino.es_prueba:
        scripts.append(con_marcas(leer("prueba", "00_crea_tabla_sla.sql"), destino))
    scripts.append(con_marcas(leer("ajustes", "10_sla_decimal.sql"), destino))
    scripts.append(para_sla(leer("sla", "10_trunca_tabla.sql"), destino))
    return scripts


def script_despues_sla(destino: Destino) -> str:
    """UPDATE: nulos a '' y 'Voz Fija' -> 'Fija'."""
    return para_sla(leer("sla", "30_update.sql"), destino)


def insert_sla(destino: Destino, columnas: tuple[str, ...]) -> str:
    """INSERT parametrizado (equivalente al fast load del OLE DB Destination)."""
    return (
        f"INSERT INTO {destino.tbl_sla} ("
        + ", ".join(f"[{c}]" for c in columnas)
        + ") VALUES ("
        + ", ".join("?" for _ in columnas)
        + ")"
    )


# --------------------------------------------------------------------------- #
# Paquete 2: PUNTUALIDAD
# --------------------------------------------------------------------------- #
ARCHIVOS_PUNTUALIDAD = ("10_calendario.sql", "20_base.sql", "25_valida_calendario.sql", "30_calculo.sql", "40_destino.sql")


def scripts_puntualidad(destino: Destino, fuente: str | None = None) -> list[str]:
    return [con_marcas(leer("puntualidad", n), destino, fuente) for n in ARCHIVOS_PUNTUALIDAD]
