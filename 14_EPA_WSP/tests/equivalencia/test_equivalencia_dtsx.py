"""Equivalencia estructural SSIS <-> Python.

Estas pruebas leen el paquete ORIGINAL (CL_Proc_EPA_WSP.dtsx) y los scripts
.py que ejecutaba (102_calidad/) y verifican que la migracion reproduce:

  1. el T-SQL de cada Execute SQL Task (byte a byte) y su Connection Manager;
  2. las tareas, contenedores y Precedence Constraints del Control Flow, y
     que el orden serial del pipeline respeta todas las restricciones;
  3. los 5 Execute Process (scripts migrados, FailTaskIfReturnCode=False) y
     la tarea 'Carga Azure' deshabilitada;
  4. las columnas, filtros y tablas de los scripts de 102_calidad/;
  5. que ninguna credencial de los scripts originales quedo en el codigo.

Se omiten (skip) si el .dtsx o 102_calidad/ no estan disponibles en la
maquina. Rutas configurables con DTSX_PATH y SCRIPTS_ORIGINALES_DIR.
"""

from __future__ import annotations

import ast
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mappings
import sql
from tests.unit.test_pipeline import ORDEN_ESPERADO

RAIZ = Path(__file__).resolve().parents[2]
DTSX = Path(os.getenv("DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_EPA_WSP.dtsx"))
SCRIPTS_DIR = Path(os.getenv("SCRIPTS_ORIGINALES_DIR", str(RAIZ.parent / "102_calidad")))
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable") if e.get(DTS + "refId") != "Package"}


def _connection_managers(raiz) -> dict[str, str]:
    """DTSID -> nombre del Connection Manager."""
    return {cm.get(DTS + "DTSID"): cm.get(DTS + "ObjectName") for cm in raiz.iter(DTS + "ConnectionManager") if cm.get(DTS + "ObjectName")}


def _restricciones(raiz) -> list[tuple[str, str]]:
    return [(pc.get(DTS + "From"), pc.get(DTS + "To")) for pc in raiz.iter(DTS + "PrecedenceConstraint")]


# --------------------------------------------------------------------------- #
# 1. Execute SQL Tasks
# --------------------------------------------------------------------------- #
TAREAS_SQL = {
    "Package\\Log_Inicio": (sql.LOG_INICIO, "162.BBDD_GENERAL"),
    "Package\\Log_Fin": (sql.LOG_FIN, "162.BBDD_GENERAL"),
    "Package\\WSP\\TRUNCATE TBL_ENCUESTAS_WSP_MEDALLIA": (sql.TRUNCATE_WSP_MEDALLIA, "162.CL_TEMPORALES_INDICADORES"),
    "Package\\EPA_ISN\\TRUNCATE TBL_ENCUESTAS_CHILE": (sql.TRUNCATE_ENCUESTAS_CHILE, "162.CL_TEMPORALES_INDICADORES"),
    "Package\\SP_EPA_ISN_CHILE": (sql.SP_EPA_ISN_CHILE, "162.CL_CALIDAD"),
    "Package\\MEDALIA\\SP_PROCESO_ENCUESTAS_MEDALLIA": (sql.SP_PROCESO_ENCUESTAS_MEDALLIA, "162.CL_CALIDAD"),
}


def test_sql_literal_de_cada_execute_sql_task(raiz):
    ejecutables = _ejecutables(raiz)
    cms = _connection_managers(raiz)
    encontrados = {}
    for ref, e in ejecutables.items():
        datos = e.find(f"{DTS}ObjectData/{SQLNS}SqlTaskData")
        if datos is None:
            continue
        encontrados[ref] = (datos.get(SQLNS + "SqlStatementSource"), cms[datos.get(SQLNS + "Connection")])
    assert set(encontrados) == set(TAREAS_SQL)
    for ref, (texto, cm) in encontrados.items():
        esperado_sql, esperado_cm = TAREAS_SQL[ref]
        assert texto == esperado_sql, f"{ref}: el T-SQL difiere del .dtsx"
        assert cm == esperado_cm, f"{ref}: Connection Manager {cm}"


def test_connection_managers_sin_password_reutilizable(raiz):
    for cm in raiz.iter(DTS + "ConnectionManager"):
        cadena = cm.get(DTS + "ConnectionString")
        if cadena:
            assert "Data Source=172.17.0.162" in cadena and "User ID=mparedes" in cadena
            assert "Password" not in cadena  # cifrada con DPAPI aparte: se declara en .env
            assert cm.get(DTS + "ConnectRetryCount") == "1" and cm.get(DTS + "ConnectRetryInterval") == "5"


# --------------------------------------------------------------------------- #
# 2-3. Control Flow
# --------------------------------------------------------------------------- #
def test_tareas_y_contenedores(raiz):
    assert set(_ejecutables(raiz)) == {
        "Package\\Carga Azure", "Package\\enviar_alerta_encuesta_py",
        "Package\\EPA_ISN", "Package\\EPA_ISN\\Traslado_Calidad_Servidor_55_EPA_ISN_py",
        "Package\\EPA_ISN\\TRUNCATE TBL_ENCUESTAS_CHILE", "Package\\Log_Fin", "Package\\Log_Inicio",
        "Package\\MEDALIA", "Package\\MEDALIA\\CARGA BASE CL_Carga_de_encuestas_MEDALLIA_py",
        "Package\\MEDALIA\\DESCARGA_MEDALLIA CL_Descarga_encuestas_Medallia_PY",
        "Package\\MEDALIA\\SP_PROCESO_ENCUESTAS_MEDALLIA", "Package\\SP_EPA_ISN_CHILE",
        "Package\\WSP", "Package\\WSP\\Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA_py",
        "Package\\WSP\\TRUNCATE TBL_ENCUESTAS_WSP_MEDALLIA",
    }


def test_carga_azure_esta_deshabilitada_y_no_se_migra(raiz):
    carga = _ejecutables(raiz)["Package\\Carga Azure"]
    assert carga.get(DTS + "Disabled") == "True"
    assert not any("Azure" in paso for paso in ORDEN_ESPERADO)


def test_execute_process_son_los_5_scripts_migrados_y_toleran_fallos(raiz):
    procesos = {}
    for ref, e in _ejecutables(raiz).items():
        datos = e.find(f"{DTS}ObjectData/ExecuteProcessData")
        if datos is not None and e.get(DTS + "Disabled") != "True":
            procesos[ref.split("\\")[-1]] = datos
    assert {d.get("Arguments") for d in procesos.values()} == {
        "enviar_alerta_encuesta.py",
        "Traslado_Calidad_Servidor_55_EPA_ISN.py",
        "Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py",
        "CL_Descarga_encuestas_Medallia.py",
        "CL_Carga_de_encuestas_MEDALLIA.py",
    }
    assert all(d.get("FailTaskIfReturnCodeIsNotSuccessValue") == "False" for d in procesos.values())
    assert mappings.ENCUESTA.paso in procesos and mappings.WSP.paso in procesos
    assert mappings.MEDALLIA.paso in procesos


# Tarea del .dtsx -> evento del pipeline serial (tests/unit/test_pipeline.py)
_EVENTO = {
    "Package\\Log_Inicio": "Log_Inicio",
    "Package\\enviar_alerta_encuesta_py": "enviar_alerta_encuesta_py",
    "Package\\WSP": "INSERT TBL_ENCUESTAS_WSP_MEDALLIA",
    "Package\\WSP\\TRUNCATE TBL_ENCUESTAS_WSP_MEDALLIA": "DELETE TBL_ENCUESTAS_WSP_MEDALLIA",
    "Package\\WSP\\Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA_py": "INSERT TBL_ENCUESTAS_WSP_MEDALLIA",
    "Package\\EPA_ISN": "INSERT TBL_ENCUESTAS_CHILE",
    "Package\\EPA_ISN\\TRUNCATE TBL_ENCUESTAS_CHILE": "DELETE TBL_ENCUESTAS_CHILE",
    "Package\\EPA_ISN\\Traslado_Calidad_Servidor_55_EPA_ISN_py": "INSERT TBL_ENCUESTAS_CHILE",
    "Package\\SP_EPA_ISN_CHILE": "SP_EPA_ISN_CHILE",
    "Package\\MEDALIA": "SP_PROCESO_ENCUESTAS_MEDALLIA",
    "Package\\MEDALIA\\DESCARGA_MEDALLIA CL_Descarga_encuestas_Medallia_PY": "DESCARGA_MEDALLIA",
    "Package\\MEDALIA\\CARGA BASE CL_Carga_de_encuestas_MEDALLIA_py": "INSERT TBL_ENCUESTAS_MEDALLIA",
    "Package\\MEDALIA\\SP_PROCESO_ENCUESTAS_MEDALLIA": "SP_PROCESO_ENCUESTAS_MEDALLIA",
    "Package\\Log_Fin": "Log_Fin",
}


def test_orden_serial_respeta_todas_las_precedence_constraints(raiz):
    restricciones = _restricciones(raiz)
    assert len(restricciones) == 13  # 9 del paquete + 4 dentro de WSP, EPA_ISN y MEDALIA
    for origen, destino in restricciones:
        if "Carga Azure" in origen or "Carga Azure" in destino:
            continue  # deshabilitada: SP_EPA_ISN_CHILE -> [Carga Azure] -> Log_Fin
        a, b = ORDEN_ESPERADO.index(_EVENTO[origen]), ORDEN_ESPERADO.index(_EVENTO[destino])
        assert a < b, f"{origen} -> {destino}"
    # la cadena que pasaba por Carga Azure se conserva: SP_EPA_ISN_CHILE antes de Log_Fin
    assert ORDEN_ESPERADO.index("SP_EPA_ISN_CHILE") < ORDEN_ESPERADO.index("Log_Fin")


# --------------------------------------------------------------------------- #
# 4. Scripts de 102_calidad
# --------------------------------------------------------------------------- #
requiere_scripts = pytest.mark.skipif(not SCRIPTS_DIR.exists(), reason=f"no se encuentra {SCRIPTS_DIR}")


def _script(nombre: str) -> str:
    candidatos = [p for p in SCRIPTS_DIR.iterdir() if p.name.lower() == nombre.lower()]
    assert candidatos, f"no existe {nombre} en {SCRIPTS_DIR}"
    return candidatos[0].read_text(encoding="utf-8")


def _asignacion(codigo: str, nombre: str):
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == nombre for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise AssertionError(f"no se encontro '{nombre}'")


@requiere_scripts
def test_epa_isn_columnas_filtro_y_destino():
    codigo = _script(mappings.ENCUESTA.script_original)
    columnas = [c.strip() for c in _asignacion(codigo, "column_list").split(",")]
    assert columnas == list(mappings.ENCUESTA.esquema)
    assert "FROM ENCUESTA WHERE periodo_evento >= 202601" in codigo
    assert "INSERT INTO TBL_ENCUESTAS_CHILE" in codigo


@requiere_scripts
def test_wsp_columnas_limpieza_y_destino():
    codigo = _script(mappings.WSP.script_original)
    assert tuple(_asignacion(codigo, "column_list")) == mappings.WSP_COLUMNAS_ORIGEN
    assert "FROM Externos_Frac.dbo.WS_MEDALLIA_2" in codigo
    assert 'float_suffix_indices = {column_list.index("rutcli")}' in codigo
    assert r"FLOAT_SUFFIX_RE = re.compile(r'^-?\d+\.0$')" in codigo


@requiere_scripts
def test_clean_row_del_oraculo_es_copia_literal():
    from tools import oraculos
    import inspect

    codigo = _script(mappings.WSP.script_original)
    assert inspect.getsource(oraculos.clean_row).strip() in codigo


@requiere_scripts
def test_medallia_columnas_lectura_y_destino():
    codigo = _script(mappings.MEDALLIA.script_original)
    assert _asignacion(codigo, "columnas") == list(mappings.MEDALLIA.columnas)
    assert "pd.read_csv(csv_file, encoding='latin1', dtype=str)" in codigo
    assert "format='%d-%m-%Y', errors='coerce'" in codigo
    assert 'TRUNCATE TABLE [TBL_ENCUESTAS_MEDALLIA]' in codigo
    assert _asignacion(codigo, "columna_original") == mappings.MEDALLIA_COLUMNA_DUPLICADA


@requiere_scripts
def test_alerta_misma_tabla_columnas_y_limite():
    codigo = _script("enviar_alerta_encuesta.py")
    assert _asignacion(codigo, "TABLE_NAME") == "ENCUESTA"
    assert _asignacion(codigo, "DATE_COLUMN").lower() == mappings.ALERTA_COLUMNA_FECHA
    assert _asignacion(codigo, "TIME_COLUMN") == mappings.ALERTA_COLUMNA_HORA
    assert _asignacion(codigo, "HORA_LIMITE") == 17 and _asignacion(codigo, "SEGUNDOS_ESPERA") == 30


@requiere_scripts
def test_descarga_medallia_mismas_urls_y_prefijo():
    from config import MEDALLIA_URL_LOGIN_DEFAULT, MEDALLIA_URL_REGISTROS_DEFAULT

    codigo = _script("CL_Descarga_encuestas_Medallia.py")
    assert _asignacion(codigo, "prefijo_archivo") == "Telefonica Moviles Chile SA_export_"
    assert f"url_login = '{MEDALLIA_URL_LOGIN_DEFAULT}'" in codigo
    assert f"url_registros = '{MEDALLIA_URL_REGISTROS_DEFAULT}'" in codigo


# --------------------------------------------------------------------------- #
# 5. Credenciales
# --------------------------------------------------------------------------- #
@requiere_scripts
def test_ninguna_credencial_de_los_scripts_originales_quedo_en_el_codigo():
    secretos = set()
    for p in SCRIPTS_DIR.glob("*.py"):
        texto = p.read_text(encoding="utf-8")
        secretos |= set(re.findall(r"PWD=([^\"';]+)", texto))
        secretos |= set(re.findall(r'password\.send_keys\("([^"]+)"\)', texto))
    assert secretos, "no se detectaron credenciales en los originales (cambio el formato?)"
    for p in RAIZ.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".md", ".sql", ".toml", ".txt") and ".env" not in p.name:
            if "evidencias" in p.parts or "logs" in p.parts:
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
            for s in secretos:
                assert s not in texto, f"credencial embebida en {p}"
