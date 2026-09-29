"""Oraculos: copias LITERALES de la logica de los scripts originales de
102_calidad/ (sin conexiones ni credenciales), para comparar la migracion
contra el comportamiento original sobre los mismos datos.

No se usan en produccion: solo en tests/equivalencia/ y tools/equivalencia.py.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Traslado_Calidad_Servidor_55_EPA_WSP_MEDALLIA.py (lineas 8-25, literal)
# --------------------------------------------------------------------------- #
FLOAT_SUFFIX_RE = re.compile(r'^-?\d+\.0$')

def clean_row(row, max_lengths=None, float_suffix_indices=None):
    cleaned = []
    for i, value in enumerate(row):
        if value is None:
            cleaned.append(None)
        elif isinstance(value, float) and math.isnan(value):
            cleaned.append(None)
        elif isinstance(value, str) and value.lower() == 'nan':
            cleaned.append(None)
        elif isinstance(value, str) and float_suffix_indices and i in float_suffix_indices and FLOAT_SUFFIX_RE.match(value):
            cleaned.append(value[:-2])
        elif isinstance(value, str) and max_lengths and max_lengths[i] is not None and len(value) > max_lengths[i]:
            cleaned.append(value[:max_lengths[i]])
        else:
            cleaned.append(value)
    return tuple(cleaned)


# --------------------------------------------------------------------------- #
# CL_Carga_de_encuestas_MEDALLIA.py (lineas 8-52 + 97, literal salvo el
# nombre de la variable de entrada y el print)
# --------------------------------------------------------------------------- #
def medallia_datos(csv_file) -> list[tuple]:
    df = pd.read_csv(csv_file, encoding='latin1', dtype=str)
    df = df.replace({np.nan: None, '': None, 'nan': None, 'None': None, 'NULL': None, 'Null': None})
    columna_original = '¿Podrías contarnos las razones de tu respuesta?'
    columna_duplicada = columna_original + '.1'
    if columna_duplicada in df.columns:
        df[columna_original] = df[columna_original].combine_first(df[columna_duplicada])
        df.drop(columns=[columna_duplicada], inplace=True)
    columnas = [
        'ID de encuesta', 'Tipo de Encuesta', 'ANI_CONTACTO', 'Responsedate', 'FECHA_EVENTO', 'NPS',
        '¿Lograste resolver tu requerimiento?', 'SAT - Asesor', 'Facilidad de gestión',
        'SAT - Satisfacción General', 'Estado de encuesta', '¿Podrías contarnos las razones de tu respuesta?',
        'ID_CLIENTE_BIEN', 'PLATAFORMA', 'CATEGORIA_EMPRESA', 'NOMBRE_EMPRESA'
    ]
    df['Responsedate'] = pd.to_datetime(df['Responsedate'], format='%d-%m-%Y', errors='coerce')
    df['Responsedate'] = df['Responsedate'].where(df['Responsedate'].notnull(), None)
    for col in columnas:
        if col != 'Responsedate':
            df[col] = df[col].astype(str).where(df[col].notnull(), None)
    df = df[columnas]
    return [tuple(x) for x in df.values]


# --------------------------------------------------------------------------- #
# enviar_alerta_encuesta.py: obtener_fecha_limite() (literal, con 'hoy'
# inyectado en vez de datetime.now().date())
# --------------------------------------------------------------------------- #
HORA_LIMITE = 17
MINUTO_LIMITE = 0

def obtener_fecha_limite(hoy):
    if hoy.weekday() == 0:  # Lunes
        fecha_referencia = hoy - timedelta(days=3)  # Viernes
    else:
        fecha_referencia = hoy - timedelta(days=1)  # Día anterior
    fecha_limite = datetime.combine(
        fecha_referencia,
        datetime.min.time()
    ).replace(
        hour=HORA_LIMITE,
        minute=MINUTO_LIMITE,
        second=0,
        microsecond=0
    )
    return fecha_limite
