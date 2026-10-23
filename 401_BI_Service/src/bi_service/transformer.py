"""Convierte el Inventario crudo en tablas (DataFrames) listas para el Excel.

- Fechas: la API entrega ISO 8601 en UTC; se dejan columnas *_UTC y *_LOCAL
  (ZONA_HORARIA), ambas sin zona (Excel no soporta datetimes con zona).
- serviceExceptionJson (string JSON) -> ERROR_CODIGO / ERROR_DETALLE.
- Los IDs se manejan como texto para que el merge con el CSV historico no
  dependa del tipo inferido.
- Programacion: una fila por dataset y horario; HORA/DIAS_LOCAL convertidos
  a ZONA_HORARIA (cada programacion puede estar en otra zona, ver zonas.py).
  Las columnas que empiezan con '_' son de uso interno (no van al Excel).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from extractor import Inventario
from zonas import DIAS_EN, DIAS_ES, a_iana, convertir_horario, lunes_de

COLUMNAS_ACTUALIZACIONES = [
    "WORKSPACE", "WORKSPACE_ID", "INFORME", "DATASET", "DATASET_ID", "REFRESH_ID", "REQUEST_ID", "TIPO", "ESTADO",
    "INICIO_UTC", "FIN_UTC", "INICIO_LOCAL", "FIN_LOCAL", "DURACION_MIN", "INTENTOS",
    "ERROR_CODIGO", "ERROR_DETALLE", "CONFIGURADO_POR", "FECHA_EXTRACCION",
]
COLUMNAS_FECHA_ACTUALIZACIONES = ["INICIO_UTC", "FIN_UTC", "INICIO_LOCAL", "FIN_LOCAL", "FECHA_EXTRACCION"]
CLAVE_ACTUALIZACION = ["DATASET_ID", "REQUEST_ID", "REFRESH_ID"]

COLUMNAS_DATASETS = [
    "WORKSPACE", "DATASET", "DATASET_ID", "CONFIGURADO_POR", "ACTUALIZABLE", "MODO_ALMACENAMIENTO", "CREADO_UTC",
    "N_INFORMES", "ULTIMO_ESTADO", "ULTIMO_INICIO_LOCAL", "ULTIMO_FIN_LOCAL", "ULTIMA_DURACION_MIN",
    "ULTIMO_ERROR", "ULTIMO_OK_LOCAL", "URL",
]
COLUMNAS_INFORMES = ["WORKSPACE", "INFORME", "INFORME_ID", "TIPO", "DATASET", "DATASET_ID", "URL"]
COLUMNAS_WORKSPACES = ["WORKSPACE", "WORKSPACE_ID", "TIPO", "CAPACIDAD_DEDICADA", "N_DATASETS", "N_INFORMES"]
COLUMNAS_ERRORES = ["NIVEL", "WORKSPACE", "WORKSPACE_ID", "OBJETO", "HTTP", "DETALLE"]
COLUMNAS_PROGRAMACION = [
    "WORKSPACE", "INFORME", "DATASET", "DATASET_ID", "HABILITADA", "HORA_LOCAL", "DIAS_LOCAL",
    "HORA_ORIGEN", "DIAS_ORIGEN", "ZONA_ORIGEN", "NOTA", "_ZONA_IANA", "_DIAS_IDX_ORIGEN", "_DIAS_IDX_LOCAL",
]


@dataclass
class Tablas:
    actualizaciones: pd.DataFrame
    datasets: pd.DataFrame
    informes: pd.DataFrame
    workspaces: pd.DataFrame
    errores: pd.DataFrame
    programacion: pd.DataFrame


def _utc(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, utc=True, errors="coerce", format="ISO8601")


def _sin_zona(serie: pd.Series, zona: str | None = None) -> pd.Series:
    return (serie.dt.tz_convert(zona) if zona else serie).dt.tz_localize(None)


def _error_servicio(texto: str | None) -> tuple[str | None, str | None]:
    if not texto:
        return None, None
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        return None, str(texto)
    return datos.get("errorCode"), datos.get("errorDescription") or datos.get("message")


def _texto(valor) -> str:
    return "" if valor is None else str(valor)


def informes_por_dataset(inv: Inventario) -> dict[str, str]:
    """{dataset_id: 'Informe A; Informe B'} (un dataset puede alimentar varios informes)."""
    nombres: dict[str, set[str]] = {}
    for r in inv.informes:
        if r.get("datasetId") and r.get("name"):
            nombres.setdefault(r["datasetId"], set()).add(r["name"])
    return {dsid: "; ".join(sorted(n)) for dsid, n in nombres.items()}


def tabla_actualizaciones(inv: Inventario, zona: str, extraido: datetime) -> pd.DataFrame:
    informes = informes_por_dataset(inv)
    filas = []
    for r in inv.actualizaciones:
        ws, ds = r["_workspace"], r["_dataset"]
        codigo, detalle = _error_servicio(r.get("serviceExceptionJson"))
        filas.append(
            {
                "WORKSPACE": ws.get("name"),
                "WORKSPACE_ID": ws.get("id"),
                "INFORME": informes.get(ds.get("id")),
                "DATASET": ds.get("name"),
                "DATASET_ID": ds.get("id"),
                "REFRESH_ID": _texto(r.get("id")),
                "REQUEST_ID": _texto(r.get("requestId")),
                "TIPO": r.get("refreshType"),
                "ESTADO": r.get("status"),
                "INICIO_UTC": r.get("startTime"),
                "FIN_UTC": r.get("endTime"),
                "INTENTOS": len(r.get("refreshAttempts") or []) or None,
                "ERROR_CODIGO": codigo,
                "ERROR_DETALLE": detalle,
                "CONFIGURADO_POR": ds.get("configuredBy"),
            }
        )
    df = pd.DataFrame(filas, columns=COLUMNAS_ACTUALIZACIONES)
    if df.empty:
        return df.astype({c: "datetime64[ns]" for c in COLUMNAS_FECHA_ACTUALIZACIONES})

    inicio, fin = _utc(df["INICIO_UTC"]), _utc(df["FIN_UTC"])
    df["INICIO_UTC"], df["FIN_UTC"] = _sin_zona(inicio), _sin_zona(fin)
    df["INICIO_LOCAL"], df["FIN_LOCAL"] = _sin_zona(inicio, zona), _sin_zona(fin, zona)
    df["DURACION_MIN"] = ((fin - inicio).dt.total_seconds() / 60).round(2)
    df["INTENTOS"] = df["INTENTOS"].astype("Int64")
    df["FECHA_EXTRACCION"] = pd.Timestamp(extraido)
    return df.sort_values("INICIO_UTC", ascending=False, ignore_index=True)


def tabla_datasets(inv: Inventario, actualizaciones: pd.DataFrame) -> pd.DataFrame:
    """Un registro por dataset con su ultima actualizacion y la ultima exitosa."""
    informes_por_ds = pd.Series([r.get("datasetId") for r in inv.informes], dtype="object").value_counts()
    ordenadas = actualizaciones.sort_values("INICIO_UTC", ascending=False)
    ultima = ordenadas.drop_duplicates("DATASET_ID").set_index("DATASET_ID")
    ultimo_ok = ordenadas[ordenadas["ESTADO"] == "Completed"].drop_duplicates("DATASET_ID").set_index("DATASET_ID")

    filas = []
    for ds in inv.datasets:
        dsid = ds.get("id")
        u = ultima.loc[dsid] if dsid in ultima.index else None
        filas.append(
            {
                "WORKSPACE": ds["_workspace"].get("name"),
                "DATASET": ds.get("name"),
                "DATASET_ID": dsid,
                "CONFIGURADO_POR": ds.get("configuredBy"),
                "ACTUALIZABLE": ds.get("isRefreshable"),
                "MODO_ALMACENAMIENTO": ds.get("targetStorageMode"),
                "CREADO_UTC": ds.get("createdDate"),
                "N_INFORMES": int(informes_por_ds.get(dsid, 0)),
                "ULTIMO_ESTADO": None if u is None else u["ESTADO"],
                "ULTIMO_INICIO_LOCAL": None if u is None else u["INICIO_LOCAL"],
                "ULTIMO_FIN_LOCAL": None if u is None else u["FIN_LOCAL"],
                "ULTIMA_DURACION_MIN": None if u is None else u["DURACION_MIN"],
                "ULTIMO_ERROR": None if u is None else u["ERROR_CODIGO"],
                "ULTIMO_OK_LOCAL": ultimo_ok.loc[dsid, "FIN_LOCAL"] if dsid in ultimo_ok.index else None,
                "URL": ds.get("webUrl"),
            }
        )
    df = pd.DataFrame(filas, columns=COLUMNAS_DATASETS)
    df["CREADO_UTC"] = _sin_zona(_utc(df["CREADO_UTC"]))
    for col in ("ULTIMO_INICIO_LOCAL", "ULTIMO_FIN_LOCAL", "ULTIMO_OK_LOCAL"):
        df[col] = pd.to_datetime(df[col])
    return df.sort_values(["WORKSPACE", "DATASET"], ignore_index=True)


def tabla_informes(inv: Inventario) -> pd.DataFrame:
    nombres_ds = {ds.get("id"): ds.get("name") for ds in inv.datasets}
    filas = [
        {
            "WORKSPACE": r["_workspace"].get("name"),
            "INFORME": r.get("name"),
            "INFORME_ID": r.get("id"),
            "TIPO": r.get("reportType"),
            "DATASET": nombres_ds.get(r.get("datasetId")),
            "DATASET_ID": r.get("datasetId"),
            "URL": r.get("webUrl"),
        }
        for r in inv.informes
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_INFORMES).sort_values(["WORKSPACE", "INFORME"], ignore_index=True)


def tabla_workspaces(inv: Inventario) -> pd.DataFrame:
    filas = [
        {
            "WORKSPACE": w.get("name"),
            "WORKSPACE_ID": w.get("id"),
            "TIPO": w.get("type"),
            "CAPACIDAD_DEDICADA": w.get("isOnDedicatedCapacity"),
            "N_DATASETS": sum(1 for d in inv.datasets if d["_workspace"].get("id") == w.get("id")),
            "N_INFORMES": sum(1 for r in inv.informes if r["_workspace"].get("id") == w.get("id")),
        }
        for w in inv.workspaces
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_WORKSPACES).sort_values("WORKSPACE", ignore_index=True)


def tabla_programacion(inv: Inventario, zona: str, semana: date) -> pd.DataFrame:
    """Una fila por dataset y hora programada. Power BI aplica las mismas horas
    a todos los dias marcados; los datasets sin horas quedan con HORA vacia."""
    informes = informes_por_dataset(inv)
    filas = []
    for p in inv.programaciones:
        ws, ds = p["_workspace"], p["_dataset"]
        zona_iana = a_iana(p.get("localTimeZoneId"))
        dias = sorted(DIAS_EN.index(d) for d in p.get("days") or [] if d in DIAS_EN)
        nota = None
        if p.get("localTimeZoneId") and not zona_iana:
            nota = f"Zona no reconocida: {p.get('localTimeZoneId')} (agregarla en zonas.py)"
        for hora in p.get("times") or [None]:
            hora_local, dias_local = None, []
            if hora and dias and zona_iana:
                convertidos = [convertir_horario(d, hora, zona_iana, zona, semana) for d in dias]
                hora_local = convertidos[0][1]
                dias_local = sorted({d for d, _ in convertidos})
            filas.append(
                {
                    "WORKSPACE": ws.get("name"),
                    "INFORME": informes.get(ds.get("id")),
                    "DATASET": ds.get("name"),
                    "DATASET_ID": ds.get("id"),
                    "HABILITADA": p.get("enabled"),
                    "HORA_LOCAL": hora_local,
                    "DIAS_LOCAL": ", ".join(DIAS_ES[d] for d in dias_local) or None,
                    "HORA_ORIGEN": hora,
                    "DIAS_ORIGEN": ", ".join(DIAS_ES[d] for d in dias) or None,
                    "ZONA_ORIGEN": p.get("localTimeZoneId"),
                    "NOTA": nota or (None if hora else "Sin horas programadas"),
                    "_ZONA_IANA": zona_iana,
                    "_DIAS_IDX_ORIGEN": dias,
                    "_DIAS_IDX_LOCAL": dias_local,
                }
            )
    df = pd.DataFrame(filas, columns=COLUMNAS_PROGRAMACION)
    return df.sort_values(["HORA_LOCAL", "DATASET"], na_position="last", ignore_index=True)


def transformar(inv: Inventario, zona: str, extraido: datetime | None = None) -> Tablas:
    extraido = extraido or datetime.now()
    actualizaciones = tabla_actualizaciones(inv, zona, extraido)
    return Tablas(
        actualizaciones=actualizaciones,
        datasets=tabla_datasets(inv, actualizaciones),
        informes=tabla_informes(inv),
        workspaces=tabla_workspaces(inv),
        errores=pd.DataFrame(inv.errores, columns=COLUMNAS_ERRORES),
        programacion=tabla_programacion(inv, zona, lunes_de(extraido.date())),
    )
