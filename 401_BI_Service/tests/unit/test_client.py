import pytest

from config import PowerBISettings
from exceptions import PowerBIApiError
from powerbi import client as modulo
from powerbi.client import PowerBIClient
from tests.unit.fakes import FakeResponse, FakeSession

SETTINGS = PowerBISettings("t", "c", "s", 10)


def _cliente(respuestas, tokens=None):
    tokens = tokens if tokens is not None else []

    def obtener_token(*_):
        tokens.append(1)
        return f"tok{len(tokens)}", 3600

    esperas = []
    sesion = FakeSession(respuestas)
    return PowerBIClient(SETTINGS, sesion, obtener_token, dormir=esperas.append), sesion, esperas


def test_token_se_reutiliza_entre_llamadas():
    tokens = []
    cli, _, _ = _cliente([FakeResponse(json_data={"value": []})] * 2, tokens)
    cli.datasets("ws")
    cli.informes("ws")
    assert len(tokens) == 1


def test_401_renueva_token_una_vez():
    tokens = []
    cli, sesion, _ = _cliente([FakeResponse(401), FakeResponse(json_data={"value": [1]})], tokens)
    assert cli.datasets("ws") == [1]
    assert len(tokens) == 2
    assert sesion.llamadas[1][2]["Authorization"] == "Bearer tok2"


def test_429_respeta_retry_after():
    cli, _, esperas = _cliente([FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(json_data={"value": []})])
    cli.actualizaciones("ws", "ds", 50)
    assert esperas == [7.0]


def test_error_http_levanta_powerbiapierror_con_status():
    cli, _, _ = _cliente([FakeResponse(403, {"error": {"code": "Unauthorized", "message": "sin permiso"}})])
    with pytest.raises(PowerBIApiError) as exc:
        cli.datasets("ws")
    assert exc.value.status_code == 403
    assert "sin permiso" in str(exc.value)


def test_workspaces_pagina_con_skip(monkeypatch):
    monkeypatch.setattr(modulo, "_TOP_WORKSPACES", 2)
    cli, sesion, _ = _cliente(
        [FakeResponse(json_data={"value": [1, 2]}), FakeResponse(json_data={"value": [3]})]
    )
    assert cli.workspaces() == [1, 2, 3]
    assert [p["$skip"] for _, p, _ in sesion.llamadas] == [0, 2]


def test_actualizaciones_envia_top():
    cli, sesion, _ = _cliente([FakeResponse(json_data={"value": []})])
    cli.actualizaciones("ws-1", "ds-1", 25)
    url, params, _ = sesion.llamadas[0]
    assert url.endswith("/groups/ws-1/datasets/ds-1/refreshes")
    assert params == {"$top": 25}
