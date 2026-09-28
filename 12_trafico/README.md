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
| CL_TRAFICO | `DELETE PERIODO` y Data Flow `CARGA` hacia 8 tablas (en una transacción). Luego ejecuta `UPDATE_WSP`. | `transformacion/`, `carga/` |
| Log Fin | `UPDATE LOGS_PROCESOS` → `OK` | `carga/loader.py` |

**Periodo** (`User::Periodo`): los días 1 al 4 se usa el mes anterior y desde el día 5, el mes actual.

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
python -m pytest                # 87 pruebas
```

Los logs se escriben en `logs/trafico_YYYYMMDD_HHMMSS.log`. El código de salida es 0 si todo sale bien y 1 si hay un error.

## Configuración (`.env`)

Ver [.env.example](.env.example). Contiene las credenciales de SQL Server, el App Registration de Graph (`TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`), la carpeta de SharePoint, la ruta de `resultado.txt` (`ALERTA_TXT_PATH`), el periodo y `BATCH_SIZE`. **No hay credenciales en el código.**

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
