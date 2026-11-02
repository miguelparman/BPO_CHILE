r"""Corrige el duplicado (DNI, Periodo) en [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO].

Origen del problema: un reingreso (mismo DNI y periodo) deja dos filas y el
LEFT JOIN de SP_ASESOR_RESPONSABLE duplica los casos -> "Numeros de casos
duplicados". Caso actual: DNI 74224906, periodo 202610.

Regla: por cada (DNI, Periodo) repetido se CONSERVA la fila con
[Fecha Ingreso a la Empresa] mas reciente (el reingreso) y se BORRAN las demas.

Seguridad:
  - por defecto solo SIMULA; borra solo con --aplicar;
  - las filas a borrar se guardan completas en evidencias/ (JSON) antes del DELETE;
  - UNA transaccion: si lo borrado no coincide con lo esperado, ROLLBACK.

Uso:
    python tools/corregir_personal_duplicado.py            # simulacion
    python tools/corregir_personal_duplicado.py --aplicar  # borra (con respaldo)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "seguimiento"))

from config import cargar_configuracion  # noqa: E402
from db import crear_conexion  # noqa: E402

TABLA = "[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO]"

# Filas que sobran: no son la de [Fecha Ingreso a la Empresa] mas reciente de su (DNI, Periodo).
CTE_SOBRANTES = f"""
WITH R AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY DNI, Periodo
                                 ORDER BY [Fecha Ingreso a la Empresa] DESC) AS rn,
              COUNT(*)     OVER (PARTITION BY DNI, Periodo) AS n
    FROM {TABLA})"""
SQL_SOBRANTES = CTE_SOBRANTES + " SELECT * FROM R WHERE n > 1 AND rn > 1"
SQL_DELETE = CTE_SOBRANTES + " DELETE FROM R WHERE n > 1 AND rn > 1"
SQL_GRUPOS = f"SELECT COUNT(*) FROM (SELECT 1 x FROM {TABLA} GROUP BY DNI, Periodo HAVING COUNT(*) > 1) G"
SQL_EMPATES = f"""SELECT COUNT(*) FROM (SELECT 1 x FROM {TABLA} GROUP BY DNI, Periodo
                  HAVING COUNT(*) > 1 AND COUNT(DISTINCT [Fecha Ingreso a la Empresa]) < COUNT(*)) G"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aplicar", action="store_true", help="Borra las filas sobrantes (con respaldo). Sin esto solo simula.")
    args = parser.parse_args()

    conn = crear_conexion(cargar_configuracion(RAIZ).db)  # autocommit=False: una transaccion
    cursor = conn.cursor()
    try:
        grupos = cursor.execute(SQL_GRUPOS).fetchone()[0]
        empates = cursor.execute(SQL_EMPATES).fetchone()[0]
        cursor.execute(SQL_SOBRANTES)
        columnas = [c[0] for c in cursor.description if c[0] not in ("rn", "n")]
        sobrantes = [dict(zip([c[0] for c in cursor.description], f)) for f in cursor.fetchall()]
        print(f"(DNI, Periodo) duplicados: {grupos}; filas a borrar: {len(sobrantes)}")
        for f in sobrantes:
            print(f"  DNI {f['DNI']} periodo {f['Periodo']} ingreso {f['Fecha Ingreso a la Empresa']} baja {f.get('Fecha de Baja')}")
        if empates:
            print(f"ABORTA: {empates} grupo(s) con la misma fecha de ingreso; no se puede elegir cual conservar.")
            return 1
        if not sobrantes:
            print("Nada que corregir.")
            return 0
        if len(sobrantes) != grupos:
            print("ABORTA: filas a borrar distinto de grupos duplicados (hay mas de 2 filas por grupo).")
            return 1
        if not args.aplicar:
            print("Simulacion: no se borro nada. Use --aplicar para borrar.")
            return 0

        respaldo = RAIZ / "evidencias" / f"personal_consolidado_duplicados_{datetime.now():%Y%m%d_%H%M%S}.json"
        respaldo.parent.mkdir(exist_ok=True)
        filas = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in f.items() if k in columnas} for f in sobrantes]
        respaldo.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Respaldo: {respaldo}")

        borradas = cursor.execute(SQL_DELETE).rowcount
        if borradas != len(sobrantes):
            conn.rollback()
            print(f"ROLLBACK: se esperaban {len(sobrantes)} filas y el DELETE afecto {borradas}.")
            return 1
        if cursor.execute(SQL_GRUPOS).fetchone()[0] != 0:
            conn.rollback()
            print("ROLLBACK: siguen quedando duplicados tras el DELETE.")
            return 1
        conn.commit()
        print(f"OK: {borradas} fila(s) borrada(s); sin duplicados (DNI, Periodo).")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
