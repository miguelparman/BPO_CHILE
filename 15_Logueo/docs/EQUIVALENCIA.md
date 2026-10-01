# Equivalencia SSIS ↔ Python: `Cl_Proc_Logueo.dtsx`

Este documento muestra cómo cada elemento del paquete original se reproduce en Python. También indica cómo se demuestra que ambos procesos dan el mismo resultado.

## 1. Control Flow

| # | Tarea SSIS (refId) | Tipo | Python | Notas |
|---|---|---|---|---|
| 1 | `Package\Log Inicio` | Execute SQL | `LogueoLoader.log_inicio` → `scripts_sql/00_log_inicio.sql` | INSERT `'exec...'` en `BBDD_GENERAL.dbo.LOGS_PROCESOS` |
| 2 | `Package\LOGUEO CHILE\CARGA TABLA` | Data Flow | `LogueoPipeline._carga_tabla` | Ver §2 |
| 3 | `Package\LOGUEO CHILE\AGREGA DNI` | Execute SQL | `LogueoLoader.agregar_dni` → `scripts_sql/20_agrega_dni.sql` | `? = User::Periodo` (tipo 131 → `Decimal`) |
| 4 | `Package\Log Fin` | Execute SQL | `LogueoLoader.log_fin` → `scripts_sql/30_log_fin.sql` | UPDATE `'OK'` |
| 5 | `Package\SP` | Execute SQL | `LogueoLoader.sp_logueo` → `scripts_sql/40_sp_logueo.sql` | `EXEC [CL_LOGUEO].[dbo].[SP_LOGUEO]` |
| 6 | `Package\BK` | Execute SQL | **no se migra** | Está deshabilitada en el .dtsx (`DTS:Disabled="True"`). Su SQL queda en `docs/BK_deshabilitado_no_migrado.sql`. |

- **Orden de ejecución:** los pasos van en serie, en el orden de las Precedence Constraints.
- **Ante un fallo:** todas las restricciones son *Success*, así que el primer error detiene el proceso (`PipelineError`). Log Fin no se ejecuta y `LOGS_PROCESOS` queda en `'exec...'`, igual que en SSIS.
- **Conexión:** todas las tareas usan el Connection Manager `CL_LOGUEO`, representado por un único `DatabaseGateway` en autocommit. Las bases `BBDD_GENERAL` y `CL_DATA` se alcanzan con nombres de 3 partes, como en el paquete.
- **T-SQL:** se copia byte a byte del .dtsx (`sql.py`, `scripts_sql/`). La prueba `test_sql_literal_de_cada_execute_sql_task` lo verifica.

## 2. Data Flow `CARGA TABLA`

| Componente SSIS | Python | Comportamiento conservado |
|---|---|---|
| Flat File Source `Logueo` | `extraccion/extractor.py` | <ul><li>CP1252 y separador `;`.</li><li>CRLF como delimitador de fila y de la última columna: un `;` de más queda dentro de `T_NOTR_603` y un LF suelto queda dentro del dato.</li><li>Sin calificador de texto.</li><li>Cabecera en la primera fila y mapeo por posición.</li><li>`RetainNulls`: un campo vacío pasa a `NULL`.</li></ul> |
| Truncamiento del origen (`DT_STR(100)`, FailComponent) | `validator.validar_archivo` | Un valor de más de 100 caracteres hace fallar el proceso. |
| Derived Column `Dia_mes` | `transformer.rellenar_dia_mes`, `rellenar_intervalo` | <ul><li>`MES`/`DIA`: `(DT_I2)x < 10 ? "0"+x : x`, aplicado literalmente (`"09"` → `"009"`).</li><li>`INTERVALO`: `LEN(TRIM(x))==4 ? "0"+TRIM(x) : TRIM(x)`. `TRIM` quita solo espacios.</li><li>El resultado reemplaza la columna original.</li></ul> |
| `(DT_I2)` no convertible (FailComponent) | `validator.validar_casts` | Hace fallar el proceso. |
| Derived Column `FechaAnsi` | `transformer.fecha_ansi` | `[AÑO]+MES+DIA`, calculado sobre `MES`/`DIA` ya rellenados. Si alguna parte es NULL, el resultado es NULL. |
| Data Conversion (`DT_STR(50)`, 1252, FailComponent) | `validator.validar_conversion` | Un valor de más de 50 caracteres hace fallar el proceso. No se trunca. |
| Lookup `Búsqueda` | `transformacion/lookup.py` | <ul><li>Full Cache, con el `SqlCommand` literal (ventana de 1 mes según el reloj del SQL Server).</li><li>Claves: `FECHA ANSI`, `HORA`, `ID CONEXION`.</li><li>Comparación exacta: distingue mayúsculas y espacios.</li><li>`NULL` coincide con `NULL`.</li><li>Solo la salida *no coincidentes* va al destino.</li><li>La caché no se actualiza con lo que se inserta.</li></ul> |
| OLE DB Destination (fast load) | `LogueoLoader.insertar` → `DatabaseGateway.insertar_todo_o_nada` | <ul><li>Destino: `[dbo].[TBL_CONEXIONES]`, con `TABLOCK`.</li><li>Un solo commit, igual que `FastLoadMaxInsertCommitSize=2147483647`.</li><li>`[DNI]` no se mapea y entra como NULL.</li></ul> |

## 3. Variable `User::Periodo`

- **Regla:** se copia la expresión del .dtsx (`periodo.calcular_periodo`): si el día es ≤ 4 se toma el mes anterior; si no, el mes actual. Usa el reloj de la máquina que ejecuta.
- **Prioridad:** `--periodo` en la línea de comandos, luego `PERIODO` en el `.env` y, si ninguno está definido, la regla anterior. El valor se valida (formato `YYYYMM`, mes de 01 a 12).
- **Uso:** solo lo usa `AGREGA DNI`.

## 4. Cambio de origen

El paquete leía `D:\…\15 PORTAL COMERCIAL\REPORTE_AGENTES_FRACTALIA_SEM.csv` (variable `User::Ruta_General_Whatsapp`). Ahora el archivo se descarga por **Microsoft Graph** desde:

- sitio: `ReportingFractalia`
- biblioteca: `Data Reporting`
- carpeta: `REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/15 PORTAL COMERCIAL`

`--archivo-local` se mantiene solo para contingencias.

## 5. Diferencias deliberadas

| Diferencia | Motivo |
|---|---|
| Se valida que la **cabecera** coincida con la del .dtsx. | SSIS mapea por posición: si `203_bot_portal_comercial` cambiara el orden de las columnas, SSIS cargaría datos corridos sin avisar. |
| Una fila con **menos de 45 columnas** hace fallar el proceso. | Indica un archivo corrupto. |
| Se valida el **esquema de `TBL_CONEXIONES`** antes de cargar. | Falla con un mensaje claro en vez de un error de inserción. Ampliar una columna se acepta. |
| Los 5 bytes que **CP1252 no define** se conservan con el mismo código. | SSIS los pasa tal cual a `varchar`; el codec de Python fallaría. |
| La validación del archivo ocurre **antes del INSERT** y la inserción es de todo o nada. | Mismo resultado final que SSIS: si algo falla, no queda ninguna fila. |

## 6. Cómo se demuestra la equivalencia

1. **Estructural** (`tests/equivalencia/test_equivalencia_dtsx.py`). Lee el .dtsx original y compara contra el código:
   - T-SQL byte a byte y parámetros;
   - tareas, BK deshabilitada y precedencias;
   - expresión de `Periodo`;
   - columnas, tipos y anchos del Flat File;
   - expresiones de las Derived Columns;
   - Data Conversion;
   - Lookup y mapeo del destino;
   - ausencia de credenciales en el código.
2. **Unitaria** (`tests/unit/`). Cubre cada expresión con sus casos límite, la regla de periodo, el Lookup y el orden y la semántica de fallo del pipeline (con fakes).
3. **De datos** (`tools/equivalencia.py`, solo lectura):
   - Procesa el CSV de SharePoint y compara columna a columna con las filas que SSIS cargó para las mismas fechas.
   - Además **simula la inserción** en una tabla temporal `#SIM` con el mismo INSERT y relee lo que guardó SQL Server.
   - Resultado del 2026-10-01: **25.763 de 25.763 filas idénticas** en ambos casos. El Lookup encontró 0 filas nuevas porque el archivo ya lo había cargado SSIS. Ver `evidencias/reporte_ssis_vs_python.md`.
4. **Ejecución real** del 2026-10-01 a las 11:16:
   - Se ejecutaron los 5 pasos y `LOGS_PROCESOS` quedó en `'OK'` (`Chile_Logueo` y `CL_LOGUEO`).
   - `TBL_CONEXIONES` quedó idéntica (mismo conteo, mismos DNI y mismo checksum): 0 inserciones y `AGREGA DNI` reasignó los mismos 84.434 DNI.

### Observación sobre `SP_LOGUEO` (no depende de la migración)

`TBL_LOGUEO_CHILE` y `TBL_LOGUEO_CHILE_TRAMOS` conservaron sus conteos (222.413 y 3.185.973), pero su checksum cambió entre la ejecución de SSIS (10:45) y la de Python (11:16), aunque la entrada fue idéntica.

- **Causa:** el SP deduplica con `ROW_NUMBER() OVER (PARTITION BY AÑO,MES,DIA,HORA,[ID CONEXION],[DNI] ORDER BY dia)`. `dia` es constante dentro de la partición y `TBL_CONEXIONES` es un heap.
- **Efecto:** en 36 particiones históricas (de 20240131 a 20260107) los duplicados tienen métricas distintas, y la fila elegida cambia de una ejecución a otra, también entre dos ejecuciones de SSIS.
- **Solución posible:** corregirlo en el SP (agregar un desempate determinista al `ORDER BY`). Queda fuera del alcance de esta migración.
