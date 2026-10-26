# 18_puntualidad

Migración a Python del paquete SSIS **`SSIS_CL_Puntualidad.dtsx`** (Chile):

```
SLA PRUEBA ( TRUNCA TABLA -> TBL_SLA_CHILE -> UPDATE )  ->  PUNTUALIDAD
```

1. **SLA:** el Excel `DB.xlsx` (hoja `SLA - Carterizado`) se carga en `[CL_ANALISIS].[dbo].[TBL_SLA]`.
2. **PUNTUALIDAD:** se regenera `[CL_MOVIL].[dbo].[TBL_PUNTUALIDAD]` desde `CL_VISTAS.dbo.VIEW_FACT_SEGUIMIENTO_VOL_GENERAL`,
   cruzada con las vistas SLA, con su fecha de vencimiento, estado de cumplimiento y tiempos de atención/pendiente.

Origen: el mismo `DB.xlsx`, ahora en **SharePoint** (ReportingFractalia / Data Reporting / REPOSITORIOS DE CRUDOS / CHILE /
BPOCHIPE / `08 PUNTUALIDAD`), leído por Microsoft Graph. Antes era
`...\BPO - Insumos\Chile\INDICADORES CHILE\SLA Puntualidad\DB.xlsx`.

La equivalencia, las decisiones y la evidencia están en [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md).

## Qué cambió respecto de SSIS

| | SSIS | Python |
|---|---|---|
| `PUNTUALIDAD` | `DROP` + `SELECT INTO` + 13 `ALTER`/`UPDATE`, con 3 funciones escalares con `WHILE` ejecutadas **fila por fila** (~10–20 min) | un `SELECT INTO` con aritmética de calendario (**~20 s**), mismo resultado, probado columna por columna |
| Si algo falla | `TBL_PUNTUALIDAD` queda borrada; `TBL_SLA` queda vacía si el Excel es malo (el `TRUNCATE` corre antes de leerlo) | todo va en una transacción: la tabla anterior queda intacta; el Excel se valida **antes** de tocar la base |
| `SLA` decimal | `TBL_SLA.SLA` es `int`: 13,5 queda en 14 | se conserva el valor real: `TBL_SLA.SLA` pasa a `decimal(10,2)` (13,5) — decisión del usuario, ver [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md) §5b |
| Credenciales | passwords DPAPI dentro del `.dtsx` | `.env` (no versionado) |

Las funciones de `SERVICIOS_GENERALES` (`FUNC_CH_FECHA_INICIO`, `FUNC_CH_FECHA_FIN`, `FUNC_CH_FECHA_VENCIMIENTO`,
`FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS`) **no se modifican**: siguen en el servidor y son la referencia contra la que se
prueba la equivalencia.

## Uso

```bat
python main.py                          :: corrida completa en modo PRUEBA (TBL_SLA_PY y TBL_PUNTUALIDAD_PY)
python main.py --destino produccion     :: corrida completa sobre TBL_SLA y TBL_PUNTUALIDAD reales
python main.py --solo sla               :: solo la carga de TBL_SLA
python main.py --solo puntualidad       :: solo TBL_PUNTUALIDAD
python main.py --solo-validar           :: lee, valida y transforma el Excel; no escribe nada
python main.py --verificar              :: solo conexiones; no carga nada
python main.py --origen-local "D:\ruta\DB.xlsx"   :: contingencia: Excel local
python main.py --equivalencia           :: compara contra el T-SQL original del .dtsx (~10 min)
scripts\ejecutar_puntualidad.cmd        :: para el Programador de tareas (devuelve el exit code)
```

**Modo prueba (por defecto)** escribe `TBL_SLA_PY` y `TBL_PUNTUALIDAD_PY` y **no toca producción**. `TBL_SLA_PY` es un clon de
`TBL_SLA` con `SLA` decimal (se crea sola) y `TBL_PUNTUALIDAD_PY` se calcula leyendo las vistas SLA sobre `TBL_SLA_PY`. Para escribir las
tablas reales hay que pasar `--destino produccion` explícitamente: ese modo hace el `ALTER COLUMN SLA` de `TBL_SLA` a
`decimal(10,2)` (hacerlo después de deshabilitar el job SSIS).

Antes de cargar se validan las conexiones (SQL Server `172.17.0.162` y SharePoint con `DB.xlsx`): si alguna falla, se
reintenta cada 5 min hasta 3 veces y luego termina con exit 1 sin ejecutar nada. Cada corrida deja su log en `logs/` y el
nombre del proyecto aparece en la consola y en el título de la ventana.

Código de salida: 0 OK; 1 error; con `--equivalencia`, 2 si no resulta equivalente.

## Configuración

Copiar `.env.example` como `.env` y completar (SQL Server y App Registration de Graph con `Sites.Selected` sobre
ReportingFractalia). Ninguna credencial está en el código.

## Estructura (src layout, modular por componentes)

```
main.py                                composition root (CLI, título de consola)
src/puntualidad/
  pipeline.py                          orquestador (Control Flow del .dtsx)
  extraccion/extractor.py              SharePoint/local; lectura del Excel (Excel Source)
  validacion/validator.py              encabezados, esquema y anchos reales del destino
  transformacion/transformer.py        Data Conversion: tipos, anchos, cp1252, numeric(10,2) -> int
  carga/loader.py                      TBL_SLA (TRUNCATE + carga + UPDATE) y generación de PUNTUALIDAD
  equivalencia/comparador.py           prueba de equivalencia contra el T-SQL original, en el servidor
  conexiones.py                        validación previa de conexiones (5 min x 3)
  mappings.py, sql.py                  constantes del .dtsx y T-SQL
  scripts_sql/sla/                     TRUNCATE y UPDATE: copia literal del .dtsx
  scripts_sql/puntualidad/             10 calendario, 20 base, 25 valida, 30 cálculo, 40 destino
  scripts_sql/prueba/                  crea TBL_SLA_PY
  db.py, sharepoint/                   adaptadores: pyodbc y Microsoft Graph
  config.py, logging_setup.py, exceptions.py
docs/EQUIVALENCIA.md                   equivalencia, decisiones y evidencia
docs/referencia_sql/p2_PUNTUALIDAD.sql el T-SQL ORIGINAL de PUNTUALIDAD (referencia de la prueba)
evidencias/                            informes de equivalencia (no versionados)
tests/unit, tests/equivalencia
```

## Pruebas

```bat
pip install -r requirements-dev.txt
python -m pytest
```

Las pruebas de `tests/equivalencia` leen el `.dtsx` original (si está en esta máquina) y verifican que los T-SQL
literales, los anchos del Data Conversion, el mapeo de columnas y el Control Flow siguen siendo los del paquete. La
equivalencia de **datos** se mide contra el servidor con `python main.py --equivalencia`.
