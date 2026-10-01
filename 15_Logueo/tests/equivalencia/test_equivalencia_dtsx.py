"""Equivalencia estructural SSIS <-> Python.

Leen el paquete ORIGINAL (Cl_Proc_Logueo.dtsx) y verifican que la migracion
reproduce:

  1. el T-SQL de cada Execute SQL Task (byte a byte), su conexion y el
     parametro de 'AGREGA DNI' (User::Periodo, tipo 131);
  2. las tareas, el contenedor y las Precedence Constraints, y que el orden
     del pipeline las respeta; la tarea 'BK' deshabilitada;
  3. la expresion de la variable User::Periodo;
  4. el Flat File Connection Manager (columnas, tipos, anchos, delimitadores,
     code page, cabecera) y RetainNulls del origen;
  5. las expresiones de 'Dia_mes' y 'FechaAnsi';
  6. la Data Conversion (DT_STR 50, FailComponent);
  7. el Lookup (Full Cache, consulta, claves, salida no coincidentes);
  8. el destino (tabla, mapeo de columnas, fast load);
  9. que ninguna credencial quedo en el codigo.

Se omiten (skip) si el .dtsx no esta disponible. Ruta configurable con DTSX_PATH.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mappings
import sql
from periodo import calcular_periodo
from tests.unit.test_pipeline import ORDEN_ESPERADO
from transformacion.transformer import EXPRESIONES_SSIS

RAIZ = Path(__file__).resolve().parents[2]
DTSX = Path(os.getenv("DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\Cl_Proc_Logueo.dtsx"))
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"
DF = "Package\\LOGUEO CHILE\\CARGA TABLA\\"

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable") if e.get(DTS + "refId") != "Package"}


def _componentes(raiz) -> dict[str, ET.Element]:
    return {c.get("refId").removeprefix(DF): c for c in raiz.iter("component")}


def _props(elem) -> dict[str, str | None]:
    return {p.get("name"): p.text for p in elem.findall("properties/property")}


# --------------------------------------------------------------------------- #
# 1. Execute SQL Tasks
# --------------------------------------------------------------------------- #
TAREAS_SQL = {
    "Package\\Log Inicio": sql.LOG_INICIO,
    "Package\\LOGUEO CHILE\\AGREGA DNI": sql.AGREGA_DNI,
    "Package\\Log Fin": sql.LOG_FIN,
    "Package\\SP": sql.SP_LOGUEO,
}


def test_sql_literal_de_cada_execute_sql_task(raiz):
    cms = {cm.get(DTS + "DTSID"): cm.get(DTS + "ObjectName") for cm in raiz.iter(DTS + "ConnectionManager") if cm.get(DTS + "ObjectName")}
    encontrados = {}
    for ref, e in _ejecutables(raiz).items():
        datos = e.find(f"{DTS}ObjectData/{SQLNS}SqlTaskData")
        if datos is not None:
            encontrados[ref] = datos
            assert cms[datos.get(SQLNS + "Connection")] == "CL_LOGUEO"
    assert set(encontrados) == set(TAREAS_SQL) | {"Package\\BK"}
    for ref, texto in TAREAS_SQL.items():
        assert encontrados[ref].get(SQLNS + "SqlStatementSource") == texto, ref
    bk = (RAIZ / "docs" / "BK_deshabilitado_no_migrado.sql").read_text(encoding="utf-8")
    assert encontrados["Package\\BK"].get(SQLNS + "SqlStatementSource") == bk


def test_parametro_de_agrega_dni(raiz):
    datos = _ejecutables(raiz)["Package\\LOGUEO CHILE\\AGREGA DNI"].find(f"{DTS}ObjectData/{SQLNS}SqlTaskData")
    bindings = datos.findall(SQLNS + "ParameterBinding")
    assert [(b.get(SQLNS + "ParameterName"), b.get(SQLNS + "DtsVariableName"), b.get(SQLNS + "DataType")) for b in bindings] == [
        ("0", "User::Periodo", "131")
    ]


# --------------------------------------------------------------------------- #
# 2. Control Flow
# --------------------------------------------------------------------------- #
def test_tareas_y_precedencias(raiz):
    ejecutables = _ejecutables(raiz)
    assert set(ejecutables) == {
        "Package\\Log Inicio", "Package\\LOGUEO CHILE", "Package\\LOGUEO CHILE\\CARGA TABLA",
        "Package\\LOGUEO CHILE\\AGREGA DNI", "Package\\Log Fin", "Package\\SP", "Package\\BK",
    }
    assert ejecutables["Package\\BK"].get(DTS + "Disabled") == "True"
    assert all(e.get(DTS + "Disabled") != "True" for r, e in ejecutables.items() if r != "Package\\BK")

    restricciones = [(pc.get(DTS + "From"), pc.get(DTS + "To"), pc.get(DTS + "Value")) for pc in raiz.iter(DTS + "PrecedenceConstraint")]
    assert all(v in (None, "0") for _, _, v in restricciones)  # todas 'Success'
    # El contenedor 'LOGUEO CHILE' se expande a sus 2 tareas internas.
    expandir = {"Package\\LOGUEO CHILE": ["LOGUEO CHILE\\CARGA TABLA", "LOGUEO CHILE\\AGREGA DNI"]}
    pos = {p: i for i, p in enumerate(ORDEN_ESPERADO)}
    for desde, hasta, _ in restricciones:
        ultimo_desde = expandir.get(desde, [desde.removeprefix("Package\\")])[-1]
        primero_hasta = expandir.get(hasta, [hasta.removeprefix("Package\\")])[0]
        if "BK" in hasta:
            continue  # deshabilitada
        assert pos[ultimo_desde] < pos[primero_hasta], (desde, hasta)


# --------------------------------------------------------------------------- #
# 3. Variable User::Periodo
# --------------------------------------------------------------------------- #
def test_expresion_de_periodo(raiz):
    variables = {v.get(DTS + "ObjectName"): v for v in raiz.iter(DTS + "Variable")}
    periodo = variables["Periodo"]
    assert periodo.get(DTS + "EvaluateAsExpression") == "True"
    expresion = " ".join(periodo.get(DTS + "Expression").split())
    assert expresion == (
        'DAY(GETDATE()) <= 4 ? (YEAR(DATEADD("Month",-1,GETDATE()))*100 + MONTH(DATEADD("Month",-1,GETDATE()))) '
        ": (YEAR(GETDATE())*100 + MONTH(GETDATE()))"
    )
    # El valor de diseno guardado en el paquete es coherente con la regla.
    from datetime import date

    assert int(periodo.find(DTS + "VariableValue").text) == calcular_periodo(date(2026, 9, 30))


# --------------------------------------------------------------------------- #
# 4. Flat File Source
# --------------------------------------------------------------------------- #
def test_flat_file_connection_manager(raiz):
    cm = next(c for c in raiz.iter(DTS + "ConnectionManager") if c.get(DTS + "ObjectName") == "Logueo")
    ff = cm.find(f"{DTS}ObjectData/{DTS}ConnectionManager")
    assert ff.get(DTS + "Format") == "Delimited"
    assert ff.get(DTS + "CodePage") == "1252" == mappings.CODE_PAGE.removeprefix("cp")
    assert ff.get(DTS + "ColumnNamesInFirstDataRow") == "True"
    assert ff.get(DTS + "TextQualifier") == "_x003C_none_x003E_"
    assert ff.get(DTS + "HeaderRowDelimiter") == "_x000D__x000A_"
    assert ff.get(DTS + "ConnectionString").endswith("\\15 PORTAL COMERCIAL\\" + mappings.ARCHIVO)

    columnas = ff.findall(f"{DTS}FlatFileColumns/{DTS}FlatFileColumn")
    assert tuple(c.get(DTS + "ObjectName") for c in columnas) == mappings.COLUMNAS_ORIGEN
    assert {(c.get(DTS + "DataType"), c.get(DTS + "MaximumWidth")) for c in columnas} == {("129", str(mappings.ANCHO_ORIGEN))}
    delimitadores = [c.get(DTS + "ColumnDelimiter") for c in columnas]
    assert set(delimitadores[:-1]) == {"_x003B_"} and delimitadores[-1] == "_x000D__x000A_"


def test_flat_file_source_retain_nulls(raiz):
    assert _props(_componentes(raiz)["Logueo"])["RetainNulls"] == "true"


# --------------------------------------------------------------------------- #
# 5. Derived Columns
# --------------------------------------------------------------------------- #
def _expresiones(componente) -> dict[str, str]:
    out = {}
    for col in [*componente.iter("inputColumn"), *componente.iter("outputColumn")]:
        props = {p.get("name"): p.text for p in col.iter("property")}
        if props.get("FriendlyExpression"):
            out[col.get("cachedName") or col.get("name")] = props["FriendlyExpression"]
    return out


def test_derived_columns(raiz):
    comps = _componentes(raiz)
    dia_mes = _expresiones(comps["Dia_mes"])
    fecha = _expresiones(comps["FechaAnsi"])
    assert dia_mes == {k: EXPRESIONES_SSIS[k] for k in ("MES", "DIA", "INTERVALO")}
    assert fecha == {mappings.COLUMNA_FECHA_ANSI: EXPRESIONES_SSIS[mappings.COLUMNA_FECHA_ANSI]}
    # Dia_mes REEMPLAZA las columnas (usageType ReadWrite)
    assert {c.get("cachedName") for c in comps["Dia_mes"].iter("inputColumn") if c.get("usageType") == "readWrite"} == {"MES", "DIA", "INTERVALO"}


# --------------------------------------------------------------------------- #
# 6. Data Conversion
# --------------------------------------------------------------------------- #
def test_data_conversion(raiz):
    comp = next(c for n, c in _componentes(raiz).items() if n.startswith("Conversi"))
    salida = next(o for o in comp.iter("output") if o.get("isErrorOut") != "true")
    columnas = salida.findall("outputColumns/outputColumn")
    assert {c.get("name").removeprefix("Copy of ") for c in columnas} == set(mappings.MAPEO_DESTINO)
    for c in columnas:
        assert (c.get("dataType"), c.get("length"), c.get("codePage")) == ("str", str(mappings.ANCHO_CONVERSION), "1252")
        assert c.get("errorRowDisposition") == c.get("truncationRowDisposition") == "FailComponent"


# --------------------------------------------------------------------------- #
# 7. Lookup
# --------------------------------------------------------------------------- #
def test_lookup(raiz):
    comp = next(c for c in raiz.iter("component") if c.get("componentClassID") == "Microsoft.Lookup")
    props = _props(comp)
    assert props["SqlCommand"] == sql.LOOKUP_REFERENCIA
    assert props["CacheType"] == "0"  # Full Cache
    assert props["NoMatchBehavior"] == "1"  # redirige a la salida 'no coincidentes'
    claves = []
    for col in comp.iter("inputColumn"):
        p = {x.get("name"): x.text for x in col.iter("property")}
        claves.append((mappings.MAPEO_DESTINO[col.get("cachedName").removeprefix("Copy of ")], p["JoinToReferenceColumn"]))
    assert tuple(claves) == mappings.CLAVE_LOOKUP
    # Solo la salida 'no coincidentes' llega al destino
    caminos = [(p.get("startId"), p.get("endId")) for p in raiz.iter("path")]
    al_destino = [s for s, e in caminos if "Destino de OLE DB" in e]
    assert len(al_destino) == 1 and "no coincidentes" in al_destino[0]


# --------------------------------------------------------------------------- #
# 8. Destino
# --------------------------------------------------------------------------- #
def test_destino(raiz):
    comp = _componentes(raiz)["Destino de OLE DB"]
    props = _props(comp)
    assert props["OpenRowset"] == f"[{mappings.SCHEMA}].[{mappings.TABLA_DESTINO}]"
    assert props["AccessMode"] == "3"
    assert props["FastLoadOptions"] == "TABLOCK,CHECK_CONSTRAINTS"
    assert props["FastLoadMaxInsertCommitSize"] == "2147483647"
    externas = {c.get("refId"): c.get("name") for c in comp.iter("externalMetadataColumn")}
    assert tuple(externas.values()) == mappings.COLUMNAS_DESTINO
    mapeo = {c.get("cachedName").removeprefix("Copy of "): externas[c.get("externalMetadataColumnId")] for c in comp.iter("inputColumn")}
    assert mapeo == mappings.MAPEO_DESTINO
    assert "DNI" not in mapeo.values()


# --------------------------------------------------------------------------- #
# 9. Sin credenciales en el codigo
# --------------------------------------------------------------------------- #
def test_sin_credenciales_en_el_codigo():
    from dotenv import dotenv_values

    secretos = [v for k, v in dotenv_values(RAIZ / ".env").items() if v and k in ("DB_PASSWORD", "CLIENT_SECRET")]
    if not secretos:
        pytest.skip("sin .env con secretos para comparar")
    for archivo in [*RAIZ.glob("*.py"), *(RAIZ / "src").rglob("*.py"), *(RAIZ / "src").rglob("*.sql"), *(RAIZ / "tools").rglob("*.py"), RAIZ / ".env.example"]:
        texto = archivo.read_text(encoding="utf-8")
        assert not any(s in texto for s in secretos), archivo
