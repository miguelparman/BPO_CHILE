"""Equivalencia estructural SSIS <-> Python.

Leen el paquete ORIGINAL (CL_Proc_Volumetria_Gerencia.dtsx) y verifican que
mappings.py (la unica fuente de verdad de los 4 flujos) reproduce:

  1. los 4 contenedores, sin Precedence Constraints entre ellos, y el orden
     TRUNCATE -> Data Flow -> DELETE dentro de cada uno;
  2. el T-SQL literal de cada Execute SQL Task y su conexion;
  3. el Excel Connection Manager de cada flujo (archivo y subcarpeta, HDR=YES)
     y el Excel Source (hoja 'Hoja1$', columnas, tipos DT_R8/DT_DATE/DT_WSTR);
  4. la Conversion de datos (DT_STR(n)/DT_DBDATE, code page 1252,
     disposicion de error y truncamiento por columna);
  5. el OLE DB Destination (tabla, mapeo de columnas, tipos, fast load);
  6. que ninguna credencial quedo en el codigo.

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
    os.getenv(
        "DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_Volumetria_Gerencia.dtsx"
    )
)
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"
SEQ = "Package\\Contenedor de secuencias 1"
CM_SQL = "162.CL_MOVIL"
# Contenedor del .dtsx -> nombre de su Excel Connection Manager.
CM_EXCEL = {"GERENCIA": "Gerencia", "ESCALAMIENTO": "Escalamiento", "CLOSE THE LOOP": "CLOSE THE LOOP", "T-ATIENDO": "T-ATIENDO"}

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable")}


def _componentes(raiz, flujo: mappings.FlujoSpec) -> dict[str, ET.Element]:
    """{componentClassID: componente} del Data Flow del contenedor."""
    prefijo = f"{SEQ}\\{flujo.nombre}\\"
    return {c.get("componentClassID"): c for c in raiz.iter("component") if c.get("refId").startswith(prefijo)}


def _props(elem) -> dict[str, str | None]:
    return {p.get("name"): p.text for p in elem.findall("properties/property")}


def _connection_managers(raiz) -> dict[str, ET.Element]:
    return {
        cm.get(DTS + "ObjectName"): cm
        for cm in raiz.iter(DTS + "ConnectionManager")
        if cm.get(DTS + "ObjectName") is not None
    }


def _cadena_cm(cm: ET.Element) -> str:
    """ConnectionString (vive en el DTS:ConnectionManager anidado en ObjectData)."""
    return next(e.get(DTS + "ConnectionString") for e in cm.iter(DTS + "ConnectionManager") if e.get(DTS + "ConnectionString"))


def _ancho(dtype: str | None, length: str | None) -> int | None:
    return None if dtype == "dbDate" else int(length)


# ---------------------------------------------------------------- 1. control flow
def test_cuatro_contenedores_en_paralelo(raiz):
    ejecutables = _ejecutables(raiz)
    contenedores = {r.split("\\")[-1] for r in ejecutables if r.count("\\") == 2 and r.startswith(SEQ + "\\")}
    assert contenedores == {f.nombre for f in mappings.FLUJOS}
    restricciones = [(pc.get(DTS + "From"), pc.get(DTS + "To")) for pc in raiz.iter(DTS + "PrecedenceConstraint")]
    for desde, hacia in restricciones:  # todas son internas a un contenedor
        assert desde.split("\\")[2] == hacia.split("\\")[2]
    assert all(e.get(DTS + "Disabled") in (None, "False") for e in ejecutables.values())


@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_orden_truncate_dataflow_delete(raiz, flujo):
    base = f"{SEQ}\\{flujo.nombre}"
    dft = f"{base}\\TBL_VOLUMETRIA_{flujo.nombre}"
    restricciones = {
        (pc.get(DTS + "From"), pc.get(DTS + "To"), pc.get(DTS + "Value"))
        for pc in raiz.iter(DTS + "PrecedenceConstraint")
        if pc.get(DTS + "From").startswith(base + "\\")
    }
    # Value ausente = Success (0).
    assert restricciones == {(f"{base}\\TRUNCATE", dft, None), (dft, f"{base}\\DELETE", None)}


# ---------------------------------------------------------------- 2. Execute SQL Tasks
@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_sql_literal_y_conexion(raiz, flujo):
    ejecutables = _ejecutables(raiz)
    guid_sql = _connection_managers(raiz)[CM_SQL].get(DTS + "DTSID")
    for tarea, esperado in (("TRUNCATE", flujo.sql_truncate), ("DELETE", flujo.sql_delete)):
        datos = next(ejecutables[f"{SEQ}\\{flujo.nombre}\\{tarea}"].iter(SQLNS + "SqlTaskData"))
        assert datos.get(SQLNS + "SqlStatementSource") == esperado
        assert datos.get(SQLNS + "Connection") == guid_sql


def test_conexion_sql_es_cl_movil(raiz):
    cadena = _cadena_cm(_connection_managers(raiz)[CM_SQL])
    assert "Initial Catalog=CL_MOVIL" in cadena and "Data Source=172.17.0.162" in cadena


# ---------------------------------------------------------------- 3. Excel Source
@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_excel_connection_manager(raiz, flujo):
    cadena = _cadena_cm(_connection_managers(raiz)[CM_EXCEL[flujo.nombre]])
    ruta = PureWindowsPath(re.search(r"Data Source=([^;]+);", cadena).group(1))
    assert ruta.name == flujo.archivo
    assert ruta.parent.name == flujo.subcarpeta
    assert "HDR=YES" in cadena


@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_excel_source(raiz, flujo):
    origen = _componentes(raiz, flujo)["Microsoft.ExcelSource"]
    props = _props(origen)
    assert props["OpenRowset"] == mappings.HOJA + "$"
    assert props["AccessMode"] == "2"  # comando SQL
    seleccion = re.findall(r"\[([^\]]+)\]", props["SqlCommand"])
    assert seleccion[-1] == mappings.HOJA + "$"
    assert set(seleccion[:-1]) == set(flujo.columnas_origen)
    conexion = origen.find("connections/connection").get("connectionManagerRefId")
    assert conexion == f"Package.ConnectionManagers[{CM_EXCEL[flujo.nombre]}]"

    tipos = {c.get("name"): c.get("dataType") for c in origen.iter("outputColumn")}
    esperado = {mappings.CASO: "r8", mappings.FECHA: "date", mappings.TEXTO: "wstr"}
    for c in flujo.columnas:
        assert tipos[c.origen] == esperado[c.tipo], c.origen


# ---------------------------------------------------------------- 4. Conversion de datos
@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_conversion_de_datos(raiz, flujo):
    conversion = _componentes(raiz, flujo)["Microsoft.DataConvert"]
    salida = next(o for o in conversion.iter("output") if o.get("isErrorOut") != "true")
    salidas = {}
    for col in salida.iter("outputColumn"):
        fuente = next(p.text for p in col.iter("property") if p.get("name") == "SourceInputColumnLineageID")
        origen = re.search(r"\.Columns\[([^\]]+)\]", fuente).group(1)
        salidas[origen] = col
    assert set(salidas) == set(flujo.columnas_origen)
    for c in flujo.columnas:
        col = salidas[c.origen]
        assert col.get("dataType") == ("dbDate" if c.tipo == mappings.FECHA else "str"), c.origen
        ancho_dtsx = mappings.ANCHOS_AMPLIADOS.get((flujo.nombre, c.origen), c.ancho)
        assert _ancho(col.get("dataType"), col.get("length")) == ancho_dtsx, c.origen
        if c.tipo != mappings.FECHA:
            assert col.get("codePage") == "1252"
        assert col.get("errorRowDisposition") == c.disposicion, c.origen
        assert col.get("truncationRowDisposition") == c.disposicion, c.origen


# ---------------------------------------------------------------- 5. OLE DB Destination
@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_destino(raiz, flujo):
    destino = _componentes(raiz, flujo)["Microsoft.OLEDBDestination"]
    props = _props(destino)
    assert props["OpenRowset"] == f"[dbo].[{flujo.tabla}]"
    assert props["AccessMode"] == ("3" if flujo.fast_load else "0")
    assert destino.find("connections/connection").get("connectionManagerRefId") == (
        f"Package.ConnectionManagers[{CM_SQL}]"
    )

    externas = {c.get("refId"): c for c in destino.iter("externalMetadataColumn")}
    mapeo = {}
    for col in destino.iter("inputColumn"):
        origen = col.get("cachedName").removeprefix("Copy of ")
        externa = externas[col.get("externalMetadataColumnId")]
        mapeo[origen] = (externa.get("name"), externa.get("dataType"), externa.get("length"))
    assert set(mapeo) == set(flujo.columnas_origen)
    for c in flujo.columnas:
        nombre, dtype, largo = mapeo[c.origen]
        assert nombre == c.destino, c.origen
        assert dtype == ("dbDate" if c.tipo == mappings.FECHA else "str"), c.origen
        if c.tipo != mappings.FECHA:  # la columna destino admite al menos el ancho de la conversion
            assert int(largo) >= mappings.ANCHOS_AMPLIADOS.get((flujo.nombre, c.origen), c.ancho), c.origen


def test_ampliaciones_solo_en_columnas_ignore_failure():
    """Solo se ampliaron columnas IgnoreFailure (las que truncaban en silencio)."""
    for (nombre, origen), ancho_dtsx in mappings.ANCHOS_AMPLIADOS.items():
        c = next(c for c in mappings.FLUJOS_POR_NOMBRE[nombre].columnas if c.origen == origen)
        assert c.disposicion == mappings.IGNORE and c.ancho == 255 > ancho_dtsx


@pytest.mark.parametrize("flujo", mappings.FLUJOS, ids=lambda f: f.nombre)
def test_insert_usa_las_columnas_del_mapeo(flujo):
    sql = insert_sql(flujo)
    assert sql.startswith(f"INSERT INTO [dbo].[{flujo.tabla}] (")
    assert re.findall(r"\[([^\]]+)\]", sql)[2:] == list(flujo.columnas_destino)


# ---------------------------------------------------------------- 6. credenciales
def test_sin_credenciales_en_el_codigo():
    patron = re.compile(r"(PWD|Password|CLIENT_SECRET|client_secret)\s*=\s*['\"][^'\"{]+['\"]", re.IGNORECASE)
    for archivo in list((RAIZ / "src").rglob("*.py")) + [RAIZ / "main.py"] + list((RAIZ / "tools").rglob("*.py")):
        texto = archivo.read_text(encoding="utf-8")
        assert not patron.search(texto), archivo
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()
