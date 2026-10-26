r"""Limpieza de comentarios duplicados en
[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS].

Origen del problema: el MERGE de 'CARGA COMENTARIOS CHILE' (paquete 06)
compara el comentario de la staging (nvarchar) con el varchar(6000) guardado;
si el texto trae un caracter no representable en cp1252 se guarda con '?' y
nunca vuelve a coincidir, asi que SSIS lo reinsertaba en CADA corrida. La
migracion Python ya lo corrige (mappings.FLUJO_TEMP_COMENTARIOS.tipos_temporal).

Regla (clave del MERGE = caso + fecha del comentario + texto):
  - se CONSERVAN todas las filas de la PRIMERA carga ([Fecha de Carga al SQL]
    minima) de cada comentario, incluidos los comentarios que llegaron
    repetidos desde Salesforce en esa misma carga (pueden ser legitimos);
  - se BORRAN las filas de cargas posteriores (reinserciones).

Seguridad:
  - por defecto solo SIMULA (cuenta); borra solo con --aplicar;
  - las filas borradas se copian (OUTPUT) a TABLA_RESPALDO antes de borrarse;
  - todo en UNA transaccion: si algun control no cuadra, ROLLBACK.
Es idempotente: se puede volver a ejecutar (p.ej. tras apagar SSIS) y solo
borra lo nuevo.

Uso:
    python tools/limpiar_duplicados_comentarios.py            # simulacion
    python tools/limpiar_duplicados_comentarios.py --aplicar  # borra (con respaldo)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "seguimiento"))

from config import cargar_configuracion  # noqa: E402
from db import crear_conexion  # noqa: E402

TABLA = "[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS]"
TABLA_RESPALDO = "[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS_DUPLICADOS_BK]"
COLUMNAS = (
    "[Número del caso]",
    "[Comentario del caso creado por]",
    "[Fecha de creación de Comentario del caso]",
    "[Caso público comentado]",
    "[Comentarios del caso]",
    "[Fecha de Carga al SQL]",
)
CLAVE = "[Número del caso], [Fecha de creación de Comentario del caso], [Comentarios del caso]"

CON_PRIMERA = f"""
SELECT {", ".join(COLUMNAS)}, MIN([Fecha de Carga al SQL]) OVER (PARTITION BY {CLAVE}) AS primera
FROM {TABLA}"""

SQL_A_BORRAR = f"SELECT COUNT(*) FROM ({CON_PRIMERA}) D WHERE [Fecha de Carga al SQL] > primera"
SQL_TOTAL = f"SELECT COUNT(*) FROM {TABLA}"
SQL_GRUPOS_CON_REINSERCION = f"""
SELECT COUNT(*) FROM (SELECT 1 x FROM {TABLA} GROUP BY {CLAVE}
                      HAVING COUNT(DISTINCT [Fecha de Carga al SQL]) > 1) G"""
SQL_DUP_MISMA_CARGA = f"""
SELECT COUNT(*), ISNULL(SUM(n - 1), 0) FROM (SELECT COUNT(*) n FROM {TABLA} GROUP BY {CLAVE}
                                              HAVING COUNT(*) > 1) G"""


def _uno(cursor, sql):
    return cursor.execute(sql).fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Borra las reinserciones (con respaldo). Sin esto solo simula.")
    args = parser.parse_args()

    conn = crear_conexion(cargar_configuracion(RAIZ).db)  # autocommit=False: una transaccion
    cursor = conn.cursor()
    try:
        total = _uno(cursor, SQL_TOTAL)[0]
        a_borrar = _uno(cursor, SQL_A_BORRAR)[0]
        grupos = _uno(cursor, SQL_GRUPOS_CON_REINSERCION)[0]
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {TABLA}")
        print(f"  Filas totales:                         {total:>10,}")
        print(f"  Comentarios con reinserciones:         {grupos:>10,}")
        print(f"  Filas a borrar (cargas posteriores):   {a_borrar:>10,}")
        print(f"  Filas que quedarian:                   {total - a_borrar:>10,}")
        if not args.aplicar:
            print("SIMULACION: no se borro nada (use --aplicar).")
            conn.rollback()
            return 0
        if a_borrar == 0:
            print("Nada que borrar.")
            conn.rollback()
            return 0

        cursor.execute("SET LOCK_TIMEOUT 120000")
        cursor.execute(
            f"IF OBJECT_ID('{TABLA_RESPALDO.replace('[', '').replace(']', '')}') IS NULL "
            f"SELECT TOP 0 {', '.join(COLUMNAS)}, CAST(NULL AS datetime) AS [Fecha de Limpieza] "
            f"INTO {TABLA_RESPALDO} FROM {TABLA}"
        )
        ahora = datetime.now().replace(microsecond=0)
        cursor.execute(
            f"WITH D AS ({CON_PRIMERA}) DELETE FROM D "
            f"OUTPUT {', '.join('DELETED.' + c for c in COLUMNAS)}, ? INTO {TABLA_RESPALDO} ({', '.join(COLUMNAS)}, [Fecha de Limpieza]) "
            "WHERE [Fecha de Carga al SQL] > primera",
            ahora,
        )
        borradas = cursor.rowcount

        # Controles antes de confirmar
        despues = _uno(cursor, SQL_TOTAL)[0]
        respaldadas = cursor.execute(
            f"SELECT COUNT(*) FROM {TABLA_RESPALDO} WHERE [Fecha de Limpieza] = ?", ahora
        ).fetchone()[0]
        grupos_despues = _uno(cursor, SQL_GRUPOS_CON_REINSERCION)[0]
        controles = {
            "borradas == a borrar": borradas == a_borrar,
            "total despues == total - borradas": despues == total - borradas,
            "respaldadas == borradas": respaldadas == borradas,
            "sin comentarios con reinserciones": grupos_despues == 0,
        }
        for nombre, ok in controles.items():
            print(f"  [{'OK' if ok else 'FALLO'}] {nombre}")
        if not all(controles.values()):
            conn.rollback()
            print("ROLLBACK: un control no cuadro; no se borro nada.")
            return 1
        conn.commit()
        n_dup, filas_dup = _uno(cursor, SQL_DUP_MISMA_CARGA)
        print(f"COMMIT: {borradas:,} filas borradas y respaldadas en {TABLA_RESPALDO} (Fecha de Limpieza = {ahora}).")
        print(f"  Filas en la tabla: {despues:,}")
        print(f"  Quedan {n_dup:,} comentarios repetidos DENTRO de una misma carga ({filas_dup:,} filas; vinieron asi de Salesforce, no se tocan).")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
