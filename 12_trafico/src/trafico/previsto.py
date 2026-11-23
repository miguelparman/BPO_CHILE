"""Previsto de contactos: CSV 'PVTA_PROYECCION_PPP_FRACTALIA_PERU.csv' -> [CL_DATA].[dbo].[TBL_PREVISTO_CL].

No forma parte del paquete SSIS original (CL_Proc_Trafico_01.dtsx): se agrego al bloque que descarga
los archivos fuente. Este modulo contiene la logica PURA (sin base ni SharePoint): leer/validar el CSV,
transformarlo al modelo de la tabla y decidir que filas se insertan y cuales se reemplazan. La
escritura va en carga/loader.py (cargar_previsto) y el orden de los pasos en pipeline.py.

Modelo de la tabla (CL_DATA.dbo.TBL_PREVISTO_CL, heap sin clave; llave natural Servicio+Fecha+Tramo):
    Servicio nvarchar(50), Fecha date, ID_Tramo nvarchar(50), Tramo time, Tramo_Horario nvarchar(50),
    Prev_Voz decimal(10,4), Prev_Chat decimal(10,4); todas NOT NULL.

Mapeo desde el CSV:
    PCRC        -> Servicio  (solo 'Usuarios Empresa' -> USUARIOS; PYMES CARTERIZADOS y TRIADA NO
                   CARTERIZADO MICRO se ignoran; cualquier otro PCRC detiene la carga)
    FECHA       -> Fecha     (yyyy-MM-dd)
    INTERVALO   -> Tramo     (HH:mm:ss, inicio del tramo de 30 minutos)
    (derivado)  -> ID_Tramo = d/MM/yyyy + HH:mm, SIN separador, dia sin cero inicial (p.ej. '1/09/202600:30',
                   '28/02/202600:30'), igual que el 2025 de la tabla
    (derivado)  -> Tramo_Horario = 'HH:mm-HH:mm' inicio-fin (el ultimo tramo del dia es '23:30-24:00')
    PRONOSTICO  -> Prev_Voz  (coma o punto decimal; antes se evaluo REQUERIDOVOZ, descartado el 2026-11-23)
    (constante) -> Prev_Chat = 0 (el archivo no trae chat)
Las demas columnas del CSV (PRONOSTICOTMO, REQUERIDOVOZ, REQUERIDOCALLBACK, REQUERIDOMULTISKILL,
REQUERIDO, AGENTEPROGRAMADO, AGENTEOJT, PROVEEDOR) no se cargan.

Regla de carga ACUMULATIVA (hoy = fecha de Chile):
    Fecha <= hoy -> solo se INSERTAN las llaves que faltan; lo existente no se toca nunca.
    Fecha  > hoy -> se REEMPLAZAN: se borran las fechas futuras de la tabla y se insertan las del archivo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd

from exceptions import ValidacionError

logger = logging.getLogger("trafico")

ARCHIVO = "PVTA_PROYECCION_PPP_FRACTALIA_PERU.csv"
CARPETA_DEFAULT = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/15 PORTAL COMERCIAL"
TABLA = "TBL_PREVISTO_CL"
ESQUEMA = "dbo"
ZONA_HORARIA = "America/Santiago"

COLUMNAS_REQUERIDAS = ["FECHA", "INTERVALO", "PCRC", "PRONOSTICO"]
# El CSV completo trae 12 columnas; se exige la cabecera completa para detectar cambios de formato.
COLUMNAS_CSV = [
    "FECHA", "INTERVALO", "PCRC", "PROVEEDOR", "PRONOSTICO", "PRONOSTICOTMO", "REQUERIDOVOZ",
    "REQUERIDOCALLBACK", "REQUERIDOMULTISKILL", "REQUERIDO", "AGENTEPROGRAMADO", "AGENTEOJT",
]
COLUMNAS_TABLA = ["Servicio", "Fecha", "ID_Tramo", "Tramo", "Tramo_Horario", "Prev_Voz", "Prev_Chat"]
LLAVE = ["Servicio", "Fecha", "Tramo"]

# PCRC del archivo -> Servicio de la tabla (comparacion sin distinguir mayusculas). Solo se carga USUARIOS.
SERVICIOS = {
    "USUARIOS EMPRESA": "USUARIOS",
    "PLAT USUARIOS EMPRESA": "USUARIOS",  # nombre que trae el archivo de relleno de mar-ago 2026
}
# PCRC conocidos que NO se cargan (decision del usuario, 2026-11-23: el archivo los trae siempre en 0).
# Se descartan sin error; cualquier PCRC que no este ni aqui ni en SERVICIOS detiene la carga.
PCRC_IGNORADOS = {"PYMES CARTERIZADOS", "TRIADA NO CARTERIZADO MICRO"}

TRAMOS_POR_DIA = 48
_MAX_PREV = Decimal("999999.9999")  # decimal(10,4)
_CUATRO_DECIMALES = Decimal("0.0001")


def hoy_chile(ahora: datetime | None = None) -> date:
    """Fecha de hoy en Chile (el servidor y el equipo pueden estar en otra zona horaria)."""
    from zoneinfo import ZoneInfo

    return (ahora or datetime.now(ZoneInfo(ZONA_HORARIA))).date()


# ---------------------------------------------------------------------- #
# Validacion + transformacion
# ---------------------------------------------------------------------- #
def _decimal(texto: str, fila: int) -> Decimal:
    limpio = texto.strip().replace(",", ".")
    try:
        valor = Decimal(limpio)
    except InvalidOperation as exc:
        raise ValidacionError(f"{ARCHIVO}: PRONOSTICO no numerico {texto!r} (fila {fila})") from exc
    if not valor.is_finite() or valor < 0 or valor > _MAX_PREV:
        raise ValidacionError(f"{ARCHIVO}: PRONOSTICO fuera de rango {texto!r} (fila {fila})")
    return valor.quantize(_CUATRO_DECIMALES)


def _tramo(texto: str, fila: int) -> time:
    try:
        t = datetime.strptime(texto.strip(), "%H:%M:%S").time()
    except ValueError as exc:
        raise ValidacionError(f"{ARCHIVO}: INTERVALO invalido {texto!r} (fila {fila}), se espera HH:mm:ss") from exc
    if t.minute not in (0, 30) or t.second != 0:
        raise ValidacionError(f"{ARCHIVO}: INTERVALO {texto!r} fuera de la grilla de 30 minutos (fila {fila})")
    return t


def _fecha(texto: str, fila: int) -> date:
    try:
        return datetime.strptime(texto.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidacionError(f"{ARCHIVO}: FECHA invalida {texto!r} (fila {fila}), se espera yyyy-MM-dd") from exc


def id_tramo(fecha: date, tramo: time) -> str:
    """'d/MM/yyyy' + 'HH:mm' sin separador: dia SIN cero inicial y mes con 2 digitos (p.ej. '1/09/202600:30').
    Es el formato de 2025 en la tabla (ene-nov 2025); dic-2025 a feb-2026 usan dd/MM/yyyy, pero por
    pedido del usuario (2026-11-23) las filas nuevas se homogenizan con el de 2025."""
    return f"{fecha.day}/{fecha:%m/%Y}{tramo:%H:%M}"


def tramo_horario(tramo: time) -> str:
    """'HH:mm-HH:mm'; el ultimo tramo del dia termina en '24:00', como en la tabla."""
    inicio = tramo.hour * 60 + tramo.minute
    fin = inicio + 30
    return f"{tramo:%H:%M}-{fin // 60:02d}:{fin % 60:02d}"


def transformar(crudo: pd.DataFrame) -> pd.DataFrame:
    """Valida el CSV (todo texto) y lo devuelve con las 7 columnas de TBL_PREVISTO_CL.

    Lanza ValidacionError (antes de escribir nada) si: faltan columnas o esta vacio, hay un PCRC
    desconocido, una fecha/intervalo/cantidad invalidos, o una llave Servicio+Fecha+Tramo repetida.
    Un dia con menos de 48 tramos para un servicio NO detiene la carga: se avisa en el log."""
    faltan = [c for c in COLUMNAS_CSV if c not in crudo.columns]
    if faltan:
        raise ValidacionError(f"{ARCHIVO}: faltan las columnas {faltan} (cabecera: {list(crudo.columns)})")
    if crudo.empty:
        raise ValidacionError(f"{ARCHIVO} no trae filas")

    pcrc = crudo["PCRC"].str.strip().str.upper()
    desconocidos = sorted({p for p in crudo["PCRC"] if p.strip().upper() not in set(SERVICIOS) | PCRC_IGNORADOS})
    if desconocidos:
        raise ValidacionError(
            f"{ARCHIVO}: PCRC sin servicio mapeado {desconocidos}; agregarlo a previsto.SERVICIOS o PCRC_IGNORADOS"
        )
    ignoradas = int(pcrc.isin(PCRC_IGNORADOS).sum())
    if ignoradas:
        logger.info("[Previsto] %s filas de PCRC ignorados (%s) no se cargan", ignoradas, sorted(PCRC_IGNORADOS))
    crudo = crudo[pcrc.isin(SERVICIOS)]
    if crudo.empty:
        raise ValidacionError(f"{ARCHIVO} no trae filas de los servicios a cargar {sorted(SERVICIOS.values())}")

    filas = []
    for i, r in enumerate(crudo[["FECHA", "INTERVALO", "PCRC", "PRONOSTICO"]].itertuples(index=False), start=2):
        fecha = _fecha(r.FECHA, i)
        tramo = _tramo(r.INTERVALO, i)
        filas.append(
            (
                SERVICIOS[r.PCRC.strip().upper()],
                fecha,
                id_tramo(fecha, tramo),
                tramo,
                tramo_horario(tramo),
                _decimal(r.PRONOSTICO, i),
                Decimal("0").quantize(_CUATRO_DECIMALES),
            )
        )
    df = pd.DataFrame(filas, columns=COLUMNAS_TABLA, dtype=object)

    repetidas = df.duplicated(subset=LLAVE, keep=False)
    if repetidas.any():
        ejemplo = df.loc[repetidas, LLAVE].head(3).values.tolist()
        raise ValidacionError(
            f"{ARCHIVO}: {int(repetidas.sum())} filas con llave Servicio+Fecha+Tramo repetida (p.ej. {ejemplo})"
        )

    por_dia = df.groupby(["Servicio", "Fecha"]).size()
    incompletos = por_dia[por_dia != TRAMOS_POR_DIA]
    if len(incompletos):
        logger.warning(
            "[Previsto] %s servicio-dia no tienen los %s tramos (p.ej. %s)",
            len(incompletos), TRAMOS_POR_DIA, [(s, f.isoformat(), int(n)) for (s, f), n in incompletos.head(3).items()],
        )
    return df


# ---------------------------------------------------------------------- #
# Plan acumulativo
# ---------------------------------------------------------------------- #
@dataclass
class PlanPrevisto:
    hoy: date
    insertar_pasado: pd.DataFrame  # Fecha <= hoy, llave inexistente en la tabla
    reemplazar_futuro: pd.DataFrame  # Fecha > hoy: sustituyen a las fechas futuras de la tabla
    pasado_existente: int = 0  # filas del archivo (Fecha <= hoy) cuya llave ya estaba: NO se tocan
    pasado_distinto: int = 0  # de las anteriores, cuantas difieren en Prev_Voz del archivo (solo informativo)
    futuro_en_tabla: int = 0  # filas futuras actuales en la tabla que se borran
    detalle: dict = field(default_factory=dict)

    def resumen(self) -> str:
        return (
            f"hoy={self.hoy} | pasado: insertar={len(self.insertar_pasado)}, ya existentes (sin tocar)="
            f"{self.pasado_existente} (con Prev_Voz distinto: {self.pasado_distinto}) | futuro: "
            f"borrar={self.futuro_en_tabla}, insertar={len(self.reemplazar_futuro)}"
        )


def _clave(servicio, fecha, tramo) -> tuple:
    return (str(servicio).strip().upper(), fecha, tramo)


def planificar(archivo: pd.DataFrame, existente: pd.DataFrame, hoy: date, futuro_en_tabla: int = 0) -> PlanPrevisto:
    """Aplica la regla acumulativa. 'existente' = filas de la tabla con Servicio, Fecha, Tramo y
    Prev_Voz (basta el rango de fechas <= hoy del archivo); no se modifica."""
    es_pasado = archivo["Fecha"] <= hoy
    pasado = archivo[es_pasado]
    futuro = archivo[~es_pasado]

    voz_existente = {
        _clave(s, f, t): v for s, f, t, v in existente[["Servicio", "Fecha", "Tramo", "Prev_Voz"]].itertuples(index=False)
    }
    claves = [_clave(s, f, t) for s, f, t in pasado[LLAVE].itertuples(index=False)]
    ya = pd.Series([c in voz_existente for c in claves], index=pasado.index, dtype=bool)
    distintos = sum(
        1 for c, v in zip(claves, pasado["Prev_Voz"]) if c in voz_existente and Decimal(voz_existente[c]) != v
    )
    return PlanPrevisto(
        hoy=hoy,
        insertar_pasado=pasado[~ya].reset_index(drop=True),
        reemplazar_futuro=futuro.reset_index(drop=True),
        pasado_existente=int(ya.sum()),
        pasado_distinto=distintos,
        futuro_en_tabla=futuro_en_tabla,
    )


def siguiente_dia(hoy: date) -> date:
    return hoy + timedelta(days=1)
