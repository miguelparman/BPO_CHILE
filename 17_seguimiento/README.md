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
  transformacion/descripciones_nc.py   Carga_Reporte_Descripciones_NC_Chile.py migrado
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
