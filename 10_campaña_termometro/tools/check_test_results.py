"""
Valida el resultado del pipeline contra los 8 casos de borde sintéticos
generados por generate_sample_data.py. Se corre DESPUÉS de main.py.

A diferencia del módulo tools/parity/ (que compara contra una corrida real de
SSIS), este script no necesita el paquete SSIS -- valida directamente que la
lógica de negocio (Estado, NPS, deduplicación, filtro de rango de fechas,
marca de detractor) se comporta como se espera, usando casos conocidos.

Uso:
    python tools/check_test_results.py --periodo 202607
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "termometro"))

import pandas as pd
from sqlalchemy import text

from db import get_engine

EXPECTATIONS = [
    {"RUT_SIN_DV": "111111111", "desc": "encuesta normal", "Estado": "CAMPAÑA OK", "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "222222222", "desc": "promedio 0 sin comentarios", "Estado": "NO RECORRIDO", "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "333333333", "desc": "promedio 0, comentario SIN CONTACTO", "Estado": "SIN CONTACTO", "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "444444444", "desc": "sin fila de encuesta", "Estado": "NO RECORRIDO", "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "555555555", "desc": "cliente detractor", "Estado": "CAMPAÑA OK", "ESTADO DETRACTOR": "DETRACTOR"},
    {"RUT_SIN_DV": "666666666", "desc": "encuesta fuera de rango (debe tratarse como sin encuesta)", "Estado": "NO RECORRIDO", "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "777777777", "desc": "encuesta duplicada, debe prevalecer la más reciente", "Estado": "CAMPAÑA OK", "Prom 14.": 9.0, "ESTADO DETRACTOR": "-"},
    {"RUT_SIN_DV": "888888888", "desc": "Q11/Q14 'No evaluado' -> deben quedar NULL", "Estado": "CAMPAÑA OK", "Prom 11.": None, "Prom 14.": None, "ESTADO DETRACTOR": "-"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--periodo", type=int, required=True)
    args = parser.parse_args()

    engine = get_engine()
    df = pd.read_sql(
        text("SELECT * FROM [CL_CAMPAÑAS].[dbo].[TBL_CAMPAÑA_TERMOMETRO] WHERE PERIODO = :periodo"),
        engine,
        params={"periodo": args.periodo},
    )
    df = df.set_index("RUT_SIN_DV")

    print(f"\n{'='*80}\nVALIDACIÓN DE CASOS DE PRUEBA -- periodo {args.periodo}\n{'='*80}")
    fallas = 0
    for exp in EXPECTATIONS:
        rut = exp["RUT_SIN_DV"]
        desc = exp["desc"]
        if rut not in df.index:
            print(f"❌ RUT {rut} ({desc}): no aparece en el resultado final")
            fallas += 1
            continue

        row = df.loc[rut]
        ok = True
        detalle = []
        for campo, esperado in exp.items():
            if campo in ("RUT_SIN_DV", "desc"):
                continue
            actual = row.get(campo)
            if pd.isna(actual):
                actual = None
            coincide = (actual == esperado) or (esperado is None and actual is None)
            if not coincide:
                ok = False
                detalle.append(f"{campo}: esperado={esperado!r} obtenido={actual!r}")

        if ok:
            print(f"✅ RUT {rut} ({desc}): OK")
        else:
            print(f"❌ RUT {rut} ({desc}): " + "; ".join(detalle))
            fallas += 1

    print(f"{'='*80}")
    if fallas == 0:
        print("✅ Todos los casos de prueba pasaron.")
    else:
        print(f"❌ {fallas} caso(s) fallaron.")
    print(f"{'='*80}\n")

    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
