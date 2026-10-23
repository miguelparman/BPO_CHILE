"""Cliente minimo de la API REST de Power BI (v1.0/myorg) con 'requests'.

Endpoints usados (todos de lectura):
    GET /groups                                          workspaces visibles para la app
    GET /groups/{ws}/datasets                            modelos semanticos (datasets)
    GET /groups/{ws}/reports                             informes (y su dataset)
    GET /groups/{ws}/datasets/{ds}/refreshes?$top=N      historial de actualizaciones
    GET /groups/{ws}/datasets/{ds}/refreshSchedule       programacion (dias, horas, zona)

- El token se renueva solo cuando esta por vencer (o ante un 401).
- 429 (throttling) y 5xx se reintentan respetando 'Retry-After'.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from config import PowerBISettings
from exceptions import PowerBIApiError
from logging_setup import NOMBRE_LOGGER
from powerbi.auth import get_powerbi_token

logger = logging.getLogger(NOMBRE_LOGGER)

API_BASE = "https://api.powerbi.com/v1.0/myorg"
_MARGEN_TOKEN_S = 300  # renovar 5 min antes de que venza
_REINTENTOS_HTTP = 5
_ESPERA_DEFECTO_S = 30
_TOP_WORKSPACES = 5000


class PowerBIClient:
    def __init__(
        self,
        settings: PowerBISettings,
        session: requests.Session | None = None,
        obtener_token: Callable[..., tuple[str, int]] = get_powerbi_token,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._obtener_token = obtener_token
        self._dormir = dormir
        self._reloj = reloj
        self._token: str | None = None
        self._vence: float = 0.0

    # --- autenticacion -------------------------------------------------------
    def _cabeceras(self, forzar: bool = False) -> dict[str, str]:
        if forzar or self._token is None or self._reloj() >= self._vence:
            s = self._settings
            token, vigencia = self._obtener_token(s.tenant_id, s.client_id, s.client_secret, s.timeout_s)
            self._token = token
            self._vence = self._reloj() + max(vigencia - _MARGEN_TOKEN_S, 60)
        return {"Authorization": f"Bearer {self._token}"}

    # --- HTTP ----------------------------------------------------------------
    def _get(self, ruta: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{API_BASE}{ruta}"
        token_renovado = False
        for intento in range(_REINTENTOS_HTTP + 1):
            try:
                resp = self._session.get(
                    url, headers=self._cabeceras(), params=params, timeout=self._settings.timeout_s
                )
            except requests.RequestException as exc:
                if intento >= _REINTENTOS_HTTP:
                    raise PowerBIApiError(f"GET {ruta}: {exc}") from exc
                logger.warning("GET %s fallo (%s); reintento en %s s.", ruta, exc, _ESPERA_DEFECTO_S)
                self._dormir(_ESPERA_DEFECTO_S)
                continue

            if resp.status_code == 401 and not token_renovado:
                self._cabeceras(forzar=True)
                token_renovado = True
                continue
            if (resp.status_code == 429 or resp.status_code >= 500) and intento < _REINTENTOS_HTTP:
                espera = _retry_after(resp)
                logger.warning("GET %s -> HTTP %s; reintento en %s s.", ruta, resp.status_code, espera)
                self._dormir(espera)
                continue
            if not resp.ok:
                raise PowerBIApiError(f"GET {ruta} -> HTTP {resp.status_code}: {_mensaje(resp)}", resp.status_code)
            return resp.json()
        raise PowerBIApiError(f"GET {ruta}: sin respuesta valida tras {_REINTENTOS_HTTP} reintentos")

    # --- endpoints -----------------------------------------------------------
    def ping(self) -> None:
        """Token + una llamada minima (validacion de conexiones)."""
        self._get("/groups", {"$top": 1})

    def workspaces(self) -> list[dict]:
        """Workspaces donde la app es miembro (paginado con $top/$skip)."""
        resultado: list[dict] = []
        while True:
            pagina = self._get("/groups", {"$top": _TOP_WORKSPACES, "$skip": len(resultado)}).get("value", [])
            resultado.extend(pagina)
            if len(pagina) < _TOP_WORKSPACES:
                return resultado

    def datasets(self, workspace_id: str) -> list[dict]:
        return self._get(f"/groups/{workspace_id}/datasets").get("value", [])

    def informes(self, workspace_id: str) -> list[dict]:
        return self._get(f"/groups/{workspace_id}/reports").get("value", [])

    def actualizaciones(self, workspace_id: str, dataset_id: str, top: int) -> list[dict]:
        return self._get(f"/groups/{workspace_id}/datasets/{dataset_id}/refreshes", {"$top": top}).get("value", [])

    def programacion(self, workspace_id: str, dataset_id: str) -> dict:
        """{days, times, enabled, localTimeZoneId, notifyOption}; las mismas horas aplican a todos los dias."""
        return self._get(f"/groups/{workspace_id}/datasets/{dataset_id}/refreshSchedule")


def _retry_after(resp: requests.Response) -> float:
    try:
        return max(float(resp.headers.get("Retry-After", _ESPERA_DEFECTO_S)), 1.0)
    except ValueError:
        return _ESPERA_DEFECTO_S


def _mensaje(resp: requests.Response) -> str:
    try:
        error = resp.json().get("error", {})
        return error.get("message") or error.get("code") or resp.text[:200]
    except ValueError:
        return resp.text[:200] or resp.reason
