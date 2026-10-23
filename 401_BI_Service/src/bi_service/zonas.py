"""Zonas horarias de las programaciones de Power BI.

La API de refreshSchedule entrega 'localTimeZoneId' con nombres de Windows
('SA Pacific Standard Time', 'UTC', ...). Cada programacion puede estar en
una zona distinta, asi que para comparar horarios se convierten todas a
ZONA_HORARIA.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DIAS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DIAS_ES = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]

# Zonas de Windows que ofrece Power BI -> IANA (las de la region y Espana).
WINDOWS_A_IANA = {
    "UTC": "UTC",
    "SA Pacific Standard Time": "America/Bogota",  # Lima, Bogota, Quito (UTC-5)
    "Pacific SA Standard Time": "America/Santiago",
    "SA Western Standard Time": "America/La_Paz",
    "SA Eastern Standard Time": "America/Cayenne",
    "Argentina Standard Time": "America/Buenos_Aires",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Venezuela Standard Time": "America/Caracas",
    "Paraguay Standard Time": "America/Asuncion",
    "Montevideo Standard Time": "America/Montevideo",
    "Central America Standard Time": "America/Guatemala",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Pacific Standard Time": "America/Los_Angeles",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Romance Standard Time": "Europe/Madrid",
    "W. Europe Standard Time": "Europe/Berlin",
}


def a_iana(zona_windows: str | None) -> str | None:
    if not zona_windows:
        return None
    return WINDOWS_A_IANA.get(zona_windows)


def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def convertir_horario(
    dia_idx: int, hhmm: str, zona_origen: str, zona_destino: str, semana: date
) -> tuple[int, str]:
    """(dia, 'HH:MM') de una programacion en zona_origen -> (dia, 'HH:MM') en
    zona_destino, usando la semana que empieza en 'semana' (lunes) para
    resolver el horario de verano. El dia puede cambiar al cruzar medianoche."""
    hora, minuto = (int(x) for x in hhmm.split(":"))
    origen = datetime.combine(semana + timedelta(days=dia_idx), datetime.min.time()).replace(
        hour=hora, minute=minuto, tzinfo=ZoneInfo(zona_origen)
    )
    destino = origen.astimezone(ZoneInfo(zona_destino))
    return destino.weekday(), f"{destino:%H:%M}"
