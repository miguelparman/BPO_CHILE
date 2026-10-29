# Equivalencia SSIS ↔ Python — `CL_Proc_Carga_Places.dtsx`

## Matriz de componentes

| SSIS | Python | Notas |
|---|---|---|
| Connection Manager `162.CL_DATA` (OLE DB, 172.17.0.162, usuario `mparedes`) | `config.DbSettings` + `db.py` (pyodbc) | Password DPAPI no reutilizable → `DB_*` en `.env` |
| Connection Manager `Places` (Excel, ruta física) | `sharepoint/` (Microsoft Graph) | Ruta: `REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/05 CARTERA/Place utilizados.xlsx` en ReportingFractalia |
| Variable `User::Fecha_Actual` (`yyyy-mm-dd` de `GETDATE()`) | `HistoricoLoader(hoy=date.today)` | Se enlaza como `DT_DATE` → `datetime.date` |
| `Log Inicio` | `logs_proceso.LogsProceso.inicio` | T-SQL literal |
| `TRUNCA TABLA` | `carga/loader.py` (`SQL_TRUNCATE`) | T-SQL literal |
| `CARGA TABLA` — Origen de Excel (`Hoja1$`, HDR=YES, 7 × `DT_WSTR(255)`) | `extraccion/extractor.py` | Celdas no texto → NULL (como ACE sin IMEX) |
| `CARGA TABLA` — Conversión de datos (6 × `DT_STR(n)` cp1252, `FailComponent`) | `validacion/validator.py` + `transformacion/transformer.py` | id 8, Etiqueta 30, plataforma 30, RUT 50, Asesor 100, DNI 15. `Correo Electronico` no se convierte ni se carga |
| `CARGA TABLA` — Destino OLE DB `[dbo].[TBL_PLACES]` (fast load) | `carga/loader.py` (`executemany` + `fast_executemany`) | `Fecha Ingeso Empresa` / `Fecha Baja Empresa` sin mapear → NULL hasta `LIMPIA TABLA` |
| `LIMPIA TABLA` | `carga/loader.py` (`SQL_LIMPIA`) | T-SQL literal |
| `ELIMINA FECHA ACTUAL TABLA` + `CARGA TABLA` (histórico) | `carga/historico.py` | T-SQL literal, parámetro `Fecha_Actual` |
| `Log Fin` | `logs_proceso.LogsProceso.fin` | Solo si todo lo anterior terminó bien |
| Precedence Constraints (Success) | `pipeline.py` | Una etapa que falla detiene las siguientes |

## Tipos de datos

Excel Source: todas las columnas `DT_WSTR(255)`. Conversión: `DT_STR` code page 1252 con `FailComponent` en error y truncamiento → el validador detiene el proceso antes de tocar la tabla si un valor excede el ancho o tiene caracteres fuera de cp1252. Destino: columnas `str` (ID 8, Etiqueta 30, Plataforma 30, Rut 50, Asesor 100, DNI 15, fechas 8). Histórico: `Fecha Impacto` recibe `Fecha_Actual` (`DT_DATE`).

## Diferencias deliberadas

1. **Transacciones.** SSIS ejecuta cada tarea por separado; si el Data Flow falla, `TBL_PLACES` queda vacía. Aquí `TRUNCATE + INSERT + LIMPIA TABLA` van en una transacción (rollback completo si algo falla) y `DELETE + INSERT` del histórico en otra. Ante una corrida exitosa el resultado es idéntico.
2. **Validación previa.** Antes de cualquier escritura se revisan los puntos `FailComponent` (SSIS falla a mitad de la carga, con la tabla ya truncada).
3. **Conexiones.** Si SQL Server o Graph no responden tras 3 reintentos cada 5 min, no se ejecuta nada (SSIS fallaría a mitad del flujo).
4. **Fuente del Excel.** Ruta física → Microsoft Graph.

## Comportamientos del original que se mantienen tal cual

- DNI sin coincidencia en `TBL_PERSONAL_CONSOLIDADO` queda NULL.
- `CAST(DNI AS INT)` falla si algún DNI no es numérico.
- Sin fecha de baja, `Fecha Baja Empresa` = fecha de hoy.
- Si el proceso falla no hay `Log Fin`: la fila de `LOGS_PROCESOS` queda en `exec...`.

## Evidencia (2026-10-29)

- `tests/`: 54 pruebas (unitarias y equivalencia estructural con el .dtsx) en verde.
- `python -m tools.equivalencia simular` vs foto SSIS: `TBL_PLACES` 203 filas idénticas en ID, Etiqueta, Plataforma, Rut y Asesor.
- Carga real y foto posterior: `TBL_PLACES` (203 filas, 8 columnas) y `TBL_HISTORICO_PLACES` (286 282 filas, 9 columnas) idénticas fila a fila a las de SSIS (`evidencias/reporte_ssis_vs_python.md`).
