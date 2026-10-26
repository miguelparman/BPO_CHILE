from __future__ import annotations

import pyodbc
import pytest

import mappings as m
import sql
from config import DbSettings, cargar_configuracion
from db import crear_conexion, dividir_en_batches, tamanos_parametros
from exceptions import ConfiguracionError


def test_go_separa_batches_solo_en_su_propia_linea():
    assert dividir_en_batches("SELECT 1\r\nGO\r\nSELECT 'GO'\nGO -- fin\n") == ["SELECT 1", "SELECT 'GO'"]


def test_tamanos_parametros_segun_tipo_real():
    esquema = {"a": ("nvarchar", 25), "b": ("nvarchar", -1), "c": ("datetime", None), "d": ("numeric", None), "e": ("varchar", 10)}
    assert tamanos_parametros(list(esquema), esquema) == [
        (pyodbc.SQL_WVARCHAR, 25, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 23, 3),
        (pyodbc.SQL_DECIMAL, 18, 0),
        (pyodbc.SQL_WVARCHAR, 10, 0),
    ]


def test_conexion_usa_el_idioma_de_ssis():
    capturado = {}

    class Conn:
        timeout = None

    def conectar(cadena, autocommit):
        capturado["cadena"] = cadena
        return Conn()

    crear_conexion(DbSettings("srv", "CL_TEMPORALES", "u", "p"), conectar=conectar)
    assert capturado["cadena"].endswith("Language=us_english")
    assert "DATABASE=CL_TEMPORALES" in capturado["cadena"]


def test_insert_en_la_temporal_incluye_columnas_del_cruce():
    assert sql.insert_temporal(m.FLUJO_TEMP_HISTORIAL).startswith(
        "INSERT INTO #TBL_SALESFORCE_HISTORIAL_CASOS ([Número del caso], "
    )
    casos = sql.insert_temporal(m.FLUJO_TEMP_REPORTE_CASOS)
    assert casos.count("?") == len(m.FLUJO_TEMP_REPORTE_CASOS.columnas) + 4
    assert "[Móvil Contacto]) VALUES" in casos


def test_crear_temporal_usa_la_staging_como_molde():
    assert sql.crear_temporal("TBL_SALESFORCE_CASOS") == (
        "DROP TABLE IF EXISTS #TBL_SALESFORCE_CASOS; "
        "SELECT TOP 0 * INTO #TBL_SALESFORCE_CASOS FROM [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_CASOS];"
    )


def test_correccion_comentarios_texto_con_el_tipo_del_destino():
    """El texto de la #temporal de Comentarios se guarda como el varchar del
    destino (Modern_Spanish_CI_AS, cp1252): el MERGE compara lo mismo que
    quedo guardado y deja de reinsertar comentarios con caracteres no cp1252."""
    flujo = m.FLUJO_TEMP_COMENTARIOS
    assert flujo.tipos_temporal == (("Comentarios del caso", "varchar(max) COLLATE Modern_Spanish_CI_AS"),)
    assert sql.crear_temporal(flujo.tabla, flujo.tipos_temporal).endswith(
        " ALTER TABLE #TBL_SALESFORCE_HISTORIAL_COMENTARIOS ALTER COLUMN [Comentarios del caso] "
        "varchar(max) COLLATE Modern_Spanish_CI_AS NULL;"
    )
    assert all(not f.tipos_temporal for f in m.TODOS_LOS_FLUJOS if f is not flujo)


def test_a_temporal_redirige_solo_las_staging_reemplazadas():
    merge = sql.leer("p03", "30_carga_correos.sql")
    assert "[CL_TEMPORALES].[dbo].[TBL_SALESFORCE_REPORTE_CORREOS]X0" in merge  # alias pegado en el .dtsx
    assert "#TBL_SALESFORCE_REPORTE_CORREOS X0" in sql.a_temporal(merge)
    truncate_nc = sql.leer("p06", "50_truncate_temporal_descripciones_nc.sql")
    assert sql.a_temporal(truncate_nc) == truncate_nc  # TBL_DESCRIPCIONES_NC sigue permanente (SP_FOLIOS_NC)
    for tabla in m.TABLAS_TEMPORALES:
        assert tabla != m.TABLA_DESCRIPCIONES_NC


def test_configuracion_desde_env(tmp_path, monkeypatch):
    for k in ("DB_SERVER", "DB_USER", "DB_PASSWORD", "TENANT_ID", "CLIENT_ID", "CLIENT_SECRET", "SHAREPOINT_SITE_PATH", "SHAREPOINT_DRIVE_NAME"):
        monkeypatch.setenv(k, "x")
    for k in ("DB_NAME", "DB_LANGUAGE", "SHAREPOINT_FOLDER_SEGUIMIENTO", "SHAREPOINT_FOLDER_AUXILIARES"):
        monkeypatch.delenv(k, raising=False)
    s = cargar_configuracion(tmp_path)
    assert s.db.database == "CL_TEMPORALES" and s.db.language == "us_english"
    assert s.sharepoint.carpetas[m.CARPETA_SEGUIMIENTO].endswith("01 SEGUIMIENTO")
    assert s.sharepoint.carpetas[m.CARPETA_AUXILIARES].endswith("12 AUXILIARES")
    assert (s.reintentos_conexion, s.espera_reintento_s) == (3, 300)
    monkeypatch.delenv("DB_PASSWORD")
    with pytest.raises(ConfiguracionError):
        cargar_configuracion(tmp_path)
