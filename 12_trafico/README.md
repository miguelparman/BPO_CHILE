# 12_trafico

Migración a Python del paquete SSIS **`CL_Proc_Trafico_01.dtsx`**: carga diaria del tráfico de Chile (llamadas atendidas, abandonadas, transferidas, outbound, cleared, callback, cross inbound y chat) en `CL_TEMPORALES` y `CL_TRAFICO`.

El origen cambia. Antes los 7 scripts `Traslado_Trafico_Servidor_55_*.py` leían `[Externos_Frac]`, en el SQL Server del dominio de Chile. Ahora se leen **CSV en SharePoint** mediante Microsoft Graph, desde `REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/13 SERVIDOR CHILE`, la carpeta donde los publica `01_servidor_chile`.

## Flujo

```
Log Inicio ─► alerta ─► TEMPORALES ─► LIMPIA TEMPORALES ─► CL_TRAFICO ─► Log Fin
```

| Paso | Qué hace | Dónde |
|---|---|---|
| Log Inicio | `INSERT` en `BBDD_GENERAL.dbo.LOGS_PROCESOS` (`Chile_Trafico`, `exec...`) | `carga/loader.py` |
| enviar_alerta_trafico | Revisa si `ATENDIDA` tiene registros desde las 17:00 de ayer y escribe `resultado.txt` para Power Automate. **No detiene el proceso si falla.** | `alerta.py` |
| TEMPORALES | Descarga y valida los 7 CSV y **después** hace `TRUNCATE` y el INSERT de las 7 temporales (en una transacción). Luego ejecuta `UPDATE`. | `extraccion/`, `validacion/`, `carga/`, `transformacion/` |
| LIMPIA TEMPORALES | 6 tareas SQL: ANI, RUT, COD_DNI, SEGMENTO, SEGMENTO COLA, LLAMA CCAA? | `transformacion/transformer.py` + `scripts_sql/` |
| PREVISTO | Carga acumulativa de `CL_DATA.dbo.TBL_PREVISTO_CL` desde un CSV de SharePoint, dentro del bloque TEMPORALES. **No estaba en el `.dtsx`** y **no detiene el proceso si falla**. Ver [Previsto](#previsto-tbl_previsto_cl). | `previsto.py`, `carga/loader.py`, `pipeline.py` |
| CL_TRAFICO | `DELETE PERIODO` y Data Flow `CARGA` hacia 8 tablas (en una transacción). Luego ejecuta `UPDATE_WSP`. | `transformacion/`, `carga/` |
| Log Fin | `UPDATE LOGS_PROCESOS` → `OK` | `carga/loader.py` |

**Periodo** (`User::Periodo`): los días 1 al 4 se usa el mes anterior y desde el día 5, el mes actual.

## Previsto (`TBL_PREVISTO_CL`)

Carga el previsto de contactos a `[CL_DATA].[dbo].[TBL_PREVISTO_CL]` (172.17.0.162) desde `PVTA_PROYECCION_PPP_FRACTALIA_PERU.csv`, en `REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/15 PORTAL COMERCIAL` del SharePoint ReportingFractalia, mediante Microsoft Graph. Antes no había ningún ETL conocido que cargara esa tabla (no está en el Agent ni en SSISDB). La lógica pura (leer, validar, transformar y planificar) está en `src/trafico/previsto.py`; la escritura, en `carga/loader.py` (`cargar_previsto`), y el orden de los pasos, en `pipeline.py`.

**Modelo de la tabla** (heap sin clave; llave natural `Servicio + Fecha + Tramo`; todas las columnas `NOT NULL`): `Servicio`, `Fecha`, `ID_Tramo`, `Tramo`, `Tramo_Horario`, `Prev_Voz`, `Prev_Chat`.

| Columna | Origen |
|---|---|
| `Servicio` | `PCRC`. Solo se carga `Usuarios Empresa` y `PLAT USUARIOS EMPRESA`, que pasan a `USUARIOS`. `PYMES CARTERIZADOS` y `TRIADA NO CARTERIZADO MICRO` se ignoran (el archivo los trae siempre en 0). Cualquier otro PCRC detiene la carga. |
| `Fecha` | `FECHA` (`yyyy-MM-dd`) |
| `Tramo` | `INTERVALO` (`HH:mm:ss`, grilla de 30 minutos) |
| `ID_Tramo` | `d/MM/yyyy` + `HH:mm`, sin separador y con el día **sin cero inicial** (p. ej. `1/09/202600:30`), el formato que tenía la tabla en 2025. Toda la tabla quedó uniformada con él. |
| `Tramo_Horario` | `HH:mm-HH:mm` (el último tramo del día es `23:30-24:00`) |
| `Prev_Voz` | `PRONOSTICO` (coma o punto decimal). **No** se usa `REQUERIDOVOZ`. |
| `Prev_Chat` | `0`: el archivo no trae chat |

Las demás columnas del CSV (`PROVEEDOR`, `PRONOSTICOTMO`, `REQUERIDOVOZ`, `REQUERIDOCALLBACK`, `REQUERIDOMULTISKILL`, `REQUERIDO`, `AGENTEPROGRAMADO`, `AGENTEOJT`) no se cargan.

**Regla de carga acumulativa** (con `hoy` = fecha de Chile):

| Fechas | Qué se hace |
|---|---|
| `Fecha <= hoy` | Solo se **insertan** las llaves que faltan. Lo existente no se modifica ni se borra nunca (aunque el archivo traiga otro `Prev_Voz`). |
| `Fecha > hoy` | Se **borran** las fechas futuras de la tabla y se reinsertan las del archivo, **solo si el archivo trae fechas futuras**. El futuro que el archivo no cubra se pierde; está aceptado. |

**Condición de ejecución:** el previsto solo se carga si el archivo trae registros con `Fecha >= hoy`. Si no, se omite (queda un aviso en el log y el resultado `omitido`) y la tabla se mantiene. No aplica al relleno único (`--solo-faltantes`).

**Validaciones** (antes de escribir; si fallan, la tabla queda intacta): cabecera completa de 12 columnas, archivo no vacío, PCRC conocido, `FECHA` e `INTERVALO` con formato válido y en la grilla de 30 minutos, `PRONOSTICO` numérico y no negativo, y llave `Servicio + Fecha + Tramo` sin repetidos. Si un servicio-día no trae los 48 tramos solo se avisa en el log.

**Tolerancia a fallos:** el previsto va en su propia transacción sobre `CL_DATA` (tercera conexión, `DB_NAME_DATA`). Si algo falla (descarga, validación o escritura), se registra el error, se revierte lo escrito y el tráfico continúa.

**Cómo correrlo:**

```bash
python main.py --solo-previsto --solo-validar   # ensayo: descarga, valida y muestra qué insertaría y reemplazaría; no escribe
python main.py --solo-previsto                  # solo el previsto, con la regla acumulativa (no toca tráfico ni LOGS_PROCESOS)
python main.py --solo-previsto --solo-faltantes # relleno único de historia: solo inserta lo que falta hasta hoy
python main.py                                  # flujo completo: tráfico y, dentro de TEMPORALES, el previsto
```

`--solo-faltantes` es para cargar un archivo histórico (que no llega a hoy): inserta las llaves que faltan hasta hoy y no toca nada con `Fecha > hoy`. **No usar la carga normal con un archivo viejo o más corto que el futuro ya cargado**, porque borraría ese futuro. El ensayo con `--solo-validar` muestra siempre las filas a insertar, las que ya existen y las futuras a borrar y reinsertar.

**Migración a PostgreSQL:** esta carga al 172.17.0.162 se migró a `fractalia-data-platform` (`proyectos/chile/bpo`) como rama opcional de `main_trafico`: crudo `sharepoint.tb_sharepoint_previsto_bronce_bpochipe`, silver `silver.tb_sharepoint_previsto_silver` y gold `hechos.tb_fact_previsto_bpo_gold`, con las mismas reglas (sql `083_previsto.sql`). El histórico (98.592 filas) se cargó una vez desde esta tabla y quedó idéntico fila a fila. Cuando ese flujo sea el que corra a diario, esta carga del 162 no debe ejecutarse en paralelo.

## Estructura (src layout)

```
12_trafico/
├── main.py                     composition root + CLI
├── src/trafico/
│   ├── pipeline.py             orquestador (orden del Control Flow)
│   ├── extraccion/extractor.py CSV → DataFrame tipado; lectura de temporales
│   ├── validacion/validator.py esquema real vs mappings; anchos de datos
│   ├── transformacion/transformer.py  tareas SQL + Data Flow CARGA (pandas)
│   ├── carga/loader.py         LOGS_PROCESOS, temporales, CL_TRAFICO
│   ├── alerta.py               enviar_alerta_trafico.py migrado
│   ├── previsto.py             previsto (TBL_PREVISTO_CL): validar, transformar y planificar la carga
│   ├── mappings.py             orígenes, esquema temporales, mapeo CARGA (401 columnas)
│   ├── sql.py + scripts_sql/   T-SQL LITERAL de cada Execute SQL Task
│   ├── db.py                   pyodbc (lotes separados por GO, transacciones)
│   ├── sharepoint/             Graph: auth, client, reader (CSV)
│   └── config.py, models.py, exceptions.py, logging_setup.py
├── tests/unit/                 pruebas con dobles (sin base ni SharePoint)
├── tests/equivalencia/         pruebas contra el .dtsx y los .py originales
├── tools/equivalencia.py       comparación SSIS vs Python sobre datos reales
└── docs/EQUIVALENCIA.md        matriz de equivalencia y diferencias
```

## Instalación y uso

```bash
pip install -r requirements-dev.txt
cp .env.example .env            # completar credenciales (NUNCA versionar .env)

python main.py --solo-validar   # descarga y valida CSV + esquema; no escribe nada
python main.py                  # corrida normal (User::Periodo)
python main.py --periodo 202609 # fuerza el periodo
python main.py --solo-previsto  # solo el previsto (ver la sección Previsto)
python -m pytest                # 116 pruebas
```

Los logs se escriben en `logs/trafico_YYYYMMDD_HHMMSS.log`. El código de salida es 0 si todo sale bien y 1 si hay un error.

## Configuración (`.env`)

Ver [.env.example](.env.example). Contiene las credenciales de SQL Server, el App Registration de Graph (`TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`), la carpeta de SharePoint, la ruta de `resultado.txt` (`ALERTA_TXT_PATH`), el periodo y `BATCH_SIZE`. Para el previsto: `DB_NAME_DATA` (por defecto `CL_DATA`) y `SHAREPOINT_FOLDER_PATH_PREVISTO` (por defecto `15 PORTAL COMERCIAL`). **No hay credenciales en el código.**

**Periodo** (antes calculado dentro de cada script `Traslado_Trafico_Servidor_55_*.py`):

| Variable | Valor | Efecto |
|---|---|---|
| `PERIODO` | vacío (operación diaria) | Automático: si hoy es día ≤ `DIA_CIERRE_MES`, se procesa el mes anterior; si no, el mes actual |
| `PERIODO` | `YYYYMM`, p. ej. `202608` | Recarga desde ese mes: filtra los CSV con `>= PERIODO` y lo usa en `DELETE PERIODO` |
| `DIA_CIERRE_MES` | `4` (valor original) | Último día del mes en que se sigue recargando el mes anterior |

Prioridad: `--periodo` en la línea de comandos, luego `PERIODO` del `.env` y, si no hay ninguno, el cálculo automático. El log muestra qué periodo se usó y de dónde salió.

Los scripts `101_trafico/*.py` originales tenían el usuario y la contraseña de SQL Server escritos en el código. Esa contraseña debería cambiarse.

## Diferencias con SSIS

Ver [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md). En resumen:
1. **Origen**: CSV de SharePoint en lugar de `[Externos_Frac]`.
2. **Los errores ya no se descartan en silencio.** Los scripts Outbound, Transfer y Callback descartaban los lotes que fallaban, y Cleared y Cross_In las filas. El 28/09/2026, por ejemplo, SSIS cargó 10.000 de las 38.413 filas de OUTBOUND. Ahora cualquier error detiene el proceso.
3. **Validación previa**: si un CSV falta o trae datos inválidos, el proceso se detiene *antes* del `TRUNCATE`.
4. **Transacciones**: `DELETE PERIODO` y `CARGA` son atómicos. Si algo falla, el periodo no queda borrado.
5. **MENSAJES WSP** no se migra porque está deshabilitado en el `.dtsx`.
6. **Previsto** (`TBL_PREVISTO_CL`): paso nuevo que no existía en el paquete; se agregó al bloque TEMPORALES (ver [Previsto](#previsto-tbl_previsto_cl)).
