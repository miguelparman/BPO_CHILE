"""Analisis de cruces entre actualizaciones (todo en ZONA_HORARIA, sobre los
ultimos DIAS_ANALISIS dias del historico):

  Programacion        cada informe/dataset y hora programada, con la duracion
                      real de las ejecuciones de ESE horario (mediana, p90, max),
                      el retraso de inicio y el % de fallos.
  Mapa_cruces         bloques de 15 min x dia: cuantos datasets estarian
                      actualizandose a la vez segun programacion + duracion p90.
  Cruces              detalle de los bloques con 2 o mas datasets a la vez.
  Concurrencia_hora   segun el historial REAL: por hora de inicio, ejecuciones,
                      fallos y cuantas otras actualizaciones corrian en paralelo.
  Fallos              cada actualizacion fallida y con quienes se cruzo.

Asignacion ejecucion -> horario: una actualizacion 'Scheduled' pertenece al
horario programado (en la zona de la programacion) que la precede por menos
de VENTANA_ASIGNACION_MIN (Power BI inicia en promedio ~1 min tarde, mediana
maxima observada 4 min; se toleran TOLERANCIA_ANTES_MIN de adelanto). La
ventana es corta a proposito: si se cambia un horario (08:00 -> 07:30), las
ejecuciones antiguas de las 08:00 no deben contarse como 'retraso' del nuevo.

Duracion: la de las ejecuciones de ese horario; si el horario aun no tiene
(p.ej. recien creado), la de todas las ejecuciones programadas del dataset
(BASE_DURACION indica cual se uso).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from zonas import DIAS_ES

TOLERANCIA_ANTES_MIN = 5
VENTANA_ASIGNACION_MIN = 15
BLOQUE_MIN = 15
DURACION_SIN_HISTORIAL_MIN = 5  # para el mapa, si un horario no tiene ejecuciones registradas
_MIN_DIA = 24 * 60
_MIN_SEMANA = 7 * _MIN_DIA
_BLOQUES_DIA = _MIN_DIA // BLOQUE_MIN
ESTADOS_FALLO = ("Failed", "Cancelled")

COLUMNAS_PROGRAMACION = [
    "WORKSPACE", "INFORME", "DATASET", "HABILITADA", "HORA_LOCAL", "DIAS_LOCAL",
    "DURACION_MEDIANA_MIN", "DURACION_P90_MIN", "DURACION_MAX_MIN", "BASE_DURACION", "RETRASO_INICIO_MEDIANO_MIN",
    "INICIO_REAL_ESTIMADO", "FIN_ESTIMADO", "N_EJECUCIONES", "N_FALLIDAS", "PCT_FALLO",
    "HORA_ORIGEN", "DIAS_ORIGEN", "ZONA_ORIGEN", "NOTA", "DATASET_ID",
]
COLUMNAS_CRUCES = ["BLOQUE", "N_DATASETS", "DIAS", "INFORMES"]
COLUMNAS_CONCURRENCIA = [
    "HORA", "EJECUCIONES", "FALLIDAS", "PCT_FALLO", "CONCURRENCIA_MEDIA", "CONCURRENCIA_MAX", "DURACION_MEDIANA_MIN",
]
COLUMNAS_FALLOS = [
    "INICIO_LOCAL", "FIN_LOCAL", "INFORME", "DATASET", "TIPO", "ESTADO", "DURACION_MIN", "ERROR_CODIGO",
    "N_CONCURRENTES", "CONCURRENTES", "ERROR_DETALLE",
]


def _minutos(hhmm: str) -> int:
    hora, minuto = (int(x) for x in hhmm.split(":"))
    return hora * 60 + minuto


def _hhmm(minutos: float) -> str:
    minutos = int(round(minutos)) % _MIN_DIA
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _etiqueta(fila) -> str:
    informe, dataset = fila.get("INFORME"), fila.get("DATASET")
    return informe if isinstance(informe, str) and informe else str(dataset)


def ventana(historico: pd.DataFrame, dias: int, ahora_utc: datetime) -> pd.DataFrame:
    return historico[historico["INICIO_UTC"] >= pd.Timestamp(ahora_utc - timedelta(days=dias))]


def asignar_a_horario(programacion: pd.DataFrame, historico: pd.DataFrame) -> pd.DataFrame:
    """Actualizaciones 'Scheduled' con HORA_ORIGEN (horario al que pertenecen) y RETRASO_MIN."""
    horarios: dict[str, list[tuple[str, int, list[int], str]]] = {}
    for p in programacion.to_dict("records"):
        if isinstance(p["HORA_ORIGEN"], str) and p["_ZONA_IANA"] and p["_DIAS_IDX_ORIGEN"]:
            horarios.setdefault(p["DATASET_ID"], []).append(
                (p["HORA_ORIGEN"], _minutos(p["HORA_ORIGEN"]), p["_DIAS_IDX_ORIGEN"], p["_ZONA_IANA"])
            )

    programadas = historico[(historico["TIPO"] == "Scheduled") & historico["INICIO_UTC"].notna()]
    indices, horas, retrasos = [], [], []
    for idx, fila in programadas.iterrows():
        candidatos = horarios.get(fila["DATASET_ID"])
        if not candidatos:
            continue
        inicio = pd.Timestamp(fila["INICIO_UTC"]).tz_localize("UTC").tz_convert(candidatos[0][3])
        minuto_semana = inicio.weekday() * _MIN_DIA + inicio.hour * 60 + inicio.minute + inicio.second / 60
        mejor = None
        for hora, minuto, dias, _ in candidatos:
            for dia in dias:
                retraso = (minuto_semana - (dia * _MIN_DIA + minuto)) % _MIN_SEMANA
                if retraso > _MIN_SEMANA - TOLERANCIA_ANTES_MIN:
                    retraso -= _MIN_SEMANA
                if retraso <= VENTANA_ASIGNACION_MIN and (mejor is None or abs(retraso) < abs(mejor[1])):
                    mejor = (hora, retraso)
        if mejor:
            indices.append(idx)
            horas.append(mejor[0])
            retrasos.append(round(mejor[1], 1))
    return programadas.loc[indices].assign(HORA_ORIGEN=horas, RETRASO_MIN=retrasos)


def _duraciones(g: pd.DataFrame) -> dict:
    ok = g.loc[g["ESTADO"] == "Completed", "DURACION_MIN"].dropna()
    if not len(ok):
        return {}
    return {
        "DURACION_MEDIANA_MIN": round(ok.median(), 1),
        "DURACION_P90_MIN": round(ok.quantile(0.9), 1),
        "DURACION_MAX_MIN": round(ok.max(), 1),
    }


def _estadisticas_por_horario(asignadas: pd.DataFrame) -> pd.DataFrame:
    if asignadas.empty:
        return pd.DataFrame(columns=["DATASET_ID", "HORA_ORIGEN"])
    filas = []
    for (dsid, hora), g in asignadas.groupby(["DATASET_ID", "HORA_ORIGEN"]):
        fallidas = int(g["ESTADO"].isin(ESTADOS_FALLO).sum())
        filas.append(
            {
                "DATASET_ID": dsid,
                "HORA_ORIGEN": hora,
                "N_EJECUCIONES": len(g),
                "N_FALLIDAS": fallidas,
                "PCT_FALLO": round(100 * fallidas / len(g), 1),
                "RETRASO_INICIO_MEDIANO_MIN": round(g["RETRASO_MIN"].median(), 1),
                **_duraciones(g),
            }
        )
    return pd.DataFrame(filas)


def _duraciones_por_dataset(historico: pd.DataFrame) -> dict[str, dict]:
    programadas = historico[historico["TIPO"] == "Scheduled"]
    return {dsid: _duraciones(g) for dsid, g in programadas.groupby("DATASET_ID")}


def _duracion_mapa(fila) -> float:
    for col in ("DURACION_P90_MIN", "DURACION_MEDIANA_MIN"):
        if pd.notna(fila.get(col)):
            return max(float(fila[col]), 1.0)
    return DURACION_SIN_HISTORIAL_MIN


def tabla_programacion(programacion: pd.DataFrame, asignadas: pd.DataFrame, historico: pd.DataFrame) -> pd.DataFrame:
    df = programacion.merge(_estadisticas_por_horario(asignadas), on=["DATASET_ID", "HORA_ORIGEN"], how="left")
    df = df.reindex(columns=list(df.columns) + [c for c in COLUMNAS_PROGRAMACION if c not in df.columns])
    por_dataset = _duraciones_por_dataset(historico)
    df["BASE_DURACION"] = df["DURACION_MEDIANA_MIN"].notna().map({True: "horario", False: None})
    for i, fila in df[df["DURACION_MEDIANA_MIN"].isna() & df["HORA_LOCAL"].notna()].iterrows():
        duraciones = por_dataset.get(fila["DATASET_ID"])
        if duraciones:
            for col, valor in duraciones.items():
                df.at[i, col] = valor
            df.at[i, "BASE_DURACION"] = "dataset (horario sin ejecuciones)"
        else:
            df.at[i, "BASE_DURACION"] = f"sin historial (se asumen {DURACION_SIN_HISTORIAL_MIN} min)"
    inicio, fin = [], []
    for _, fila in df.iterrows():
        if not isinstance(fila["HORA_LOCAL"], str):
            inicio.append(None)
            fin.append(None)
            continue
        retraso = fila.get("RETRASO_INICIO_MEDIANO_MIN")
        arranque = _minutos(fila["HORA_LOCAL"]) + (max(retraso, 0) if pd.notna(retraso) else 0)
        inicio.append(_hhmm(arranque))
        fin.append(_hhmm(arranque + _duracion_mapa(fila)) if pd.notna(fila.get("DURACION_MEDIANA_MIN")) else None)
    df["INICIO_REAL_ESTIMADO"], df["FIN_ESTIMADO"] = inicio, fin
    for col in ("N_EJECUCIONES", "N_FALLIDAS"):
        df[col] = df[col].fillna(0).astype(int)
    columnas = COLUMNAS_PROGRAMACION + [c for c in programacion.columns if c.startswith("_")]
    return df.reindex(columns=columnas).sort_values(["HORA_LOCAL", "INFORME", "DATASET"], na_position="last",
                                                    ignore_index=True)


def ocupacion(programacion: pd.DataFrame) -> list[set[str]]:
    """Por bloque de 15 min de la semana (lunes 00:00 = 0): datasets que estarian
    actualizandose (desde hora + retraso mediano, durante la duracion p90)."""
    bloques: list[set[str]] = [set() for _ in range(7 * _BLOQUES_DIA)]
    for _, fila in programacion.iterrows():
        if fila["HABILITADA"] is not True or not isinstance(fila["HORA_LOCAL"], str):
            continue
        retraso = fila.get("RETRASO_INICIO_MEDIANO_MIN")
        inicio_dia = _minutos(fila["HORA_LOCAL"]) + (max(retraso, 0) if pd.notna(retraso) else 0)
        duracion = _duracion_mapa(fila)
        for dia in fila["_DIAS_IDX_LOCAL"]:
            inicio = dia * _MIN_DIA + inicio_dia
            for b in range(math.floor(inicio / BLOQUE_MIN), math.ceil((inicio + duracion) / BLOQUE_MIN)):
                bloques[b % len(bloques)].add(_etiqueta(fila))
    return bloques


def _bloque(b: int) -> str:
    inicio = (b % _BLOQUES_DIA) * BLOQUE_MIN
    return f"{_hhmm(inicio)}-{_hhmm(inicio + BLOQUE_MIN)}"


def tabla_mapa(bloques: list[set[str]]) -> pd.DataFrame:
    filas = []
    for b in range(_BLOQUES_DIA):
        fila = {"BLOQUE": _bloque(b)}
        fila.update({DIAS_ES[d]: len(bloques[d * _BLOQUES_DIA + b]) for d in range(7)})
        filas.append(fila)
    return pd.DataFrame(filas, columns=["BLOQUE"] + DIAS_ES)


def tabla_cruces(bloques: list[set[str]]) -> pd.DataFrame:
    """Bloques con 2+ datasets; mismos datasets en el mismo bloque se agrupan por dias."""
    grupos: dict[tuple[int, tuple[str, ...]], list[int]] = {}
    for b, nombres in enumerate(bloques):
        if len(nombres) >= 2:
            grupos.setdefault((b % _BLOQUES_DIA, tuple(sorted(nombres))), []).append(b // _BLOQUES_DIA)
    filas = [
        {"BLOQUE": _bloque(b), "N_DATASETS": len(nombres), "DIAS": ", ".join(DIAS_ES[d] for d in dias),
         "INFORMES": " | ".join(nombres)}
        for (b, nombres), dias in sorted(grupos.items())
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_CRUCES)


def concurrencia_real(historico: pd.DataFrame) -> pd.DataFrame:
    """Actualizaciones con inicio y fin + N_CONCURRENTES / CONCURRENTES (otras que
    se superpusieron en el tiempo, de cualquier tipo)."""
    df = historico.dropna(subset=["INICIO_UTC", "FIN_UTC"]).reset_index(drop=True)
    inicios, fines = df["INICIO_UTC"].to_numpy(), df["FIN_UTC"].to_numpy()
    etiquetas = [_etiqueta(f) for f in df.to_dict("records")]
    n, nombres = [], []
    for i in range(len(df)):
        solapadas = (inicios < fines[i]) & (fines > inicios[i])
        solapadas[i] = False
        otros = sorted({etiquetas[j] for j in solapadas.nonzero()[0]})
        n.append(int(solapadas.sum()))
        nombres.append(" | ".join(otros) or None)
    return df.assign(N_CONCURRENTES=n, CONCURRENTES=nombres)


def tabla_concurrencia_hora(concurrentes: pd.DataFrame) -> pd.DataFrame:
    if concurrentes.empty:
        return pd.DataFrame(columns=COLUMNAS_CONCURRENCIA)
    filas = []
    for hora, g in concurrentes.groupby(concurrentes["INICIO_LOCAL"].dt.hour):
        fallidas = int(g["ESTADO"].isin(ESTADOS_FALLO).sum())
        filas.append(
            {
                "HORA": f"{hora:02d}:00",
                "EJECUCIONES": len(g),
                "FALLIDAS": fallidas,
                "PCT_FALLO": round(100 * fallidas / len(g), 1),
                "CONCURRENCIA_MEDIA": round(g["N_CONCURRENTES"].mean(), 1),
                "CONCURRENCIA_MAX": int(g["N_CONCURRENTES"].max()),
                "DURACION_MEDIANA_MIN": round(g["DURACION_MIN"].median(), 1),
            }
        )
    return pd.DataFrame(filas, columns=COLUMNAS_CONCURRENCIA)


def tabla_fallos(concurrentes: pd.DataFrame) -> pd.DataFrame:
    fallos = concurrentes[concurrentes["ESTADO"].isin(ESTADOS_FALLO)]
    return fallos.reindex(columns=COLUMNAS_FALLOS).sort_values("INICIO_LOCAL", ascending=False, ignore_index=True)


def analizar(
    programacion: pd.DataFrame, historico: pd.DataFrame, dias: int, ahora_utc: datetime | None = None
) -> dict[str, pd.DataFrame]:
    """Hojas de analisis. 'historico' son las actualizaciones (tabla del transformer
    o el CSV historico); 'programacion' es Tablas.programacion."""
    ahora_utc = ahora_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    reciente = ventana(historico, dias, ahora_utc)
    prog = tabla_programacion(programacion, asignar_a_horario(programacion, reciente), reciente)
    bloques = ocupacion(prog)
    concurrentes = concurrencia_real(reciente)
    return {
        "Programacion": prog,
        "Mapa_cruces": tabla_mapa(bloques),
        "Cruces": tabla_cruces(bloques),
        "Concurrencia_hora": tabla_concurrencia_hora(concurrentes),
        "Fallos": tabla_fallos(concurrentes),
    }
