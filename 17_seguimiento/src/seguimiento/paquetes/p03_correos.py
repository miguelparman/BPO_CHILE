"""CL_Seguimiento_03_Proc_Carga_Correos.dtsx

SSIS (7 tareas):
  Log Inicio
  -> CARGA BASE CORREOS SALESFORCE
       TRUNCA TEMPORAL CORREOS -> CARGA TEMPORAL CORREOS -> LIMPIA TEMPORAL CORREOS
  -> CARGA CORREOS PERU (MERGE en CL_SALESFORCE_ACTUAL.TBL_CORREOS)
  -> TRUNCA TEMPORAL CORREOS -> Log Fin

Python (5 tareas): Log Inicio -> CARGA TEMPORAL CORREOS (#temporal)
  -> LIMPIA TEMPORAL CORREOS -> CARGA CORREOS PERU -> Log Fin
"""

from __future__ import annotations

import mappings as m
from paquetes.base import Bloque, Paquete, TareaDataFlow, TareaSql
from sql import leer

_C = "Package\\CARGA BASE CORREOS SALESFORCE\\"

PAQUETE = Paquete(
    "03",
    "CL_Seguimiento_03_Proc_Carga_Correos.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p03", "00_log_inicio.sql")),
        TareaDataFlow(_C + "CARGA TEMPORAL CORREOS", (m.FLUJO_TEMP_CORREOS,)),
        TareaSql(_C + "LIMPIA TEMPORAL CORREOS", leer("p03", "20_limpia_temporal_correos.sql")),
        TareaSql("Package\\CARGA CORREOS PERÙ", leer("p03", "30_carga_correos.sql")),
        TareaSql("Package\\Log Fin", leer("p03", "99_log_fin.sql")),
    ),
    redundantes=(
        (_C + "TRUNCA TEMPORAL CORREOS", "#temporal de la sesion (nace vacia)"),
        ("Package\\TRUNCA TEMPORAL CORREOS", "la #temporal se descarta al cerrar la sesion"),
    ),
    bloques=(
        Bloque(
            "Correos",
            (m.ARCHIVO_CORREOS,),
            (_C + "CARGA TEMPORAL CORREOS", _C + "LIMPIA TEMPORAL CORREOS", "Package\\CARGA CORREOS PERÙ"),
        ),
    ),
)
