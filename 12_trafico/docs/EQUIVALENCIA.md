# Equivalencia SSIS ↔ Python: `CL_Proc_Trafico_01.dtsx`

Este documento muestra, tarea por tarea, cómo se reproduce en Python el paquete original, qué cambia a propósito y cómo se comprueba la equivalencia.

## 1. Matriz de equivalencia

### Connection Managers y variables

| SSIS | Python |
|---|---|
| `PEOPEDESK0328.CL_TEMPORALES` (OLE DB, 172.17.0.162) | `DatabaseGateway` sobre `DB_NAME_TEMPORALES` (`config.py`, `db.py`) |
| `PEOPEDESK0328.CL_TRAFICO` | `DatabaseGateway` sobre `DB_NAME_TRAFICO` |
| Contraseñas cifradas con DPAPI y credenciales escritas en los `.py` | `.env` (no versionado) |
| `User::Periodo` (expresión) | `models.calcular_periodo()` |

### Control Flow

| # | Tarea SSIS | Tipo | Python | Conexión |
|---|---|---|---|---|
| 1 | Log Inicio | Execute SQL | `loader.registrar_inicio` → `00_log_inicio.sql` | CL_TRAFICO |
| 2 | enviar_alerta_trafico | Execute Process (`enviar_alerta_trafico.py`, sin fallo) | `alerta.enviar_alerta` (nunca lanza excepción) | SharePoint |
| 3.1 | TEMPORALES\TRUNCA TABLAS | Execute SQL | `10_temporales_trunca_tablas.sql` | CL_TEMPORALES |
| 3.2–3.8 | TEMPORALES\Atendidas … Cross_In | Execute Process (7 `.py`) | `extractor.extraer_origen` + `validator.validar_origen` + `loader.cargar_temporales` | SharePoint → CL_TEMPORALES |
| 3.9 | TEMPORALES\UPDATE | Execute SQL | `transformer.actualizar_temporales` → `11_temporales_update.sql` | CL_TEMPORALES |
| 4.1–4.6 | LIMPIA TEMPORALES (FORMATEANDO ANI, UPDATE RUT, UPDATE COD_DNI, UPDATE SEGMENTO, SEGMENTO COLA, LLAMA CCAA?) | Execute SQL | `transformer.limpiar_temporales` → `20_…` a `25_….sql` | CL_TEMPORALES |
| 5.1 | CL_TRAFICO\DELETE PERIODO (`? = User::Periodo`) | Execute SQL | `loader.cargar_cl_trafico` → `30_cl_trafico_delete_periodo.sql` | CL_TRAFICO |
| 5.2 | CL_TRAFICO\CARGA | Data Flow | `transformer.transformar_carga` + `loader.cargar_cl_trafico` | CL_TEMPORALES → CL_TRAFICO |
| 5.3 | CL_TRAFICO\UPDATE_WSP | Execute SQL | `transformer.actualizar_wsp` → `31_cl_trafico_update_wsp.sql` | CL_TEMPORALES |
| 6 | Log Fin | Execute SQL | `loader.registrar_fin` → `99_log_fin.sql` | CL_TRAFICO |
| — | MENSAJES WSP (LIMPIAR + `Traslado_Servidor_55_Mensajes_WSP.py`) | **Deshabilitado** | No se migra | — |

El T-SQL de `scripts_sql/` es **una copia literal** del `SqlStatementSource` de cada tarea. Los separadores `GO` se procesan igual que en el Execute SQL Task: el script se ejecuta lote por lote.

### Scripts `.py` migrados (TEMPORALES)

| Script original | Origen antes | Origen ahora | Filtro | Tabla temporal |
|---|---|---|---|---|
| Traslado_Trafico_Servidor_55_Atendida.py | `Externos_Frac.dbo.ATENDIDA` | `ATENDIDA.csv` | `DATE_YYYYMM >= periodo` | TBL_TRAFICO_ATENDIDA |
| …_Abondono.py | `ABANDONO` | `ABANDONO.csv` | ídem | TBL_TRAFICO_ABANDONO |
| …_Transfer.py | `TRANSFER` | `TRANSFER.csv` | ídem | TBL_TRAFICO_TRANSFER |
| …_Outbound.py | `OUTBOUND` | `OUTBOUND.csv` | ídem | TBL_TRAFICO_OUTBOUND |
| …_Cleared.py | `CLEARED` | `CLEARED.csv` | ídem | TBL_TRAFICO_CLEARED |
| …_Callback.py | `CALLBACK` | `CALLBACK.csv` | `CONVERT(VARCHAR(6),FECHA,112) >= periodo` | TBL_TRAFICO_CALLBACK |
| …_Cross_Inbound.py | `cross_inbound` | `cross_inbound.csv` | `DATE_YYYYMM >= periodo` | TBL_TRAFICO_CROSS_INBOUND |
| enviar_alerta_trafico.py | `MAX(START_…)` de `ATENDIDA` | `ATENDIDA.csv` | — | `resultado.txt` |

### Data Flow `CARGA`

| Componente SSIS | Python |
|---|---|
| 7 OLE DB Source `TBL_55_*` (tabla completa) | `extractor.leer_temporal` |
| Conditional Split sobre ATENDIDA: `Inbound` (`MEDIA=="VOICE" && INTERACTION_TYPE=="INBOUND"`) y `Chat` (`MEDIA=="CHAT" && INTERACTION_TYPE=="INBOUND_WSP"`). Salida predeterminada sin conectar. | `transformer.dividir_atendida`, con lógica de tres valores de SSIS. Si una condición da NULL, falla (`FailComponent`). |
| Derived Column (CALLBACK): `FECHA_DATE=(DT_DATE)FECHA`, `FECHA_HORA=SUBSTRING((DT_STR,30,1252)FECHA,12,8)` | `transformer.derivar_callback` |
| 8 Data Conversion (`DT_STR` n, `DT_I4`, `DT_DBTIMESTAMP`, `DT_DBDATE`, `DT_WSTR`) | `transformer.convertir_ssis`. `DT_STR` exige code page 1252 y que el valor no se trunque. |
| 8 OLE DB Destination (fast load) y la conversión implícita al tipo real de la columna | `transformer.convertir_destino` + `DatabaseGateway.bulk_insert` |
| Disposiciones: todas `FailComponent` salvo `HORA_INICIO_LLAMADA` y `HORA_FIN_LLAMADA` de Callback (`IgnoreFailure`) | `ConversionError`, o NULL si `ignorar_fallo=True` |

El mapeo columna a columna (401 columnas, con renombres como `VIRTUAL_QUEUE→COLA`, `AGENT_NAME→NOMBRE_AGENTE` o `CALC_NUM_TELEFONO→ANI`) está en `mappings.DESTINOS`. Se **generó trazando el linaje del .dtsx** y la prueba `test_carga_mapea_las_mismas_columnas_con_las_mismas_conversiones` lo vuelve a trazar para comprobarlo.

## 2. Tipos de datos

- Las temporales reciben los valores **con el tipo nativo de cada columna**: `int`, `date`, `datetime` y texto, según `INFORMATION_SCHEMA`.
- **Las fechas nunca se envían como texto.** La sesión de SQL Server usa `DATEFORMAT dmy`, así que `'2026-09-01'` en texto podría leerse como 9 de enero.
- **Celda vacía del CSV.** El CSV no distingue NULL de `''`. Se usa lo que tenía la tabla de origen, verificado contra la temporal que dejó SSIS: **NULL** en todas salvo **`cross_inbound`**, que guarda `''`. En las columnas que no son texto, una celda vacía siempre es NULL.
- **`HORA_INICIO_LLAMADA` y `HORA_FIN_LLAMADA` de Callback** son `nvarchar` en la temporal y venían de un `datetime2(7)`. Se escriben con el mismo formato que dejaba SQL Server: `YYYY-MM-DD HH:MM:SS.fffffff`.
- Antes de cargar, `validator.validar_esquemas` comprueba que las 15 tablas mantienen los tipos y anchos que asume `mappings.py`.

## 3. Diferencias intencionales

| # | SSIS / scripts originales | Python | Motivo |
|---|---|---|---|
| 1 | Origen `[Externos_Frac]` (servidor del dominio de Chile) | CSV en SharePoint mediante Graph | Pedido de la migración |
| 2 | Transfer, Outbound y Callback descartaban los lotes que fallaban; Cleared y Cross_In, las filas. Atendida y Abandono hacían rollback de su tabla. **El proceso seguía igual.** | Cualquier error detiene el proceso con un mensaje claro | No perder datos en silencio. El 28/09 SSIS cargó 10.000 de 38.413 filas de OUTBOUND. |
| 3 | Cada script leía su origen después del `TRUNCATE` | Los 7 CSV se descargan y validan **antes** del `TRUNCATE` | Si falta un origen, no quedan temporales vacías a medias |
| 4 | `DELETE PERIODO` y `CARGA` eran tareas separadas | Una sola transacción | Un fallo en CARGA no deja el periodo borrado |
| 5 | `TRUNCATE` y los INSERT se confirmaban por separado | Una sola transacción | Ídem |
| 6 | Los scripts hacían `DELETE … WHERE DATE_YYYYMM >= ?` sobre la temporal recién truncada | Se omite | No hacía nada |
| 7 | MENSAJES WSP (deshabilitado) | No se migra | Ya estaba deshabilitado |
| 8 | Mensaje de error de la alerta: "Revisar la conexión a Azure SQL…" | "Revisar la conexión a SharePoint (Microsoft Graph)…" | El origen cambió. Los demás textos se mantienen, incluida la frase "18:00 del día anterior", aunque el límite real del script siempre fue 17:00. |

Igual que en SSIS: si el proceso falla, `Log Fin` no se ejecuta y `LOGS_PROCESOS` queda en `exec...`.

## 4. Cómo se demuestra la equivalencia

### a) Pruebas estructurales contra el .dtsx (`tests/equivalencia/`)

`python -m pytest tests/equivalencia` lee el `.dtsx` original y los `.py` de `101_trafico/`, y verifica:
- que el T-SQL es idéntico;
- el orden de las Precedence Constraints;
- la expresión de `User::Periodo` y el parámetro de `DELETE PERIODO`;
- el linaje y las conversiones de las 401 columnas;
- las condiciones de la división condicional y las columnas derivadas;
- las columnas de los INSERT, las tablas de origen y los filtros de los 7 scripts.

### b) Pruebas unitarias (`tests/unit/`)

Cubren el periodo en fechas límite, el separador `GO` con LF y CRLF, la tipificación del CSV, las reglas de NULL, cada conversión SSIS (truncamiento, code page 1252, `IgnoreFailure`), la lógica de tres valores del Split, el orden de las tareas y la conexión de cada una, que un fallo antes del `TRUNCATE` no borre nada, los rollbacks y que un fallo de la alerta no detenga el proceso.

### c) Datos reales: `tools/equivalencia.py`

| Comando | Qué prueba | Escribe en la base |
|---|---|---|
| `foto ssis --periodo P` | Guarda las 7 temporales y el periodo de las 8 tablas de CL_TRAFICO | No |
| `carga-offline ssis` | Pasa **las temporales que dejó SSIS** por el Data Flow de Python y compara con lo que **SSIS escribió** en CL_TRAFICO | No |
| `extraccion-offline ssis` | Extrae los CSV con Python y compara con lo que los `.py` originales insertaron en las temporales | No |
| `foto python` + `comparar ssis python` | Después de una corrida real de Python, compara las 15 tablas fila por fila | No (solo lee) |

**Resultados del 28/09/2026** (foto `ssis` tomada tras la corrida SSIS de las 11:41, periodo 202609):

| Verificación | Resultado |
|---|---|
| `carga-offline`: 8 tablas de CL_TRAFICO (48.051 filas) | **Idénticas, fila por fila** |
| `extraccion-offline`: ATENDIDA, ABANDONO, TRANSFER, CLEARED, CALLBACK, cross_inbound | **Idénticas** |
| `extraccion-offline`: OUTBOUND | Las 10.000 filas de SSIS están todas en Python. Python agrega las 28.413 que SSIS perdió (diferencia #2). |

**Corrida real de Python** (28/09/2026, 15:50–15:52, unos 2,5 min contra 7 min de SSIS). Comparación `comparar ssis python` de las 15 tablas:

| Tablas | Resultado |
|---|---|
| ABANDONO, CLEARED, CROSS_INBOUND y CHAT (temporales + CL_TRAFICO, 7 tablas) | **Idénticas** |
| OUTBOUND (temporal y `TBL_LLAMADAS_ATENDIDAS_OUTBOUND`) | Las 10.000 filas de SSIS son idénticas. Se suman 28.413 filas que SSIS no cargó. |
| CALLBACK (temporal y `TBL_CALLBACK`) | 3.273 de 3.344 idénticas. En 71 filas solo cambia `RUT`, que SSIS dejó en NULL y Python completó. **Es consecuencia de OUTBOUND**: `UPDATE RUT` busca el RUT de Callback en `TBL_ANI_SIN_RUT`, que se arma con las temporales, entre ellas OUTBOUND. |
| ATENDIDA / INBOUND y TRANSFER | 2 filas de 23.089 y 2 de 7.155 difieren en `RUT`, `SEGMENTO*` y `LLAMA CCAA?`. Se debe a **datos de referencia que cambiaron** entre las 11:41 y las 15:51. Por ejemplo, el ANI 967621684 pasó a figurar en `CL_ANALISIS.TBL_CONTACTOS_AUTORIZADOS_CHILE_NUMEROS`, que se consulta con un JOIN exacto. |

Como el T-SQL es literal y las temporales de entrada son idénticas, las columnas enriquecidas solo pueden variar porque cambian las tablas de otras bases (CL_ANALISIS, CL_PLANTA, CL_CARTERA, CL_DATA y el consolidado de CL_TRAFICO). Para una comparación sin esa variable, se puede correr Python justo después de SSIS y volver a comparar.

**Incidencia de la primera corrida:** el servidor cortó la conexión a CL_TEMPORALES tras unos 30 s de inactividad mientras se descargaban los CSV (08S01 / 10054). Falló antes del `TRUNCATE` y no se modificó nada. Desde entonces `DatabaseGateway` comprueba la conexión antes de cada operación y la reabre si hace falta, nunca dentro de una transacción (`tests/unit/test_db_reconexion.py`).
