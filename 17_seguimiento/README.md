# 17_seguimiento

Migración a Python de los paquetes SSIS **CL_Seguimiento** de Chile:

```
02 Carga Casos -> 03 Carga Correos -> 04 Historial Casos -> 06 Historial Comentarios -> 07 Proc Seguimiento
```

El 05 (Historial Asignaciones) queda fuera de alcance. Los paquetes se ejecutan en ese orden: cada uno empieza solo si
el anterior terminó OK, y **ante cualquier fallo se detiene todo**.

Origen: los CSV **crudos** que `201_bot_salesforce` publica en SharePoint (ReportingFractalia / Data Reporting /
REPOSITORIOS DE CRUDOS / CHILE / BPOCHIPE / `01 SEGUIMIENTO`, y `12 AUXILIARES` para Nombre_Contacto y
Descripciones_NC). Se leen **tal cual**, sin el paso intermedio del paquete 01 (`Nuevo`), y se descargan en paralelo.

Destino: las mismas tablas finales que SSIS (`CL_SALESFORCE_ACTUAL`, `CL_SEGUIMIENTO_ACTUAL`, `TBL_DESCRIPCIONES_NC`) y
los logs en `BBDD_GENERAL.LOGS_PROCESOS`. Las staging se cargan en **#temporales** de la sesión de cada paquete, y se
quitaron los pasos redundantes (TRUNCATE, Tipificaciones, staging de Contacto). El detalle está en la sección 2 de la
equivalencia.

La equivalencia, las decisiones, lo que no se migró y la evidencia están en [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md).

## Uso

```bat
python main.py                      :: corrida completa 02 -> 07
python main.py --desde 04           :: retomar desde un paquete
python main.py --solo 03 04         :: solo esos paquetes (en orden)
python main.py --solo-validar       :: extrae, valida y transforma; no escribe nada
python main.py --verificar          :: solo conexiones + frescura de los archivos; no carga nada (exit 0 / 1 / 2)
python main.py --origen-local "D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO"
scripts\ejecutar_seguimiento.cmd    :: para el Programador de tareas (devuelve el exit code)
```

Programación: tarea `\ETL\ETL Seguimiento Chile`, de **lunes a viernes** a las 07:00, 10:00, 13:00 y 16:00, media hora
después de cada publicación de `201_bot_salesforce`. Mantenimiento del índice de comentarios: tarea
`\ETL\ETL Seguimiento Mantener Indice`, primer lunes de cada mes a las 06:00 (`scripts\mantener_indice.cmd`).

Antes de cargar:
1. **Conexiones:** SQL Server `172.17.0.162` y SharePoint, con sus archivos. Si alguna falla, se reintenta cada 5 min
   hasta 3 veces y luego termina con exit 1 sin ejecutar nada.
2. **Frescura de los archivos** (`frescura.py`): un archivo no actualizado (más de `FRESCURA_MAX_MIN` = 150 minutos) o
   sin filas **no se carga**. Si el bot está publicando, no se espera: se toma lo que haya. Se omiten solo los bloques de tareas que lo
   usan (`paquetes/pXX_*.py`, `bloques=`) y la corrida continua con los demás. Si se omiten todos los bloques de un
   paquete, no se escriben sus Log Inicio/Fin en `LOGS_PROCESOS`. El paquete 07 (SP) corre siempre. Cada omisión
   queda como advertencia en el log.

`--verificar` devuelve 0 si todo está listo, 1 si falla una conexión y 2 si alguna carga se omitiría por frescura.
Cada corrida deja su log en `logs/`.

## Cola de reclamos dentro del paquete 02 (carga acumulativa)

El paquete 02 carga ademas `Chi_cola_reclamo_aux_propietario.csv` (SharePoint `09 RECLAMOS`, lo publica
`201_bot_salesforce`) en `[CL_FACTURACION].[dbo].[TBL_COLA_CHI_RECLAMO_PROPIETARIO]` (172.17.0.162), en la misma sesion
y a continuacion de Casos B. **No existe en `CL_Seguimiento_02_...dtsx`**: reemplaza la carga del paquete SSIS
`SSIS_BBDD_Local_CH_CL_SEGUIMIENTO.dtsx` (TRUNCATE + carga completa desde el `_v2.csv`), y por eso esta marcada en
`Paquete.agregadas` (las pruebas de equivalencia contra el .dtsx la excluyen; el resto del 02 se sigue comparando).

El CSV trae los registros nuevos y los modificados; la carga es un upsert por `[Número del caso]`: los casos nuevos se
insertan y los que ya estan y cambiaron (propietario, email o subtipo) se actualizan, en una sola transaccion. Nunca se
trunca ni se borra; es idempotente (recargar el mismo archivo no duplica ni vuelve a modificar) y un caso que no viene en
el CSV no se toca. Las celdas vacias se cargan como NULL, como el historico de la tabla.

* Tareas (nuevo bloque de frescura `Cola de reclamos`): `CARGA TEMPORAL COLA RECLAMO` (Data Flow: CSV -> `#temporal`
  con la propia tabla destino de molde; valida columnas, anchos y conversiones) -> `ACTUALIZA COLA RECLAMO` +
  `CARGA COLA RECLAMO` (UPDATE e INSERT en una transaccion). T-SQL en `scripts_sql/p02/90_*.sql` y `95_*.sql`.
* Mismo control de frescura que los demas: si el CSV no esta actualizado (`FRESCURA_MAX_MIN`) o viene vacio, se omite
  solo ese bloque (con una advertencia) y el resto del 02 sigue.
* Comparte Log Inicio/Fin con el 02 (`Update_Carga_Casos_Chile`).
* Codigo: tareas en `paquetes/p02_casos.py` y `FLUJO_COLA_RECLAMO` en `mappings.py`; pruebas en
  `tests/unit/test_cola_reclamo_en_02.py`. Carpeta configurable con `SHAREPOINT_FOLDER_RECLAMOS`.

## Estructura (src layout, modular por componentes)

```
main.py                           composition root (CLI)
src/seguimiento/
  pipeline.py                     orquestador
  paquetes/pXX_*.py               Control Flow de cada .dtsx, como datos
  extraccion/extractor.py         SharePoint/local, descarga en paralelo, lectura del CSV crudo (Flat File Source)
  validacion/validator.py         columnas por fila, esquema y anchos reales
  transformacion/transformer.py   Derived Column + Data Conversion + saltos de línea CRLF
  transformacion/cruce.py         cruce Casos x Nombre Contacto (reemplaza staging + UPDATE)
  transformacion/fechas.py        texto -> DT_DATE (día primero)
  transformacion/descripciones_nc.py   Carga_Reporte_Descripciones_NC_Chile.py migrado (carga ACUMULATIVA: upsert por [Número del caso])
  carga/loader.py                 sesión por paquete, #temporales, Execute SQL Tasks y transacciones
  mappings.py                     archivos, columnas, tipos y anchos del .dtsx
  sql.py + scripts_sql/pXX/       T-SQL literal de cada Execute SQL Task
  db.py, sharepoint/              adaptadores pyodbc / Microsoft Graph
  conexiones.py                   validación previa de conexiones
  frescura.py                     antigüedad / publicación en curso / vacío de los CSV (omite bloques)
  config.py, logging_setup.py, exceptions.py
tests/unit/                       pruebas unitarias (sin base ni SharePoint)
tests/equivalencia/               equivalencia estructural contra los .dtsx originales
tools/equivalencia.py             equivalencia de datos SSIS vs Python (solo lectura)
tools/limpiar_duplicados_comentarios.py   limpieza de comentarios reinsertados por SSIS (simula; --aplicar borra con respaldo)
tools/optimizar_sp_proceso_seguimiento.py optimizacion de SP_PROCESO_SEGUIMIENTO + indice de comentarios (probar / aplicar / revertir / indice / mantener-indice)
docs/                             EQUIVALENCIA.md, no_migrado/, referencia_sp/
```

## Configuración

Copiar `.env.example` como `.env` y completar los valores; ninguna credencial está en el código. Variables:

* `DB_*`: servidor 172.17.0.162. `DB_LANGUAGE=us_english` es el idioma de las sesiones SSIS.
* `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `SHAREPOINT_*`: Graph.
* Opcionales: `SHAREPOINT_FOLDER_SEGUIMIENTO`, `SHAREPOINT_FOLDER_AUXILIARES`, `BATCH_SIZE`, `REINTENTOS_CONEXION`,
  `ESPERA_REINTENTO_S`.

## Pruebas

```bat
pip install -r requirements-dev.txt
python -m pytest                    :: unitarias + estructurales (los .dtsx se buscan en DTSX_DIR)
python tools\equivalencia.py        :: datos: crudos locales vs lo que cargó la última corrida SSIS
```
