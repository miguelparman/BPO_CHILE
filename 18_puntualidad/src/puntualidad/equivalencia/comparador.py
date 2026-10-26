"""Equivalencia SSIS <-> Python, medida contra el servidor.

PUNTUALIDAD (ejecutar_equivalencia):
  1. Congela los casos: copia de la vista a TBL_PUNTUALIDAD_EQ_SNAP. Es necesario porque
     'En proceso' toma la hora actual como cierre y cambia entre ejecuciones.
  2. REFERENCIA: el T-SQL ORIGINAL del .dtsx (docs/referencia_sql/p2_PUNTUALIDAD.sql, con
     las funciones fila por fila) sobre esa copia -> TBL_PUNTUALIDAD_EQ_REF.
  3. OPTIMIZADO: scripts_sql/puntualidad/ sobre la misma copia -> TBL_PUNTUALIDAD_EQ_OPT.
  4. Compara: filas, esquema (columna, tipo, ancho, nulabilidad, orden) y contenido
     (EXCEPT en ambos sentidos, con multiplicidad), mas las diferencias por columna.
  5. Deja el informe en evidencias/ (.md y .json) y borra las tablas _EQ_*.

comparar_sla: TBL_SLA de prueba (cargada por Python desde el Excel) contra TBL_SLA
real (la que dejo SSIS), mismo contenido y mismas filas.

Solo escribe en tablas *_EQ_* y *_PY: nunca toca TBL_SLA ni TBL_PUNTUALIDAD de produccion.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import sql
from db import DatabaseGateway
from exceptions import CargaError
from logging_setup import NOMBRE_LOGGER
from mappings import BD_PUNTUALIDAD, ESQUEMA, FUENTE_PUNTUALIDAD, TBL_SLA_REAL, Destino

logger = logging.getLogger(NOMBRE_LOGGER)

_ORIGINAL_TABLA = "[CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]"
_ORIGINAL_FUENTE = "CL_VISTAS.dbo.VIEW_FACT_SEGUIMIENTO_VOL_GENERAL x0"


def _tabla_eq(sufijo: str) -> str:
    return f"[{BD_PUNTUALIDAD}].[{ESQUEMA}].[TBL_PUNTUALIDAD_EQ_{sufijo}]"


SNAP, REF, OPT = _tabla_eq("SNAP"), _tabla_eq("REF"), _tabla_eq("OPT")


@dataclass
class Comparacion:
    nombre: str
    tabla_referencia: str
    tabla_python: str
    filas_referencia: int = 0
    filas_python: int = 0
    mismo_esquema: bool = False
    diferencias_esquema: list = field(default_factory=list)
    solo_referencia: int = 0
    solo_python: int = 0
    por_columna: dict = field(default_factory=dict)
    muestra_referencia: list = field(default_factory=list)  # filas que solo estan en la referencia
    muestra_python: list = field(default_factory=list)  # filas que solo estan en Python
    explicadas_por_empates: int | None = None  # filas distintas que caen en un grupo SLA con empate
    notas: list = field(default_factory=list)  # diferencias deliberadas, etc.

    @property
    def diferencias(self) -> int:
        return max(self.solo_referencia, self.solo_python)

    @property
    def equivalente_salvo_empates(self) -> bool:
        """Mismo esquema y filas, y TODAS las filas distintas caen en un grupo SLA con empate."""
        return (
            self.filas_referencia == self.filas_python
            and self.mismo_esquema
            and self.explicadas_por_empates is not None
            and self.explicadas_por_empates >= self.diferencias
        )

    @property
    def equivalente(self) -> bool:
        return (
            self.filas_referencia == self.filas_python
            and self.mismo_esquema
            and self.solo_referencia == 0
            and self.solo_python == 0
            and not any(self.por_columna.values())
        )


@dataclass
class ResultadoEquivalencia:
    generado: str
    comparaciones: list[Comparacion] = field(default_factory=list)
    segundos: dict = field(default_factory=dict)  # etapa -> segundos
    notas: list = field(default_factory=list)

    @property
    def equivalente(self) -> bool:
        return bool(self.comparaciones) and all(c.equivalente for c in self.comparaciones)

    @property
    def equivalente_salvo_empates(self) -> bool:
        return bool(self.comparaciones) and all(c.equivalente or c.equivalente_salvo_empates for c in self.comparaciones)


# --------------------------------------------------------------------------- #
# Utilidades de comparacion
# --------------------------------------------------------------------------- #
def _escalar(db: DatabaseGateway, consulta: str, params=None) -> int:
    _, filas = db.run_query(consulta, params)
    return int(filas[0][0])


def _columnas(db: DatabaseGateway, tabla: str) -> list[tuple]:
    """(nombre, tipo, ancho, precision, escala, nulable, collation) en orden de columna.
    'tabla' es un nombre de 3 partes: la base sale de el."""
    base = tabla.split("].[")[0].strip("[")
    _, filas = db.run_query(
        "SELECT c.name, t.name, c.max_length, c.precision, c.scale, c.is_nullable, ISNULL(c.collation_name, '') "
        f"FROM [{base}].sys.columns c JOIN [{base}].sys.types t ON t.user_type_id = c.user_type_id "
        "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
        (tabla,),
    )
    return [tuple(f) for f in filas]


def comparar_tablas(db: DatabaseGateway, nombre: str, referencia: str, python: str, claves: tuple[str, ...] = ()) -> Comparacion:
    """Compara dos tablas con la misma estructura. 'claves': columnas para listar las
    diferencias por columna (las que se agregan aqui se comparan junto a las claves)."""
    c = Comparacion(nombre, referencia, python)
    cols_ref, cols_py = _columnas(db, referencia), _columnas(db, python)
    c.mismo_esquema = cols_ref == cols_py
    if not c.mismo_esquema:
        c.diferencias_esquema = [
            f"REF {a} | PY {b}" for a, b in zip(cols_ref, cols_py) if a != b
        ] + ([f"columnas: REF {len(cols_ref)}, PY {len(cols_py)}"] if len(cols_ref) != len(cols_py) else [])
    c.filas_referencia = _escalar(db, f"SELECT COUNT(*) FROM {referencia}")
    c.filas_python = _escalar(db, f"SELECT COUNT(*) FROM {python}")
    nombres = [col[0] for col in cols_ref if col[0] in {x[0] for x in cols_py}]
    lista = ", ".join(f"[{n}]" for n in nombres)

    def agrupado(tabla: str) -> str:
        return f"SELECT {lista}, COUNT_BIG(*) n FROM {tabla} GROUP BY {lista}"

    c.solo_referencia = _escalar(db, f"SELECT COUNT(*) FROM ({agrupado(referencia)} EXCEPT {agrupado(python)}) z")
    c.solo_python = _escalar(db, f"SELECT COUNT(*) FROM ({agrupado(python)} EXCEPT {agrupado(referencia)}) z")
    for n in nombres:
        if n in claves:
            continue
        sel = ", ".join(f"[{k}]" for k in (*claves, n))
        c.por_columna[n] = _escalar(db, f"SELECT COUNT(*) FROM (SELECT {sel} FROM {referencia} EXCEPT SELECT {sel} FROM {python}) z")
    if c.solo_referencia or c.solo_python:
        c.muestra_referencia = _muestra(db, referencia, python)
        c.muestra_python = _muestra(db, python, referencia)
        if "SLA (ARBOL)" in nombres:
            c.explicadas_por_empates = _explicadas_por_empates(db, referencia, python)
    return c


_COLUMNAS_MUESTRA = (
    "[Número del caso]", "[Linea de negocio general]", "[Motivo de contacto]", "[Tipología]", "[Subtipología]",
    "[ESTADO (ARBOL)]", "[SLA (ARBOL)]", "[Día/Hora (ARBOL)]", "[Calendario/Laboral (ARBOL)]", "[SLA HORA]",
)


def _muestra(db: DatabaseGateway, a: str, b: str, n: int = 10) -> list:
    """Hasta 'n' filas que estan en 'a' y no en 'b' (columnas que identifican la rama SLA)."""
    _, filas = db.run_query(
        f"SELECT TOP ({n}) {', '.join(_COLUMNAS_MUESTRA)} FROM (SELECT * FROM {a} EXCEPT SELECT * FROM {b}) d ORDER BY 1"
    )
    return [tuple(str(v) for v in f) for f in filas]


_MISMO_SLA = "CONCAT(s.SLA, '|', s.[Día/Hora], '|', s.[Calendario/Laboral], '|', s.Estado)"
# Grupos de TBL_SLA con empate: mismas columnas de la particion de la vista (VIEW_SLA_4TIP / 3TIP / 1TIP)
# pero valores de SLA distintos. Esas vistas numeran con ROW_NUMBER() ordenando por las mismas columnas
# de la particion, asi que cual fila queda como 1 no esta definido: depende del plan de ejecucion.
_EMPATE_4TIP = (
    "EXISTS (SELECT 1 FROM [CL_ANALISIS].[dbo].[TBL_SLA] s WHERE s.[Línea de Negocio] <> '' "
    "AND s.[Línea de Negocio] = d.[Linea de negocio general] AND s.[Motivo de contacto] = d.[Motivo de contacto] "
    "AND s.[Tipología] = d.[Tipología] AND s.[Subtipología] = d.[Subtipología] "
    f"GROUP BY s.[Línea de Negocio], s.[Motivo de contacto], s.[Tipología], s.[Subtipología] HAVING COUNT(DISTINCT {_MISMO_SLA}) > 1)"
)
_EMPATE_3TIP = (
    "EXISTS (SELECT 1 FROM [CL_ANALISIS].[dbo].[TBL_SLA] s WHERE s.[Línea de Negocio] = '' "
    "AND s.[Motivo de contacto] = d.[Motivo de contacto] AND s.[Tipología] = d.[Tipología] AND s.[Subtipología] = d.[Subtipología] "
    f"GROUP BY s.[Motivo de contacto], s.[Tipología], s.[Subtipología] HAVING COUNT(DISTINCT {_MISMO_SLA}) > 1)"
)
_EMPATE_1TIP = (
    "EXISTS (SELECT 1 FROM [CL_ANALISIS].[dbo].[TBL_SLA] s WHERE s.[Tipología] = '' AND s.[Subtipología] = '' "
    "AND s.[Motivo de contacto] = d.[Motivo de contacto] "
    f"GROUP BY s.[Línea de Negocio], s.[Motivo de contacto] HAVING COUNT(DISTINCT {_MISMO_SLA}) > 1)"
)


def _explicadas_por_empates(db: DatabaseGateway, referencia: str, python: str) -> int:
    """Filas distintas (las que estan en la referencia y no en Python, y al reves; se toma el mayor de los
    dos conteos) cuya combinacion Motivo/Tipologia/Subtipologia esta en un grupo SLA con empate."""
    condicion = f"({_EMPATE_4TIP} OR {_EMPATE_3TIP} OR {_EMPATE_1TIP})"
    conteos = [
        _escalar(db, f"SELECT COUNT(*) FROM (SELECT * FROM {a} EXCEPT SELECT * FROM {b}) d WHERE {condicion}")
        for a, b in ((referencia, python), (python, referencia))
    ]
    return max(conteos)


# --------------------------------------------------------------------------- #
# SLA: TBL_SLA de prueba vs la real
# --------------------------------------------------------------------------- #
def _normalizada(columnas: list[tuple]) -> list[tuple]:
    """El tipo de SLA es la diferencia deliberada (decimal(10,2) en Python, int en SSIS): se compara solo la nulabilidad."""
    return [(c[0], "numerico", c[5]) if c[0] == "SLA" else c for c in columnas]


def comparar_sla(db: DatabaseGateway, destino: Destino) -> Comparacion:
    """TBL_SLA de prueba (Python) contra TBL_SLA (SSIS): mismas filas y contenido, incluido 'Llave' (NULL),
    salvo la decision de conservar el decimal: SLA es decimal(10,2) en Python (13,5) y era int en SSIS (14).
    Para el contenido, el SLA de Python se redondea half-up (lo que hacia SSIS) y se informa aparte cuantas filas
    conservan decimales."""
    ref, py = TBL_SLA_REAL, destino.tbl_sla
    logger.info("Comparando %s (Python) contra %s (SSIS)...", py, ref)
    c = Comparacion("TBL_SLA: Python vs SSIS (SLA decimal a proposito)", ref, py)
    cr, cp = _columnas(db, ref), _columnas(db, py)
    c.mismo_esquema = _normalizada(cr) == _normalizada(cp)
    if not c.mismo_esquema:
        c.diferencias_esquema = [f"REF {a} | PY {b}" for a, b in zip(cr, cp) if _normalizada([a]) != _normalizada([b])]
    tipo = {x[0]: x[1] for x in cr}["SLA"], {x[0]: x[1] for x in cp}["SLA"]
    c.notas.append(f"Tipo de la columna SLA: SSIS {tipo[0]}, Python {tipo[1]} (decision del usuario: conservar el valor real).")
    c.filas_referencia = _escalar(db, f"SELECT COUNT(*) FROM {ref}")
    c.filas_python = _escalar(db, f"SELECT COUNT(*) FROM {py}")
    nombres = [x[0] for x in cr]
    lista = ", ".join(f"[{n}]" for n in nombres)

    def agrupado(tabla: str, expresion_sla: str) -> str:
        proyeccion = ", ".join(expresion_sla if n == "SLA" else f"[{n}]" for n in nombres)
        return f"SELECT {lista}, COUNT_BIG(*) n FROM (SELECT {proyeccion} FROM {tabla}) t GROUP BY {lista}"

    a_ref = agrupado(ref, "CAST([SLA] AS DECIMAL(10,2)) [SLA]")
    a_py = agrupado(py, "CAST(FLOOR([SLA] + 0.5) AS DECIMAL(10,2)) [SLA]")
    c.solo_referencia = _escalar(db, f"SELECT COUNT(*) FROM ({a_ref} EXCEPT {a_py}) z")
    c.solo_python = _escalar(db, f"SELECT COUNT(*) FROM ({a_py} EXCEPT {a_ref}) z")
    decimales = _escalar(db, f"SELECT COUNT(*) FROM {py} WHERE [SLA] <> FLOOR([SLA])")
    c.notas.append(f"Filas de Python con SLA decimal (en SSIS quedaron redondeadas): {decimales}.")
    return c


# --------------------------------------------------------------------------- #
# PUNTUALIDAD: original (funciones fila por fila) vs optimizado
# --------------------------------------------------------------------------- #
def _sql_original(ruta_original: Path, tbl_sla: str) -> str:
    """El T-SQL del .dtsx apuntado a la copia congelada y a la tabla _EQ_REF. Las vistas VIEW_SLA_* leen la TBL_SLA
    real (int), asi que se reemplazan por su misma definicion en linea (con el desempate fijado, ver
    docs/EQUIVALENCIA.md) sobre la tabla SLA decimal de la prueba; asi el original y Python leen el mismo SLA."""
    with open(ruta_original, encoding="utf-8", newline="") as f:
        texto = f.read()
    if _ORIGINAL_TABLA not in texto or _ORIGINAL_FUENTE not in texto:
        raise ValueError("El T-SQL de referencia no tiene la forma esperada; no se puede redirigir.")
    for nombre, alias in (("4TIP", "x1"), ("3TIP", "x2"), ("1TIP", "x3")):
        vista = f"[CL_ANALISIS].[dbo].[VIEW_SLA_{nombre}] {alias}"
        if vista not in texto:
            raise ValueError(f"El T-SQL de referencia no usa {vista}.")
        texto = texto.replace(vista, sql.VISTAS_SLA[nombre].replace("{{TBL_SLA}}", tbl_sla) + f" {alias}")
    return texto.replace(_ORIGINAL_TABLA, REF).replace(_ORIGINAL_FUENTE, f"{SNAP} x0")


def ejecutar_equivalencia(
    db: DatabaseGateway,
    ruta_original: Path,
    evidencias_dir: Path,
    destino_sla: Destino,
    con_referencia: bool = True,
    conservar: bool = False,
) -> ResultadoEquivalencia:
    resultado = ResultadoEquivalencia(generado=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    claves = ("Número del caso", "Fecha/Hora de apertura", "Fecha de cierre general", "SLA HORA")
    destino_opt = Destino("prueba", destino_sla.tbl_sla, OPT, SNAP)  # lee la tabla SLA decimal de la prueba

    def etapa(nombre: str, accion) -> None:
        inicio = time.monotonic()
        logger.info("[equivalencia] %s...", nombre)
        accion()
        resultado.segundos[nombre] = round(time.monotonic() - inicio, 1)
        logger.info("[equivalencia] %s: %.1f s", nombre, resultado.segundos[nombre])

    def borrar() -> None:
        for t in (SNAP, REF, OPT):
            db.execute_autocommit(f"DROP TABLE IF EXISTS {t}")

    try:
        borrar()
        if not _escalar(db, "SELECT CASE WHEN OBJECT_ID(?, 'U') IS NULL THEN 0 ELSE 1 END", (destino_sla.tbl_sla,)):
            raise CargaError(f"{destino_sla.tbl_sla} no existe: correr primero 'python main.py' (modo prueba).")
        etapa("TBL_SLA de prueba vs la real", lambda: resultado.comparaciones.append(comparar_sla(db, destino_sla)))
        etapa(
            "Copia congelada de los casos",
            lambda: db.execute_autocommit(
                f"SELECT * INTO {SNAP} FROM {FUENTE_PUNTUALIDAD} WHERE CAST([Fecha/Hora de apertura] AS date) >= '2025-08-01'"
            ),
        )
        resultado.notas.append(f"Casos congelados: {db.run_query(f'SELECT COUNT(*) FROM {SNAP}')[1][0][0]}")
        resultado.notas.append(f"Tabla SLA usada por ambos lados: {destino_sla.tbl_sla} (SLA decimal(10,2)).")
        etapa("Python: aritmetica de calendario", lambda: _ejecutar_optimizado(db, destino_opt))
        if con_referencia:
            etapa("SSIS: funciones fila por fila (T-SQL original)", lambda: db.execute_autocommit(_sql_original(ruta_original, destino_sla.tbl_sla)))
            etapa(
                "Comparacion",
                lambda: resultado.comparaciones.append(
                    comparar_tablas(db, "TBL_PUNTUALIDAD: Python vs T-SQL original", REF, OPT, claves)
                ),
            )
        else:
            resultado.notas.append("Se omitio la referencia (--sin-referencia): no hay comparacion.")
    finally:
        if not conservar:
            borrar()
    _escribir(resultado, evidencias_dir)
    return resultado


def _ejecutar_optimizado(db: DatabaseGateway, destino: Destino) -> None:
    db.nueva_sesion()
    try:
        db.execute_transaccion(sql.scripts_puntualidad(destino))
    finally:
        db.nueva_sesion()


# --------------------------------------------------------------------------- #
# Informe
# --------------------------------------------------------------------------- #
def veredicto(r: ResultadoEquivalencia) -> str:
    if r.equivalente:
        return "EQUIVALENTE"
    if r.equivalente_salvo_empates:
        return "EQUIVALENTE SALVO EMPATES NO DETERMINISTAS DEL ORIGINAL"
    return "NO EQUIVALENTE / SIN COMPARACION"


def _escribir(r: ResultadoEquivalencia, evidencias_dir: Path) -> Path:
    evidencias_dir.mkdir(parents=True, exist_ok=True)
    base = evidencias_dir / f"equivalencia_{datetime.now():%Y%m%d_%H%M%S}"
    base.with_suffix(".json").write_text(
        json.dumps({**asdict(r), "equivalente": r.equivalente, "equivalente_salvo_empates": r.equivalente_salvo_empates}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lineas = [
        "# Equivalencia SSIS_CL_Puntualidad.dtsx <-> Python",
        "",
        f"Generado: {r.generado} | Resultado: **{veredicto(r)}**",
        "",
    ]
    for n in r.notas:
        lineas.append(f"- {n}")
    lineas += ["", "## Tiempos", "", "| Etapa | Segundos |", "|---|---|"]
    lineas += [f"| {k} | {v} |" for k, v in r.segundos.items()]
    for c in r.comparaciones:
        lineas += [
            "",
            f"## {c.nombre}",
            "",
            f"- Referencia: `{c.tabla_referencia}` ({c.filas_referencia} filas)",
            f"- Python: `{c.tabla_python}` ({c.filas_python} filas)",
            f"- Mismo esquema (columnas, tipos, anchos, nulabilidad, orden): {'si' if c.mismo_esquema else 'NO'}",
            f"- Filas distintas (solo en la referencia / solo en Python): {c.solo_referencia} / {c.solo_python}",
        ]
        lineas += [f"  - {d}" for d in c.diferencias_esquema]
        lineas += [f"- {n}" for n in c.notas]
        if c.explicadas_por_empates is not None:
            lineas.append(
                "- Filas distintas que caen en un grupo SLA con empate (ROW_NUMBER sin desempate): "
                f"{c.explicadas_por_empates} de {c.diferencias} -> "
                + ("equivalente salvo empates" if c.equivalente_salvo_empates else "HAY diferencias sin explicar")
            )
        for titulo, muestra in (("Solo en la referencia", c.muestra_referencia), ("Solo en Python", c.muestra_python)):
            if muestra:
                lineas += ["", f"{titulo} (muestra; columnas: {', '.join(_COLUMNAS_MUESTRA)}):", ""]
                lineas += [f"- {' | '.join(f)}" for f in muestra]
        if c.por_columna:
            lineas += ["", "| Columna | Filas con valor distinto |", "|---|---|"]
            lineas += [f"| {k} | {v} |" for k, v in c.por_columna.items()]
    base.with_suffix(".md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    logger.info("Informe de equivalencia: %s", base.with_suffix(".md"))
    return base.with_suffix(".md")
