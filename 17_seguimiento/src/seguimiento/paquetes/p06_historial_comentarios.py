"""CL_Seguimiento_06_Proc_Carga_Historial_Comentarios.dtsx

SSIS (9 tareas):
  Log Inicio -> (dos ramas en paralelo; Log Fin espera a ambas)
     rama 1: CARGA BASE TEMPORAL HISTORIAL COMENTARIOS
               TRUNCATE TEMPORAL COMENTARIOS -> CARGA TEMPORAL COMENTARIOS
               -> LIMPIA TEMPORAL ASIGNACIONES (limpia la staging de COMENTARIOS)
             -> CARGA COMENTARIOS CHILE (MERGE en TBL_HISTORIAL_COMENTARIOS)
             -> TRUNCA TEMPORAL HISTORICO
     rama 2: CARGA DESCRIPCIONES NC
               TRUNCATE TEMPORAL -> Carga Descripciones NC (script Python)
  -> Log Fin

Python (6 tareas, ramas en serie): Log Inicio -> CARGA TEMPORAL COMENTARIOS
  (#temporal) -> LIMPIA -> CARGA COMENTARIOS CHILE -> Carga Descripciones NC -> Log Fin.
TBL_DESCRIPCIONES_NC sigue siendo permanente: la lee SP_FOLIOS_NC.

CAMBIO (decision del usuario 2026-11-13): 'Carga Descripciones NC' es ACUMULATIVA (upsert por [Número del caso]),
ya no una recarga completa. Se elimino 'CARGA DESCRIPCIONES NC\\TRUNCATE TEMPORAL' (SQL en
docs/no_migrado/p06_TRUNCATE_TEMPORAL_DESCRIPCIONES_NC_reemplazada.sql): la tabla nunca se vacia; los casos nuevos
se insertan y los existentes con otra descripcion se actualizan (loader.cargar_descripciones_nc, scripts_sql/p06/
60_ y 65_). Asi el CSV puede traer solo las novedades. SP_FOLIOS_NC sigue corriendo despues de la carga.
"""

from __future__ import annotations

import mappings as m
from paquetes.base import Bloque, Paquete, TareaDataFlow, TareaDescripcionesNC, TareaSql
from sql import leer

_C = "Package\\CARGA BASE TEMPORAL HISTORIAL COMENTARIOS\\"
_NC = "Package\\CARGA DESCRIPCIONES NC\\"

PAQUETE = Paquete(
    "06",
    "CL_Seguimiento_06_Proc_Carga_Historial_Comentarios.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p06", "00_log_inicio.sql")),
        TareaDataFlow(_C + "CARGA TEMPORAL COMENTARIOS", (m.FLUJO_TEMP_COMENTARIOS,)),
        TareaSql(_C + "LIMPIA TEMPORAL ASIGNACIONES", leer("p06", "20_limpia_temporal_comentarios.sql")),
        TareaSql("Package\\CARGA COMENTARIOS CHILE", leer("p06", "30_carga_comentarios_chile.sql")),
        TareaDescripcionesNC(_NC + "Carga Descripciones NC"),
        TareaSql("Package\\Log Fin", leer("p06", "99_log_fin.sql")),
    ),
    redundantes=(
        (_C + "TRUNCATE TEMPORAL COMENTARIOS", "#temporal de la sesion (nace vacia)"),
        ("Package\\TRUNCA TEMPORAL HISTORICO", "la #temporal se descarta al cerrar la sesion"),
    ),
    bloques=(
        Bloque(
            "Comentarios",
            (m.ARCHIVO_COMENTARIOS,),
            (_C + "CARGA TEMPORAL COMENTARIOS", _C + "LIMPIA TEMPORAL ASIGNACIONES", "Package\\CARGA COMENTARIOS CHILE"),
        ),
        Bloque("Descripciones NC", (m.ARCHIVO_DESCRIPCIONES_NC,), (_NC + "Carga Descripciones NC",)),
    ),
)
