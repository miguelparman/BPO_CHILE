"""Punto de entrada unico del proceso (estructura medallion):

1. ingesta: copia todos los Excel de 'Control Correos Chile' (sitio
   SharePoint 'BPO') hacia '14 CORREOS' (sitio 'ReportingFractalia').
2. bronze:  consolida 'Registro'/'Bandejas' de esos archivos y los carga tal
   cual en SQL Server ('CL_MOVIL'), por periodo.
3. silver:  bronze -> TBL_CORREO_REGISTRO_SILVER (limpio + ASUNTO_AGRUPADO +
            COORDINADOR) y TBL_CORREO_BANDEJAS_SILVER.
4. gold:    silver -> modelo estrella en el esquema 'gold' (lee solo silver),
            y valida que cuadre.

El periodo sale de FECHA_INICIO/FECHA_FIN en '.env' (o --fecha-inicio/
--fecha-fin). Si ambas estan vacias es automatico: el mes en curso y, los
primeros 7 dias del mes, tambien el anterior (ver comun/periodo.py). Un
fallo en una etapa detiene las siguientes pero no deshace las anteriores;
se reintenta con --desde / --solo. Cada corrida (salvo --verificar-copia)
queda en dbo.TBL_CORREO_LOG_EJECUCION; su ID_EJECUCION se graba
en cada fila de gold.FACT_MENSAJE.

Uso:
    python main.py                            # todo: ingesta -> bronze -> silver -> gold
                                              # (periodo automatico si '.env' no lo fija)
    python main.py --desde silver             # reintentar desde silver (bronze ya cargado)
    python main.py --solo gold                # una sola etapa
    python main.py --solo gold --completo     # reconstruir una etapa completa (silver/gold)
    python main.py --fecha-inicio 2026-09-01 --fecha-fin 2026-09-30
    python main.py --verificar-copia          # solo auditar la copia de ingesta
    python main.py --sin-validar              # sin validar conexiones al inicio (emergencia)

Antes de cualquier etapa se validan las conexiones que usa la corrida (ver
comun/conexiones.py): si alguna no responde, el ETL no se ejecuta y se
pregunta en consola si reintentar o cancelar.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # 11_correos/: para '.env' y 'logs/'
sys.path.insert(0, str(BASE_DIR / "src" / "correos"))

from bronze.cargar import ejecutar_bronze
from comun.conexiones import validar_conexiones, verificaciones_para
from comun.config import DbSettings, Settings, cargar_configuracion, cargar_configuracion_db
from comun.db import DatabaseGateway, crear_conexion
from comun.ejecucion import (
    ESTADO_ERROR,
    ESTADO_OK,
    Ejecucion,
    ResultadoEjecucion,
    finalizar_ejecucion,
    iniciar_ejecucion,
)
from comun.exceptions import CorreosError
from comun.logging_setup import NOMBRE_LOGGER, configurar_logging
from comun.periodo import resolver_periodo
from gold.cargar import cargar_periodo_gold, recargar_gold_completo, validar
from ingesta.copiar import ejecutar_copia
from ingesta.verificar_copia import ejecutar_verificacion
from silver.cargar import cargar_bandejas_silver, cargar_periodo_silver, recargar_silver_completo

logger = logging.getLogger(NOMBRE_LOGGER)

ETAPAS = ["ingesta", "bronze", "silver", "gold"]
# Etapas que pueden reconstruirse completas (bronze siempre es por periodo:
# reconstruir desde los .xlsx implica pasar el periodo que cubren).
ETAPAS_CON_COMPLETO = {"silver", "gold"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="11_correos: ingesta -> bronze -> silver -> gold")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--desde", choices=ETAPAS, help="Corre desde esta etapa hasta gold.")
    grupo.add_argument("--solo", choices=ETAPAS, help="Corre solo esta etapa.")
    grupo.add_argument("--verificar-copia", action="store_true", help="Solo audita la copia de ingesta.")
    parser.add_argument(
        "--completo",
        action="store_true",
        help="Silver/gold se reconstruyen completos (sin filtro de periodo). Solo con --solo/--desde silver|gold.",
    )
    parser.add_argument(
        "--sin-validar",
        action="store_true",
        help="No valida las conexiones al inicio (solo para emergencias).",
    )
    parser.add_argument("--fecha-inicio", default=None, help="UTC; solo fecha (2026-09-01) o fecha y hora. Si se omite, FECHA_INICIO de '.env' (vacia = periodo automatico).")
    parser.add_argument("--fecha-fin", default=None, help="UTC; solo fecha (2026-09-30, dia incluido completo) o fecha y hora (exclusiva). Si se omite, FECHA_FIN de '.env' (vacia = periodo automatico).")
    args = parser.parse_args(argv)

    args.etapas = seleccionar_etapas(args.desde, args.solo)
    if args.completo and not set(args.etapas) <= ETAPAS_CON_COMPLETO:
        parser.error("--completo solo aplica a silver/gold: usa --solo silver|gold o --desde silver|gold.")
    return args


def seleccionar_etapas(desde: str | None, solo: str | None) -> list[str]:
    if solo:
        return [solo]
    return ETAPAS[ETAPAS.index(desde):] if desde else list(ETAPAS)


def _necesita_periodo(etapas: list[str], completo: bool) -> bool:
    return "bronze" in etapas or (not completo and bool(set(etapas) & ETAPAS_CON_COMPLETO))


def aviso_periodo_manual(
    periodo: tuple[datetime, datetime] | None, cli_inicio: str | None, cli_fin: str | None, settings: Settings
) -> str | None:
    """Mensaje de advertencia cuando el periodo NO es el automatico: se
    fijo por --fecha-inicio/--fecha-fin o por FECHA_INICIO/FECHA_FIN en
    '.env'. None si el periodo es automatico o la corrida no usa periodo."""
    if periodo is None or not (settings.fecha_inicio or settings.fecha_fin):
        return None
    origen = "--fecha-inicio/--fecha-fin" if cli_inicio or cli_fin else "FECHA_INICIO/FECHA_FIN de '.env'"
    return (
        f"ATENCION: periodo MANUAL definido en {origen}. La carga tomara "
        f"[{periodo[0]:%Y-%m-%d %H:%M}, {periodo[1]:%Y-%m-%d %H:%M}) en vez del periodo automatico."
    )


def ejecutar_etapas_db(
    gateway: DatabaseGateway,
    settings: Settings,
    etapas: list[str],
    periodo: tuple[datetime, datetime] | None,
    completo: bool,
    ejecucion: Ejecucion,
    resultado: ResultadoEjecucion,
) -> None:
    """bronze / silver / gold sobre una misma conexion. Va completando
    'resultado' (filas por etapa, validacion de gold) a medida que avanza:
    si una etapa falla, el log conserva lo que alcanzo a cargar."""
    if "bronze" in etapas:
        _, resultado.filas_bronze, _ = ejecutar_bronze(settings.destino, gateway, *periodo)

    if "silver" in etapas:
        if completo:
            resultado.filas_silver = recargar_silver_completo(gateway)
            logger.info("Silver reconstruida completa: %s fila(s) insertadas.", resultado.filas_silver)
        else:
            eliminadas, resultado.filas_silver = cargar_periodo_silver(gateway, *periodo)
            logger.info("Silver finalizada: %s eliminadas / %s insertadas (periodo).", eliminadas, resultado.filas_silver)
        # Bandejas no tiene periodo: siempre completa (igual que en bronze).
        insertadas_bandejas = cargar_bandejas_silver(gateway)
        logger.info("Silver bandejas: %s fila(s) insertadas (total).", insertadas_bandejas)

    if "gold" in etapas:
        if completo:
            resultado.filas_gold = recargar_gold_completo(gateway, ejecucion)
            logger.info("Gold reconstruida completa: %s fila(s) en FACT_MENSAJE.", resultado.filas_gold)
            gold_ok = validar(gateway, None)
        else:
            eliminadas, resultado.filas_gold = cargar_periodo_gold(gateway, *periodo, ejecucion)
            logger.info(
                "Gold finalizada: %s eliminadas / %s insertadas en FACT_MENSAJE (periodo).", eliminadas, resultado.filas_gold
            )
            gold_ok = validar(gateway, periodo)
        resultado.validacion_gold = "OK" if gold_ok else "NO CUADRA"


def estado_final(archivos_no_copiados: int, validacion_gold: str | None) -> tuple[str, str | None]:
    """ESTADO y MENSAJE_ERROR para el log de una corrida que llego al final
    sin excepciones: ERROR si algun archivo no se copio o gold no cuadra."""
    problemas = []
    if archivos_no_copiados:
        problemas.append(f"{archivos_no_copiados} archivo(s) no se copiaron en la ingesta (ver log).")
    if validacion_gold == "NO CUADRA":
        problemas.append("La validacion de gold no cuadra (ver log).")
    return (ESTADO_ERROR, " ".join(problemas)) if problemas else (ESTADO_OK, None)


def _conexiones_disponibles(args: argparse.Namespace, settings: Settings, db_settings: DbSettings | None) -> bool:
    if args.sin_validar:
        logger.warning("ATENCION: --sin-validar, no se validan las conexiones antes de ejecutar.")
        return True
    if validar_conexiones(verificaciones_para(args.etapas, args.verificar_copia, settings, db_settings)):
        return True
    logger.error("Proceso cancelado: hay conexiones no disponibles, el ETL no se ejecuto.")
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = cargar_configuracion(BASE_DIR, fecha_inicio=args.fecha_inicio, fecha_fin=args.fecha_fin)
    configurar_logging(settings.log_dir)

    try:
        if args.verificar_copia:
            if not _conexiones_disponibles(args, settings, None):
                return 1
            return 0 if ejecutar_verificacion(settings) else 1

        # El periodo se valida ANTES de empezar: no tiene sentido copiar si
        # despues bronze no va a poder cargar.
        periodo = None
        if _necesita_periodo(args.etapas, args.completo):
            periodo = resolver_periodo(settings.fecha_inicio, settings.fecha_fin)
        if args.completo:
            detalle = " (completo)"
        elif periodo is None:
            detalle = ""
        else:
            origen = "manual" if settings.fecha_inicio or settings.fecha_fin else "automatico"
            detalle = f" | periodo {origen} [{periodo[0]:%Y-%m-%d %H:%M}, {periodo[1]:%Y-%m-%d %H:%M})"
        logger.info("Etapas: %s%s.", " -> ".join(args.etapas), detalle)
        aviso = aviso_periodo_manual(periodo, args.fecha_inicio, args.fecha_fin, settings)
        if aviso:
            logger.warning(aviso)

        # Antes de tocar nada: si alguna conexion no responde, no se ejecuta.
        db_settings = cargar_configuracion_db(BASE_DIR)
        if not _conexiones_disponibles(args, settings, db_settings):
            return 1

        # La conexion se abre al inicio (aun si solo corre la ingesta): toda
        # corrida queda registrada en dbo.TBL_CORREO_LOG_EJECUCION.
        conn = crear_conexion(db_settings)
        try:
            gateway = DatabaseGateway(conn, batch_size=db_settings.batch_size)
            ejecucion = iniciar_ejecucion(gateway, args.etapas, args.completo, periodo)
            resultado = ResultadoEjecucion()
            try:
                archivos_no_copiados = 0
                if "ingesta" in args.etapas:
                    archivos_no_copiados = sum(1 for r in ejecutar_copia(settings) if not r.ok)

                etapas_db = [e for e in args.etapas if e != "ingesta"]
                ejecutar_etapas_db(gateway, settings, etapas_db, periodo, args.completo, ejecucion, resultado)
            except Exception as exc:
                finalizar_ejecucion(gateway, ejecucion, ESTADO_ERROR, resultado, str(exc))
                raise

            estado, mensaje = estado_final(archivos_no_copiados, resultado.validacion_gold)
            finalizar_ejecucion(gateway, ejecucion, estado, resultado, mensaje)
        finally:
            conn.close()
    except CorreosError as exc:
        logger.error("Proceso detenido: %s", exc)
        return 1

    return 0 if estado == ESTADO_OK else 1


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
