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

AGREGADO (no esta en el .dtsx): carga ACUMULATIVA de la cola de reclamos (decision del usuario 2026-11-13),
despues de Casos B y antes del Log Fin:
  -> CARGA TEMPORAL COLA RECLAMO   Chi_cola_reclamo_aux_propietario.csv -> #TBL_COLA_CHI_RECLAMO_PROPIETARIO
                                   (molde: la propia tabla destino de CL_FACTURACION)
  -> ACTUALIZA + CARGA COLA RECLAMO (una transaccion) sobre [CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO]
Reemplaza las tareas 'TBL_COLA_CHI_RECLAMO_PROPIETARIO 1' (TRUNCATE + carga del CSV '_v2' en la base local) y
'SERVIDOR' (copia local -> 162) de SSIS_BBDD_Local_CH_CL_SEGUIMIENTO.dtsx. Es un upsert por [Número del caso]:
caso nuevo -> se inserta; caso existente con propietario, email o subtipo distintos -> se actualiza; sin cambios,
o que no viene en el CSV -> no se toca; nunca se trunca ni se borra. Una celda vacia es NULL (asi esta el
historico de la tabla). Idempotente: recargar el mismo archivo no duplica ni vuelve a modificar.

Bloques (frescura): 'Casos' (Casos + Nombre Contacto), 'Casos B' (Casos B) y 'Cola de reclamos' (su CSV)
se omiten por separado si su archivo no esta actualizado o viene vacio.
"""

from __future__ import annotations

import mappings as m
from paquetes.base import Bloque, Paquete, TareaDataFlow, TareaSql, TareaTransaccion
from sql import leer

_C = "Package\\CARGA BASE CASOS SALESFORCE\\"
_B = "Package\\CARGA BASE CASOS B SALESFORCE\\"

_CARGA_CASOS = TareaDataFlow(_C + "CARGA TEMPORAL CASOS", (m.FLUJO_TEMP_REPORTE_CASOS,))
_FECHA_BASE = TareaSql(_C + "FECHA BASE", leer("p02", "20_fecha_base.sql"))
_FINAL_CASOS = TareaTransaccion(
    (
        TareaSql(_C + "LIMPIA BASE CHILE", leer("p02", "30_limpia_base_chile.sql")),
        TareaSql(_C + "CARGA CASOS CHILE", leer("p02", "50_carga_casos_chile.sql")),
    )
)
_CARGA_CASOS_B = TareaDataFlow(_B + "CARGA TEMPORAL CASOS B", (m.FLUJO_TEMP_CASOS_B,))
_FINAL_CASOS_B = TareaTransaccion(
    (
        TareaSql(_B + "LIMPIA CASOS B CHILE", leer("p02", "70_limpia_casos_b_chile.sql")),
        TareaSql(_B + "CARGA CASOS B CHILE", leer("p02", "80_carga_casos_b_chile.sql")),
    )
)

_COLA = "Package\\CARGA COLA RECLAMO\\"
_CARGA_COLA = TareaDataFlow(_COLA + "CARGA TEMPORAL COLA RECLAMO", (m.FLUJO_COLA_RECLAMO,))
_UPSERT_COLA = TareaTransaccion(
    (
        TareaSql(_COLA + "ACTUALIZA COLA RECLAMO", leer("p02", "90_actualiza_cola_reclamo.sql")),
        TareaSql(_COLA + "CARGA COLA RECLAMO", leer("p02", "95_carga_cola_reclamo.sql")),
    )
)

PAQUETE = Paquete(
    "02",
    "CL_Seguimiento_02_Proc_Carga_Casos.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p02", "00_log_inicio.sql")),
        _CARGA_CASOS,
        _FECHA_BASE,
        _FINAL_CASOS,
        _CARGA_CASOS_B,
        _FINAL_CASOS_B,
        _CARGA_COLA,
        _UPSERT_COLA,
        TareaSql("Package\\Log Fin", leer("p02", "99_log_fin.sql")),
    ),
    redundantes=(
        (_C + "TRUNCA TEMPORAL CASOS", "las staging pasan a #temporales de la sesion (nacen vacias)"),
        (_C + "Agrega Nombre de Contacto", "el cruce con Nombre Contacto se hace en Python al cargar la #temporal"),
        (_B + "TRUNCA TEMPORAL CASOS B", "#temporal de la sesion (nace vacia)"),
        ("Package\\TRUNCAR TEMPORALES", "las #temporales se descartan al cerrar la sesion"),
    ),
    bloques=(
        Bloque(
            "Casos",
            (m.ARCHIVO_CASOS, m.ARCHIVO_NOMBRE_CONTACTO),
            (_CARGA_CASOS.nombre, _FECHA_BASE.nombre, _FINAL_CASOS.nombre),
        ),
        Bloque("Casos B", (m.ARCHIVO_CASOS_B,), (_CARGA_CASOS_B.nombre, _FINAL_CASOS_B.nombre)),
        Bloque("Cola de reclamos", (m.ARCHIVO_COLA_RECLAMO,), (_CARGA_COLA.nombre, _UPSERT_COLA.nombre)),
    ),
    agregadas=(_CARGA_COLA.nombre, *(t.nombre for t in _UPSERT_COLA.tareas)),
)
