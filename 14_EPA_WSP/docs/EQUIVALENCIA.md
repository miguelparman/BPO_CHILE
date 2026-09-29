# Equivalencia SSIS ↔ Python: `CL_Proc_EPA_WSP.dtsx`

Este documento muestra, tarea por tarea, que la migración conserva la lógica del paquete. Se apoya en tres tipos de evidencia:

1. **Pruebas estructurales** contra el .dtsx y los scripts originales: `tests/equivalencia/`.
2. **Oráculos**, que son copias literales de la lógica de los scripts de `102_calidad/`: `tools/oraculos.py`.
3. **Comparaciones sobre datos reales**: `tools/equivalencia.py`, con resultados en `evidencias/` (fuera de git porque contiene RUT y teléfonos).

## 1. Matriz de equivalencia

| # | Tarea del .dtsx | Tipo | Connection Manager | Python | Cómo se demuestra |
|---|---|---|---|---|---|
| 1 | `Log_Inicio` | Execute SQL | 162.BBDD_GENERAL | `loader.registrar_inicio` (`00_log_inicio.sql`) | T-SQL byte a byte (`test_sql_literal_de_cada_execute_sql_task`) |
| 2 | `enviar_alerta_encuesta_py` | Execute Process | — | `alerta.py` | Fecha límite igual al oráculo durante 14 días seguidos; textos literales; BOM |
| 3a | `WSP\TRUNCATE TBL_ENCUESTAS_WSP_MEDALLIA` | Execute SQL | 162.CL_TEMPORALES_INDICADORES | `DELETE … WHERE Periodo IN (<periodos del CSV>)` | Decisión (a), ver §3 |
| 3b | `WSP\Traslado_…_EPA_WSP_MEDALLIA_py` | Execute Process | — | `transformer.wsp_medallia` + `loader.cargar_ventana` | `clean_value` = `clean_row` literal; columnas = `column_list`; datos reales, §4 |
| 4a | `EPA_ISN\TRUNCATE TBL_ENCUESTAS_CHILE` | Execute SQL | 162.CL_TEMPORALES_INDICADORES | `DELETE … periodo_evento IN (…)` + `DELETE < 202601` | Decisión (a) |
| 4b | `EPA_ISN\Traslado_…_EPA_ISN_py` | Execute Process | — | `transformer.encuestas_chile` + `loader.cargar_ventana` | Columnas = `column_list`; filtro `>= 202601`; datos reales, §4 |
| 5 | `SP_EPA_ISN_CHILE` | Execute SQL | 162.CL_CALIDAD | `loader.ejecutar_sp` (`30_sp_epa_isn_chile.sql`) | T-SQL literal; los 4 logs internos terminan OK |
| 6 | `Carga Azure` | Execute Process | — | **No se migra** | `Disabled=True`; el script `carga_TBL_CALIDAD_TRIADA_azure.py` no existe |
| 7a | `MEDALIA\DESCARGA_MEDALLIA …` | Execute Process | — | `extraccion/medallia_descarga.py` | Mismas URLs y prefijo (`test_descarga_medallia_mismas_urls_y_prefijo`); mismos pasos y selectores, ahora con Playwright (`test_recorre_el_portal_en_el_mismo_orden_que_el_script_selenium`) |
| 7b | `MEDALIA\CARGA BASE …` | Execute Process | — | `transformer.medallia` + `loader.cargar_medallia` | Oráculo literal sobre el mismo CSV: idéntico (§4) |
| 7c | `MEDALIA\SP_PROCESO_ENCUESTAS_MEDALLIA` | Execute SQL | 162.CL_CALIDAD | `loader.ejecutar_sp` (`40_*.sql`) | T-SQL literal; log `SP_Proceso_Medallia_Chile` = OK |
| 8 | `Log_Fin` | Execute SQL | 162.BBDD_GENERAL | `loader.registrar_fin` (`99_log_fin.sql`) | T-SQL literal |

**Orden.** El .dtsx tiene 13 Precedence Constraints: 9 del paquete y 4 dentro de los contenedores. WSP, EPA_ISN y MEDALIA corrían en paralelo después de la alerta. Aquí se ejecutan en serie, como se pidió. `test_orden_serial_respeta_todas_las_precedence_constraints` verifica que el orden serial cumple las 13 restricciones.

**Política de fallos.** Los 5 Execute Process tienen `FailTaskIfReturnCodeIsNotSuccessValue=False`: en SSIS, un script que falla no detiene el paquete. Python replica ese comportamiento: los pasos tolerantes registran el error y siguen. Las Execute SQL sí cortan su rama. Las pruebas `test_pipeline.py` cubren:

- fallo de un traslado;
- rollback cuando falla el INSERT;
- SP fallido: no se ejecuta `Log_Fin`, pero sí la rama Medallia;
- descarga de Medallia fallida: se carga el CSV existente;
- `Log_Inicio` fallido;
- modo `--estricto`.

**Semántica de conexión.** Los SP y los logs se ejecutan en *autocommit*, como el Connection Manager OLE DB. Si `SP.EPA_ISN_CHILE` hace `THROW`, lo que ya confirmó queda confirmado, incluido su propio registro `ERROR` en `PE_CALIDAD.dbo.LOGS_PROCESOS_SQL`. La conexión se reintenta una vez tras 5 s (`ConnectRetryCount=1`, `ConnectRetryInterval=5`).

## 2. Tipos de datos

El .dtsx no tiene Data Flow, así que no declara columnas. Los tipos son los de las tablas destino, tomados de `INFORMATION_SCHEMA` y fijados en `mappings.py`. `validator.validar_esquemas` los verifica en cada corrida, antes de escribir.

Antes, los scripts leían filas **tipadas** de `[Externos_Frac]` con pyodbc. Ahora el origen es un CSV de texto, y cada valor se convierte al tipo destino:

| Tipo destino | Regla | Por qué |
|---|---|---|
| `int` | `int(Decimal(texto))`: `'10.00'` → 10, trunca hacia cero | Origen `decimal` → pyodbc `Decimal` → conversión implícita numeric→int de SQL Server |
| `datetime` | `'YYYY-MM-DD HH:MM:SS'` → `datetime` (parámetro nativo) | La sesión usa `DATEFORMAT dmy`: nunca se inserta la fecha como texto |
| `(n)varchar` | Texto tal cual | `periodo_evento` es `nvarchar(10)`: el DELETE lo compara como texto |
| Celda vacía | NULL, con la excepción de WSP descrita abajo | `csv.writer` (01_servidor_chile) escribe igual NULL y `''` |

**`''` y NULL.** El CSV no distingue una cadena vacía de un NULL. La regla se derivó de los datos reales:

- **`ENCUESTA`:** en los periodos que publica el CSV (202608 y 202609), el origen no tiene `''` en ninguna columna de texto (0 de 15.279 filas). Por eso vacío = NULL.
- **`WS_MEDALLIA_2`:** `tipificacion` es `''` cuando la encuesta cruzó con la interacción (`pcrc_eac` informado) y NULL cuando no. Se cumple en 131 de 131 filas de todo el histórico. El resto de las columnas vacías son NULL (`Subtype`: 587/587; `pcrc_eac`, `loginid` y `vq`: 7/7). La regla está en `mappings.WSP_TEXTO_VACIO_SI_INFORMADA`.

**Anchos.**

- **WSP:** trunca al ancho de la columna, igual que `clean_row`. Además fija `setinputsizes`, que era la corrección del bug "String data, right truncation".
- **EPA_ISN:** el original no truncaba. Un valor largo hacía fallar toda la transacción, así que aquí se valida antes y el traslado falla con la tabla intacta.
- **Medallia:** el original omitía la fila que fallaba. Aquí también: se intenta un INSERT masivo y, si falla, se inserta fila a fila.

**Medallia: `Responsedate`.** En el original, una fecha vacía o que no cumple `dd-mm-aaaa` queda como `NaT`, porque `.where(..., None)` no cambia una columna datetime. pyodbc la envía fuera de rango y **esa fila falla** (verificado contra SQL Server: error 242, "conversión de datetime2 en datetime … fuera de intervalo"). Python rechaza esas filas antes de insertar y las informa con el mismo número de fila. `test_medallia_equivale_al_script_original` lo verifica con el oráculo.

## 3. Cambios deliberados respecto del original

| Cambio | Motivo |
|---|---|
| **Origen `[Externos_Frac]` → CSV de SharePoint (Graph)** | Requerimiento de la migración |
| **TRUNCATE → DELETE de los periodos del CSV + INSERT, en 1 transacción** (decisión (a)) | El CSV trae solo 2 meses. Con TRUNCATE, `TBL_ENCUESTAS_CHILE` perdería 202601-202607 y WSP perdería 202509-202607, que `SP.EPA_ISN_CHILE` usa (RETENCIONES `>= 202401`, USUARIOS `>= 202510`) |
| Un traslado fallido deja la tabla **intacta** | En SSIS la tabla quedaba truncada y el SP reconstruía `TBL_CALIDAD_RETENCIONES` vacía |
| `Encuestas_Medallia.csv` y `resultado.txt` se guardan vía Graph en SharePoint (`Data Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA`) y no en carpetas locales | Requerimiento. La alerta conserva la secuencia original (borrar → esperar 30 s → recrear, UTF-8 con BOM) y la carga lee el CSV desde SharePoint con la misma lectura `latin1`/`dtype=str`. Verificado en real el 29/09 a las 12:15. **El flujo de Power Automate debe vigilar la nueva ubicación** |
| Credenciales en `.env` | Los scripts tenían en texto plano la password SQL y la cuenta Medallia. **Rotarlas** |
| Descarga Medallia: **Playwright** en vez de Selenium + geckodriver. La descarga se captura con `expect_download` (hasta 60 s), se valida el prefijo del nombre y se guarda de forma atómica. Si falla, deja una captura de pantalla en `logs/` | El original esperaba 10 s fijos, tomaba el archivo con prefijo más reciente de `D:\Descargas` (aunque fuera de una descarga anterior) y, ante cualquier error, terminaba con código 0. La carga leía en silencio el CSV del día anterior. Prueba real del 29/09 11:36: login y export en 9,7 s (antes unos 29 s), y el oráculo sale idéntico, 50/50 |
| Ejecución en serie | Requerimiento. En el .dtsx las 3 ramas corrían en paralelo |
| Mensaje de error de la alerta: "Acción: Revisar la conexión a SharePoint…" | El origen ya no es Azure SQL. Los mensajes OK y DESACTUALIZADA quedan byte a byte, porque Power Automate los reenvía |

## 4. Evidencia sobre datos reales (2026-09-29)

**1. Simulación previa, sin escribir** (`tools/equivalencia.py simular`, 11:18). La transformación Python del CSV de SharePoint se comparó con lo que SSIS había cargado el 28/09 para 202608-202609:

| Tabla | SSIS | Python | Solo SSIS | Columnas distintas | Solo Python |
|---|---|---|---|---|---|
| TBL_ENCUESTAS_CHILE | 15.279 | 15.779 | **0** | **ninguna** | 500 encuestas nuevas del 28-29/09 |
| TBL_ENCUESTAS_WSP_MEDALLIA | 587 | 589 | **0** | **ninguna** | 2 encuestas nuevas |

`01_servidor_chile` actualizó el CSV entre las 11:15 y las 11:18. Esas filas "solo Python" son encuestas que el origen recibió después de la corrida SSIS del 28/09.

**2. Corrida real** (`python main.py`, 11:22:37 a 11:24:49, código de salida 0). Todos los pasos terminaron OK:

- Log_Inicio.
- Alerta: `TABLA ENCUESTA ACTUALIZADA ✅`, último registro 28/09 22:48.
- WSP: 589 filas.
- EPA_ISN: 15.779 filas.
- `SP.EPA_ISN_CHILE`: 48 s; `Update_Chile_Retenciones`, `Usuarios`, `Carterizados` y `Calidad_WSP` en OK.
- Descarga Medallia: 50 encuestas.
- Carga: 50/50, 0 errores.
- `SP_PROCESO_ENCUESTAS_MEDALLIA`: OK.
- Log_Fin: `Update_Chile_Calidad_Epa` = OK.

**3. Fotos antes y después** (`foto ssis` antes de la corrida, `foto python` después, `comparar ssis python`):

| Tabla | Periodos fuera de la ventana | Ventana 202608-202609 |
|---|---|---|
| TBL_ENCUESTAS_CHILE (76.871 → 77.371) | 202601-202607: **idénticos fila a fila** (61.592 filas) | 202608 idéntico; 202609 +500 nuevas; 0 filas SSIS perdidas o cambiadas |
| TBL_ENCUESTAS_WSP_MEDALLIA (3.211 → 3.213) | 202509-202607: **idénticos** (2.624 filas) | 202608 idéntico; 202609 +2 nuevas; 0 perdidas o cambiadas |

Salida de los SP en CL_CALIDAD (filas totales): crece solo por las encuestas nuevas.

| Tabla | Después de SSIS (28/09) | Después de Python (29/09) |
|---|---|---|
| TBL_CALIDAD_RETENCIONES | 4.544 | 4.568 |
| TBL_CALIDAD_TRIADAS | 132.790 | 132.997 |
| TBL_CALIDAD_USUARIOS | 46.760 | 46.841 |
| TBL_CALIDAD_ISN_CARTERIZADOS | 3.515 | 3.517 |
| TBL_EPA_WSP_TRIADAS_CARTERIZADOS_MEDALLIA | 7.459 | 7.461 |
| TBL_ENCUESTAS_MEDALLIA | 2.756 | 2.770 |

**4. Oráculo Medallia** (`tools/equivalencia.py medallia`). `CL_Carga_de_encuestas_MEDALLIA.py` literal y Python, aplicados al mismo `Encuestas_Medallia.csv` recién descargado: **50/50 filas idénticas**, 0 rechazadas en ambos. Con el CSV del 28/09 también salen idénticas, 36/36.

## 5. Cómo repetir la verificación

```bash
python tools/equivalencia.py foto ssis        # después de una corrida SSIS
python tools/equivalencia.py simular          # solo lectura: CSV → Python vs tabla
python tools/equivalencia.py medallia         # solo lectura: oráculo vs Python
python main.py
python tools/equivalencia.py foto python
python tools/equivalencia.py comparar ssis python
python -m pytest                              # 103 pruebas (unitarias + estructurales)
```

## 6. Dependencias y observaciones

- **Orden entre procesos:** `01_servidor_chile` debe publicar los CSV antes de este proceso. La alerta mide justamente la frescura de `ENCUESTA.csv`.
- **Lógica que permanece en SQL Server:** `SP.EPA_ISN_CHILE` y `SP.SP_PROCESO_ENCUESTAS_MEDALLIA` se ejecutan tal cual. Leen solo las temporales de `CL_TEMPORALES_INDICADORES` y otras bases del mismo servidor, **no** `[Externos_Frac]`. Por eso el cambio de origen es completo. Sus definiciones quedan como referencia en `docs/referencia_sp/`.
- **Particularidades preexistentes que no se tocaron:**
  - `SP_PROCESO_ENCUESTAS_MEDALLIA` tiene un `CATCH` vacío, así que sus errores no se propagan.
  - El SP trunca `TBL_ENCUESTAS_MEDALLIA` al terminar, por eso esa tabla siempre queda en 0.
  - El docstring de la alerta dice 18:00, pero `HORA_LIMITE = 17`.
