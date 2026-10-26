"""CL_Seguimiento_07_Proc_Seguimiento.dtsx

Log Inicio -> INSUMOS SEGUIMIENTO -> Log Fin
-> Log Inicio 1 -> ASESOR RESPONSABLE -> Log Fin 1
-> Log Inicio 2 -> SEGUIMIENTO -> Log Fin 2
(-> CARGA ESPEJO AZURE: deshabilitada)        (BK: deshabilitada, sin precedencia)

Los SP viven en SQL Server (CL_SEGUIMIENTO_ACTUAL); su definicion queda como
referencia en docs/referencia_sp/.
"""

from __future__ import annotations

from paquetes.base import Paquete, TareaSql
from sql import leer

PAQUETE = Paquete(
    "07",
    "CL_Seguimiento_07_Proc_Seguimiento.dtsx",
    (
        TareaSql("Package\\Log Inicio", leer("p07", "00_log_inicio.sql")),
        TareaSql("Package\\INSUMOS SEGUIMIENTO", leer("p07", "10_insumos_seguimiento.sql")),
        TareaSql("Package\\Log Fin", leer("p07", "19_log_fin.sql")),
        TareaSql("Package\\Log Inicio 1", leer("p07", "20_log_inicio_1.sql")),
        TareaSql("Package\\ASESOR RESPONSABLE", leer("p07", "30_asesor_responsable.sql")),
        TareaSql("Package\\Log Fin 1", leer("p07", "39_log_fin_1.sql")),
        TareaSql("Package\\Log Inicio 2", leer("p07", "40_log_inicio_2.sql")),
        TareaSql("Package\\SEGUIMIENTO", leer("p07", "50_seguimiento.sql")),
        TareaSql("Package\\Log Fin 2", leer("p07", "59_log_fin_2.sql")),
    ),
)
