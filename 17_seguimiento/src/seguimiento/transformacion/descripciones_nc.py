r"""Migracion de Carga_Reporte_Descripciones_NC_Chile.py (tarea 'Carga
Descripciones NC' del paquete 06, Execute Process).

El script original:
    df = pd.read_csv(r"...\Nuevo\Reporte_Descripciones_NC_Chile.csv", encoding='utf-8')
    df.columns = ['Numero del caso', 'Descripcion']
    df.to_sql('TBL_DESCRIPCIONES_NC', schema='dbo', con=engine, if_exists='append', index=False)
    EXEC dbo.SP_FOLIOS_NC          (solo si la carga funciono)
    except Exception: print(...)   (nunca falla: y en SSIS FailTaskIfReturnCodeIsNotSuccessValue = False)

Aqui se lee el CSV CRUDO del bot tal cual (cp1252) con pandas (mismas
reglas de NaN y de inferencia de tipos). Lo que cambiaba el archivo 'Nuevo'
y lo que hacia to_sql se reproduce por valor:
  - tildes mal codificadas reparadas (transformacion/codificacion.py;
    desviacion intencional de SSIS, pedida por el usuario 2026-10-26);
  - saltos de linea dentro del texto -> CRLF (SP_FOLIOS_NC corta el folio en CHAR(13));
  - NaN -> NULL, enteros -> su texto ('12250117');
  - el texto pasa por cp1252: SQLAlchemy+pyodbc lo enviaba como VARCHAR, asi
    que un caracter no representable (U+FFFD de un byte invalido) llegaba
    como '?' aunque la columna sea nvarchar(max). Verificado contra la
    TBL_DESCRIPCIONES_NC cargada por SSIS.
La conexion ya no es 'PEOPEDESK0328' con autenticacion de Windows: se usa
la del '.env', como el resto del proceso.
"""

from __future__ import annotations

import io
import logging
import math
from typing import Any

import pandas as pd

from extraccion.extractor import CODIFICACION_BOT, CONSERVAR_BYTES
from logging_setup import NOMBRE_LOGGER
from mappings import ARCHIVO_DESCRIPCIONES_NC, COLUMNAS_DESCRIPCIONES_NC
from transformacion.codificacion import reparar_codificacion
from transformacion.transformer import saltos_crlf

logger = logging.getLogger(NOMBRE_LOGGER)


def _valor_sql(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        return str(int(valor)) if valor.is_integer() else str(valor)
    if hasattr(valor, "item"):  # numpy int64/bool
        valor = valor.item()
    if isinstance(valor, bool):
        return str(int(valor))
    texto = reparar_codificacion(str(valor))
    return saltos_crlf(texto).encode("cp1252", errors="replace").decode("cp1252")


def leer_descripciones_nc(crudo: bytes) -> list[tuple]:
    """Filas (Numero del caso, Descripcion) que el script insertaba."""
    df = pd.read_csv(io.BytesIO(crudo), encoding=CODIFICACION_BOT, encoding_errors=CONSERVAR_BYTES)
    df.columns = list(COLUMNAS_DESCRIPCIONES_NC)
    filas = [tuple(_valor_sql(v) for v in fila) for fila in df.itertuples(index=False, name=None)]
    reparadas = sum(
        1
        for fila in df.itertuples(index=False, name=None)
        for v in fila
        if isinstance(v, str) and reparar_codificacion(v) != v
    )
    if reparadas:
        logger.info("  %s: %s valor(es) con tildes mal codificadas reparados.", ARCHIVO_DESCRIPCIONES_NC.nombre, reparadas)
    return filas
