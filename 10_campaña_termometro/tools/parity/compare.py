"""
Compara dos snapshots de TBL_CAMPAÑA_TERMOMETRO (uno del SSIS original, otro
del pipeline Python) y reporta diferencias.

Uso:
    python -m tools.parity.compare --periodo 202607 --base ssis --nuevo python

Genera:
    - Reporte en consola (resumen)
    - tools/parity/snapshots/<periodo>_diff_report.md  (detalle)
"""
import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "src", "termometro"))

import pandas as pd

SNAPSHOT_DIR = os.path.join(_ROOT, "tools", "parity", "snapshots")

# Columna(s) que identifican una fila de forma única
KEY_COLUMNS = ["RUT", "PERIODO"]

# Columnas numéricas donde se tolera una diferencia mínima por redondeo
NUMERIC_TOLERANCE_COLUMNS = {
    "Prom 11.": 0.01,
    "Prom 14.": 0.01,
}


def _load(periodo: int, etiqueta: str) -> pd.DataFrame:
    path = os.path.join(SNAPSHOT_DIR, f"{periodo}_{etiqueta}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No existe {path}. Corre primero: python -m tools.parity.snapshot --periodo {periodo} --etiqueta {etiqueta}"
        )
    return pd.read_parquet(path)


def _values_equal(a, b, col: str) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    if col in NUMERIC_TOLERANCE_COLUMNS:
        try:
            return abs(float(a) - float(b)) <= NUMERIC_TOLERANCE_COLUMNS[col]
        except (TypeError, ValueError):
            pass
    return a == b


def compare(periodo: int, base_label: str, nuevo_label: str) -> dict:
    df_base = _load(periodo, base_label)
    df_nuevo = _load(periodo, nuevo_label)

    faltan_key = set(KEY_COLUMNS) - set(df_base.columns) - set(df_nuevo.columns)
    if faltan_key:
        raise ValueError(f"Faltan columnas clave {faltan_key} en alguno de los snapshots")

    df_base = df_base.set_index(KEY_COLUMNS)
    df_nuevo = df_nuevo.set_index(KEY_COLUMNS)

    keys_base = set(df_base.index)
    keys_nuevo = set(df_nuevo.index)

    solo_en_base = keys_base - keys_nuevo
    solo_en_nuevo = keys_nuevo - keys_base
    en_ambos = keys_base & keys_nuevo

    columnas_comunes = [c for c in df_base.columns if c in df_nuevo.columns]
    columnas_solo_base = [c for c in df_base.columns if c not in df_nuevo.columns]
    columnas_solo_nuevo = [c for c in df_nuevo.columns if c not in df_base.columns]

    diffs_por_columna = {col: [] for col in columnas_comunes}

    for key in en_ambos:
        row_base = df_base.loc[key]
        row_nuevo = df_nuevo.loc[key]
        for col in columnas_comunes:
            v_base = row_base[col]
            v_nuevo = row_nuevo[col]
            if not _values_equal(v_base, v_nuevo, col):
                diffs_por_columna[col].append((key, v_base, v_nuevo))

    resultado = {
        "periodo": periodo,
        "filas_base": len(df_base),
        "filas_nuevo": len(df_nuevo),
        "solo_en_base": solo_en_base,
        "solo_en_nuevo": solo_en_nuevo,
        "en_ambos": len(en_ambos),
        "columnas_solo_base": columnas_solo_base,
        "columnas_solo_nuevo": columnas_solo_nuevo,
        "diffs_por_columna": {k: v for k, v in diffs_por_columna.items() if v},
    }
    return resultado


def print_report(resultado: dict, base_label: str, nuevo_label: str) -> None:
    print(f"\n{'='*70}")
    print(f"REPORTE DE PARIDAD -- periodo {resultado['periodo']}")
    print(f"{'='*70}")
    print(f"Filas en '{base_label}':  {resultado['filas_base']}")
    print(f"Filas en '{nuevo_label}': {resultado['filas_nuevo']}")
    print(f"Filas presentes en ambos (mismo RUT+PERIODO): {resultado['en_ambos']}")

    if resultado["solo_en_base"]:
        print(f"\n⚠️  {len(resultado['solo_en_base'])} filas están en '{base_label}' pero NO en '{nuevo_label}':")
        for k in list(resultado["solo_en_base"])[:10]:
            print(f"   - {k}")

    if resultado["solo_en_nuevo"]:
        print(f"\n⚠️  {len(resultado['solo_en_nuevo'])} filas están en '{nuevo_label}' pero NO en '{base_label}':")
        for k in list(resultado["solo_en_nuevo"])[:10]:
            print(f"   - {k}")

    if resultado["columnas_solo_base"]:
        print(f"\n⚠️  Columnas solo en '{base_label}': {resultado['columnas_solo_base']}")
    if resultado["columnas_solo_nuevo"]:
        print(f"\n⚠️  Columnas solo en '{nuevo_label}': {resultado['columnas_solo_nuevo']}")

    if not resultado["diffs_por_columna"]:
        print("\n✅ Sin diferencias de valores en las columnas comunes. Paridad OK.")
    else:
        print(f"\n⚠️  Columnas con diferencias de valor:")
        for col, diffs in sorted(resultado["diffs_por_columna"].items(), key=lambda x: -len(x[1])):
            print(f"   - {col}: {len(diffs)} filas distintas")

    total_filas = resultado["en_ambos"]
    total_ok = total_filas - len(
        {k for diffs in resultado["diffs_por_columna"].values() for k, _, _ in diffs}
    )
    if total_filas:
        pct = 100 * total_ok / total_filas
        print(f"\nResumen: {total_ok}/{total_filas} filas idénticas en todas las columnas comparadas ({pct:.1f}%)")
    print(f"{'='*70}\n")


def write_markdown_report(resultado: dict, base_label: str, nuevo_label: str) -> str:
    path = os.path.join(SNAPSHOT_DIR, f"{resultado['periodo']}_diff_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Reporte de paridad — periodo {resultado['periodo']}\n\n")
        f.write(f"- Filas en `{base_label}`: {resultado['filas_base']}\n")
        f.write(f"- Filas en `{nuevo_label}`: {resultado['filas_nuevo']}\n")
        f.write(f"- Filas en ambos: {resultado['en_ambos']}\n\n")

        if resultado["diffs_por_columna"]:
            f.write("## Diferencias por columna\n\n")
            for col, diffs in sorted(resultado["diffs_por_columna"].items(), key=lambda x: -len(x[1])):
                f.write(f"### `{col}` — {len(diffs)} filas distintas\n\n")
                f.write(f"| Clave | {base_label} | {nuevo_label} |\n|---|---|---|\n")
                for key, v_base, v_nuevo in diffs[:20]:
                    f.write(f"| {key} | {v_base} | {v_nuevo} |\n")
                f.write("\n")
        else:
            f.write("Sin diferencias. Paridad OK.\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara dos snapshots de TBL_CAMPAÑA_TERMOMETRO")
    parser.add_argument("--periodo", type=int, required=True)
    parser.add_argument("--base", type=str, default="ssis", help="Etiqueta del snapshot de referencia (ej. 'ssis')")
    parser.add_argument("--nuevo", type=str, default="python", help="Etiqueta del snapshot nuevo (ej. 'python')")
    args = parser.parse_args()

    resultado = compare(args.periodo, args.base, args.nuevo)
    print_report(resultado, args.base, args.nuevo)
    path = write_markdown_report(resultado, args.base, args.nuevo)
    print(f"Reporte detallado guardado en: {path}")
    return 0 if not resultado["diffs_por_columna"] and not resultado["solo_en_base"] and not resultado["solo_en_nuevo"] else 1


if __name__ == "__main__":
    sys.exit(main())
