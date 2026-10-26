"""Equivalencia con el .dtsx (sin servidor): los T-SQL literales, los anchos y las columnas
del Data Flow, y que no queden credenciales. Se omite si el .dtsx no esta en esta maquina."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import sql
from mappings import COLUMNAS, TEXTO

DTSX = Path(r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\SSIS_CL_Puntualidad.dtsx")
RAIZ = Path(__file__).resolve().parents[2]
D = "{www.microsoft.com/SqlServer/Dts}"
S = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"

requiere_dtsx = pytest.mark.skipif(not DTSX.exists(), reason="el .dtsx original no esta en esta maquina")


@pytest.fixture(scope="module")
def raiz_xml():
    return ET.parse(DTSX).getroot()


def _scripts_dtsx(raiz):
    return {
        e.get(D + "ObjectName"): t.get(S + "SqlStatementSource")
        for e in raiz.iter(D + "Executable")
        if e.get(D + "ExecutableType") == "Microsoft.ExecuteSQLTask"
        for t in e.iter(S + "SqlTaskData")
    }


@requiere_dtsx
def test_control_flow_es_el_esperado(raiz_xml):
    nombres = {e.get(D + "ObjectName") for e in raiz_xml.iter(D + "Executable") if e.get(D + "ObjectName")}
    assert {"PUNTUALIDAD", "SLA PRUEBA", "TBL_SLA_CHILE", "TRUNCA TABLA", "UPDATE"} <= nombres
    precedencias = {(p.get(D + "From"), p.get(D + "To")) for p in raiz_xml.iter(D + "PrecedenceConstraint")}
    assert ("Package\\SLA PRUEBA\\TRUNCA TABLA", "Package\\SLA PRUEBA\\TBL_SLA_CHILE") in precedencias
    assert ("Package\\SLA PRUEBA\\TBL_SLA_CHILE", "Package\\SLA PRUEBA\\UPDATE") in precedencias
    assert ("Package\\SLA PRUEBA", "Package\\PUNTUALIDAD") in precedencias


@requiere_dtsx
def test_scripts_literales_de_sla_son_identicos_al_dtsx(raiz_xml):
    d = _scripts_dtsx(raiz_xml)
    assert sql.leer("sla", "10_trunca_tabla.sql") == d["TRUNCA TABLA"]
    assert sql.leer("sla", "30_update.sql") == d["UPDATE"]


@requiere_dtsx
def test_referencia_puntualidad_es_identica_al_dtsx(raiz_xml):
    with open(RAIZ / "docs" / "referencia_sql" / "p2_PUNTUALIDAD.sql", encoding="utf-8", newline="") as f:
        ref = f.read()
    assert ref == _scripts_dtsx(raiz_xml)["PUNTUALIDAD"]


@requiere_dtsx
def test_base_de_puntualidad_conserva_las_columnas_y_los_joins_del_original(raiz_xml):
    original = _scripts_dtsx(raiz_xml)["PUNTUALIDAD"]
    base = sql.leer("puntualidad", "20_base.sql")

    def seleccion(texto):
        return texto[texto.index("SELECT \n"): texto.index("INTO \n")]

    assert seleccion(base).replace("\t,ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) [rid]\n", "") == seleccion(original)
    for on in re.findall(r"ON\n(?:\tx\d\.[^\n]+\n)+", original):
        assert on in base
    assert "'2025-08-01'" in base


@requiere_dtsx
def test_columnas_del_data_flow(raiz_xml):
    """Anchos del Data Conversion y destino de cada columna, leidos del .dtsx."""
    conversion = {}
    for oc in raiz_xml.iter("outputColumn"):
        nombre = oc.get("name", "")
        if nombre.startswith("Copy of ") and "Data Conversion Output" in oc.get("refId", ""):
            conversion[nombre[len("Copy of "):].lower()] = (oc.get("dataType"), oc.get("length"))
    assert len(conversion) == 8
    for col in COLUMNAS:
        tipo, largo = conversion[col.origen.lower()]
        if col.tipo == TEXTO:
            assert tipo == "str" and int(largo) == col.largo, col
        else:
            assert tipo == "numeric", col
    mapeo = {}
    for ic in raiz_xml.iter("inputColumn"):
        if "TBL_SLA.Inputs" in ic.get("refId", ""):
            externa = ic.get("externalMetadataColumnId", "")
            mapeo[ic.get("cachedName")[len("Copy of "):].lower()] = re.search(r"ExternalColumns\[(.+)\]$", externa).group(1)
    for col in COLUMNAS:
        assert mapeo[col.origen.lower()] == col.destino, col


def test_no_hay_credenciales_embebidas():
    patron = re.compile(r"(password|pwd|secret)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE)
    for archivo in (RAIZ / "src").rglob("*.py"):
        assert not patron.search(archivo.read_text(encoding="utf-8")), archivo
    for archivo in (RAIZ / "src" / "puntualidad" / "scripts_sql").rglob("*.sql"):
        assert "PWD=" not in archivo.read_text(encoding="utf-8").upper(), archivo
