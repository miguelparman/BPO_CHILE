"""Tests de silver/cargar.py: reglas de ASUNTO_AGRUPADO (orden, mayusculas/tildes,
vacios) y la carga de TBL_CORREO_REGISTRO_SILVER desde bronze (por periodo
y completa)."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from bronze.mappings import TABLA_BANDEJAS, TABLA_REGISTRO
from silver.cargar import (
    ACTUALIZAR_NUMERO_CASO,
    actualizar_numero_caso,
    agrupar_asunto,
    cargar_bandejas_silver,
    cargar_periodo_silver,
    coordinador_desde_origen,
    agregar_jefatura,
    fecha_desde_utc,
    id_place_desde_bandeja,
    jefatura_por_place_fecha,
    normalizar_plataforma,
    recargar_silver_completo,
)
from silver.mappings import (
    COLUMNAS_EXCLUIDAS_SILVER,
    SEPARADOR_CASOS,
    TABLA_BANDEJAS_SILVER,
    TABLA_HISTORICO_PLACES,
    TABLA_REGISTRO_SILVER,
    TABLA_SEGUIMIENTO,
    TIPO_CASO_SEGUIMIENTO,
)
from tests.unit.fakes import FakeDatabaseGateway


@pytest.mark.parametrize(
    ("asunto", "esperado"),
    [
        ("Actualización de correo de contacto de su Service Manager", "PRESENTACIÓN"),
        ("actualizacion de correo de contacto", "PRESENTACIÓN"),
        ("PRESENTACIÓN DE SU EJECUTIVO", "PRESENTACIÓN"),
        ("Presentacion comercial", "PRESENTACIÓN"),
        ("Re: Presentación de Nueva Service Manager", "PRESENTACIÓN"),
        ("[Presentación]", "PRESENTACIÓN"),
        # palabra completa: 'presentacion' dentro de otra palabra no cuenta
        ("RE: Tecno-Aguas SpA// Documentación para representación legal", None),
        ("Presentaciones comerciales", None),
        ("Correo de PRUEBA", "PRUEBA"),
        ("[PROMOSEPTIEMBRE] ¡Beneficios exclusivos para tu empresa!", "PROMO"),
        ("[PROMOSETIEMBRE] ¡Beneficios exclusivos para tu empresa!", "PROMO"),
        ("PROMO SETIEMBRE ¡Beneficios!", "PROMO"),
        ("LLEGARON LAS PROMOCIONES PARA TU EMPRESA", "PROMO"),
        ("Delivery Status Notification (Failure)", "REBOTE"),
        ("Fwd: Delivery Status Notification (Failure)", "REBOTE"),
        ("Notificacion de estado de entrega", "REBOTE"),
        ("Undelivered Mail Returned to Sender.", "REBOTE"),
        ("Re: COTIZACION LINEA+EQUIPO", None),
        ("", None),
        ("   ", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_agrupar_asunto(asunto, esperado):
    assert agrupar_asunto(asunto) == esperado


@pytest.mark.parametrize(
    ("asunto", "contacto", "tipo", "esperado"),
    [
        # SEGUIMIENTO TÉCNICA / VENTAS: solo mensajes de Entrada desde esos correos
        ("Consulta", "seguimiento.moviles@movistar.cl", "Entrada", "SEGUIMIENTO TÉCNICA"),
        ("Consulta", "  SEGUIMIENTO.MOVILES@MOVISTAR.CL ", "Entrada", "SEGUIMIENTO TÉCNICA"),
        ("Consulta", "seguimiento.moviles@movistar.cl", "Salida", None),
        ("Consulta", "otro.seguimiento.moviles@movistar.cl", "Entrada", None),
        ("Consulta", "vanessa.vilcachagua@fractaliasystems.es", "Entrada", "SEGUIMIENTO VENTAS"),
        ("Consulta", "johnny.cossio@fractaliasystems.es", "Entrada", "SEGUIMIENTO VENTAS"),
        ("Consulta", "johnny.cossio@fractaliasystems.es", "Salida", None),
        # varios correos: basta que uno este en la lista
        ("Consulta", "administracion@cafecaribe.cl; braulio.cadenillasf@fractaliasystems.es", "Entrada", "SEGUIMIENTO VENTAS"),
        ("Consulta", "hugo.matias@fractaliasystems.es", "Entrada", None),
        # el remitente gana sobre el asunto (PRUEBA), pero no sobre REBOTE
        ("Correo de prueba", "gerson.pinedo@fractaliasystems.es", "Entrada", "SEGUIMIENTO VENTAS"),
        ("Delivery Status Notification (Failure)", "seguimiento.moviles@movistar.cl", "Entrada", "REBOTE"),
        # SEGUIMIENTO REMEDY: por asunto, Entrada y Salida
        ("[REF:11506148]Actividad Remedy[ID:REQ000000703338]", "x@y.cl", "Entrada", "SEGUIMIENTO REMEDY"),
        ("RE: Actividad Remedy REQ000000701441 CLIENTE INGRESO BAJA PO", "x@y.cl", "Salida", "SEGUIMIENTO REMEDY"),
        ("RE: CREACION DE CLIENTE EN REMEDY", "x@y.cl", "Entrada", None),
        # SEGUIMIENTO COBRANZA: 'Contacto' CONTIENE la casilla, Entrada y Salida,
        # y gana incluso sobre REBOTE
        ("Consulta", "cobranzas@emailmovistar.cl", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Consulta", "cobranzas@emailmovistar.cl", "Salida", "SEGUIMIENTO COBRANZA"),
        ("Consulta", "COBRANZAS@EmailMovistar.CL", None, "SEGUIMIENTO COBRANZA"),
        ("Consulta", "SM52@movistar.cl; cobranzas@emailmovistar.cl", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Consulta", "otro.cobranzas@emailmovistar.cl", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Consulta", "Cobranzas <cobranzas@emailmovistar.cl>", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Delivery Status Notification (Failure)", "cobranzas@emailmovistar.cl", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Correo de prueba", "cobranzas@emailmovistar.cl", "Entrada", "SEGUIMIENTO COBRANZA"),
        ("Consulta", "cobranzas@movistar.cl", "Entrada", None),
        # las reglas de contacto sin contiene=True siguen exigiendo igualdad
        ("Consulta", "x.seguimiento.moviles@movistar.cl.y", "Entrada", None),
        (None, None, None, None),
    ],
)
def test_agrupar_por_contacto_tipo_y_asunto(asunto, contacto, tipo, esperado):
    assert agrupar_asunto(asunto, contacto, tipo) == esperado


def test_rebote_tiene_prioridad_sobre_presentacion():
    # Un rebote cita el asunto original: debe contar como rebote.
    assert agrupar_asunto("No entregable: Actualización de correo de contacto de su Service Manager") == "REBOTE"


def _bronze_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Bandeja": ["SM68@movistar.cl", "otra@movistar.cl"],
            "Tipo": ["Salida", "Entrada"],
            "Contacto": ["cliente@empresa.cl", "Seguimiento.Moviles@movistar.cl"],
            "FechaHora_UTC_Texto": [datetime(2026, 9, 5), datetime(2026, 9, 6)],
            "Asunto": ["Correo de prueba", "Re: consulta"],
            "ID_Mensaje": ["MSG-1", "MSG-2"],
            "ORIGEN": ["Registro_JHON_MORALES_PENA.xlsx", None],
        }
    )


def _places_df() -> pd.DataFrame:
    return pd.DataFrame(
        {"ID_PLACE": ["51030068", "-"], "FECHA": [date(2026, 9, 5), date(2026, 9, 5)], "PLATAFORMA": ["Triada masivo", "SOC"]}
    )


def test_cargar_periodo_silver_lee_bronze_y_reemplaza_el_periodo():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_bronze_df(), _places_df()]
    gateway.filas_a_eliminar = 5
    fecha_inicio, fecha_fin = datetime(2026, 9, 1), datetime(2026, 10, 1)

    eliminadas, insertadas = cargar_periodo_silver(gateway, fecha_inicio, fecha_fin)

    sql_select, params_select = gateway.selects[0]
    assert TABLA_REGISTRO in sql_select and "WHERE" in sql_select
    assert params_select == (fecha_inicio, fecha_fin)
    # Los calculos del Excel no confiables quedan solo en bronze.
    for columna in COLUMNAS_EXCLUIDAS_SILVER:
        assert f"[{columna}]" not in sql_select

    # Historico de places: solo los dias presentes en lo leido de bronze
    # (desde, hasta) + la ultima foto anterior a 'desde'.
    sql_places, params_places = gateway.selects[1]
    assert TABLA_HISTORICO_PLACES in sql_places
    assert params_places == (date(2026, 9, 5), date(2026, 9, 6), date(2026, 9, 5))

    sql_delete, params_delete = gateway.deletes[0]
    assert TABLA_REGISTRO_SILVER in sql_delete
    assert params_delete == (fecha_inicio, fecha_fin)

    insertado = gateway.inserted[TABLA_REGISTRO_SILVER]
    assert list(insertado["ASUNTO_AGRUPADO"]) == ["PRUEBA", "SEGUIMIENTO TÉCNICA"]
    assert list(insertado["COORDINADOR"]) == ["JHON MORALES PENA", None]
    assert insertado["ID_PLACE"].tolist() == [51030068, pd.NA]
    assert list(insertado["JEFATURA"]) == ["Triadas", None]
    assert not {"FECHA", "FECHA_FOTO", "_FILA"} & set(insertado.columns)
    assert (eliminadas, insertadas) == (5, 2)

    # NUMERO_CASO: despues del insert, UPDATE sobre toda silver (sin periodo).
    assert len(gateway.deletes) == 2
    sql_caso, params_caso = gateway.deletes[1]
    assert sql_caso == ACTUALIZAR_NUMERO_CASO and params_caso == ()


def test_recargar_silver_completo_trunca_y_lee_todo_bronze():
    gateway = FakeDatabaseGateway()
    gateway.resultados_select = [_bronze_df(), _places_df()]

    insertadas = recargar_silver_completo(gateway)

    sql_select, params_select = gateway.selects[0]
    assert "WHERE" not in sql_select
    assert params_select == ()
    assert gateway.truncated_tables == [TABLA_REGISTRO_SILVER]
    assert [sql for sql, _ in gateway.deletes] == [ACTUALIZAR_NUMERO_CASO]
    assert insertadas == 2


@pytest.mark.parametrize(
    ("origen", "esperado"),
    [
        ("Registro_JHON_MORALES_PENA.xlsx", "JHON MORALES PENA"),
        ("registro_ana_perez.XLSX", "ana perez"),  # prefijo sin distinguir mayusculas
        ("Registro_RODRIGUEZ_ALEY_DE_GARCIA_MARITZA_JOHANNA.xlsm", "RODRIGUEZ ALEY DE GARCIA MARITZA JOHANNA"),
        ("OTRO_ARCHIVO.xlsx", "OTRO ARCHIVO"),  # sin prefijo: se conserva el nombre
        ("Registro_.xlsx", None),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_coordinador_desde_origen(origen, esperado):
    assert coordinador_desde_origen(origen) == esperado


def test_cargar_bandejas_silver_reemplaza_completo_y_agrega_coordinador():
    gateway = FakeDatabaseGateway()
    gateway.resultado_select = pd.DataFrame(
        {
            "Correo_Bandeja": ["SM1@movistar.cl", "SM2@movistar.cl"],
            "Asesor": ["A", "B"],
            "UltimaRevisionEntrada": [datetime(2026, 9, 22), None],
            "UltimaRevisionSalida": [None, None],
            "ORIGEN": ["Registro_JHON_MORALES_PENA.xlsx", "Registro_ALICIA_DEL_VALLE_SANCHEZ_NAMIAS.xlsx"],
        }
    )

    insertadas = cargar_bandejas_silver(gateway)

    sql_select, params_select = gateway.selects[0]
    assert f"[{TABLA_BANDEJAS}]" in sql_select and "WHERE" not in sql_select
    assert gateway.truncated_tables == [TABLA_BANDEJAS_SILVER]
    assert list(gateway.inserted[TABLA_BANDEJAS_SILVER]["COORDINADOR"]) == [
        "JHON MORALES PENA",
        "ALICIA DEL VALLE SANCHEZ NAMIAS",
    ]
    assert gateway.inserted[TABLA_BANDEJAS_SILVER]["ID_PLACE"].tolist() == [51030001, 51030002]
    assert insertadas == 2


@pytest.mark.parametrize(
    ("bandeja", "esperado"),
    [
        ("SM68@movistar.cl", 51030068),
        ("SM69@movistar.cl", 51030069),
        ("SM73@movistar.cl", 51030073),
        ("SM5@movistar.cl", 51030005),
        ("SM256@movistar.cl", 51030256),
        ("sm68@MOVISTAR.CL", 51030068),  # sin distinguir mayusculas
        ("  SM68@movistar.cl ", 51030068),  # espacios alrededor
        ("SM68@otro.cl", None),
        ("XSM68@movistar.cl", None),
        ("SM@movistar.cl", None),
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_id_place_desde_bandeja(bandeja, esperado):
    assert id_place_desde_bandeja(bandeja) == esperado


def test_fecha_desde_utc_usa_el_dia_utc():
    fechas = pd.Series([datetime(2026, 9, 30, 23, 10), datetime(2026, 10, 1, 0, 30), None])
    assert fecha_desde_utc(fechas).tolist() == [pd.Timestamp(2026, 9, 30), pd.Timestamp(2026, 10, 1), pd.NaT]


@pytest.mark.parametrize(
    ("plataforma", "esperado"),
    [
        ("Triada masivo", "Triadas"),
        ("Triada alto valor", "Triadas"),
        ("Triada_micro", "Triadas"),
        ("TRIADAS", "Triadas"),
        ("CARTERIZADOS", "Carterizados"),
        (" USUARIOS ", "Usuarios"),
        ("Crosselling Chile", "Crosselling Chile"),  # no viene en mayusculas: tal cual
        ("", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_normalizar_plataforma(plataforma, esperado):
    assert normalizar_plataforma(plataforma) == esperado


def test_jefatura_por_place_fecha_descarta_no_numericos_y_desempata():
    dia = date(2026, 9, 5)
    places = pd.DataFrame(
        {
            "ID_PLACE": ["51030068", " 51030068 ", "51030068", "-", "51030069", "51030070", "51030071", "51030071"],
            "FECHA": [dia] * 8,
            "PLATAFORMA": ["Triada masivo", "Triada_micro", "CARTERIZADOS", "SOC", "CARTERIZADOS", None, "B", "A"],
        }
    )

    resultado = jefatura_por_place_fecha(places)

    por_place = dict(zip(resultado["ID_PLACE"].tolist(), resultado["JEFATURA"]))
    # 51030068: la mas frecuente (las dos Triada* -> Triadas); 51030071: empate
    # -> primera alfabetica; '-' y la plataforma NULL se descartan.
    assert por_place == {51030068: "Triadas", 51030069: "Carterizados", 51030071: "A"}


def test_agregar_jefatura_usa_la_foto_del_dia_o_la_anterior_sin_duplicar_filas():
    silver = pd.DataFrame(
        {
            "ID_PLACE": pd.array([51030165, 51030165, 51030165, 51030069, 51030070, None], dtype="Int64"),
            "FechaHora_UTC_Texto": [
                datetime(2026, 9, 30, 23, 0),  # foto del dia 30-09
                datetime(2026, 10, 1, 1, 0),  # dia UTC 01-10: foto del dia
                datetime(2026, 10, 3, 1, 0),  # sin foto del 03-10: la anterior (01-10)
                datetime(2026, 9, 5),  # sin ninguna foto anterior
                datetime(2026, 9, 5),  # place sin fotos
                datetime(2026, 9, 5),  # sin ID_PLACE
            ],
        }
    )
    jefaturas = jefatura_por_place_fecha(
        pd.DataFrame(
            {
                "ID_PLACE": ["51030165", "51030165", "51030069"],
                "FECHA": [date(2026, 9, 30), date(2026, 10, 1), date(2026, 9, 6)],
                "PLATAFORMA": ["CARTERIZADOS", "Triada masivo", "USUARIOS"],
            }
        )
    )

    resultado = agregar_jefatura(silver, jefaturas)

    assert len(resultado) == 6
    assert list(resultado["JEFATURA"]) == ["Carterizados", "Triadas", "Triadas", None, None, None]
    assert list(resultado.columns) == ["ID_PLACE", "FechaHora_UTC_Texto", "JEFATURA"]


def test_actualizar_numero_caso_cruza_conversation_id_sobre_toda_silver():
    sql = ACTUALIZAR_NUMERO_CASO
    assert TABLA_SEGUIMIENTO in sql and f"[{TABLA_REGISTRO_SILVER}]" in sql
    assert "[To Addres]" in sql and "[ConversationID]" in sql and "[Número del caso]" in sql
    # Todos los casos de la conversacion, por apertura, con el separador.
    assert f"'{SEPARADOR_CASOS}'" in sql and "ORDER BY t.[Fecha/Hora de apertura]" in sql
    # LEFT JOIN: un caso que desaparece del origen vuelve la fila a NULL.
    assert "LEFT JOIN casos" in sql
    # Sin filtro de periodo: toda la tabla, en cada corrida.
    assert "?" not in sql


def test_actualizar_numero_caso_solo_trae_casos_comercial_ii():
    assert TIPO_CASO_SEGUIMIENTO == "Caso Comercial II"
    assert f"AND t.[Tipo del caso] = '{TIPO_CASO_SEGUIMIENTO}'" in ACTUALIZAR_NUMERO_CASO


def test_actualizar_numero_caso_devuelve_filas_cambiadas():
    gateway = FakeDatabaseGateway()
    gateway.filas_a_eliminar = 7
    gateway.resultado_select = pd.DataFrame({"FILAS": [100], "CON_CASO": [3]})

    assert actualizar_numero_caso(gateway) == 7
    assert gateway.deletes == [(ACTUALIZAR_NUMERO_CASO, ())]
