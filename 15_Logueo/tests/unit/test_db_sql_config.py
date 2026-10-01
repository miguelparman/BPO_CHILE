from decimal import Decimal

import mappings
import sql
from carga.loader import LogueoLoader
from config import cargar_configuracion
from db import dividir_en_batches


def test_go_separa_batches():
    assert dividir_en_batches("SELECT 1\nGO\nSELECT 2\ngo -- fin\n") == ["SELECT 1", "SELECT 2"]
    assert dividir_en_batches(sql.AGREGA_DNI) == [sql.AGREGA_DNI.strip()]


def test_insert_destino_columnas_y_parametros():
    assert sql.INSERT_DESTINO.startswith("INSERT INTO [dbo].[TBL_CONEXIONES] WITH (TABLOCK) ([FECHA ANSI], [AÑO],")
    assert sql.INSERT_DESTINO.count("?") == len(mappings.COLUMNAS_INSERT) == 46
    assert "[DNI]" not in sql.INSERT_DESTINO


def test_agrega_dni_un_parametro():
    assert sql.AGREGA_DNI.count("?") == 1


class _FakeDb:
    def __init__(self):
        self.llamadas = []

    def execute_autocommit(self, texto, params=None):
        self.llamadas.append((texto, params))
        return 3


def test_loader_pasa_el_periodo_como_numerico():
    db = _FakeDb()
    assert LogueoLoader(db).agregar_dni(202609) == 3
    assert db.llamadas == [(sql.AGREGA_DNI, (Decimal(202609),))]


def test_config_lee_periodo_y_defaults(tmp_path, monkeypatch):
    for k, v in {
        "DB_SERVER": "srv", "DB_USER": "u", "DB_PASSWORD": "p", "TENANT_ID": "t", "CLIENT_ID": "c",
        "CLIENT_SECRET": "s", "SHAREPOINT_SITE_PATH": "/sites/x", "SHAREPOINT_DRIVE_NAME": "Data Reporting",
    }.items():
        monkeypatch.setenv(k, v)
    for k in ("PERIODO", "DB_NAME", "SHAREPOINT_FOLDER_PATH", "LOGUEO_ARCHIVO"):
        monkeypatch.delenv(k, raising=False)
    s = cargar_configuracion(tmp_path)
    assert s.db.database == "CL_LOGUEO"
    assert s.sharepoint.folder_path.endswith("15 PORTAL COMERCIAL")
    assert s.sharepoint.archivo == "REPORTE_AGENTES_FRACTALIA_SEM.csv"
    assert s.periodo_env is None
    monkeypatch.setenv("PERIODO", "202608")
    assert cargar_configuracion(tmp_path).periodo_env == "202608"
