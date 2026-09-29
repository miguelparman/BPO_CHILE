"""Equivalencia estructural SSIS <-> Python.

Estas pruebas leen el paquete ORIGINAL (CL_Proc_Trafico_FCR_02.dtsx) y
verifican que la migracion reproduce exactamente:

  1. el T-SQL de cada Execute SQL Task (byte a byte, salvo finales de linea);
  2. el orden del Control Flow (Precedence Constraints);
  3. la variable User::Periodo (Int32) y los parametros de las tareas;
  4. la logica de Alimenta Tabla que Python reimplementa, extraida del propio
     T-SQL: las 5 bases (tabla, SERVICIO, BASE), el filtro de periodo, la
     ventana LEAD, los 14 umbrales, el CASE de TRAMO_QUIEBRE, el orden de
     columnas del INSERT posicional y el orden del UNION ALL.

Se omiten (skip) si el .dtsx no esta disponible en la maquina. Ruta
configurable con DTSX_PATH.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mappings
import sql

DTSX = Path(
    os.getenv("DTSX_PATH", r"C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_Trafico_FCR_02.dtsx")
)
DTS = "{www.microsoft.com/SqlServer/Dts}"
SQLNS = "{www.microsoft.com/sqlserver/dts/tasks/sqltask}"

pytestmark = pytest.mark.skipif(not DTSX.exists(), reason=f"no se encuentra el .dtsx original: {DTSX}")

SCRIPTS = {
    "Package\\Log Inicio": sql.LOG_INICIO,
    "Package\\Proceso Carga Tabla\\Limpia Tabla": sql.LIMPIA_TABLA,
    "Package\\Proceso Carga Tabla\\Alimenta Tabla": sql.ALIMENTA_TABLA,
    "Package\\Log Fin": sql.LOG_FIN,
}


@pytest.fixture(scope="module")
def raiz():
    return ET.parse(DTSX).getroot()


def _ejecutables(raiz) -> dict[str, ET.Element]:
    return {e.get(DTS + "refId"): e for e in raiz.iter(DTS + "Executable")}


def _norm(texto: str) -> str:
    return texto.replace("\r\n", "\n")


@pytest.fixture(scope="module")
def alimenta_activo(raiz):
    """T-SQL de Alimenta Tabla sin el bloque comentado 'PROCESO ANTERIOR'."""
    texto = next(_ejecutables(raiz)["Package\\Proceso Carga Tabla\\Alimenta Tabla"].iter(SQLNS + "SqlTaskData")).get(
        SQLNS + "SqlStatementSource"
    )
    return _norm(texto).split("---- PROCESO ANTERIOR")[0]


@pytest.fixture(scope="module")
def bloques(alimenta_activo):
    """{#temp: texto del SELECT ... INTO #temp FROM (...)} en orden de aparicion."""
    partes = re.split(r"INTO (#TBL_TMP_\w+)", alimenta_activo)
    # partes = [antes, nombre1, despues1, nombre2, despues2, ...]; el SELECT XB
    # de cada bloque queda al final del trozo anterior al INTO.
    return {
        partes[i]: partes[i - 1].rsplit("SELECT XB.*", 1)[1]
        + partes[i + 1].split("SELECT XB.*")[0].split("INSERT INTO")[0]
        for i in range(1, len(partes), 2)
    }


# --------------------------------------------------------------------------- #
# 1. T-SQL literal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", list(SCRIPTS))
def test_tsql_identico_al_dtsx(raiz, ref):
    original = next(_ejecutables(raiz)[ref].iter(SQLNS + "SqlTaskData")).get(SQLNS + "SqlStatementSource")
    assert _norm(SCRIPTS[ref]) == _norm(original)


def test_todas_las_tareas_estan_migradas_y_no_hay_otros_componentes(raiz):
    tipos = {r: e.get(DTS + "ExecutableType") for r, e in _ejecutables(raiz).items() if r != "Package"}
    assert {r for r, t in tipos.items() if t == "Microsoft.ExecuteSQLTask"} == set(SCRIPTS)
    # Sin Data Flow ni Execute Process: el paquete no invoca scripts .py.
    assert set(tipos.values()) == {"Microsoft.ExecuteSQLTask", "STOCK:SEQUENCE"}
    assert not any(e.get(DTS + "Disabled") == "True" for e in _ejecutables(raiz).values())


# --------------------------------------------------------------------------- #
# 2. Orden del Control Flow
# --------------------------------------------------------------------------- #
def test_orden_del_control_flow(raiz):
    aristas = {(p.get(DTS + "From"), p.get(DTS + "To")) for p in raiz.iter(DTS + "PrecedenceConstraint")}
    assert aristas == {
        ("Package\\Log Inicio", "Package\\Proceso Carga Tabla"),
        ("Package\\Proceso Carga Tabla", "Package\\Log Fin"),
        ("Package\\Proceso Carga Tabla\\Limpia Tabla", "Package\\Proceso Carga Tabla\\Alimenta Tabla"),
    }
    # todas "On Success" (sin DTS:Value = 1 Failure / 2 Completion)
    assert all(p.get(DTS + "Value") in (None, "0") for p in raiz.iter(DTS + "PrecedenceConstraint"))


# --------------------------------------------------------------------------- #
# 3. User::Periodo y parametros
# --------------------------------------------------------------------------- #
def test_user_periodo_es_int32_constante(raiz):
    var = next(v for v in raiz.iter(DTS + "Variable") if v.get(DTS + "ObjectName") == "Periodo")
    assert var.find(DTS + "VariableValue").get(DTS + "DataType") == "3"  # DT_I4 / Int32
    # Expresion constante editada a mano; Python la reemplaza por el calculo
    # automatico de 12_trafico (decision del usuario, ver models.calcular_periodo).
    assert re.fullmatch(r"\d{6}", var.get(DTS + "Expression"))


@pytest.mark.parametrize("ref", ["Package\\Proceso Carga Tabla\\Limpia Tabla", "Package\\Proceso Carga Tabla\\Alimenta Tabla"])
def test_parametro_unico_user_periodo(raiz, ref):
    params = list(_ejecutables(raiz)[ref].iter(SQLNS + "ParameterBinding"))
    assert [(p.get(SQLNS + "DtsVariableName"), p.get(SQLNS + "ParameterDirection")) for p in params] == [
        ("User::Periodo", "Input")
    ]
    assert SCRIPTS[ref].count("?") == 1


def test_limpia_tabla_borra_desde_el_periodo():
    assert re.sub(r"\s+", " ", sql.LIMPIA_TABLA) == "DELETE [CL_TRAFICO].[dbo].[TBL_FCR] WHERE YEAR(FECHA)*100+MONTH(FECHA)>=?"
    assert sql.CONTAR_PERIODO.endswith("WHERE YEAR(FECHA)*100+MONTH(FECHA)>=?")


# --------------------------------------------------------------------------- #
# 4. Logica de Alimenta Tabla
# --------------------------------------------------------------------------- #
def test_las_5_bases(bloques):
    extraidas = []
    for temp, texto in bloques.items():
        tabla = re.search(r"FROM (?:CL_TRAFICO\.dbo\.|\[CL_TRAFICO\]\.\[dbo\]\.\[)(\w+)", texto).group(1)
        base = re.search(r"'(\w+)' BASE", texto).group(1)
        servicio = re.findall(r"SERVICIO IN \('(\w+)'\)", texto)
        extraidas.append(mappings.BaseFCR(temp, tabla, *servicio, base))
    assert tuple(extraidas) == mappings.BASES


def test_filtro_de_periodo_y_columnas_xa_iguales_en_cada_base(bloques):
    c = mappings.COLUMNA_INICIO
    for texto in bloques.values():
        assert f"WHERE CONVERT(VARCHAR(6),[{c}],112)>=@PERIODO AND SERVICIO IN" in texto
        assert (
            f"SELECT CAST([{c}] AS DATE)FECHA,CAST(CAST([{c}] AS TIME) AS VARCHAR(8))HORA,ANI,SERVICIO,LOGINID,"
        ) in texto
        assert f" BASE,CAST([{c}] AS DATETIME)[FECHA/HORA]" in texto


def test_ventana_lead_por_ani_y_servicio(bloques):
    for texto in bloques.values():
        assert (
            "LEAD ( [FECHA/HORA] ) OVER (  partition by ANI,SERVICIO order by  [FECHA/HORA] asc) [FECHA/HORA-PROXIMO]"
            in texto
        )


def test_umbrales_fcr(bloques):
    esperado = [(u.segundos, u.columna) for u in mappings.UMBRALES]
    for texto in bloques.values():
        umbrales = re.findall(
            r"CASE WHEN DATEDIFF\(SECOND, \[FECHA/HORA\], \[FECHA/HORA-PROXIMO\]\) <= (\d+) THEN 0 ELSE 1 END (\w+)", texto
        )
        assert [(int(s), c) for s, c in umbrales] == esperado


def test_tramo_quiebre(alimenta_activo):
    insert = alimenta_activo.split("INSERT INTO [CL_TRAFICO].[dbo].[TBL_FCR]")[1]
    assert re.findall(r"WHEN (\w+) = 0 THEN '([^']+)'", insert) == [(u.columna, u.tramo) for u in mappings.UMBRALES]
    assert f"ELSE '{mappings.SIN_QUIEBRE}'" in insert and "END AS TRAMO_QUIEBRE" in insert


def test_union_all_en_el_orden_de_bases(alimenta_activo):
    insert = alimenta_activo.split("INSERT INTO [CL_TRAFICO].[dbo].[TBL_FCR]")[1]
    assert re.findall(r"SELECT \* FROM (#TBL_TMP_\w+)", insert) == [b.tabla_temporal for b in mappings.BASES]
    assert insert.count("UNION ALL") == len(mappings.BASES) - 1


def test_insert_posicional_en_el_orden_de_columnas_destino(bloques, alimenta_activo):
    """A.* = columnas XA + [FECHA/HORA-PROXIMO] + FCR_x, luego TRAMO_QUIEBRE."""
    texto = next(iter(bloques.values()))
    xa = ["FECHA", "HORA", "ANI", "SERVICIO", "LOGINID", "BASE", "FECHA/HORA"]
    fcr = re.findall(r"THEN 0 ELSE 1 END (\w+)", texto)
    assert xa + ["FECHA/HORA-PROXIMO"] + fcr + ["TRAMO_QUIEBRE"] == list(mappings.NOMBRES_DESTINO)
    assert re.search(r"INSERT INTO \[CL_TRAFICO\]\.\[dbo\]\.\[TBL_FCR\]\s+SELECT\s+A\.\*,", alimenta_activo)
