"""
Orquestador del pipeline de Notas de Crédito: consolida en un solo proyecto
los dos pasos que antes se ejecutaban por separado.

    1) bot_extraccion  (antes: 203_bot_notas_de_credito)
       Exporta la tabla "Detalle NC" desde Power BI Service y sobrescribe
       el Excel compartido (DESTINO_FINAL en bot_extraccion/.env).

    2) etl_carga       (antes: 03_Notas_de_credito)
       Lee ese mismo Excel (EXCEL_PATH en etl_carga/.env) y recarga las
       Notas de Crédito en SQL Server.

El paso 2 solo se ejecuta si el paso 1 termina con código de salida 0.

Cada subproyecto conserva su propio código, su propio '.env' (las rutas
DESTINO_FINAL y EXCEL_PATH ya apuntan al mismo archivo, ver .env de cada
carpeta) y su propio log. Se ejecutan como subprocesos independientes
-para no mezclar en un mismo intérprete dos paquetes 'app.*' con el mismo
nombre pero distinto contenido, ni pisar la configuración de logging
(logging.basicConfig) que cada uno arma por su cuenta.

Período (ANIO/MES):
    Se define una sola vez en el '.env' de esta carpeta raíz y reemplaza a
    las variables de período que antes vivían por proyecto (ANIO/MES en
    etl_carga/.env y FILTRO_ANIO/FILTRO_MES_NC en bot_extraccion/.env).
    Cada subproyecto lee este .env general como respaldo (ver sus
    config.py), y --anio/--mes en la línea de comandos tiene prioridad
    sobre el .env para ambos pasos.

Uso:
    python main.py                     # bot -> (si OK) -> etl
    python main.py --solo-bot          # solo el paso de extracción
    python main.py --solo-etl          # solo el paso de carga (usa el Excel ya existente)
    python main.py --diagnose          # pasa --diagnose al bot
    python main.py --anio 2026 --mes 9 # sobrescribe el período de .env para ambos pasos
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
BOT_DIR = BASE_DIR / "bot_extraccion"
ETL_DIR = BASE_DIR / "etl_carga"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--solo-bot", action="store_true", help="Ejecuta únicamente bot_extraccion.")
    modo.add_argument("--solo-etl", action="store_true", help="Ejecuta únicamente etl_carga (omite el bot).")
    parser.add_argument("--diagnose", action="store_true", help="Se reenvía a bot_extraccion/main.py --diagnose.")
    parser.add_argument("--anio", type=int, default=None, help="Se reenvía a etl_carga/main.py --anio.")
    parser.add_argument("--mes", type=int, default=None, help="Se reenvía a etl_carga/main.py --mes.")
    return parser.parse_args()


def _ejecutar_paso(nombre: str, directorio: Path, argumentos: list[str], env: dict[str, str]) -> int:
    print(f"\n=== [{nombre}] Iniciando ({directorio / 'main.py'}) ===")
    resultado = subprocess.run(
        [sys.executable, "main.py", *argumentos],
        cwd=directorio,
        env=env,
    )
    if resultado.returncode == 0:
        print(f"=== [{nombre}] Finalizado correctamente ===")
    else:
        print(f"=== [{nombre}] Falló (código de salida {resultado.returncode}) ===")
    return resultado.returncode


def main() -> int:
    args = _parse_args()
    load_dotenv(BASE_DIR / ".env")

    # El período resuelto aquí (CLI > .env general) se inyecta como variable
    # de entorno a ambos subprocesos, reemplazando lo que cada uno tuviera
    # en su propio .env (ANIO/MES en etl_carga, FILTRO_ANIO/FILTRO_MES_NC en
    # bot_extraccion -- ver el mapeo en cada config.py).
    env_periodo = dict(os.environ)
    if args.anio is not None:
        env_periodo["ANIO"] = str(args.anio)
    if args.mes is not None:
        env_periodo["MES"] = str(args.mes)

    if not args.solo_etl:
        args_bot = ["--diagnose"] if args.diagnose else []
        codigo_bot = _ejecutar_paso("bot_extraccion", BOT_DIR, args_bot, env_periodo)
        if codigo_bot != 0:
            print("\nEl bot de extracción falló: no se ejecuta la carga a SQL Server (etl_carga).")
            return codigo_bot

        if args.solo_bot:
            return 0

    args_etl: list[str] = []
    if args.anio is not None:
        args_etl += ["--anio", str(args.anio)]
    if args.mes is not None:
        args_etl += ["--mes", str(args.mes)]

    return _ejecutar_paso("etl_carga", ETL_DIR, args_etl, env_periodo)


def _mostrar_proyecto():
    """Muestra el nombre del proyecto en la consola y en el titulo de la ventana."""
    import ctypes
    import sys
    from pathlib import Path

    carpeta = Path(__file__).resolve().parent
    nombre = carpeta.name
    print("=" * 60, f" PROYECTO: {nombre}", "=" * 60, sep="\n", flush=True)
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleTitleW(nombre)


if __name__ == "__main__":
    _mostrar_proyecto()
    sys.exit(main())
