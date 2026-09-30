"""Constantes de la capa GOLD (ver cargar.py / sql.py): modelo estrella en
su propio esquema."""

from __future__ import annotations

from comun.periodo import DESFASE_HORAS_LOCAL  # noqa: F401 -- re-exportado para sql.py

ESQUEMA_GOLD = "gold"
TABLA_FACT_MENSAJE = "FACT_MENSAJE"
TABLA_DIM_FECHA = "DIM_FECHA"
TABLA_DIM_BANDEJA = "DIM_BANDEJA"
TABLA_DIM_TIPO = "DIM_TIPO"
TABLA_DIM_ASUNTO_AGRUPADO = "DIM_ASUNTO_AGRUPADO"
TABLA_DIM_JEFATURA = "DIM_JEFATURA"

# Columnas de auditoria de FACT_MENSAJE (ver cargar.py): de que tabla silver
# viene la fila, que codigo la inserto, en que corrida (enlaza con
# dbo.TBL_CORREO_LOG_EJECUCION) y cuando (hora local Peru/Bogota).
PROCESO_CARGA_PERIODO = "11_correos/src/correos/gold/cargar.py:cargar_periodo_gold"
PROCESO_CARGA_COMPLETO = "11_correos/src/correos/gold/cargar.py:recargar_gold_completo"
