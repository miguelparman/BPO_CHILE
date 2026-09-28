"""Equivalencia estructural SSIS <-> Python.

Estas pruebas leen el paquete ORIGINAL (CL_Proc_Trafico_01.dtsx) y los
scripts .py que ejecutaba (101_trafico/) y verifican que la migracion
reproduce exactamente:

  1. el T-SQL de cada Execute SQL Task (byte a byte, salvo finales de linea);
  2. el orden del Control Flow (Precedence Constraints);
  3. la variable User::Periodo y el parametro de DELETE PERIODO;
  4. el Data Flow CARGA: linaje columna a columna, tipo/largo de cada Data
     Conversion, disposiciones FailComponent/IgnoreFailure y el Conditional Split;
  5. las columnas y filtros de los 7 scripts Traslado_Trafico_Servidor_55_*.py.

Se omiten (skip) si el .dtsx o 101_trafico/ no estan disponibles en la
maquina. Rutas configurables con DTSX_PATH y SCRIPTS_ORIGINALES_DIR.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mappings
import sql

DTSX = Path(os.getenv("DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_Trafico_01.dtsx"))
SCRIPTS_DIR = Path(
    os.getenv("SCRIPTS_ORIGINALES_DIR", str(Path(__file__).resolve().parents[3] / "101_trafico"))
)
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable")}


def _cadena(raiz, contenedor: str) -> list[str]:
    """Ordena las tareas hijas de un contenedor siguiendo sus Precedence Constraints."""
    hijos = [r for r in _ejecutables(raiz) if r.rsplit("\\", 1)[0] == contenedor]
    aristas = {}
    for p in raiz.iter(DTS + "PrecedenceConstraint"):
        a, b = p.get(DTS + "From"), p.get(DTS + "To")
        if a in hijos and b in hijos:
            aristas.setdefault(a, []).append(b)
    destinos = {b for bs in aristas.values() for b in bs}
    inicio = [h for h in hijos if h not in destinos]
    orden, actual = [], inicio
    while actual:
        orden.extend(actual)
        actual = [b for a in actual for b in aristas.get(a, [])]
    return [o.rsplit("\\", 1)[1] for o in orden]


def _norm(texto: str) -> str:
    return texto.replace("\r\n", "\n")


# --------------------------------------------------------------------------- #
# 1. T-SQL literal
# --------------------------------------------------------------------------- #
SCRIPTS = {
    "Package\\Log Inicio": sql.LOG_INICIO,
    "Package\\TEMPORALES\\TRUNCA TABLAS": sql.TEMPORALES_TRUNCA_TABLAS,
    "Package\\TEMPORALES\\UPDATE": sql.TEMPORALES_UPDATE,
    "Package\\LIMPIA TEMPORALES\\FORMATEANDO ANI": sql.LIMPIA_FORMATEANDO_ANI,
    "Package\\LIMPIA TEMPORALES\\UPDATE RUT": sql.LIMPIA_UPDATE_RUT,
    "Package\\LIMPIA TEMPORALES\\UPDATE COD_DNI": sql.LIMPIA_UPDATE_COD_DNI,
    "Package\\LIMPIA TEMPORALES\\UPDATE SEGMENTO - UPDATE SUBSEGMENTO": sql.LIMPIA_UPDATE_SEGMENTO,
    "Package\\LIMPIA TEMPORALES\\SEGMENTO COLA": sql.LIMPIA_SEGMENTO_COLA,
    "Package\\LIMPIA TEMPORALES\\LLAMA CCAA?": sql.LIMPIA_LLAMA_CCAA,
    "Package\\CL_TRAFICO\\DELETE PERIODO": sql.CL_TRAFICO_DELETE_PERIODO,
    "Package\\CL_TRAFICO\\UPDATE_WSP": sql.CL_TRAFICO_UPDATE_WSP,
    "Package\\Log Fin": sql.LOG_FIN,
}


@pytest.mark.parametrize("ref", list(SCRIPTS))
def test_tsql_identico_al_dtsx(raiz, ref):
    tarea = _ejecutables(raiz)[ref]
    original = next(tarea.iter(SQLNS + "SqlTaskData")).get(SQLNS + "SqlStatementSource")
    assert _norm(SCRIPTS[ref]) == _norm(original)


def test_todas_las_execute_sql_task_habilitadas_estan_migradas(raiz):
    tareas = {
        r
        for r, e in _ejecutables(raiz).items()
        if e.get(DTS + "ExecutableType") == "Microsoft.ExecuteSQLTask" and not r.startswith("Package\\MENSAJES WSP")
    }
    assert tareas == set(SCRIPTS)


def test_mensajes_wsp_esta_deshabilitado_y_por_eso_no_se_migra(raiz):
    assert _ejecutables(raiz)["Package\\MENSAJES WSP"].get(DTS + "Disabled") == "True"


# --------------------------------------------------------------------------- #
# 2. Orden del Control Flow
# --------------------------------------------------------------------------- #
def test_orden_principal(raiz):
    # Cadena habilitada (se ignora la rama deshabilitada MENSAJES WSP).
    siguiente = {}
    for p in raiz.iter(DTS + "PrecedenceConstraint"):
        siguiente.setdefault(p.get(DTS + "From"), []).append(p.get(DTS + "To"))
    camino, nodo = [], "Package\\Log Inicio"
    while nodo:
        camino.append(nodo.split("\\")[-1])
        nodo = next((n for n in siguiente.get(nodo, []) if "MENSAJES WSP" not in n), None)
    assert camino == ["Log Inicio", "enviar_alerta_trafico", "TEMPORALES", "LIMPIA TEMPORALES", "CL_TRAFICO", "Log Fin"]


def test_orden_temporales_coincide_con_origenes(raiz):
    assert _cadena(raiz, "Package\\TEMPORALES") == ["TRUNCA TABLAS"] + [o.paso for o in mappings.ORIGENES] + ["UPDATE"]


def test_orden_limpia_temporales(raiz):
    assert _cadena(raiz, "Package\\LIMPIA TEMPORALES") == [n for n, _ in sql.LIMPIA_TEMPORALES]


def test_orden_cl_trafico(raiz):
    assert _cadena(raiz, "Package\\CL_TRAFICO") == ["DELETE PERIODO", "CARGA", "UPDATE_WSP"]


def test_execute_process_llaman_a_los_scripts_migrados(raiz):
    ej = _ejecutables(raiz)
    for o in mappings.ORIGENES:
        datos = ej[f"Package\\TEMPORALES\\{o.paso}"].find(DTS + "ObjectData")[0]
        assert datos.get("Arguments") == o.script_original
    alerta = ej["Package\\enviar_alerta_trafico"].find(DTS + "ObjectData")[0]
    assert alerta.get("Arguments") == "enviar_alerta_trafico.py"
    assert alerta.get("FailTaskIfReturnCodeIsNotSuccessValue") == "False"  # no detiene el paquete


# --------------------------------------------------------------------------- #
# 3. Variable User::Periodo y parametro de DELETE PERIODO
# --------------------------------------------------------------------------- #
def test_expresion_de_user_periodo(raiz):
    var = next(v for v in raiz.iter(DTS + "Variable") if v.get(DTS + "ObjectName") == "Periodo")
    expr = re.sub(r"\s+", "", var.get(DTS + "Expression"))
    assert expr == (
        'DAY(GETDATE())<=4?(YEAR(DATEADD("Month",-1,GETDATE()))*100+MONTH(DATEADD("Month",-1,GETDATE())))'
        ":(YEAR(GETDATE())*100+MONTH(GETDATE()))"
    )


def test_delete_periodo_usa_user_periodo_como_unico_parametro(raiz):
    tarea = _ejecutables(raiz)["Package\\CL_TRAFICO\\DELETE PERIODO"]
    params = list(tarea.iter(SQLNS + "ParameterBinding"))
    assert [p.get(SQLNS + "DtsVariableName") for p in params] == ["User::Periodo"]
    assert sql.CL_TRAFICO_DELETE_PERIODO.count("?") == 1


# --------------------------------------------------------------------------- #
# 4. Data Flow CARGA
# --------------------------------------------------------------------------- #
_TIPOS = {"str": "DT_STR", "wstr": "DT_WSTR", "i4": "DT_I4", "dbTimeStamp": "DT_DBTIMESTAMP", "dbDate": "DT_DBDATE"}


def _linaje(raiz) -> dict:
    """{componente destino: (tabla, origen, {columna destino: (origen, conversion, largo, ignora)})}"""
    pipe = next(e for e in raiz.iter(DTS + "Executable") if e.get(DTS + "ExecutableType") == "Microsoft.Pipeline")
    pipe = pipe.find(f"{DTS}ObjectData/pipeline")
    corto = lambda s: s.replace("Package\\CL_TRAFICO\\CARGA\\", "")  # noqa: E731
    cols = {}
    for comp in pipe.iter("component"):
        for out in comp.iter("output"):
            for oc in out.iter("outputColumn"):
                props = {p.get("name"): (p.text or "") for p in oc.iter("property")}
                cols[oc.get("refId")] = dict(
                    comp=corto(comp.get("refId")), cls=comp.get("componentClassID"), name=oc.get("name"),
                    dt=oc.get("dataType"), len=oc.get("length"), err=oc.get("errorRowDisposition"),
                    src=props.get("SourceInputColumnLineageID", "").strip("#{}") or None,
                )
    resultado = {}
    for comp in pipe.iter("component"):
        if comp.get("componentClassID") != "Microsoft.OLEDBDestination":
            continue
        tabla = next(p.text for p in comp.iter("property") if p.get("name") == "OpenRowset")
        inp = comp.find("inputs/input")
        ext = {e.get("refId"): e.get("name") for e in inp.iter("externalMetadataColumn")}
        columnas, origen = {}, None
        for ic in inp.iter("inputColumn"):
            cadena, lid = [], ic.get("lineageId")
            while lid:
                cadena.append(cols[lid])
                lid = cols[lid]["src"]
            if cadena[-1]["cls"] == "Microsoft.OLEDBSource":
                origen = cadena[-1]["comp"]
            conv = next((c for c in cadena if c["cls"] in ("Microsoft.DataConvert", "Microsoft.DerivedColumn")), None)
            columnas[ext[ic.get("externalMetadataColumnId")]] = (
                cadena[-1]["name"],
                _TIPOS[conv["dt"]] if conv else None,
                int(conv["len"]) if conv and conv["len"] not in (None, "0") else None,
                bool(conv and conv["err"] == "IgnoreFailure"),
            )
        resultado[corto(comp.get("refId"))] = (tabla.replace("[dbo].[", "").rstrip("]"), origen, columnas)
    return resultado


def test_carga_mapea_las_mismas_columnas_con_las_mismas_conversiones(raiz):
    linaje = _linaje(raiz)
    assert set(linaje) == {d.componente for d in mappings.DESTINOS}
    for d in mappings.DESTINOS:
        tabla, origen, columnas = linaje[d.componente]
        assert tabla == d.tabla
        assert origen == d.tabla_origen.replace("TBL_TRAFICO_", "TBL_55_")
        esperado = {c.destino: (c.origen, c.conversion, c.largo, c.ignorar_fallo) for c in d.columnas}
        assert esperado == columnas, d.componente


def test_conditional_split(raiz):
    split = next(c for c in raiz.iter("component") if c.get("componentClassID") == "Microsoft.ConditionalSplit")
    salidas = []
    for out in split.iter("output"):
        props = {p.get("name"): p.text for p in out.iter("property")}
        if props.get("FriendlyExpression"):
            salidas.append((int(props["EvaluationOrder"]), out.get("name"), props["FriendlyExpression"], out.get("errorRowDisposition")))
    salidas.sort()
    esperado = [
        (salida, " && ".join(f'{c} == "{v}"' for c, v in cond.items())) for salida, cond in mappings.SPLIT_ATENDIDA
    ]
    assert [(s[1], s[2]) for s in salidas] == esperado
    assert all(s[3] == "FailComponent" for s in salidas)


def test_columnas_derivadas_de_callback(raiz):
    derivada = next(c for c in raiz.iter("component") if c.get("componentClassID") == "Microsoft.DerivedColumn")
    exprs = {
        oc.get("name"): next(p.text for p in oc.iter("property") if p.get("name") == "FriendlyExpression")
        for oc in derivada.iter("outputColumn")
        if any(p.get("name") == "FriendlyExpression" for p in oc.iter("property"))
    }
    assert exprs == {"FECHA_DATE": "(DT_DATE)FECHA", "FECHA_HORA": "SUBSTRING((DT_STR,30,1252)FECHA,12,8)"}


# --------------------------------------------------------------------------- #
# 5. Scripts .py originales (TEMPORALES)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not SCRIPTS_DIR.exists(), reason=f"no se encuentra {SCRIPTS_DIR}")
@pytest.mark.parametrize("origen", mappings.ORIGENES, ids=lambda o: o.paso)
def test_scripts_originales(origen):
    texto = (SCRIPTS_DIR / origen.script_original).read_text(encoding="utf-8", errors="replace")
    insert = re.search(r"INSERT INTO \[CL_TEMPORALES\]\.\[dbo\]\.\[(\w+)\]\s*\((.*?)\)\s*VALUES", texto, re.S)
    assert insert.group(1) == origen.tabla_temporal
    assert tuple(re.findall(r"\[(\w+)\]", insert.group(2))) == origen.columnas
    tabla_origen = re.search(r"FROM \[Externos_Frac\]\.\[dbo\]\.\[(\w+)\]", texto).group(1)
    assert f"{tabla_origen}.csv" == origen.archivo  # el CSV se llama igual que la tabla
    if origen.periodo_desde_fecha:
        assert f"CONVERT(VARCHAR(6),[{origen.columna_periodo}],112) >= ?" in texto
    else:
        assert f"WHERE {origen.columna_periodo} >= ?" in texto
