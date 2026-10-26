"""CL_Seguimiento_02_Proc_Carga_Casos.dtsx

SSIS (13 tareas):
  Log Inicio
  -> CARGA BASE CASOS SALESFORCE
       TRUNCA TEMPORAL CASOS -> CARGA TEMPORAL CASOS (Casos, Nombre Contacto,
       Tipificaciones) -> FECHA BASE -> LIMPIA BASE CHILE
       -> Agrega Nombre de Contacto -> CARGA CASOS CHILE
       (-> ACTUALIZA TIFICIACIONES: deshabilitada)
  -> CARGA BASE CASOS B SALESFORCE
       TRUNCA TEMPORAL CASOS B -> CARGA TEMPORAL CASOS B -> LIMPIA CASOS B CHILE
       -> CARGA CASOS B CHILE
  (-> ACTUALIZA CASOS OTRO PAIS: excluida, borraba en PE_SALESFORCE_ACTUAL)
  -> TRUNCAR TEMPORALES -> Log Fin

Python (7 tareas, mismo resultado):
  Log Inicio
  -> CARGA TEMPORAL CASOS: Casos + Nombre Contacto cruzados en Python -> #TBL_SALESFORCE_CASOS
  -> FECHA BASE
  -> LIMPIA BASE CHILE + CARGA CASOS CHILE        (una transaccion)
  -> CARGA TEMPORAL CASOS B                       -> #TBL_SALESFORCE_CASOS_B
  -> LIMPIA CASOS B CHILE + CARGA CASOS B CHILE   (una transaccion)
  -> Log Fin
"""

from __future__ import annotations

import mappings as m
from paquetes.base import Paquete, TareaDataFlow, TareaSql, TareaTransaccion
from sql import leer

_C = "Package\\CARGA BASE CASOS SALESFORCE\\"
_B = "Package\\CARGA BASE CASOS B SALESFORCE\\"

PAQUETE = Paquete(
    "02",
    "CL_Seguimiento_02_Proc_Carga_Casos.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p02", "00_log_inicio.sql")),
        TareaDataFlow(_C + "CARGA TEMPORAL CASOS", (m.FLUJO_TEMP_REPORTE_CASOS,)),
        TareaSql(_C + "FECHA BASE", leer("p02", "20_fecha_base.sql")),
        TareaTransaccion(
            (
                TareaSql(_C + "LIMPIA BASE CHILE", leer("p02", "30_limpia_base_chile.sql")),
                TareaSql(_C + "CARGA CASOS CHILE", leer("p02", "50_carga_casos_chile.sql")),
            )
        ),
        TareaDataFlow(_B + "CARGA TEMPORAL CASOS B", (m.FLUJO_TEMP_CASOS_B,)),
        TareaTransaccion(
            (
                TareaSql(_B + "LIMPIA CASOS B CHILE", leer("p02", "70_limpia_casos_b_chile.sql")),
                TareaSql(_B + "CARGA CASOS B CHILE", leer("p02", "80_carga_casos_b_chile.sql")),
            )
        ),
        TareaSql("Package\\Log Fin", leer("p02", "99_log_fin.sql")),
    ),
    redundantes=(
        (_C + "TRUNCA TEMPORAL CASOS", "las staging pasan a #temporales de la sesion (nacen vacias)"),
        (_C + "Agrega Nombre de Contacto", "el cruce con Nombre Contacto se hace en Python al cargar la #temporal"),
        (_B + "TRUNCA TEMPORAL CASOS B", "#temporal de la sesion (nace vacia)"),
        ("Package\\TRUNCAR TEMPORALES", "las #temporales se descartan al cerrar la sesion"),
    ),
)
