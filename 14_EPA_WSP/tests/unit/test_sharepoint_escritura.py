"""Escritura en SharePoint via Graph (upload_file / delete_file / CarpetaSharePoint),
con 'requests' simulado."""

import pytest

from sharepoint import client as cli
from sharepoint.carpeta import CarpetaSharePoint
from sharepoint.client import SharePointClient, SharePointResolutionError


class Resp:
    def __init__(self, status=200, json=None, content=b"{}"):
        self.status_code, self._json, self.content = status, json or {}, content
        self.ok = 200 <= status < 300
        self.text = str(self._json)

    def json(self):
        return self._json


@pytest.fixture
def llamadas(monkeypatch):
    registro = []
    respuestas = {"put": [], "post": [], "delete": [], "get": []}

    def fake(metodo):
        def _f(url, **kw):
            registro.append((metodo, url, kw))
            cola = respuestas[metodo]
            return cola.pop(0) if cola else Resp()
        return _f

    for m in respuestas:
        monkeypatch.setattr(cli.requests, m, fake(m))
    return registro, respuestas


def _carpeta():
    return CarpetaSharePoint(SharePointClient("TOKEN", 1000), "DRIVE", "/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA/")


def test_subida_simple_reemplaza_con_put_content(llamadas):
    registro, _ = llamadas
    _carpeta().escribir("resultado.txt", b"\xef\xbb\xbfhola")
    metodo, url, kw = registro[0]
    assert metodo == "put"
    assert url == (
        "https://graph.microsoft.com/v1.0/drives/DRIVE/root:/"
        "REPOSITORIOS%20DE%20CRUDOS/CHILE/BPOCHIPE/16%20MEDALLIA/resultado.txt:/content"
    )
    assert kw["data"] == b"\xef\xbb\xbfhola" and kw["headers"]["Authorization"] == "Bearer TOKEN"


def test_archivo_grande_usa_sesion_de_carga_por_bloques(llamadas, monkeypatch):
    registro, respuestas = llamadas
    monkeypatch.setattr(cli, "_SIMPLE_UPLOAD_MAX_BYTES", 10)
    monkeypatch.setattr(cli, "_CHUNK_SIZE_BYTES", 8)
    respuestas["post"].append(Resp(json={"uploadUrl": "https://upload/sesion"}))
    _carpeta().escribir("Encuestas_Medallia.csv", b"x" * 20)
    assert registro[0][0] == "post" and registro[0][1].endswith("Encuestas_Medallia.csv:/createUploadSession")
    assert registro[0][2]["json"] == {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    bloques = [(r[2]["headers"]["Content-Range"], len(r[2]["data"])) for r in registro[1:]]
    assert bloques == [("bytes 0-7/20", 8), ("bytes 8-15/20", 8), ("bytes 16-19/20", 4)]
    assert all("Authorization" not in r[2]["headers"] for r in registro[1:])  # URL pre-autenticada


def test_eliminar_devuelve_false_si_no_existia(llamadas):
    _, respuestas = llamadas
    respuestas["delete"] += [Resp(204, content=b""), Resp(404)]
    carpeta = _carpeta()
    assert carpeta.eliminar("resultado.txt") is True
    assert carpeta.eliminar("resultado.txt") is False


def test_error_de_graph_al_escribir(llamadas):
    _, respuestas = llamadas
    respuestas["put"].append(Resp(403, json={"error": {"code": "accessDenied"}}))
    with pytest.raises(SharePointResolutionError, match="403 subiendo"):
        _carpeta().escribir("resultado.txt", b"x")
