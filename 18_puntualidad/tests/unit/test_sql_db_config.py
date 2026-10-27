import pytest

import sql
from config import cargar_configuracion
from db import dividir_en_batches
from exceptions import ConfiguracionError
from mappings import COLUMNAS, FECHA_DESDE_DEFAULT, MODO_PRODUCCION, MODO_PRUEBA, destino_para


def test_destinos():
    p, r = destino_para(MODO_PRUEBA), destino_para(MODO_PRODUCCION)
    assert p.tbl_sla == "[CL_ANALISIS].[dbo].[TBL_SLA_PY]"
    assert p.tbl_puntualidad == "[CL_MOVIL].[dbo].[TBL_PUNTUALIDAD_PY]"
    assert r.tbl_sla == "[CL_ANALISIS].[dbo].[TBL_SLA]"
    assert r.tbl_puntualidad == "[CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]"
    with pytest.raises(ValueError):
        destino_para("otro")


def test_dividir_en_batches_go():
    assert dividir_en_batches("A\nGO\nB\n  go  \nC\nGO") == ["A", "B", "C"]
    assert dividir_en_batches("SELECT 'GO'") == ["SELECT 'GO'"]


@pytest.mark.parametrize("modo", [MODO_PRUEBA, MODO_PRODUCCION])
def test_scripts_puntualidad_sin_marcas_y_apuntan_al_destino(modo):
    destino = destino_para(modo)
    scripts = sql.scripts_puntualidad(destino)
    assert len(scripts) == len(sql.ARCHIVOS_PUNTUALIDAD)
    texto = "\n".join(scripts)
    assert "{{" not in texto
    assert destino.tbl_puntualidad in texto and destino.tbl_sla in texto and destino.fuente in texto


def test_scripts_puntualidad_no_llaman_las_funciones_escalares():
    # La optimizacion consiste en NO usar las funciones con WHILE fila por fila
    texto = "\n".join(sql.scripts_puntualidad(destino_para(MODO_PRUEBA)))
    codigo = "\n".join(linea for linea in texto.splitlines() if not linea.strip().startswith("--"))
    assert "SERVICIOS_GENERALES" not in codigo
    assert "FUNC_CH_" not in codigo


def test_scripts_sla_redirigen_solo_el_nombre_de_la_tabla():
    prueba, real = destino_para(MODO_PRUEBA), destino_para(MODO_PRODUCCION)
    antes_real = sql.scripts_antes_sla(real)
    assert len(antes_real) == 2 and antes_real[-1] == "TRUNCATE TABLE [CL_ANALISIS].[dbo].[TBL_SLA]"
    assert "ALTER TABLE [CL_ANALISIS].[dbo].[TBL_SLA] ALTER COLUMN [SLA] DECIMAL(10,2) NULL" in antes_real[0]
    antes = sql.scripts_antes_sla(prueba)
    assert len(antes) == 3 and antes[-1] == "TRUNCATE TABLE [CL_ANALISIS].[dbo].[TBL_SLA_PY]"
    assert "SELECT TOP 0 * INTO [CL_ANALISIS].[dbo].[TBL_SLA_PY] FROM [CL_ANALISIS].[dbo].[TBL_SLA]" in antes[0]
    assert "ALTER TABLE [CL_ANALISIS].[dbo].[TBL_SLA_PY] ALTER COLUMN [SLA] DECIMAL(10,2) NULL" in antes[1]
    assert "[TBL_SLA_PY]" in sql.script_despues_sla(prueba)
    assert "[TBL_SLA_PY]" not in sql.script_despues_sla(real)


def test_insert_sla_en_el_orden_del_destino():
    destino = destino_para(MODO_PRUEBA)
    columnas = tuple(c.destino for c in COLUMNAS)
    consulta = sql.insert_sla(destino, columnas)
    assert consulta.startswith("INSERT INTO [CL_ANALISIS].[dbo].[TBL_SLA_PY] ([Tipología], [Día/Hora], [SLA]")
    assert consulta.count("?") == len(columnas) == 8


def test_marca_sin_reemplazar_falla():
    with pytest.raises(ValueError):
        sql.con_marcas("SELECT {{OTRA}}", destino_para(MODO_PRUEBA))


def test_config_exige_variables_obligatorias(tmp_path, monkeypatch):
    obligatorias = (
        "DB_SERVER", "DB_USER", "DB_PASSWORD", "TENANT_ID", "CLIENT_ID", "CLIENT_SECRET",
        "SHAREPOINT_SITE_PATH", "SHAREPOINT_DRIVE_NAME",
    )
    for k in obligatorias:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ConfiguracionError, match="DB_SERVER"):
        cargar_configuracion(tmp_path)


def test_config_valores_por_defecto(tmp_path, monkeypatch):
    valores = dict(
        DB_SERVER="s", DB_USER="u", DB_PASSWORD="p", TENANT_ID="t", CLIENT_ID="c", CLIENT_SECRET="x",
        SHAREPOINT_SITE_PATH="/sites/S", SHAREPOINT_DRIVE_NAME="D",
    )
    for k, v in valores.items():
        monkeypatch.setenv(k, v)
    for k in ("DB_NAME", "SHAREPOINT_FOLDER_PUNTUALIDAD", "SHAREPOINT_FILE_SLA", "SHEET_SLA", "DB_LANGUAGE"):
        monkeypatch.delenv(k, raising=False)
    s = cargar_configuracion(tmp_path)
    assert s.db.database == "CL_MOVIL" and s.db.language == "us_english"
    assert s.sharepoint.ruta_archivo == "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/08 PUNTUALIDAD/DB.xlsx"
    assert s.sharepoint.hoja == "SLA - Carterizado"


def test_vistas_sla_en_linea_tienen_desempate_determinista():
    # ROW_NUMBER() de VIEW_SLA_4TIP/3TIP/1TIP no tiene desempate: se fija 'Vigente' primero (ver docs/EQUIVALENCIA.md)
    base = sql.scripts_puntualidad(destino_para(MODO_PRUEBA))[1]  # 20_base.sql con las vistas SLA en linea
    assert base.count("CASE WHEN [Estado] = 'Vigente' THEN 0 ELSE 1 END) [") == 3


# ---------------------------- FECHA_DESDE ---------------------------------- #
def _entorno_minimo(monkeypatch):
    valores = dict(
        DB_SERVER="s", DB_USER="u", DB_PASSWORD="p", TENANT_ID="t", CLIENT_ID="c", CLIENT_SECRET="x",
        SHAREPOINT_SITE_PATH="/sites/S", SHAREPOINT_DRIVE_NAME="D",
    )
    for k, v in valores.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("FECHA_DESDE", raising=False)


def test_fecha_desde_por_defecto_es_la_del_dtsx(tmp_path, monkeypatch):
    _entorno_minimo(monkeypatch)
    assert FECHA_DESDE_DEFAULT == "2025-08-01"
    assert cargar_configuracion(tmp_path).fecha_desde == "2025-08-01"


def test_fecha_desde_se_lee_del_env(tmp_path, monkeypatch):
    _entorno_minimo(monkeypatch)
    monkeypatch.setenv("FECHA_DESDE", " 2026-01-15 ")
    assert cargar_configuracion(tmp_path).fecha_desde == "2026-01-15"


@pytest.mark.parametrize("valor", ["15/01/2026", "2026-13-01", "ayer", "2026-01-01'; DROP TABLE x;--", "2019-12-31", "2020-01-01"])
def test_fecha_desde_invalida_o_fuera_del_calendario_falla(tmp_path, monkeypatch, valor):
    _entorno_minimo(monkeypatch)
    monkeypatch.setenv("FECHA_DESDE", valor)
    with pytest.raises(ConfiguracionError, match="FECHA_DESDE"):
        cargar_configuracion(tmp_path)


def test_fecha_desde_llega_al_t_sql():
    base = sql.scripts_puntualidad(destino_para(MODO_PRODUCCION, "2026-03-01"))[1]  # 20_base.sql
    assert "CAST([Fecha/Hora de apertura] AS date) >= '2026-03-01'" in base
    assert "2025-08-01" not in base and "{{" not in base
    por_defecto = sql.scripts_puntualidad(destino_para(MODO_PRODUCCION))[1]
    assert "CAST([Fecha/Hora de apertura] AS date) >= '2025-08-01'" in por_defecto
