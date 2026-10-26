"""CL_Seguimiento_04_Proc_Carga_Historial_Casos.dtsx

SSIS (7 tareas):
  Log Inicio
  -> CARGA BASE TEMPORAL HISTORIAL CASOS
       TRUNCA TEMPORAL HISTORIAL -> CARGA TEMPORAL HISTORIAL -> LIMPIA TEMPORAL HISTORIAL
  -> CARGA HISTORIAL CHILE (MERGE en CL_SALESFORCE_ACTUAL.TBL_HISTORIAL_CASOS)
  -> TRUNCA TEMPORA HISTORICO -> Log Fin

Python (5 tareas): Log Inicio -> CARGA TEMPORAL HISTORIAL (#temporal)
  -> LIMPIA TEMPORAL HISTORIAL -> CARGA HISTORIAL CHILE -> Log Fin
"""

from __future__ import annotations

import mappings as m
from paquetes.base import Bloque, Paquete, TareaDataFlow, TareaSql
from sql import leer

_C = "Package\\CARGA BASE TEMPORAL HISTORIAL CASOS\\"

PAQUETE = Paquete(
    "04",
    "CL_Seguimiento_04_Proc_Carga_Historial_Casos.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p04", "00_log_inicio.sql")),
        TareaDataFlow(_C + "CARGA TEMPORAL HISTORIAL", (m.FLUJO_TEMP_HISTORIAL,)),
        TareaSql(_C + "LIMPIA TEMPORAL HISTORIAL", leer("p04", "20_limpia_temporal_historial.sql")),
        TareaSql("Package\\CARGA HISTORIAL CHILE", leer("p04", "30_carga_historial_chile.sql")),
        TareaSql("Package\\Log Fin", leer("p04", "99_log_fin.sql")),
    ),
    redundantes=(
        (_C + "TRUNCA TEMPORAL HISTORIAL", "#temporal de la sesion (nace vacia)"),
        ("Package\\TRUNCA TEMPORA HISTORICO", "la #temporal se descarta al cerrar la sesion"),
    ),
    bloques=(
        Bloque(
            "Historial",
            (m.ARCHIVO_HISTORIAL,),
            (_C + "CARGA TEMPORAL HISTORIAL", _C + "LIMPIA TEMPORAL HISTORIAL", "Package\\CARGA HISTORIAL CHILE"),
        ),
    ),
)
