r"""Equivalencia de DATOS SSIS <-> Python (SOLO LECTURA sobre produccion).

Usa los mismos insumos que leyo la ultima corrida SSIS:
  --crudos  ...\BPO - Insumos\Chile\SEGUIMIENTO        (CSV crudos del bot: entrada de Python)
  --nuevo   ...\BPO - Insumos\Chile\SEGUIMIENTO\Nuevo  (lo que leia SSIS tras el paquete 01)

Pruebas (con los MISMOS componentes del pipeline: leer_csv, transformar,
cruce, sql.a_temporal):
  1. entradas   Para cada archivo, los valores que Python lee del crudo (con
                la regla de saltos CRLF) == los que el Flat File Source leia de
                'Nuevo', fila por fila y valor por valor. Descripciones NC:
                las filas de Python == las del script original sobre 'Nuevo'.
  2. staging    Lo que Python carga vs lo que dejo SSIS en las staging que el
                paquete NO vacia: TBL_SALESFORCE_CASOS_B (02) y
                TBL_DESCRIPCIONES_NC (06).
  3. finales    Con las #temporales de Python se ejecuta el MISMO T-SQL del
                .dtsx (sql.a_temporal, como en produccion) y se compara con lo
                que SSIS dejo en las tablas finales:
                  - TBL_CASOS / TBL_CASOS_B (DELETE + INSERT): igualdad exacta
                    en ambos sentidos para los casos del archivo (el contacto
                    viene del cruce en Python, sin 'Agrega Nombre de Contacto').
                  - TBL_SEGUIMIENTO_FECHA_BASE: mismo valor.
                  - TBL_CORREOS / TBL_HISTORIAL_CASOS / TBL_HISTORIAL_COMENTARIOS
                    (MERGE solo inserta): cada fila de Python ya esta identica
                    en la tabla y el MERGE de Python no insertaria nada nuevo.

Seguridad: todo ocurre en UNA sesion dentro de una transaccion que se
revierte al final (ROLLBACK), sobre tablas #temporales; cada sentencia se
revisa antes de enviarla y se rechaza si escribe en una tabla real (CL_*,
BBDD_*, PE_*).

Salida: evidencias/equivalencia_<fecha>.json y .md (evidencias/ esta en
.gitignore: contiene RUT y datos de clientes).

Uso:
    python tools/equivalencia.py [--crudos DIR] [--nuevo DIR]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "seguimiento"))

import mappings as m  # noqa: E402
import pandas as pd  # noqa: E402
import pyodbc  # noqa: E402
import sql  # noqa: E402
from carga.loader import SeguimientoLoader  # noqa: E402
from config import cargar_configuracion  # noqa: E402
from db import DatabaseGateway, crear_conexion, tamanos_parametros  # noqa: E402
from extraccion.extractor import FuenteLocal, leer_csv  # noqa: E402
from paquetes import PAQUETES, archivos_de  # noqa: E402
from pipeline import SeguimientoPipeline  # noqa: E402
from transformacion.descripciones_nc import leer_descripciones_nc  # noqa: E402
from transformacion import codificacion  # noqa: E402
from transformacion.codificacion import reparar_codificacion, sin_reparar_como_ssis  # noqa: E402
from transformacion.transformer import saltos_crlf  # noqa: E402

CRUDOS_DEFAULT = Path(r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO")
FINALES = "[CL_SALESFORCE_ACTUAL].[dbo]."
MAX_EJEMPLOS = 5

_ESCRITURA_REAL = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE|TRUNCATE\s+TABLE|DROP\s+TABLE(\s+IF\s+EXISTS)?|INTO|ALTER|EXEC|EXECUTE)\s+\[?(CL_|BBDD_|PE_)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Sesion de prueba (transaccion que se revierte siempre)
# --------------------------------------------------------------------------- #
class SesionPrueba:
    def __init__(self, conn: pyodbc.Connection) -> None:
        self.conn = conn  # autocommit=False: todo queda en una transaccion
        self.cursor = conn.cursor()

    def ejecutar(self, sentencia: str) -> None:
        if _ESCRITURA_REAL.search(sentencia) or "[CL_TEMPORALES]" in sentencia:
            raise RuntimeError(f"Sentencia rechazada (escribiria o leeria la staging real):\n{sentencia[:400]}")
        self.cursor.execute(sentencia)
        while self.cursor.nextset():
            pass

    def filas(self, sentencia: str) -> list[tuple]:
        if _ESCRITURA_REAL.search(sentencia):
            raise RuntimeError(f"Sentencia rechazada:\n{sentencia[:400]}")
        self.cursor.execute(sentencia)
        return [tuple(f) for f in self.cursor.fetchall()]

    def molde(self, tabla: str, tipos: tuple = ()) -> None:
        """#temporal con la estructura de la staging (solo lee su estructura)."""
        self.cursor.execute(sql.crear_temporal(tabla, tipos))
        while self.cursor.nextset():
            pass

    def insertar(self, sentencia: str, filas, tamanos) -> None:
        if not filas:
            return
        self.cursor.fast_executemany = True
        self.cursor.setinputsizes(list(tamanos))
        self.cursor.executemany(sentencia, list(filas))

    def revertir(self) -> None:
        self.conn.rollback()
        self.conn.close()


def tipo_sql(info: tuple) -> str:
    _, tipo, largo, precision, escala = info
    if tipo in ("varchar", "nvarchar", "char", "nchar"):
        return f"{tipo}({'max' if largo == -1 else largo})"
    if tipo in ("numeric", "decimal"):
        return f"{tipo}({precision},{escala})"
    return tipo


def columnas_finales(db: DatabaseGateway, base: str, tabla: str) -> list[tuple]:
    _, filas = db.run_query(
        f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
        f"FROM [{base}].INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
        (tabla,),
    )
    return filas


def _lista(cols) -> str:
    return ", ".join(f"[{c}]" for c in cols)


def comparar(ses: SesionPrueba, a: str, b: str, columnas: list[str], ambos_sentidos: bool) -> dict:
    """Multiconjunto via EXCEPT sobre 'columnas' (a = Python, b = SSIS)."""
    cols = _lista(columnas)
    n_a = ses.filas(f"SELECT COUNT(*) FROM {a}")[0][0]
    n_b = ses.filas(f"SELECT COUNT(*) FROM {b}")[0][0]
    solo_a = ses.filas(f"SELECT {cols} FROM {a} EXCEPT SELECT {cols} FROM {b}")
    r = {"filas_python": n_a, "filas_ssis": n_b, "solo_python": len(solo_a), "ejemplos_solo_python": [list(map(str, f))[:6] for f in solo_a[:MAX_EJEMPLOS]]}
    if ambos_sentidos:
        solo_b = ses.filas(f"SELECT {cols} FROM {b} EXCEPT SELECT {cols} FROM {a}")
        r["solo_ssis"] = len(solo_b)
        r["ejemplos_solo_ssis"] = [list(map(str, f))[:6] for f in solo_b[:MAX_EJEMPLOS]]
        r["equivalente"] = not solo_a and not solo_b and n_a == n_b
    else:
        r["equivalente"] = not solo_a
    return r


# --------------------------------------------------------------------------- #
# 1. Entradas: crudo (Python) vs 'Nuevo' (SSIS)
# --------------------------------------------------------------------------- #
def _flat_file_nuevo(ruta: Path) -> list[list[str]]:
    """Lo que leia el Flat File Source: 'Nuevo' (UTF-8 con BOM), sin encabezado."""
    # read_bytes + decode: read_text traduciria los CRLF a LF (newline universal)
    filas = list(csv.reader(io.StringIO(ruta.read_bytes().decode("utf-8-sig"), newline="")))
    return [f for f in filas[1:] if f]


def _nc_script_original(ruta: Path) -> list[tuple]:
    """Carga_Reporte_Descripciones_NC_Chile.py sobre 'Nuevo' + lo que enviaba to_sql."""
    df = pd.read_csv(ruta, encoding="utf-8")

    def valor(v):
        if isinstance(v, float):
            return None if math.isnan(v) else (str(int(v)) if v.is_integer() else str(v))
        if hasattr(v, "item"):
            v = v.item()
        return str(v).encode("cp1252", errors="replace").decode("cp1252")

    return [tuple(valor(v) for v in f) for f in df.itertuples(index=False, name=None)]


def prueba_entradas(crudos: Path, nuevo: Path) -> dict:
    resultado = {}
    for archivo in archivos_de(PAQUETES):
        crudo = (crudos / archivo.nombre).read_bytes()
        if archivo == m.ARCHIVO_DESCRIPCIONES_NC:
            py, ssis = leer_descripciones_nc(crudo), _nc_script_original(nuevo / archivo.nombre)
        else:
            py = [[saltos_crlf(reparar_codificacion(v)) for v in f] for f in leer_csv(crudo, archivo)]
            ssis = _flat_file_nuevo(nuevo / archivo.nombre)
        distintas = [i for i, (a, b) in enumerate(zip(py, ssis), start=2) if list(a) != list(b)]
        resultado[archivo.nombre] = {
            "filas_python": len(py),
            "filas_ssis": len(ssis),
            "filas_distintas": len(distintas) + abs(len(py) - len(ssis)),
            "ejemplo_fila_distinta": distintas[:3],
            "identico": not distintas and len(py) == len(ssis),
        }
    return resultado


def prueba_reparaciones(crudos: Path) -> dict:
    """Valores cuyas tildes mal codificadas repara Python (desviacion
    intencional de SSIS): cantidad por archivo/columna y ejemplos."""
    anterior, codificacion.REPARAR = codificacion.REPARAR, True
    try:
        resultado = {}
        for archivo in archivos_de(PAQUETES):
            for fila in leer_csv((crudos / archivo.nombre).read_bytes(), archivo):
                for i, valor in enumerate(fila):
                    reparado = reparar_codificacion(valor)
                    if reparado != valor:
                        r = resultado.setdefault(f"{archivo.nombre} [{archivo.columnas[i].nombre}]", {"valores": 0, "ejemplos": []})
                        r["valores"] += 1
                        if len(r["ejemplos"]) < 3:
                            k = next(j for j, (a, b) in enumerate(zip(valor, reparado)) if a != b)
                            r["ejemplos"].append([ascii(sin_reparar_como_ssis(valor)[max(0, k - 15): k + 12]), ascii(reparado[max(0, k - 15): k + 11])])
        return resultado
    finally:
        codificacion.REPARAR = anterior


# --------------------------------------------------------------------------- #
# 2 y 3. Staging y finales
# --------------------------------------------------------------------------- #
def select_de_insert(script: str, destino: str) -> str:
    """'SET DATEFORMAT DMY\\nINSERT INTO <destino>\\nSELECT ...' -> 'SELECT ...'."""
    i = script.index(f"INSERT INTO {destino}")
    return script[i + len(f"INSERT INTO {destino}") :].strip()


def materializar(ses: SesionPrueba, select: str, nombre: str, columnas: list[tuple]) -> None:
    """SELECT del .dtsx -> #nombre con los tipos de la tabla final (el INSERT
    real convierte implicitamente a esos tipos)."""
    alias = _lista(c[0] for c in columnas)
    casts = ", ".join(f"CAST(X.[{c[0]}] AS {tipo_sql(c)}) AS [{c[0]}]" for c in columnas)
    ses.ejecutar(f"SET DATEFORMAT DMY; SELECT {casts} INTO #{nombre} FROM ({select}) AS X({alias})")


_MERGE = re.compile(
    r"MERGE\s+(?P<destino>\[[^\]]+\]\.\[[^\]]+\]\.\[[^\]]+\])\s*AS\s+TARGET\s+USING\s+(?P<origen>.*?)\s+AS\s+SOURCE\s+"
    r"ON\s+(?P<on>.*?)\s+WHEN\s+NOT\s+MATCHED\s+THEN\s+INSERT\s*\((?P<cols>.*?)\)\s*VALUES\s*\((?P<vals>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)


def prueba_merge(ses: SesionPrueba, db: DatabaseGateway, script: str, nombre: str) -> dict:
    mm = _MERGE.search(script)
    destino, origen, on = mm["destino"], sql.a_temporal(mm["origen"]), mm["on"]
    cols = [c.strip().strip("[]") for c in mm["cols"].split(",")]
    vals = [v.strip() for v in mm["vals"].split(",")]
    pares = [(c, v) for c, v in zip(cols, vals) if v.upper() != "GETDATE()"]  # [Fecha de Carga al SQL] = GETDATE()
    tabla = destino.split(".")[-1].strip("[]")
    tipos = {c[0]: c for c in columnas_finales(db, "CL_SALESFORCE_ACTUAL", tabla)}
    seleccion = ", ".join(f"CAST(SOURCE.{v} AS {tipo_sql(tipos[c])}) AS [{c}]" for c, v in pares)
    ses.ejecutar(f"SELECT {seleccion} INTO #PY_{nombre} FROM {origen} AS SOURCE")
    nuevas = ses.filas(
        f"SELECT COUNT(*) FROM {origen} AS SOURCE WHERE NOT EXISTS (SELECT 1 FROM {destino} AS TARGET WHERE {on})"
    )[0][0]
    # El mismo MERGE pero con SOURCE ya convertido a los tipos de la tabla:
    # las filas que solo "no coinciden" porque su texto no es representable
    # en varchar (cp1252) desaparecen. Esas filas SSIS tambien las reinserta
    # en cada corrida (el ON compara nvarchar contra el varchar guardado).
    nuevas_convertidas = ses.filas(
        f"SELECT COUNT(*) FROM #PY_{nombre} AS SOURCE WHERE NOT EXISTS (SELECT 1 FROM {destino} AS TARGET WHERE {on})"
    )[0][0]
    columnas = [c for c, _ in pares]
    ses.ejecutar(
        f"SELECT {_lista(columnas)} INTO #SSIS_{nombre} FROM {destino} "
        f"WHERE [Número del caso] IN (SELECT [Número del caso] FROM #PY_{nombre})"
    )
    r = comparar(ses, f"#PY_{nombre}", f"#SSIS_{nombre}", columnas, ambos_sentidos=False)
    r["merge_insertaria_python"] = nuevas
    r["merge_insertaria_con_tipos_destino"] = nuevas_convertidas
    r["reinserciones_como_ssis"] = nuevas - nuevas_convertidas
    # Criterio: el MERGE de Python no inserta nada que SSIS no haya insertado
    # con el mismo archivo. Las filas 'solo Python' que si coinciden por la
    # clave del MERGE son cambios en columnas FUERA de la clave (p.ej. un
    # usuario de Salesforce renombrado): el MERGE solo inserta, asi que SSIS
    # tampoco las actualiza.
    r["cambios_fuera_de_clave"] = r["solo_python"] if nuevas_convertidas == 0 else None
    r["equivalente"] = nuevas_convertidas == 0
    return r


def prueba_datos(fuente: FuenteLocal, db: DatabaseGateway, ses: SesionPrueba) -> dict:
    res: dict = {}
    loader = SeguimientoLoader(db)  # solo para leer esquemas (otra conexion, lectura)
    pipeline = SeguimientoPipeline(loader, fuente, PAQUETES)

    # --- las #temporales, cargadas como en produccion -------------------------
    for flujo in m.TODOS_LOS_FLUJOS:
        filas = pipeline.preparar(flujo, fuente)
        ses.molde(flujo.tabla, flujo.tipos_temporal)
        ses.insertar(
            sql.insert_temporal(flujo), filas, tamanos_parametros(flujo.columnas_insert, loader.esquema(flujo.tabla))
        )
    filas_nc = leer_descripciones_nc(fuente.leer(m.ARCHIVO_DESCRIPCIONES_NC))
    ses.molde(m.TABLA_DESCRIPCIONES_NC)
    ses.insertar(
        sql.insert_tabla(m.TABLA_DESCRIPCIONES_NC, m.COLUMNAS_DESCRIPCIONES_NC).replace(
            sql.nombre_staging(m.TABLA_DESCRIPCIONES_NC), f"#{m.TABLA_DESCRIPCIONES_NC}"
        ),
        filas_nc,
        tamanos_parametros(m.COLUMNAS_DESCRIPCIONES_NC, loader.esquema(m.TABLA_DESCRIPCIONES_NC)),
    )

    # --- 2. staging que SSIS no vacia -------------------------------------
    for tabla, columnas in (
        ("TBL_SALESFORCE_CASOS_B", list(loader.esquema("TBL_SALESFORCE_CASOS_B"))),
        (m.TABLA_DESCRIPCIONES_NC, list(m.COLUMNAS_DESCRIPCIONES_NC)),
    ):
        ses.cursor.execute(f"SELECT * INTO #SSIS_{tabla} FROM {sql.nombre_staging(tabla)}")
        res[f"staging {tabla}"] = comparar(ses, f"#{tabla}", f"#SSIS_{tabla}", columnas, ambos_sentidos=True)

    # --- 3a. FECHA BASE -------------------------------------------------------
    fecha_base = sql.a_temporal(sql.leer("p02", "20_fecha_base.sql"))
    select_fb = fecha_base[fecha_base.index("SELECT FORMAT") :].replace(
        "INTO [CL_SEGUIMIENTO_ACTUAL].DBO.TBL_SEGUIMIENTO_FECHA_BASE", ""
    )
    ses.ejecutar("SET DATEFORMAT DMY")
    py_fb = ses.filas(select_fb)[0][0]
    ssis_fb = ses.filas("SELECT [Fecha Base] FROM [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO_FECHA_BASE]")[0][0]
    res["final TBL_SEGUIMIENTO_FECHA_BASE"] = {"python": py_fb, "ssis": ssis_fb, "equivalente": py_fb == ssis_fb}

    # --- 3b. TBL_CASOS: SELECT de CARGA CASOS CHILE (contacto ya cruzado en Python)
    cols_casos = columnas_finales(db, "CL_SALESFORCE_ACTUAL", "TBL_CASOS")
    materializar(
        ses, sql.a_temporal(select_de_insert(sql.leer("p02", "50_carga_casos_chile.sql"), FINALES + "[TBL_CASOS]")), "PY_CASOS", cols_casos
    )
    ses.ejecutar(
        "SELECT * INTO #SSIS_CASOS FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS] WHERE [Número del caso] IN "
        "(SELECT [Número del caso] FROM #PY_CASOS UNION SELECT [Número del caso] FROM #TBL_SALESFORCE_CASOS)"
    )
    res["final TBL_CASOS"] = comparar(ses, "#PY_CASOS", "#SSIS_CASOS", [c[0] for c in cols_casos], ambos_sentidos=True)

    # --- 3c. TBL_CASOS_B: SELECT de CARGA CASOS B CHILE (cruza con TBL_CASOS real)
    cols_b = columnas_finales(db, "CL_SALESFORCE_ACTUAL", "TBL_CASOS_B")
    materializar(
        ses, sql.a_temporal(select_de_insert(sql.leer("p02", "80_carga_casos_b_chile.sql"), FINALES + "[TBL_CASOS_B]")), "PY_CASOS_B", cols_b
    )
    ses.ejecutar(
        "SELECT * INTO #SSIS_CASOS_B FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CASOS_B] WHERE [Número del caso] IN "
        "(SELECT [Número del caso] FROM #PY_CASOS_B UNION SELECT [Número del caso] FROM #TBL_SALESFORCE_CASOS_B)"
    )
    res["final TBL_CASOS_B"] = comparar(ses, "#PY_CASOS_B", "#SSIS_CASOS_B", [c[0] for c in cols_b], ambos_sentidos=True)

    # --- 3d. MERGE (03, 04, 06), tras el UPDATE 'LIMPIA ...' de cada paquete
    for paquete, limpia, merge, nombre in (
        ("p03", "20_limpia_temporal_correos.sql", "30_carga_correos.sql", "CORREOS"),
        ("p04", "20_limpia_temporal_historial.sql", "30_carga_historial_chile.sql", "HISTORIAL_CASOS"),
        ("p06", "20_limpia_temporal_comentarios.sql", "30_carga_comentarios_chile.sql", "HISTORIAL_COMENTARIOS"),
    ):
        ses.ejecutar(sql.a_temporal(sql.leer(paquete, limpia)))
        res[f"final TBL_{nombre}"] = prueba_merge(ses, db, sql.leer(paquete, merge), nombre)
    return res


def _reporte(resumen: dict) -> str:
    lineas = [
        "# Equivalencia SSIS vs Python - CL_Seguimiento 02/03/04/06",
        "",
        f"- Fecha de la prueba: {resumen['fecha']}",
        f"- Crudos (entrada Python, tal cual): `{resumen['crudos']}`",
        f"- Nuevo (entrada SSIS): `{resumen['nuevo']}`",
        f"- Ultima corrida SSIS (LOGS_PROCESOS): {resumen['ultima_corrida_ssis']}",
        "",
        f"## Resultado global: **{'EQUIVALENTE' if resumen['equivalente'] else 'CON DIFERENCIAS'}**",
        "",
        "## 1. Entradas: crudo leido por Python vs 'Nuevo' leido por SSIS (valor a valor)",
        "",
        "| Archivo | Filas Python | Filas SSIS | Filas distintas | Identico |",
        "|---|---:|---:|---:|:---:|",
    ]
    for archivo, r in resumen["entradas"].items():
        lineas.append(
            f"| {archivo} | {r['filas_python']} | {r['filas_ssis']} | {r['filas_distintas']} | {'SI' if r['identico'] else 'NO'} |"
        )
    lineas += [
        "",
        "## Reparaciones de tildes mal codificadas (desviacion intencional; no entran en la comparacion estricta)",
        "",
        "| Archivo [columna] | Valores reparados | Ejemplo (SSIS -> Python) |",
        "|---|---:|---|",
    ]
    for nombre, r in resumen["reparaciones"].items():
        antes, despues = r["ejemplos"][0]
        lineas.append(f"| {nombre} | {r['valores']} | `{antes}` -> `{despues}` |")
    lineas += [
        "",
        "## 2-3. Staging y tablas finales (comparacion estricta: Python SIN reparar tildes)",
        "",
        "| Prueba | Filas Python | Filas SSIS | Solo Python | Solo SSIS | MERGE insertaria (nuevas / reinserciones como SSIS) | Equivalente |",
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    for nombre, r in resumen["datos"].items():
        if "python" in r:
            lineas.append(f"| {nombre} | `{r['python']}` | `{r['ssis']}` | | | | {'SI' if r['equivalente'] else 'NO'} |")
            continue
        merge = (
            f"{r['merge_insertaria_con_tipos_destino']} / {r['reinserciones_como_ssis']}" if "reinserciones_como_ssis" in r else ""
        )
        lineas.append(
            f"| {nombre} | {r['filas_python']} | {r['filas_ssis']} | {r['solo_python']} | {r.get('solo_ssis', 'n/a')} | "
            f"{merge} | {'SI' if r['equivalente'] else 'NO'} |"
        )
    lineas += [
        "",
        "Notas:",
        "- Las tablas con MERGE acumulan historia: 'Filas SSIS' son las filas de la tabla final para los casos del "
        "archivo; la prueba exige que el MERGE de Python no inserte nada nuevo (SSIS ya cargo ese mismo archivo). "
        "En esas tablas 'Solo Python' son filas que coinciden por la clave del MERGE pero difieren en otra columna "
        "(dato cambiado en Salesforce, p.ej. un usuario renombrado): el MERGE solo inserta, SSIS tampoco las actualiza.",
        "- 'Reinserciones como SSIS': filas que el MERGE de SSIS reinsertaria por compararse nvarchar contra el "
        "varchar guardado. Python ya no las reinserta (correccion de Comentarios, EQUIVALENCIA.md seccion 7): la "
        "columna 'nuevas' es lo que insertaria Python.",
        "- La comparacion estricta se hace con la reparacion de tildes APAGADA, para demostrar que todo lo demas es "
        "identico; lo que la reparacion cambia se lista aparte.",
        "- Todo se ejecuto en tablas #temporales dentro de una transaccion revertida: no se escribio en produccion.",
    ]
    return "\n".join(lineas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crudos", type=Path, default=CRUDOS_DEFAULT)
    parser.add_argument("--nuevo", type=Path)
    args = parser.parse_args()
    nuevo = args.nuevo or args.crudos / "Nuevo"

    settings = cargar_configuracion(RAIZ)
    db = DatabaseGateway(lambda: crear_conexion(settings.db), settings.batch_size, settings.db.server)
    ses = SesionPrueba(crear_conexion(settings.db))
    try:
        _, log = db.run_query(
            "SELECT TOP 1 [Fecha Inicio], [Fecha Fin], Estado FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] "
            "WHERE Nombre = 'Update_Carga_Casos_Chile' ORDER BY [Fecha Inicio] DESC"
        )
        resumen = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "crudos": str(args.crudos),
            "nuevo": str(nuevo),
            "ultima_corrida_ssis": " / ".join(map(str, log[0])) if log else None,
            "reparaciones": prueba_reparaciones(args.crudos),
        }
        codificacion.REPARAR = False  # comparacion estricta con SSIS (entradas y datos)
        resumen["entradas"] = prueba_entradas(args.crudos, nuevo)
        resumen["datos"] = prueba_datos(FuenteLocal(args.crudos), db, ses)
    finally:
        ses.revertir()
        db.cerrar()
    resumen["equivalente"] = all(r["identico"] for r in resumen["entradas"].values()) and all(
        r["equivalente"] for r in resumen["datos"].values()
    )
    salida = RAIZ / "evidencias"
    salida.mkdir(exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    (salida / f"equivalencia_{sello}.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (salida / f"equivalencia_{sello}.md").write_text(_reporte(resumen), encoding="utf-8")
    print(_reporte(resumen))
    return 0 if resumen["equivalente"] else 1


if __name__ == "__main__":
    sys.exit(main())
