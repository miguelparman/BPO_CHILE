"""Equivalencia estructural SSIS <-> Python.

Leen los paquetes ORIGINALES (CL_Seguimiento_02/03/04/06/07*.dtsx) y
verifican que la migracion reproduce:

  1. el T-SQL de cada Execute SQL Task (byte a byte), y que al ejecutarse
     solo cambia la redireccion de las staging a #temporales;
  2. que toda tarea del .dtsx esta migrada, es REDUNDANTE con la migracion
     (TRUNCATE de una staging que paso a #temporal, 'Agrega Nombre de
     Contacto' reemplazado por el cruce en Python, Tipificaciones que solo
     alimentaba una tarea deshabilitada) o esta documentada como no migrada
     (deshabilitada, o 'ACTUALIZA CASOS OTRO PAIS' excluida por decision);
  3. el orden: cada Precedence Constraint (tambien entre contenedores) se
     respeta en la lista de tareas de cada paquete;
  4. cada OLE DB Destination: tabla, TABLOCK y el linaje completo de cada
     columna (columna del archivo -> Derived Column -> Data Conversion,
     tipo, ancho y disposiciones de error/truncamiento);
  5. cada Flat File Connection Manager / Flat File Source: columnas, tipos y
     anchos de salida, delimitadores, calificador, code page, encabezado y
     RetainNulls;
  6. la Derived Column REPLACE de Correos;
  7. el Execute Process de Descripciones NC (script y FailTask = False);
  8. que ninguna credencial quedo en el codigo.

Se omiten (skip) si los .dtsx no estan disponibles. Carpeta configurable
con DTSX_DIR.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mappings as m
from paquetes import PAQUETES
import sql
from paquetes.base import TareaDataFlow, TareaDescripcionesNC, TareaSql, TareaTransaccion

RAIZ = Path(__file__).resolve().parents[2]
DTSX_DIR = Path(os.getenv("DTSX_DIR", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE"))
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"

pytestmark = pytest.mark.skipif(
    not all((DTSX_DIR / p.dtsx).exists() for p in PAQUETES), reason=f"no se encuentran los .dtsx en {DTSX_DIR}"
)

NO_MIGRADAS = {
    ("02", "Package\\ACTUALIZA CASOS OTRO PAIS"): "excluida",  # decision del usuario: no tocar PE_SALESFORCE_ACTUAL
    ("02", "Package\\CARGA BASE CASOS SALESFORCE\\ACTUALIZA TIFICIACIONES"): "deshabilitada",
    ("07", "Package\\BK"): "deshabilitada",
    ("07", "Package\\CARGA ESPEJO AZURE"): "deshabilitada",
}

_raices: dict[str, ET.Element] = {}


def raiz(paquete) -> ET.Element:
    if paquete.dtsx not in _raices:
        _raices[paquete.dtsx] = ET.parse(DTSX_DIR / paquete.dtsx).getroot()
    return _raices[paquete.dtsx]


def ejecutables(r) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in r.iter(DTS + "Executable") if e.get(DTS + "refId") != "Package"}


def props(elem) -> dict[str, str | None]:
    return {p.get("name"): p.text for p in elem.findall("properties/property")}


def paquete(codigo):
    return next(p for p in PAQUETES if p.codigo == codigo)


# --------------------------------------------------------------------------- #
# 1-2. Tareas: migradas, redundantes o no migradas
# --------------------------------------------------------------------------- #
def _sql_ejecutadas(pq) -> dict[str, str]:
    """{refId: T-SQL} de las Execute SQL Tasks que ejecuta la migracion."""
    salida = {}
    for t in pq.tareas:
        for x in t.tareas if isinstance(t, TareaTransaccion) else [t]:
            if isinstance(x, TareaSql):
                salida[x.nombre] = x.script
    return salida


def _sql_del_dtsx(pq) -> dict[str, tuple[str, bool]]:
    """{refId: (T-SQL, deshabilitada)} de las Execute SQL Tasks del .dtsx."""
    salida = {}
    for ref, e in ejecutables(raiz(pq)).items():
        datos = e.find(f"{DTS}ObjectData/{SQLNS}SqlTaskData")
        if datos is not None:
            salida[ref] = (datos.get(SQLNS + "SqlStatementSource"), e.get(DTS + "Disabled") == "True")
    return salida


@pytest.mark.parametrize("pq", PAQUETES, ids=lambda p: p.codigo)
def test_sql_literal_de_cada_execute_sql_task(pq):
    ejecutadas = _sql_ejecutadas(pq)
    redundantes = dict(pq.redundantes)
    for ref, (texto, deshabilitada) in _sql_del_dtsx(pq).items():
        if (pq.codigo, ref) in NO_MIGRADAS:
            assert ref not in ejecutadas
            if NO_MIGRADAS[(pq.codigo, ref)] == "deshabilitada":
                assert deshabilitada, ref
            continue
        if ref in redundantes:
            assert ref not in ejecutadas
            continue
        assert ref in ejecutadas, f"Execute SQL Task sin migrar ni justificar: {ref}"
        assert ejecutadas[ref] == texto, f"T-SQL distinto en {ref}"
        assert not deshabilitada
    assert set(ejecutadas) <= set(_sql_del_dtsx(pq)), "hay tareas migradas que no existen en el .dtsx"


_TRUNCATE = re.compile(r"^\s*(TRUNCATE TABLE \[CL_TEMPORALES\]\.\[dbo\]\.\[(?P<t>\w+)\]\s*)+$", re.IGNORECASE)


@pytest.mark.parametrize("pq", PAQUETES, ids=lambda p: p.codigo)
def test_cada_tarea_redundante_lo_es(pq):
    """Un TRUNCATE redundante solo vacia staging que pasaron a #temporales o
    que ya no se usan; 'Agrega Nombre de Contacto' es el UPDATE que hace el cruce."""
    del_dtsx = _sql_del_dtsx(pq)
    reemplazables = set(m.TABLAS_TEMPORALES) | set(m.TABLAS_ELIMINADAS)
    for ref, _motivo in pq.redundantes:
        texto, deshabilitada = del_dtsx[ref]
        assert not deshabilitada
        if ref.endswith("Agrega Nombre de Contacto"):
            assert m.FLUJO_TEMP_REPORTE_CASOS.cruce.tarea_reemplazada == ref
            assert "UPDATE X0" in texto and "LEFT JOIN [CL_TEMPORALES].[dbo].[TBL_SALESFORCE_DATOS_CONTACTO] X1" in texto
            for col in m.FLUJO_TEMP_REPORTE_CASOS.cruce.columnas:
                assert f"[{col}] = CASE WHEN X1.[{col}] = '' THEN NULL ELSE X1.[{col}] END" in texto
            continue
        assert _TRUNCATE.match(texto), ref
        tablas = set(re.findall(r"\[dbo\]\.\[(\w+)\]", texto))
        assert tablas <= reemplazables, f"{ref} vacia {tablas - reemplazables}"


def test_tipificaciones_solo_alimentaba_una_tarea_deshabilitada():
    pq = paquete("02")
    for ref, (texto, deshabilitada) in _sql_del_dtsx(pq).items():
        if "TBL_SALESFORCE_CASOS_TIPIFICACIONES" in texto and not deshabilitada:
            assert texto.lstrip().upper().startswith("TRUNCATE"), ref  # solo la vacian
    actualiza = _sql_del_dtsx(pq)["Package\\CARGA BASE CASOS SALESFORCE\\ACTUALIZA TIFICIACIONES"]
    assert actualiza[1], "ACTUALIZA TIFICIACIONES deberia estar deshabilitada"


def test_al_ejecutarse_solo_cambia_la_redireccion_a_temporales():
    for pq in PAQUETES:
        for ref, texto in _sql_ejecutadas(pq).items():
            ejecutado = sql.a_temporal(texto)
            for tabla in m.TABLAS_TEMPORALES:
                assert sql.nombre_staging(tabla) not in ejecutado, ref
            restaurado = ejecutado
            for tabla in m.TABLAS_TEMPORALES:
                restaurado = restaurado.replace(f"#{tabla} ", sql.nombre_staging(tabla))
            assert restaurado == texto, f"a_temporal cambio algo mas que los nombres en {ref}"
            for tabla in m.TABLAS_ELIMINADAS:
                assert tabla not in texto, f"{ref} usa {tabla}, que la migracion ya no carga"


def test_tarea_excluida_es_la_unica_que_toca_peru():
    pq = paquete("02")
    e = ejecutables(raiz(pq))["Package\\ACTUALIZA CASOS OTRO PAIS"]
    assert "PE_SALESFORCE_ACTUAL" in e.find(f"{DTS}ObjectData/{SQLNS}SqlTaskData").get(SQLNS + "SqlStatementSource")
    for p in PAQUETES:
        for texto in _sql_ejecutadas(p).values():
            assert "PE_SALESFORCE" not in texto
    texto = (RAIZ / "docs" / "no_migrado" / "p02_ACTUALIZA_CASOS_OTRO_PAIS_excluida.sql").read_text(encoding="utf-8")
    assert "PE_SALESFORCE_ACTUAL" in texto


# --------------------------------------------------------------------------- #
# 3. Orden (Precedence Constraints)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pq", PAQUETES, ids=lambda p: p.codigo)
def test_orden_respeta_precedence_constraints(pq):
    r = raiz(pq)
    indice = {ref: i for i, ref in enumerate(pq.refids)}
    migrables = {ref for ref in ejecutables(r) if ref in indice}

    def posiciones(ref):
        return [indice[t] for t in migrables if t == ref or t.startswith(ref + "\\")]

    for pc in r.iter(DTS + "PrecedenceConstraint"):
        desde, hasta = pc.get(DTS + "From"), pc.get(DTS + "To")
        assert pc.get(DTS + "Value") in (None, "0"), "solo hay restricciones 'Success'"
        a, b = posiciones(desde), posiciones(hasta)
        if a and b:
            assert max(a) < min(b), f"{desde} -> {hasta} no se respeta"


def test_paquetes_en_el_orden_declarado():
    assert [p.codigo for p in PAQUETES] == ["02", "03", "04", "06", "07"]
    assert [p.dtsx[:17] for p in PAQUETES] == [f"CL_Seguimiento_0{c}" for c in "23467"]


def test_toda_tarea_habilitada_esta_migrada_o_justificada():
    for pq in PAQUETES:
        hojas = {ref: e for ref, e in ejecutables(raiz(pq)).items() if e.get(DTS + "CreationName") != "STOCK:SEQUENCE"}
        justificadas = set(pq.refids) | {ref for ref, _ in pq.redundantes}
        for ref, e in hojas.items():
            if (pq.codigo, ref) in NO_MIGRADAS:
                continue
            assert ref in justificadas, f"{pq.codigo}: tarea sin migrar {ref} ({e.get(DTS + 'CreationName')})"


def test_numero_de_tareas_ssis_vs_python():
    tareas = {p.codigo: (len(p.refids), len(p.tareas), len(p.redundantes)) for p in PAQUETES}
    # (tareas del .dtsx que se ejecutan, pasos Python, tareas redundantes eliminadas)
    assert tareas == {"02": (9, 7, 4), "03": (5, 5, 2), "04": (5, 5, 2), "06": (7, 7, 2), "07": (9, 9, 0)}


# --------------------------------------------------------------------------- #
# 4-5. Data Flows
# --------------------------------------------------------------------------- #
_TIPO_CONV = {"wstr": m.WSTR, "str": m.STR1252, "nText": m.NTEXT, "date": m.FECHA, "numeric": m.NUMERICO}
_TIPO_FF = {"str": m.FF_STR, "text": m.FF_TEXT, "date": m.FF_FECHA}


def _flujos_y_paquetes():
    """Cada OLE DB Destination que se reproduce: los que se cargan y los que
    entran por un cruce (Nombre Contacto)."""
    for pq in PAQUETES:
        for t in pq.tareas:
            if isinstance(t, TareaDataFlow):
                for f in t.flujos:
                    yield pq, t, f
                    if f.cruce:
                        yield pq, t, f.cruce.flujo


FLUJOS = list(_flujos_y_paquetes())


def _linaje(r, flujo: m.FlujoSpec):
    """{columna destino: dict} derivado del .dtsx para el OLE DB Destination del flujo."""
    tarea = ejecutables(r)[flujo.tarea]
    pipe = tarea.find(f"{DTS}ObjectData/pipeline")
    salidas = {}
    componentes = {}
    for comp in pipe.iter("component"):
        componentes[comp.get("name")] = comp
        for oc in comp.iter("outputColumn"):
            salidas[oc.get("refId")] = (comp, oc)
    cms = {
        cm.get(DTS + "refId"): [c.get(DTS + "ObjectName") for c in cm.iter(DTS + "FlatFileColumn")]
        for cm in r.iter(DTS + "ConnectionManager")
        if cm.get(DTS + "CreationName") == "FLATFILE"
    }

    def seguir(ref, info):
        comp, oc = salidas[ref]
        clase = comp.get("componentClassID")
        if clase == "Microsoft.FlatFileSource":
            cm = comp.find("connections/connection").get("connectionManagerRefId")
            info["origen"] = cms[cm].index(oc.get("name"))
            return info
        if clase == "Microsoft.DataConvert":
            info.setdefault("conversion", (oc.get("dataType"), oc.get("length"), oc.get("errorRowDisposition"), oc.get("truncationRowDisposition")))
            return seguir(props(oc)["SourceInputColumnLineageID"].strip("#{}"), info)
        if clase == "Microsoft.DerivedColumn":
            expr = props(oc)["FriendlyExpression"]
            mm = re.fullmatch(r"LEFT\(\[(?P<col>.+)\],(?P<n>\d+)\)", expr)
            assert mm, expr
            info["left"] = int(mm["n"])
            info.setdefault("conversion", (oc.get("dataType"), oc.get("length"), oc.get("errorRowDisposition"), oc.get("truncationRowDisposition")))
            entrada = next(ic for ic in comp.iter("inputColumn") if ic.get("cachedName") == mm["col"])
            return seguir(entrada.get("lineageId"), info)
        raise AssertionError(f"componente inesperado {clase}")

    destino = componentes[flujo.componente]
    ext = {e.get("refId"): e.get("name") for e in destino.iter("externalMetadataColumn")}
    linaje = {}
    for ic in destino.iter("inputColumn"):
        linaje[ext[ic.get("externalMetadataColumnId")]] = seguir(ic.get("lineageId"), {})
    return destino, linaje


@pytest.mark.parametrize("pq,tarea,flujo", FLUJOS, ids=lambda x: getattr(x, "componente", getattr(x, "codigo", None)))
def test_destino_y_linaje_de_columnas(pq, tarea, flujo):
    destino, linaje = _linaje(raiz(pq), flujo)
    p = props(destino)
    assert p["OpenRowset"] == f"[dbo].[{flujo.tabla}]"
    assert p["AccessMode"] == "3"  # fast load
    assert ("TABLOCK" in (p["FastLoadOptions"] or "")) == flujo.tablock
    assert p["FastLoadMaxInsertCommitSize"] == "2147483647"  # un solo commit
    assert {c.destino for c in flujo.columnas} == set(linaje)
    for col in flujo.columnas:
        info = linaje[col.destino]
        tipo, largo, err, trunc = info["conversion"]
        assert info["origen"] == col.origen, col.destino
        assert info.get("left") == col.left, col.destino
        assert _TIPO_CONV[tipo] == col.conversion.tipo, col.destino
        assert (int(largo) if largo else None) == (col.conversion.ancho if col.conversion.tipo in (m.WSTR, m.STR1252) else None), col.destino
        assert (err == "IgnoreFailure") == col.conversion.error_ignora, col.destino
        assert (trunc == "IgnoreFailure") == col.conversion.truncamiento_ignora, col.destino


@pytest.mark.parametrize("pq,tarea,flujo", FLUJOS, ids=lambda x: getattr(x, "componente", getattr(x, "codigo", None)))
def test_flat_file_connection_manager_y_source(pq, tarea, flujo):
    r = raiz(pq)
    cm = next(c for c in r.iter(DTS + "ConnectionManager") if c.get(DTS + "ObjectName") == flujo.archivo.conexion)
    interno = cm.find(f"{DTS}ObjectData/{DTS}ConnectionManager")
    assert interno.get(DTS + "ConnectionString").endswith("\\SEGUIMIENTO\\Nuevo\\" + flujo.archivo.nombre)
    assert interno.get(DTS + "Format") == "Delimited"
    assert interno.get(DTS + "CodePage") == "65001"
    assert interno.get(DTS + "ColumnNamesInFirstDataRow") == "True"
    assert interno.get(DTS + "TextQualifier") == "_x0022_"
    columnas = list(interno.iter(DTS + "FlatFileColumn"))
    assert [c.get(DTS + "ObjectName") for c in columnas] == [c.nombre for c in flujo.archivo.columnas]
    assert all(c.get(DTS + "ColumnDelimiter") == "_x002C_" for c in columnas[:-1])
    assert columnas[-1].get(DTS + "ColumnDelimiter") == "_x000D__x000A_"

    pipe = ejecutables(r)[flujo.tarea].find(f"{DTS}ObjectData/pipeline")
    fuente = next(
        c
        for c in pipe.iter("component")
        if c.get("componentClassID") == "Microsoft.FlatFileSource"
        and c.find("connections/connection").get("connectionManagerRefId").endswith(f"[{flujo.archivo.conexion}]")
    )
    assert props(fuente)["RetainNulls"] == "false"  # celda vacia -> ''
    salida = [oc for oc in fuente.find("outputs/output").iter("outputColumn")]
    for oc, col in zip(salida, flujo.archivo.columnas):
        assert oc.get("name") == col.nombre
        assert _TIPO_FF[oc.get("dataType")] == col.tipo, col.nombre
        assert (int(oc.get("length")) if oc.get("length") else None) == col.ancho, col.nombre


def test_derived_column_replace_de_correos():
    r = raiz(paquete("03"))
    pipe = ejecutables(r)[m.FLUJO_TEMP_CORREOS.tarea].find(f"{DTS}ObjectData/pipeline")
    derivada = next(c for c in pipe.iter("component") if c.get("componentClassID") == "Microsoft.DerivedColumn")
    entrada = next(ic for ic in derivada.iter("inputColumn") if props(ic).get("FriendlyExpression"))
    (posicion, buscar, reemplazar), = m.FLUJO_TEMP_CORREOS.reemplazos
    assert entrada.get("cachedName") == m.ARCHIVO_CORREOS.columnas[posicion].nombre
    assert props(entrada)["FriendlyExpression"] == f'REPLACE([{entrada.get("cachedName")}],"{buscar}","{reemplazar}")'


def test_execute_process_descripciones_nc():
    pq = paquete("06")
    e = ejecutables(raiz(pq))["Package\\CARGA DESCRIPCIONES NC\\Carga Descripciones NC"]
    datos = next(x for x in e.find(f"{DTS}ObjectData") if x.tag.endswith("ExecuteProcessData"))
    assert datos.get("Arguments") == "Carga_Reporte_Descripciones_NC_Chile.py"
    assert datos.get("FailTaskIfReturnCodeIsNotSuccessValue") == "False"
    assert any(isinstance(t, TareaDescripcionesNC) and t.nombre == e.get(DTS + "refId") for t in pq.tareas)
    cm = next(c for c in raiz(pq).iter(DTS + "ConnectionManager") if c.get(DTS + "ObjectName") == m.ARCHIVO_DESCRIPCIONES_NC.conexion)
    assert cm.find(f"{DTS}ObjectData/{DTS}ConnectionManager").get(DTS + "ConnectionString").endswith(m.ARCHIVO_DESCRIPCIONES_NC.nombre)


# --------------------------------------------------------------------------- #
# 8. Credenciales
# --------------------------------------------------------------------------- #
def test_sin_credenciales_en_el_codigo():
    patron = re.compile(r"(PWD|Password|CLIENT_SECRET)\s*=\s*['\"][^'\"{]+['\"]", re.IGNORECASE)
    for ruta in list((RAIZ / "src").rglob("*.py")) + [RAIZ / "main.py"] + list((RAIZ / "tools").rglob("*.py")):
        texto = ruta.read_text(encoding="utf-8")
        assert not patron.search(texto), ruta
        assert "trusted_connection" not in texto.lower(), ruta
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()
