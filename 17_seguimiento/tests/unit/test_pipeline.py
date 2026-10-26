from __future__ import annotations

import pytest

import mappings as m
from exceptions import PipelineError
from paquetes import PAQUETES, seleccionar
from paquetes.base import TareaTransaccion
from pipeline import ADVERTENCIA, OK, OMITIDA, SeguimientoPipeline
from tests.unit.fakes import FuenteFalsa, LoaderFalso, csv_crudo, esquema_de


def _archivos_validos() -> dict[str, bytes]:
    casos = [""] * 42
    casos[0], casos[4], casos[31] = "19412328", "06-10-2026 10:13", "17-10-2026 9:15"
    casos[22] = "Asunto\nen dos lineas"
    return {
        m.ARCHIVO_CASOS.nombre: csv_crudo([c.nombre for c in m.ARCHIVO_CASOS.columnas], [casos]),
        m.ARCHIVO_NOMBRE_CONTACTO.nombre: csv_crudo(["a"] * 5, [["19412328", "N", "c@x.cl", "", "2"]]),
        m.ARCHIVO_CASOS_B.nombre: csv_crudo(["a"] * 14, [["19412328"] + [""] * 13]),
        m.ARCHIVO_CORREOS.nombre: csv_crudo(["a"] * 10, [["d", "p", "18-10-2026 10:31", "19412328", "", "1", "A", "O", "C", "E"]]),
        m.ARCHIVO_HISTORIAL.nombre: csv_crudo(["a"] * 6, [["19412328", "M", "23-10-2026 14:31", "Estado", "Nuevo", "Asignado"]]),
        m.ARCHIVO_COMENTARIOS.nombre: csv_crudo(["a"] * 5, [["19412328", "M", "23-10-2026 14:31", "1", "Hola\nchao"]]),
        m.ARCHIVO_DESCRIPCIONES_NC.nombre: csv_crudo(["a", "b"], [["12250117", "FOLIO NC 1"]]),
    }


def _loader(**kw) -> LoaderFalso:
    return LoaderFalso({f.tabla: esquema_de(f) for f in m.TODOS_LOS_FLUJOS}, **kw)


def test_corrida_completa_en_orden_02_03_04_06_07():
    loader = _loader()
    resultado = SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), PAQUETES).run()
    esperadas = [(p.codigo, t.nombre) for p in PAQUETES for t in p.tareas]
    assert [(r.paquete, r.tarea) for r in resultado.tareas] == esperadas
    assert all(r.estado == OK for r in resultado.tareas)
    assert sum(1 for e in loader.eventos if e[0] == "sesion") == len(PAQUETES)  # una sesion por paquete
    scripts = loader.scripts()
    assert scripts[0] == PAQUETES[0].tareas[0].script
    assert scripts[-1] == PAQUETES[-1].tareas[-1].script
    assert ("sp_folios_nc",) in loader.eventos


def test_no_se_ejecutan_las_tareas_redundantes():
    loader = _loader()
    SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), PAQUETES).run()
    scripts = loader.scripts()
    assert not any(s.lstrip().upper().startswith("TRUNCATE TABLE [CL_TEMPORALES].[DBO].[TBL_SALESFORCE") for s in scripts)
    assert not any("TBL_SALESFORCE_DATOS_CONTACTO" in s or "TIPIFICACIONES" in s for s in scripts)
    assert {e[1] for e in loader.eventos if e[0] == "temporal"} == set(m.TABLAS_TEMPORALES)


def test_casos_cargados_con_contacto_cruzado_y_saltos_crlf():
    loader = _loader()
    SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), PAQUETES[:1]).run()
    (fila,) = loader.cargas["TBL_SALESFORCE_CASOS"]
    columnas = m.FLUJO_TEMP_REPORTE_CASOS.columnas_insert
    valores = dict(zip(columnas, fila))
    assert valores["Nombre de contacto"] == "N"
    assert valores["Teléfono Contacto"] is None  # '' -> NULL (Agrega Nombre de Contacto)
    assert valores["Asunto"] == "Asunto\r\nen dos lineas"


def test_borrado_e_insercion_de_casos_en_una_transaccion():
    transacciones = [t for t in PAQUETES[0].tareas if isinstance(t, TareaTransaccion)]
    assert [[x.nombre.rsplit("\\", 1)[-1] for x in t.tareas] for t in transacciones] == [
        ["LIMPIA BASE CHILE", "CARGA CASOS CHILE"],
        ["LIMPIA CASOS B CHILE", "CARGA CASOS B CHILE"],
    ]


def test_un_fallo_detiene_el_paquete_y_los_siguientes():
    # falla la CARGA CORREOS (03): no se ejecuta su Log Fin ni 04/06/07
    loader = _loader(falla_sql="MERGE [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CORREOS]")
    with pytest.raises(PipelineError) as exc:
        SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), PAQUETES).run()
    assert exc.value.paquete == "03"
    assert "CARGA CORREOS" in exc.value.tarea
    scripts = loader.scripts()
    assert "MERGE [CL_SALESFORCE_ACTUAL].[dbo].[TBL_CORREOS]" in scripts[-1]  # la ultima: la que fallo
    assert sum("Update_Reporte_Correos_Chile" in s for s in scripts) == 1  # Log Inicio si, Log Fin no
    assert not any("TBL_HISTORIAL_CASOS" in s for s in scripts)
    assert not any("SP_INSUMOS_SEGUIMIENTO" in s for s in scripts)


def test_error_de_datos_no_carga_ningun_destino():
    archivos = _archivos_validos()
    archivos[m.ARCHIVO_NOMBRE_CONTACTO.nombre] = csv_crudo(["a"] * 5, [["19412328", "N", "c"]])  # faltan columnas
    loader = _loader()
    with pytest.raises(PipelineError):
        SeguimientoPipeline(loader, FuenteFalsa(archivos), PAQUETES[:1]).run()
    assert not [e for e in loader.eventos if e[0] == "temporal"]


def test_descripciones_nc_falla_como_advertencia_y_el_paquete_continua():
    loader = _loader(falla_nc=True)
    p06 = [p for p in PAQUETES if p.codigo == "06"]
    resultado = SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), p06).run()
    assert [r.tarea for r in resultado.advertencias] == ["Package\\CARGA DESCRIPCIONES NC\\Carga Descripciones NC"]
    assert resultado.tareas[-1].tarea == "Package\\Log Fin" and resultado.tareas[-1].estado == OK
    assert ("sp_folios_nc",) not in loader.eventos  # el SP solo corre si la carga funciono


def test_descripciones_nc_sin_archivo_tambien_es_advertencia():
    p06 = [p for p in PAQUETES if p.codigo == "06"]
    fuente = FuenteFalsa(_archivos_validos(), falla={m.ARCHIVO_DESCRIPCIONES_NC.nombre})
    resultado = SeguimientoPipeline(_loader(), fuente, p06).run()
    assert resultado.advertencias[0].estado == ADVERTENCIA


def test_error_de_descarga_se_informa_en_el_paquete_que_usa_el_archivo():
    fuente = FuenteFalsa(_archivos_validos(), falla={m.ARCHIVO_HISTORIAL.nombre})
    loader = _loader()
    with pytest.raises(PipelineError) as exc:
        SeguimientoPipeline(loader, fuente, PAQUETES).run()
    assert exc.value.paquete == "04"
    assert any("Update_Reporte_Correos_Chile" in s for s in loader.scripts())  # 02 y 03 corrieron


def test_solo_validar_no_ejecuta_sql_ni_carga():
    loader = _loader()
    resultado = SeguimientoPipeline(loader, FuenteFalsa(_archivos_validos()), PAQUETES).run(solo_validar=True)
    assert loader.eventos == []
    assert {r.estado for r in resultado.tareas} == {OMITIDA}


def test_seleccion_de_paquetes():
    assert [p.codigo for p in seleccionar()] == ["02", "03", "04", "06", "07"]
    assert [p.codigo for p in seleccionar(desde="04")] == ["04", "06", "07"]
    assert [p.codigo for p in seleccionar(solo=["07", "03"])] == ["03", "07"]
    with pytest.raises(Exception):
        seleccionar(desde="05")
