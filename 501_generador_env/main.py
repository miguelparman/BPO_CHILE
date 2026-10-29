"""Empaqueta y restaura los archivos '.env' de los proyectos de BPO_CHILE para
copiarlos a otra maquina, cifrados con 7-Zip (AES-256, nombres cifrados).

Uso:
    python main.py exportar                  # crea env_backup.7z (junto a este script) con clave aleatoria
    python main.py exportar --salida D:\\x.7z # ruta de salida distinta
    python main.py importar env_backup.7z    # pide la clave y restaura cada .env en su sitio

El archivo de salida se deja por defecto dentro de este proyecto
(501_generador_env/), cuyo .gitignore ignora '*.7z' para que no se suba a git.
Los '.env' no se versionan: este script es la via soportada para moverlos
entre maquinas.

Requiere 7-Zip instalado (7z.exe en el PATH o en 'Program Files').
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent  # 501_generador_env
RAIZ = PROYECTO.parent  # BPO_CHILE
EXCLUIR = {"Basurero", "Migrar", ".venv", "venv", "node_modules", ".git", "__pycache__"}
SALIDA_POR_DEFECTO = PROYECTO / "env_backup.7z"  # ignorado por el .gitignore de este proyecto


def _buscar_7z() -> str:
    for candidato in ("7z", "7za"):
        ruta = shutil.which(candidato)
        if ruta:
            return ruta
    for carpeta in (Path(r"C:\Program Files\7-Zip"), Path(r"C:\Program Files (x86)\7-Zip")):
        if (carpeta / "7z.exe").exists():
            return str(carpeta / "7z.exe")
    sys.exit("No se encontro 7-Zip. Instalelo desde https://www.7-zip.org y reintente.")


def _buscar_envs() -> list[Path]:
    return sorted(
        p.relative_to(RAIZ)
        for p in RAIZ.rglob(".env")
        if p.is_file() and not EXCLUIR.intersection(p.relative_to(RAIZ).parts)
    )


def exportar(salida: Path) -> int:
    envs = _buscar_envs()
    if not envs:
        print("No se encontro ningun .env.")
        return 1
    clave = secrets.token_urlsafe(18)
    salida = salida.resolve()
    if RAIZ in salida.parents and PROYECTO not in salida.parents:
        print(f"AVISO: '{salida}' queda dentro del repositorio y fuera de 501_generador_env; verifique que git lo ignore.")
    salida.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lista:
        lista.write("\n".join(str(p) for p in envs))
    try:
        subprocess.run(
            [_buscar_7z(), "a", "-t7z", "-mhe=on", f"-p{clave}", str(salida), f"@{lista.name}"],
            cwd=RAIZ, check=True, stdout=subprocess.DEVNULL,
        )
    finally:
        Path(lista.name).unlink(missing_ok=True)
    print(f"{len(envs)} archivo(s) .env empaquetados en: {salida}")
    print(f"Clave (guardela y envíela por otro canal): {clave}")
    return 0


def importar(archivo: Path) -> int:
    if not archivo.exists():
        print(f"No existe: {archivo}")
        return 1
    clave = getpass.getpass("Clave del archivo: ")
    try:
        subprocess.run(
            [_buscar_7z(), "x", f"-p{clave}", f"-o{RAIZ}", "-aos", str(archivo.resolve())],
            check=True, stdout=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print("No se pudo extraer (clave incorrecta o archivo danado).")
        return 1
    print(f"Restaurado en {RAIZ} (los .env existentes no se sobrescriben).")
    print("Recuerde borrar el .7z cuando termine y revisar rutas propias de la maquina.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="accion", required=True)
    p_exp = sub.add_parser("exportar", help="empaqueta todos los .env en un .7z cifrado")
    p_exp.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    p_imp = sub.add_parser("importar", help="restaura los .env desde un .7z")
    p_imp.add_argument("archivo", type=Path)
    args = parser.parse_args()
    return exportar(args.salida) if args.accion == "exportar" else importar(args.archivo)


if __name__ == "__main__":
    sys.exit(main())
