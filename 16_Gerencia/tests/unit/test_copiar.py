from datetime import datetime

import mappings
from ingesta.copiar import CopiadorSharePoint
from tests.unit.fakes import FakeProveedor, FakeSharePoint, fila, xlsx

G, E = mappings.GERENCIA, mappings.ESCALAMIENTO
CONTENIDO = xlsx([fila(datetime(2026, 1, 1), 1)])


def _copiador(origen: FakeSharePoint, destino: FakeSharePoint) -> CopiadorSharePoint:
    return CopiadorSharePoint(FakeProveedor(origen), FakeProveedor(destino))


def test_copia_bpo_a_reporting_mismo_nombre():
    origen = FakeSharePoint({G.ruta_bpo: CONTENIDO})
    destino = FakeSharePoint(carpetas=[G.carpeta_reporting])
    [r] = _copiador(origen, destino).copiar([G])
    assert r.ok and r.bytes_copiados == len(CONTENIDO)
    assert destino.subidas == [(G.carpeta_reporting, G.archivo)]
    assert destino.archivos[G.ruta_reporting] == CONTENIDO


def test_rutas_de_los_enlaces_del_requerimiento():
    assert G.ruta_bpo == "Planificación y Control/Insumos/Chile/Especializados/ALTA GERENCIA TCH/ALTA GERENCIA_NVO ARCHIVO.xlsx"
    assert mappings.T_ATIENDO.ruta_reporting == (
        "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/02 ESPECIALIZADOS/T-ATIENDO/CASOS SALESFORCE - T-ATIENDO.xlsx"
    )


def test_sharepoint_reescribe_metadatos_no_es_error():
    """SharePoint cambia el tamano del archivo al subirlo: se comparan los datos."""

    def reescribir(contenido):
        import io

        import openpyxl

        libro = openpyxl.load_workbook(io.BytesIO(contenido))
        libro.properties.title = "metadatos de SharePoint"
        buffer = io.BytesIO()
        libro.save(buffer)
        return buffer.getvalue()

    destino = FakeSharePoint(carpetas=[G.carpeta_reporting], transformar_subida=reescribir)
    [r] = _copiador(FakeSharePoint({G.ruta_bpo: CONTENIDO}), destino).copiar([G])
    assert r.ok and len(destino.archivos[G.ruta_reporting]) != len(CONTENIDO)


def test_datos_distintos_tras_subir_es_error():
    otro = xlsx([fila(datetime(2026, 1, 1), 2)])
    destino = FakeSharePoint(carpetas=[G.carpeta_reporting], transformar_subida=lambda _: otro)
    [r] = _copiador(FakeSharePoint({G.ruta_bpo: CONTENIDO}), destino).copiar([G])
    assert not r.ok and "no coinciden" in r.error


def test_un_archivo_que_falla_no_detiene_los_demas():
    origen = FakeSharePoint({E.ruta_bpo: CONTENIDO})  # falta el de GERENCIA
    destino = FakeSharePoint(carpetas=[G.carpeta_reporting, E.carpeta_reporting])
    resultados = _copiador(origen, destino).copiar([G, E])
    assert [(r.flujo, r.ok) for r in resultados] == [("GERENCIA", False), ("ESCALAMIENTO", True)]
