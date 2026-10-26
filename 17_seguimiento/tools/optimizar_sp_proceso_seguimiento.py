r"""Optimizacion de [CL_SEGUIMIENTO_ACTUAL].[dbo].[SP_PROCESO_SEGUIMIENTO]
(paquete 07) con EL MISMO RESULTADO (2026-10-26, pedido del usuario).

Diagnostico (sys.dm_exec_query_stats, corrida del 26/10 10:55; SP = 220 s):
  1. SELECT ... INTO TBL_SEGUIMIENTO_TOTAL_1_NUEVO: 154 s en UN hilo. La
     funcion escalar [BBDD_GENERAL].[dbo].[FECHAS_VALIDAS] tiene un WHILE (no
     se puede 'inlinear'), se ejecuta fila por fila 2 veces por caso (~836 mil
     llamadas) y fuerza un plan serial. Su resultado depende solo de la fecha
     (~1.228 fechas distintas).
  2. SELECT ... INTO TBL_SEGUIMIENTO: 55 s. Dos EXISTS correlacionados sobre
     TBL_HISTORIAL_CASOS (8,9 M filas) por cada caso.

Cambios (los unicos; el resto del SP queda igual):
  A. #FECHAS_QUIEBRE: FECHAS_VALIDAS se calcula una vez por fecha distinta,
     con la MISMA funcion, y la sentencia 1 la toma con un LEFT JOIN.
  B. #HIST_VALOR_NUEVO: los casos con [Valor nuevo] 'CHI - Especialista SSPP
     PYME' / 'CHI-Isla de Retencion' se leen una vez; los dos EXISTS consultan
     esa tabla (las condiciones del EXISTS no cambian).

Modos:
  python tools/optimizar_sp_proceso_seguimiento.py probar    # solo lectura: viejo vs nuevo en #temporales, compara y mide
  python tools/optimizar_sp_proceso_seguimiento.py aplicar   # ALTER PROCEDURE (exige que 'probar' haya dado identico hoy)
  python tools/optimizar_sp_proceso_seguimiento.py revertir  # vuelve a la definicion respaldada antes del cambio
  python tools/optimizar_sp_proceso_seguimiento.py indice    # indice agrupado en TBL_HISTORIAL_COMENTARIOS (punto 4)
  python tools/optimizar_sp_proceso_seguimiento.py quitar-indice
  python tools/optimizar_sp_proceso_seguimiento.py mantener-indice  # mensual: REORGANIZE/REBUILD solo si la fragmentacion lo pide

Respaldo de la definicion anterior: docs/referencia_sp/SP_PROCESO_SEGUIMIENTO_antes_20261026.sql
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "seguimiento"))

from config import cargar_configuracion  # noqa: E402
from db import crear_conexion  # noqa: E402

SP = "[CL_SEGUIMIENTO_ACTUAL].[dbo].[SP_PROCESO_SEGUIMIENTO]"
RESPALDO = RAIZ / "docs" / "referencia_sp" / "SP_PROCESO_SEGUIMIENTO_antes_20261026.sql"
NUEVA = RAIZ / "docs" / "referencia_sp" / "SP_PROCESO_SEGUIMIENTO.sql"
EVIDENCIA = RAIZ / "evidencias" / "optimizacion_sp_proceso_seguimiento.json"
NL = "\r\n"

MARCA_A = "-- OPTIMIZACION 2026-10-26 (17_seguimiento) A:"
MARCA_B = "-- OPTIMIZACION 2026-10-26 (17_seguimiento) B:"
LLAMADA = "[BBDD_GENERAL].[dbo].[FECHAS_VALIDAS](CAST(X4.[Fecha de creación de Comentario del caso] AS DATE))"
INICIO_1 = "SELECT " + NL + "X0.[Número del caso]" + NL + ",X0.[Número de caso principal]"
JOIN_X4 = "LEFT JOIN [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO_FRACTALIA] X4" + NL + "ON  X0.[Número del caso]  = X4.[Número del caso]"
INICIO_3 = "SELECT X0.*" + NL
HISTORIAL = "FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_CASOS] X1"

BLOQUE_A = NL.join(
    [
        MARCA_A + " FECHAS_VALIDAS se calcula UNA vez por fecha distinta",
        "-- (antes 2 veces por caso, fila por fila y en un solo hilo). Misma funcion => mismo resultado.",
        "DROP TABLE IF EXISTS #FECHAS_QUIEBRE;",
        "SELECT F.[Fecha], [BBDD_GENERAL].[dbo].[FECHAS_VALIDAS](F.[Fecha]) AS [Fecha quiebre]",
        "INTO #FECHAS_QUIEBRE",
        "FROM (SELECT DISTINCT CAST([Fecha de creación de Comentario del caso] AS DATE) AS [Fecha]",
        "      FROM [CL_INSUMOS_SEGUIMIENTO_ACTUAL].[dbo].[TBL_ULTIMO_COMENTARIO_FRACTALIA]",
        "      WHERE [Fecha de creación de Comentario del caso] IS NOT NULL) F;",
        "CREATE UNIQUE CLUSTERED INDEX IX_FECHAS_QUIEBRE ON #FECHAS_QUIEBRE ([Fecha]);",
        "",
        "",
    ]
)
JOIN_FQ = NL + "LEFT JOIN #FECHAS_QUIEBRE FQ  -- OPTIMIZACION 2026-10-26 A" + NL + "ON FQ.[Fecha] = CAST(X4.[Fecha de creación de Comentario del caso] AS DATE)"
BLOQUE_B = NL.join(
    [
        MARCA_B + " los casos con estos [Valor nuevo] en el historial se leen UNA vez",
        "-- (antes, dos EXISTS sobre TBL_HISTORIAL_CASOS por cada caso). Mismas condiciones => mismo resultado.",
        "DROP TABLE IF EXISTS #HIST_VALOR_NUEVO;",
        "SELECT DISTINCT [Número del caso], [Valor nuevo]",
        "INTO #HIST_VALOR_NUEVO",
        "FROM [CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_CASOS]",
        "WHERE [Valor nuevo] IN ('CHI - Especialista SSPP PYME', 'CHI-Isla de Retención');",
        "CREATE CLUSTERED INDEX IX_HIST_VALOR_NUEVO ON #HIST_VALOR_NUEVO ([Número del caso]);",
        "",
        "",
    ]
)


def _reemplazar(texto: str, viejo: str, nuevo: str, veces: int) -> str:
    n = texto.count(viejo)
    if n != veces:
        raise RuntimeError(f"Se esperaban {veces} ocurrencia(s) de {viejo[:60]!r} y hay {n}: el SP cambio, revisar a mano.")
    return texto.replace(viejo, nuevo)


def nueva_definicion(viva: str) -> str:
    if MARCA_A in viva or MARCA_B in viva:
        raise RuntimeError("El SP ya tiene la optimizacion aplicada.")
    t = _reemplazar(viva, INICIO_1, BLOQUE_A + INICIO_1, 1)
    t = _reemplazar(t, LLAMADA, "FQ.[Fecha quiebre]", 2)
    t = _reemplazar(t, JOIN_X4, JOIN_X4 + JOIN_FQ, 1)
    t = _reemplazar(t, INICIO_3, BLOQUE_B + INICIO_3, 1)
    t = _reemplazar(t, HISTORIAL, "FROM #HIST_VALOR_NUEVO X1", 2)
    return t


# --------------------------------------------------------------------------- #
# Prueba: version vieja vs nueva sobre #temporales (solo lectura)
# --------------------------------------------------------------------------- #
def _tramo(texto: str, inicio: str, fin: str) -> str:
    i = texto.index(inicio)
    return texto[i : texto.index(fin, i)]


def sentencias(defin: str, nueva: bool) -> dict[str, str]:
    """Las 3 sentencias pesadas (+ el UPDATE de TOTAL_1) de una definicion."""
    ini1 = MARCA_A if nueva else INICIO_1
    ini3 = MARCA_B if nueva else INICIO_3
    upd1 = "UPDATE [CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]"
    return {
        "s1": _tramo(defin, ini1, upd1),
        "u1": _tramo(defin, upd1, "IF EXISTS"),
        "s2": _tramo(defin, "SELECT " + NL + "X0.[Número del caso]," + NL, "IF EXISTS"),
        "s3": _tramo(defin, ini3, "UPDATE [CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]"),
    }


_ESCRITURA_REAL = re.compile(r"\b(INTO|UPDATE|DELETE|DROP\s+TABLE(\s+IF\s+EXISTS)?|TRUNCATE\s+TABLE|ALTER)\s+\[", re.IGNORECASE)


def _definicion(conn) -> str:
    """Definicion VIVA del SP en el servidor (OBJECT_DEFINITION solo ve la base actual)."""
    fila = conn.cursor().execute(
        "SELECT m.definition FROM [CL_SEGUIMIENTO_ACTUAL].sys.sql_modules m "
        "WHERE m.object_id = OBJECT_ID('CL_SEGUIMIENTO_ACTUAL.dbo.SP_PROCESO_SEGUIMIENTO')"
    ).fetchone()
    if not fila or not fila[0]:
        raise RuntimeError("No se encontro la definicion de SP_PROCESO_SEGUIMIENTO.")
    return fila[0]


def _a_temporales(sql: str, sufijo: str) -> str:
    sql = sql.replace("[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_1_NUEVO]", f"#T1_{sufijo}")
    sql = sql.replace("[CL_TEMPORALES].[dbo].[TBL_SEGUIMIENTO_TOTAL_2_NUEVO]", f"#T2_{sufijo}")
    sql = sql.replace("[CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]", f"#F_{sufijo}")
    if _ESCRITURA_REAL.search(sql):
        raise RuntimeError(f"La prueba escribiria en una tabla real:\n{_ESCRITURA_REAL.search(sql).group(0)}")
    return sql


def probar() -> int:
    s = cargar_configuracion(RAIZ)
    conn = crear_conexion(s.db)
    cur = conn.cursor()
    viva = _definicion(conn)
    nueva = nueva_definicion(viva)
    viejo_sql, nuevo_sql = sentencias(viva, False), sentencias(nueva, True)
    hoy = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cabecera = (
        "SET LANGUAGE SPANISH; SET DATEFORMAT DMY;" + NL
        + f"DECLARE @HOY DATETIME = '{hoy}', @periodo_actual INT;" + NL
        + "SET @periodo_actual = YEAR(@HOY)* 100 + MONTH(@HOY);" + NL
    )
    tiempos: dict[str, float] = {}

    def correr(nombre: str, sql: str) -> None:
        inicio = time.monotonic()
        cur.execute(cabecera + sql)
        while cur.nextset():
            pass
        tiempos[nombre] = round(time.monotonic() - inicio, 1)
        print(f"  {nombre}: {tiempos[nombre]} s", flush=True)

    try:
        print("Sentencia 1 + UPDATE (TOTAL_1):")
        correr("viejo_s1", _a_temporales(viejo_sql["s1"] + viejo_sql["u1"], "V"))
        correr("nuevo_s1", _a_temporales(nuevo_sql["s1"] + nuevo_sql["u1"], "N"))
        print("Sentencia 2 (TOTAL_2), sin cambios, desde cada TOTAL_1:")
        correr("viejo_s2", _a_temporales(viejo_sql["s2"], "V").replace("#T2_V", "#T2_V"))
        correr("nuevo_s2", _a_temporales(nuevo_sql["s2"], "N"))
        print("Sentencia 3 (TBL_SEGUIMIENTO):")
        correr("viejo_s3", _a_temporales(viejo_sql["s3"], "V"))
        correr("nuevo_s3", _a_temporales(nuevo_sql["s3"], "N"))

        resultado = {"fecha": datetime.now().isoformat(timespec="seconds"), "tiempos_s": tiempos, "comparacion": {}}
        for tabla in ("T1", "T2", "F"):
            cols = [r[0] for r in cur.execute(f"SELECT name FROM tempdb.sys.columns WHERE object_id = OBJECT_ID('tempdb..#{tabla}_V') ORDER BY column_id").fetchall()]
            lista = ", ".join(f"[{c}]" for c in cols)
            n_v = cur.execute(f"SELECT COUNT(*) FROM #{tabla}_V").fetchone()[0]
            n_n = cur.execute(f"SELECT COUNT(*) FROM #{tabla}_N").fetchone()[0]
            solo_v = cur.execute(f"SELECT COUNT(*) FROM (SELECT {lista} FROM #{tabla}_V EXCEPT SELECT {lista} FROM #{tabla}_N) X").fetchone()[0]
            solo_n = cur.execute(f"SELECT COUNT(*) FROM (SELECT {lista} FROM #{tabla}_N EXCEPT SELECT {lista} FROM #{tabla}_V) X").fetchone()[0]
            resultado["comparacion"][tabla] = {"filas_viejo": n_v, "filas_nuevo": n_n, "solo_viejo": solo_v, "solo_nuevo": solo_n,
                                              "columnas": len(cols), "identico": n_v == n_n and solo_v == 0 and solo_n == 0}
            print(f"  {tabla}: {n_v:,} vs {n_n:,} filas, {len(cols)} columnas, solo viejo={solo_v}, solo nuevo={solo_n}")
        resultado["identico"] = all(r["identico"] for r in resultado["comparacion"].values())
        resultado["definicion_viva_sha"] = hash(viva)
        EVIDENCIA.parent.mkdir(exist_ok=True)
        EVIDENCIA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        print("RESULTADO:", "IDENTICO" if resultado["identico"] else "CON DIFERENCIAS", "->", EVIDENCIA)
        return 0 if resultado["identico"] else 1
    finally:
        conn.rollback()
        conn.close()


# --------------------------------------------------------------------------- #
# Aplicar / revertir
# --------------------------------------------------------------------------- #
def _alter(conn, definicion: str) -> None:
    alter = re.sub(r"^\s*CREATE\s+PROCEDURE", "ALTER PROCEDURE", definicion, count=1, flags=re.IGNORECASE)
    cur = conn.cursor()
    cur.execute("USE [CL_SEGUIMIENTO_ACTUAL]")
    cur.execute(alter)
    conn.commit()


def aplicar() -> int:
    if not EVIDENCIA.exists() or not json.loads(EVIDENCIA.read_text(encoding="utf-8")).get("identico"):
        print("Primero ejecute 'probar' y verifique que el resultado sea IDENTICO.")
        return 1
    if json.loads(EVIDENCIA.read_text(encoding="utf-8"))["fecha"][:10] != datetime.now().strftime("%Y-%m-%d"):
        print("La prueba no es de hoy: vuelva a ejecutar 'probar'.")
        return 1
    s = cargar_configuracion(RAIZ)
    conn = crear_conexion(s.db)
    try:
        viva = _definicion(conn)
        nueva = nueva_definicion(viva)
        RESPALDO.write_bytes(viva.encode("utf-8"))
        _alter(conn, nueva)
        quedo = _definicion(conn)
        NUEVA.write_bytes(quedo.encode("utf-8"))
        print(f"SP actualizado. Respaldo anterior: {RESPALDO}")
        print("Contiene la optimizacion:", MARCA_A in quedo and MARCA_B in quedo)
        return 0
    finally:
        conn.close()


def revertir() -> int:
    s = cargar_configuracion(RAIZ)
    conn = crear_conexion(s.db)
    try:
        _alter(conn, RESPALDO.read_bytes().decode("utf-8"))
        quedo = _definicion(conn)
        NUEVA.write_bytes(quedo.encode("utf-8"))
        print("SP revertido a la definicion anterior:", MARCA_A not in quedo)
        return 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Punto 4: indice agrupado en TBL_HISTORIAL_COMENTARIOS (heap de 1,7 M filas)
# --------------------------------------------------------------------------- #
TABLA_COMENTARIOS = "[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS]"
INDICE = "CIX_HISTORIAL_COMENTARIOS_CASO_FECHA"


def _indice_existe(cur) -> bool:
    return bool(cur.execute(
        "SELECT 1 FROM [CL_SALESFORCE_ACTUAL].sys.indexes WHERE name = ? "
        "AND object_id = OBJECT_ID('CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_COMENTARIOS')", INDICE
    ).fetchone())


def indice() -> int:
    """Indice AGRUPADO (caso, fecha): el MERGE del paquete 06 busca por caso y
    SP_INSUMOS_SEGUIMIENTO obtiene el ultimo comentario por caso sin ordenar
    toda la tabla. ONLINE: no bloquea las lecturas mientras se crea."""
    conn = crear_conexion(cargar_configuracion(RAIZ).db)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        if _indice_existe(cur):
            print(f"El indice {INDICE} ya existe.")
            return 0
        inicio = time.monotonic()
        cur.execute(
            f"CREATE CLUSTERED INDEX {INDICE} ON {TABLA_COMENTARIOS} "
            "([Número del caso], [Fecha de creación de Comentario del caso]) WITH (ONLINE = ON, SORT_IN_TEMPDB = ON)"
        )
        print(f"Indice {INDICE} creado en {time.monotonic() - inicio:.1f} s. Existe: {_indice_existe(cur)}")
        return 0
    finally:
        conn.close()


def quitar_indice() -> int:
    conn = crear_conexion(cargar_configuracion(RAIZ).db)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        if _indice_existe(cur):
            cur.execute(f"DROP INDEX {INDICE} ON {TABLA_COMENTARIOS}")
        print(f"Indice {INDICE} existe: {_indice_existe(cur)} (la tabla vuelve a ser heap)")
        return 0
    finally:
        conn.close()


UMBRAL_REORGANIZAR = 5.0  # % de fragmentacion (recomendacion de Microsoft)
UMBRAL_RECONSTRUIR = 30.0
PAGINAS_MINIMAS = 1000  # en indices chicos la fragmentacion no importa
LOG_MANTENIMIENTO = RAIZ / "logs" / "mantenimiento_indice.log"


def _fragmentacion(cur) -> tuple[float, int]:
    fila = cur.execute(
        "SELECT avg_fragmentation_in_percent, page_count FROM sys.dm_db_index_physical_stats("
        "DB_ID('CL_SALESFORCE_ACTUAL'), OBJECT_ID('CL_SALESFORCE_ACTUAL.dbo.TBL_HISTORIAL_COMENTARIOS'), 1, NULL, 'LIMITED')"
    ).fetchone()
    return float(fila[0]), int(fila[1])


def mantener_indice() -> int:
    """Mantenimiento periodico (tarea programada mensual): mide la
    fragmentacion del indice agrupado y solo actua si hace falta:
      < 5 %  -> nada;  5-30 % -> REORGANIZE (en linea);  >= 30 % -> REBUILD ONLINE.
    Deja una linea por ejecucion en logs/mantenimiento_indice.log."""
    conn = crear_conexion(cargar_configuracion(RAIZ).db)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        if not _indice_existe(cur):
            accion, antes, paginas, despues, seg = "SIN INDICE (ejecute el modo 'indice')", None, None, None, 0.0
        else:
            antes, paginas = _fragmentacion(cur)
            inicio = time.monotonic()
            if paginas < PAGINAS_MINIMAS or antes < UMBRAL_REORGANIZAR:
                accion = "nada"
            elif antes < UMBRAL_RECONSTRUIR:
                accion = "REORGANIZE"
                cur.execute(f"ALTER INDEX {INDICE} ON {TABLA_COMENTARIOS} REORGANIZE")
            else:
                accion = "REBUILD ONLINE"
                cur.execute(f"ALTER INDEX {INDICE} ON {TABLA_COMENTARIOS} REBUILD WITH (ONLINE = ON, SORT_IN_TEMPDB = ON)")
            seg = time.monotonic() - inicio
            despues = _fragmentacion(cur)[0] if accion != "nada" else antes
        linea = (
            f"{datetime.now():%Y-%m-%d %H:%M:%S} {INDICE}: accion={accion}"
            + (f" fragmentacion={antes:.2f}% -> {despues:.2f}% paginas={paginas:,} ({seg:.1f} s)" if antes is not None else "")
        )
        print(linea)
        LOG_MANTENIMIENTO.parent.mkdir(exist_ok=True)
        with open(LOG_MANTENIMIENTO, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
        return 0 if antes is not None else 1
    finally:
        conn.close()


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    acciones = {
        "probar": probar,
        "aplicar": aplicar,
        "revertir": revertir,
        "indice": indice,
        "quitar-indice": quitar_indice,
        "mantener-indice": mantener_indice,
    }
    if modo not in acciones:
        print(__doc__)
        sys.exit(2)
    sys.exit(acciones[modo]())
