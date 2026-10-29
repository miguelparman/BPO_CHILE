"""Equivalencia estructural SSIS <-> Python.

Leen el paquete ORIGINAL (CL_Proc_Carga_Places.dtsx) y verifican que
mappings.py (la unica fuente de verdad del proceso) reproduce:

  1. el Control Flow: orden de las tareas y de los contenedores;
  2. el T-SQL literal de cada Execute SQL Task, su conexion y sus parametros;
  3. el Excel Connection Manager (archivo original, HDR=YES) y el Excel Source
     (hoja 'Hoja1$', 7 columnas DT_WSTR(255));
  4. la Conversion de datos (DT_STR(n), code page 1252, FailComponent);
  5. el OLE DB Destination (tabla, mapeo de columnas, tipos, fast load);
  6. la variable Fecha_Actual;
  7. que ninguna credencial quedo en el codigo.

Se omiten (skip) si el .dtsx no esta disponible. Ruta configurable con DTSX_PATH.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PureWindowsPath

import pytest

import mappings
from carga.loader import insert_sql

RAIZ = Path(__file__).resolve().parents[2]
DTSX = Path(
    os.getenv("DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_Carga_Places.dtsx")
)
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"
CM_SQL = "162.CL_DATA"
DFT = "Package\\CARGA PLACES\\CARGA TABLA"

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable")}


def _componentes(raiz) -> dict[str, ET.Element]:
    return {c.get("componentClassID"): c for c in raiz.iter("component")}


def _props(elem) -> dict[str, str | None]:
    return {p.get("name"): p.text for p in elem.findall("properties/property")}


def _connection_managers(raiz) -> dict[str, ET.Element]:
    return {
        cm.get(DTS + "ObjectName"): cm
        for cm in raiz.iter(DTS + "ConnectionManager")
        if cm.get(DTS + "ObjectName") is not None
    }


def _cadena_cm(cm: ET.Element) -> str:
    return next(e.get(DTS + "ConnectionString") for e in cm.iter(DTS + "ConnectionManager") if e.get(DTS + "ConnectionString"))


def _sql(raiz, tarea: str) -> ET.Element:
    return next(_ejecutables(raiz)[tarea].iter(SQLNS + "SqlTaskData"))


def _restricciones(raiz) -> set[tuple[str, str, str | None]]:
    return {
        (pc.get(DTS + "From"), pc.get(DTS + "To"), pc.get(DTS + "Value")) for pc in raiz.iter(DTS + "PrecedenceConstraint")
    }


# ---------------------------------------------------------------- 1. control flow
def test_orden_del_control_flow(raiz):
    # Value ausente = Success.
    assert _restricciones(raiz) == {
        ("Package\\Log Inicio", "Package\\CARGA PLACES", None),
        ("Package\\CARGA PLACES", "Package\\CARGA PLACES HISTORICO", None),
        ("Package\\CARGA PLACES HISTORICO", "Package\\Log Fin", None),
        ("Package\\CARGA PLACES\\TRUNCA TABLA", DFT, None),
        (DFT, "Package\\CARGA PLACES\\LIMPIA TABLA", None),
        ("Package\\CARGA PLACES HISTORICO\\ELIMINA FECHA ACTUAL TABLA", "Package\\CARGA PLACES HISTORICO\\CARGA TABLA", None),
    }
    assert all(e.get(DTS + "Disabled") in (None, "False") for e in _ejecutables(raiz).values())


def test_no_hay_script_tasks_ni_archivos_py(raiz):
    tipos = {e.get(DTS + "CreationName") for e in raiz.iter(DTS + "Executable")}
    assert not any("Script" in t for t in tipos if t)


# ---------------------------------------------------------------- 2. Execute SQL Tasks
@pytest.mark.parametrize(
    "tarea, esperado",
    [
        ("Package\\CARGA PLACES\\TRUNCA TABLA", mappings.SQL_TRUNCATE),
        ("Package\\CARGA PLACES\\LIMPIA TABLA", mappings.SQL_LIMPIA),
        ("Package\\CARGA PLACES HISTORICO\\ELIMINA FECHA ACTUAL TABLA", mappings.SQL_HISTORICO_ELIMINA),
        ("Package\\CARGA PLACES HISTORICO\\CARGA TABLA", mappings.SQL_HISTORICO_INSERTA),
        ("Package\\Log Inicio", mappings.SQL_LOG_INICIO),
        ("Package\\Log Fin", mappings.SQL_LOG_FIN),
    ],
)
def test_sql_literal_y_conexion(raiz, tarea, esperado):
    datos = _sql(raiz, tarea)
    assert datos.get(SQLNS + "SqlStatementSource") == esperado
    assert datos.get(SQLNS + "Connection") == _connection_managers(raiz)[CM_SQL].get(DTS + "DTSID")


@pytest.mark.parametrize(
    "tarea", ["Package\\CARGA PLACES HISTORICO\\ELIMINA FECHA ACTUAL TABLA", "Package\\CARGA PLACES HISTORICO\\CARGA TABLA"]
)
def test_historico_recibe_fecha_actual_como_dt_date(raiz, tarea):
    (param,) = _sql(raiz, tarea).findall(SQLNS + "ParameterBinding")
    assert param.get(SQLNS + "DtsVariableName") == "User::Fecha_Actual"
    assert param.get(SQLNS + "DataType") == "7"  # DT_DATE -> datetime.date


def test_sql_apunta_a_las_tablas_de_mappings():
    assert f"[CL_DATA].[dbo].[{mappings.TABLA_PLACES}]" in mappings.SQL_TRUNCATE
    assert f"[CL_DATA].[dbo].[{mappings.TABLA_HISTORICO}]" in mappings.SQL_HISTORICO_INSERTA
    assert "[{}].[dbo].[{}]".format(*mappings.TABLA_PERSONAL) in mappings.SQL_LIMPIA
    assert "[{}].[dbo].[{}]".format(*mappings.TABLA_LOGS) in mappings.SQL_LOG_INICIO
    assert f"'{mappings.NOMBRE_PROCESO}'" in mappings.SQL_LOG_FIN


def test_conexion_sql_es_cl_data_en_el_162(raiz):
    cadena = _cadena_cm(_connection_managers(raiz)[CM_SQL])
    assert "Initial Catalog=CL_DATA" in cadena and "Data Source=172.17.0.162" in cadena


# ---------------------------------------------------------------- 3. Excel Source
def test_excel_connection_manager(raiz):
    cadena = _cadena_cm(_connection_managers(raiz)["Places"])
    ruta = re.search(r"Data Source=([^;]+);", cadena).group(1)
    assert ruta == mappings.RUTA_ORIGINAL
    assert PureWindowsPath(ruta).name == mappings.ARCHIVO
    assert "HDR=YES" in cadena


def test_excel_source(raiz):
    origen = _componentes(raiz)["Microsoft.ExcelSource"]
    assert _props(origen)["OpenRowset"] == mappings.HOJA + "$"
    assert _props(origen)["AccessMode"] == "0"  # tabla / vista
    assert origen.find("connections/connection").get("connectionManagerRefId") == "Package.ConnectionManagers[Places]"
    salida = next(o for o in origen.iter("output") if o.get("isErrorOut") != "true")
    columnas = {c.get("name"): (c.get("dataType"), c.get("length")) for c in salida.iter("outputColumn")}
    assert columnas == {c: ("wstr", "255") for c in mappings.COLUMNAS_ORIGEN}


# ---------------------------------------------------------------- 4. Conversion de datos
def test_conversion_de_datos(raiz):
    conversion = _componentes(raiz)["Microsoft.DataConvert"]
    salida = next(o for o in conversion.iter("output") if o.get("isErrorOut") != "true")
    salidas = {}
    for col in salida.iter("outputColumn"):
        fuente = next(p.text for p in col.iter("property") if p.get("name") == "SourceInputColumnLineageID")
        salidas[re.search(r"\.Columns\[([^\]]+)\]", fuente).group(1)] = col
    assert set(salidas) == {c.origen for c in mappings.COLUMNAS}  # 'Correo Electronico' no se convierte
    for c in mappings.COLUMNAS:
        col = salidas[c.origen]
        assert col.get("dataType") == "str" and col.get("codePage") == "1252", c.origen
        assert int(col.get("length")) == c.ancho, c.origen
        assert col.get("errorRowDisposition") == "FailComponent", c.origen
        assert col.get("truncationRowDisposition") == "FailComponent", c.origen


# ---------------------------------------------------------------- 5. OLE DB Destination
def test_destino(raiz):
    destino = _componentes(raiz)["Microsoft.OLEDBDestination"]
    props = _props(destino)
    assert props["OpenRowset"] == f"[dbo].[{mappings.TABLA_PLACES}]"
    assert props["AccessMode"] == "3"  # fast load
    assert props["FastLoadOptions"] == "TABLOCK,CHECK_CONSTRAINTS"
    assert destino.find("connections/connection").get("connectionManagerRefId") == f"Package.ConnectionManagers[{CM_SQL}]"

    externas = {c.get("refId"): c for c in destino.iter("externalMetadataColumn")}
    mapeo = {}
    for col in destino.iter("inputColumn"):
        externa = externas[col.get("externalMetadataColumnId")]
        mapeo[col.get("cachedName").removeprefix("Copy of ")] = (externa.get("name"), externa.get("dataType"), externa.get("length"))
    assert set(mapeo) == {c.origen for c in mappings.COLUMNAS}
    for c in mappings.COLUMNAS:
        nombre, dtype, largo = mapeo[c.origen]
        assert (nombre, dtype, int(largo)) == (c.destino, "str", c.ancho), c.origen
    # Las dos columnas sin mapear las completa LIMPIA TABLA.
    sin_mapear = {e.get("name") for e in externas.values()} - {m[0] for m in mapeo.values()}
    assert sin_mapear == set(mappings.COLUMNAS_LIMPIA)


def test_insert_usa_las_columnas_del_mapeo():
    assert re.findall(r"\[([^\]]+)\]", insert_sql())[2:] == list(mappings.COLUMNAS_DESTINO)


# ---------------------------------------------------------------- 6. variable Fecha_Actual
def test_fecha_actual_es_la_fecha_de_hoy_yyyy_mm_dd(raiz):
    variable = next(v for v in raiz.iter(DTS + "Variable") if v.get(DTS + "ObjectName") == "Fecha_Actual")
    assert variable.get(DTS + "EvaluateAsExpression") == "True"
    assert "GETDATE()" in variable.get(DTS + "Expression")


# ---------------------------------------------------------------- 7. credenciales
def test_sin_credenciales_en_el_codigo():
    patron = re.compile(r"(PWD|Password|CLIENT_SECRET|client_secret)\s*=\s*['\"][^'\"{]+['\"]", re.IGNORECASE)
    for archivo in list((RAIZ / "src").rglob("*.py")) + [RAIZ / "main.py"] + list((RAIZ / "tools").rglob("*.py")):
        assert not patron.search(archivo.read_text(encoding="utf-8")), archivo
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()
