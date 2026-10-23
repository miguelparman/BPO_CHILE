"""Dobles de prueba: cliente Power BI en memoria y respuestas HTTP falsas."""

from __future__ import annotations

from exceptions import PowerBIApiError

WS_VENTAS = {"id": "ws-1", "name": "Ventas", "type": "Workspace", "isOnDedicatedCapacity": False}
WS_RRHH = {"id": "ws-2", "name": "RRHH", "type": "Workspace", "isOnDedicatedCapacity": False}

DS_VENTAS = {
    "id": "ds-1", "name": "Modelo Ventas", "configuredBy": "Repositorio.bi@fractaliasystems.es",
    "isRefreshable": True, "targetStorageMode": "Abf", "createdDate": "2026-01-10T12:00:00.000Z",
    "webUrl": "https://app.powerbi.com/groups/ws-1/datasets/ds-1",
}
DS_DIRECTQUERY = {"id": "ds-2", "name": "Modelo DQ", "isRefreshable": False}
DS_RRHH = {"id": "ds-3", "name": "Modelo RRHH", "isRefreshable": True}

REFRESH_OK = {
    "id": 101, "requestId": "req-ok", "refreshType": "Scheduled", "status": "Completed",
    "startTime": "2026-10-21T10:00:00Z", "endTime": "2026-10-21T10:05:30Z",
    "refreshAttempts": [{"attemptId": 1}],
}
REFRESH_FALLO = {
    "id": 102, "requestId": "req-fallo", "refreshType": "Scheduled", "status": "Failed",
    "startTime": "2026-10-22T10:00:00Z", "endTime": "2026-10-22T10:01:00Z",
    "serviceExceptionJson": '{"errorCode":"ModelRefresh_ShortMessage_CredentialsNotSpecified","errorDescription":"x"}',
    "refreshAttempts": [{"attemptId": 1}, {"attemptId": 2}],
}

# Horas en la zona de cada programacion (como las devuelve la API).
PROGRAMACIONES = {
    "ds-1": {"days": ["Wednesday", "Thursday"], "times": ["05:00", "10:00"], "enabled": True,
             "localTimeZoneId": "SA Pacific Standard Time"},
    "ds-3": {"days": ["Wednesday"], "times": ["15:00"], "enabled": True, "localTimeZoneId": "UTC"},
}


class FakeCliente:
    def __init__(self, sin_acceso: set[str] | None = None) -> None:
        self.sin_acceso = sin_acceso or set()  # ids de dataset/workspace que devuelven 403
        self.llamadas_refresh: list[str] = []

    def workspaces(self):
        return [WS_VENTAS, WS_RRHH]

    def datasets(self, workspace_id):
        if workspace_id in self.sin_acceso:
            raise PowerBIApiError("forbidden", 403)
        return {"ws-1": [DS_VENTAS, DS_DIRECTQUERY], "ws-2": [DS_RRHH]}[workspace_id]

    def informes(self, workspace_id):
        return {"ws-1": [{"id": "r-1", "name": "Informe Ventas", "datasetId": "ds-1", "reportType": "PowerBIReport"}],
                "ws-2": []}[workspace_id]

    def actualizaciones(self, workspace_id, dataset_id, top):
        self.llamadas_refresh.append(dataset_id)
        if dataset_id in self.sin_acceso:
            raise PowerBIApiError("forbidden", 403)
        return {"ds-1": [REFRESH_OK, REFRESH_FALLO], "ds-3": []}[dataset_id]

    def programacion(self, workspace_id, dataset_id):
        return PROGRAMACIONES[dataset_id]


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.text = str(self._json)
        self.reason = ""

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.llamadas.append((url, dict(params or {}), headers))
        return self.respuestas.pop(0)
