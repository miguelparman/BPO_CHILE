"""Constantes de la capa SILVER (ver cargar.py): tablas destino, columnas que
se toman de bronze y reglas de ASUNTO_AGRUPADO."""

from __future__ import annotations

from typing import NamedTuple

from bronze.mappings import COLUMNA_CONTROL_FECHA, COLUMNA_ORIGEN, COLUMNAS_BANDEJAS, COLUMNAS_REGISTRO

ESQUEMA = "dbo"
TABLA_REGISTRO_SILVER = "TBL_CORREO_REGISTRO_SILVER"
TABLA_BANDEJAS_SILVER = "TBL_CORREO_BANDEJAS_SILVER"
COLUMNA_ASUNTO_AGRUPADO = "ASUNTO_AGRUPADO"
# Nombre del coordinador, derivado de ORIGEN (cada .xlsx es el control de un
# coordinador: 'Registro_JHON_MORALES_PENA.xlsx' -> 'JHON MORALES PENA').
COLUMNA_COORDINADOR = "COORDINADOR"

# ID Place del asesor, derivado de la bandeja: 'SM<n>@movistar.cl' ->
# BASE_ID_PLACE + n (SM68 -> 51030068, SM5 -> 51030005, SM123 -> 51030123).
# Una bandeja que no calza el patron queda NULL. Se agrega en las dos tablas
# silver (registro y bandejas).
COLUMNA_ID_PLACE = "ID_PLACE"
PATRON_BANDEJA_ID_PLACE = r"^SM(\d+)@movistar\.cl$"
BASE_ID_PLACE = 51030000

# Jefatura del place en el dia del mensaje, cruzando con la foto diaria de
# places: ID_PLACE + fecha (sin hora) de FechaHora_UTC_Texto (UTC) contra
# [ID] + [Fecha Impacto], tomando [Plataforma]. Si no hay foto de ese dia se
# usa la mas reciente anterior de ese ID (las fotos con [Plataforma] NULL no
# cuentan); sin ninguna = NULL. Normalizacion (ver
# cargar.normalizar_plataforma): todo lo que contenga 'triada' -> 'Triadas';
# lo que venga en MAYUSCULAS -> 'Capitalizado' (CARTERIZADOS -> Carterizados),
# el mismo formato que tenia la base de personal anterior. Solo en
# TBL_CORREO_REGISTRO_SILVER: bandejas no tiene fecha.
COLUMNA_JEFATURA = "JEFATURA"
TABLA_HISTORICO_PLACES = "[CL_DATA].[dbo].[TBL_HISTORICO_PLACES]"
JEFATURA_TRIADAS = "Triadas"

# Numero(s) de caso de la conversacion, cruzando ConversationID con
# [To Addres] de la base de seguimiento (hoy casi siempre trae correos; solo
# los casos recientes traen ahi el ConversationID). Solo casos con
# [Tipo del caso] = TIPO_CASO_SEGUIMIENTO. Si una conversacion tiene
# varios casos van TODOS, ordenados por apertura y separados por
# SEPARADOR_CASOS. Sin caso = NULL. No se calcula en Python: es un UPDATE
# sobre TODA la tabla silver en cada corrida (ver
# cargar.actualizar_numero_caso), asi un caso abierto despues del correo
# llega aunque su periodo ya no se recargue.
COLUMNA_NUMERO_CASO = "NUMERO_CASO"
TABLA_SEGUIMIENTO = "[CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]"
TIPO_CASO_SEGUIMIENTO = "Caso Comercial II"
SEPARADOR_CASOS = "; "

# Mismo campo de control de periodo que bronze (silver conserva el nombre):
# se re-exporta para que gold lea todo lo de silver desde aqui, sin importar
# bronze.
COLUMNA_CONTROL_FECHA = COLUMNA_CONTROL_FECHA

# TBL_CORREO_BANDEJAS_SILVER: todas las columnas de bronze + COORDINADOR + ID_PLACE.
# Se reemplaza completa en cada corrida, igual que en bronze (es el estado
# actual de cada bandeja, no un historial).
COLUMNAS_BANDEJAS_SILVER_DESDE_BRONZE = [*COLUMNAS_BANDEJAS, COLUMNA_ORIGEN]

# Columnas de bronze que NO pasan a silver (ni a gold): son calculos que hace
# la macro del Excel y no son confiables (ej. Tiempo_Respuesta_Horas ~1.110.900
# h = tiempo desde la fecha 0 de Excel cuando no encuentra la entrada;
# Tiempo_Primera_Respuesta_Horas negativo; Estado siempre vacio). Quedan solo
# en bronze, tal cual llegan.
COLUMNAS_EXCLUIDAS_SILVER = [
    "EsPrimeraEntrada",
    "TieneRespuesta",
    "Tiempo_Primera_Respuesta_Horas",
    "Estado",
    "Tiempo_Respuesta_Horas",
]
COLUMNAS_SILVER_DESDE_BRONZE = [
    *[c for c in COLUMNAS_REGISTRO if c not in COLUMNAS_EXCLUIDAS_SILVER],
    COLUMNA_ORIGEN,
]

class ReglaAgrupacion(NamedTuple):
    """Una regla de ASUNTO_AGRUPADO (ver REGLAS_ASUNTO_AGRUPADO)."""

    grupo: str
    campo: str  # CAMPO_ASUNTO o CAMPO_CONTACTO
    textos: list[str]
    # Solo CAMPO_ASUNTO: True = el texto debe aparecer como palabra(s) completa(s).
    palabra_completa: bool = False
    # Solo CAMPO_CONTACTO: True = basta que 'Contacto' contenga el texto; False =
    # alguno de sus correos debe ser igual al texto.
    contiene: bool = False
    # Si se indica, la regla solo aplica a mensajes de ese 'Tipo' ('Entrada'/'Salida').
    tipo: str | None = None


CAMPO_ASUNTO = "Asunto"
CAMPO_CONTACTO = "Contacto"

# Correos cuyos mensajes ENTRANTES se agrupan como SEGUIMIENTO VENTAS.
CORREOS_SEGUIMIENTO_VENTAS = [
    "vanessa.vilcachagua@fractaliasystems.es",
    "gerson.pinedo@fractaliasystems.es",
    "elcky.alvarez@fractaliasystems.es",
    "braulio.cadenillasf@fractaliasystems.es",
    "johnny.cossio@fractaliasystems.es",
]

# Reglas de ASUNTO_AGRUPADO, evaluadas EN ORDEN (gana la primera que calza).
# Sin distinguir mayusculas ni tildes (ver cargar._normalizar). Un mensaje
# que no calza ninguna queda NULL.
# - CAMPO_ASUNTO: 'Asunto' contiene alguno de los textos. Con
#   palabra_completa=True el texto debe aparecer como palabra(s) completa(s)
#   -- ej. 'presentacion' NO calza dentro de 'representacion'; con False basta
#   que aparezca en cualquier parte.
# - CAMPO_CONTACTO: alguno de los correos de 'Contacto' (puede traer varios
#   separados por ';') es igual a uno de los textos; con contiene=True basta
#   que 'Contacto' contenga el texto en cualquier parte.
# SEGUIMIENTO COBRANZA va primero, incluso antes que REBOTE: todo mensaje con
# esa casilla en 'Contacto' cuenta como cobranza, sea cual sea el asunto.
# REBOTE va despues: un rebote puede citar el asunto original (ej. 'No
# entregable: Actualizacion de correo de contacto ...') y debe contarse como
# rebote, no como PRESENTACION. Las reglas por remitente van antes que las
# de asunto: quien envia es mas confiable que el texto del asunto.
REGLAS_ASUNTO_AGRUPADO: list[ReglaAgrupacion] = [
    ReglaAgrupacion("SEGUIMIENTO COBRANZA", CAMPO_CONTACTO, ["cobranzas@emailmovistar.cl"], contiene=True),
    ReglaAgrupacion(
        "REBOTE",
        CAMPO_ASUNTO,
        [
            "delivery status notification",
            "notificacion de estado de entrega",
            "no entregable:",
            "undelivered mail returned to sender",
        ],
    ),
    ReglaAgrupacion("SEGUIMIENTO TÉCNICA", CAMPO_CONTACTO, ["seguimiento.moviles@movistar.cl"], tipo="Entrada"),
    ReglaAgrupacion("SEGUIMIENTO VENTAS", CAMPO_CONTACTO, CORREOS_SEGUIMIENTO_VENTAS, tipo="Entrada"),
    # 'actividad remedy' a secas: cubre '[REF:...]Actividad Remedy[ID:REQ...]'
    # y 'Actividad Remedy REQ...', con o sin 'RE:'/'RV:'.
    ReglaAgrupacion("SEGUIMIENTO REMEDY", CAMPO_ASUNTO, ["actividad remedy"]),
    ReglaAgrupacion("PRESENTACIÓN", CAMPO_ASUNTO, ["actualizacion de correo de contacto", "presentacion"], palabra_completa=True),
    # Texto parcial a proposito: cubre 'pruebaaa', 'PRUEBA17/09', etc.
    ReglaAgrupacion("PRUEBA", CAMPO_ASUNTO, ["prueba"]),
    # 'promo' a secas: cubre PROMOSEPTIEMBRE, PROMOSETIEMBRE, 'PROMO SEPTIEMBRE',
    # 'PROMOCIONES', etc.
    ReglaAgrupacion("PROMO", CAMPO_ASUNTO, ["promo"]),
]
