# ETL Contactos + ISN — migración desde SSIS

Migración de dos paquetes SSIS que corren de forma **progresiva** (uno detrás del otro):

1. `SSIS_CL_ISN_Contactos.dtsx` — carga el reporte de contactos autorizados de Salesforce.
2. `SSIS_CL_ISN.dtsx` — pipeline de encuestas ISN, que depende de tablas que puebla el paquete anterior.

`pipeline.py` (raíz) corre ambos en ese orden. `main.py` es el punto de entrada.

## Arquitectura

Enfoque híbrido, igual que en otras migraciones de este repo (ver `10_campaña_termometro/`):

- **Python** reemplaza los orígenes/destinos reales de Data Flow: leer CSV, escribir CSV, cargar DataFrames a SQL Server, castear los pocos tipos que SSIS convertía de verdad.
- **SQL parametrizado** (carpetas `sql/`) reemplaza los Execute SQL Task, **verbatim** (se verificó cada uno contra el XML del `.dtsx` original, carácter por carácter en los más largos). `SSIS_CL_ISN.dtsx` en particular es casi enteramente lógica de conjunto pesada (CTEs, `ROW_NUMBER() OVER (PARTITION BY...)`, más de 10 `LEFT JOIN` contra 7 bases de datos distintas) — **no se reescribió en pandas**, para no arriesgar introducir una diferencia sutil en una consulta de cientos de líneas. Python solo orquesta el orden y pasa los pocos parámetros que variaban (`Fecha_inicio`/`Fecha_fin`).

```
05 isn/
├── config.py              # variables de entorno (reemplaza Connection Managers + variables SSIS)
├── db.py                  # engines SQLAlchemy (CL_ANALISIS, CL_ISN, CL_CALIDAD) + ejecución de scripts con "GO"
├── pipeline.py             # orquestador raíz: contactos -> isn (en ese orden)
├── main.py                 # punto de entrada / CLI
│
├── contactos/               # SSIS_CL_ISN_Contactos.dtsx
│   ├── pipeline.py
│   ├── columns.py            # mapeo de columnas origen -> destino
│   ├── extractor.py           # lee el CSV + extrae los números distintos (Data Flow "Números (Local)")
│   ├── validator.py            # valida columnas/tipos antes de transformar (ver más abajo)
│   ├── transformer.py           # tipos/anchos (Data Convert) + rename a columnas destino
│   ├── loader.py                 # truncate + load + limpieza de teléfonos + carga de números
│   └── sql/                       # 4 .sql, uno por Execute SQL Task / query de Data Flow
│
├── isn/                      # SSIS_CL_ISN.dtsx
│   ├── pipeline.py             # reproduce el árbol de PrecedenceConstraint (ver diagrama abajo)
│   ├── columns.py
│   ├── extractors/               # aux_cliente / aux_contacto (CSV) + isn_extractor (lee TBL_ISN_CALIDAD/TBL_ISN)
│   ├── validators/                 # aux_validator + envios_validator
│   ├── transformers/                 # envios_consolidado.py (cast FECHA_EVENTO / "Número del caso" a entero)
│   ├── loaders/                       # csv_writer.py (export isn.csv + archivado con fecha)
│   └── sql/                             # 19 .sql, uno por Execute SQL Task / query de Data Flow
│
├── common/sql_loader.py       # truncate_table / load_dataframe, compartido por ambos paquetes
├── parity/                    # prueba de equivalencia contra el SSIS original (ver más abajo)
├── tests/                     # pytest, sin BD: transformers/validators puros + el split de "GO"
├── infra/                     # Docker + DDL + datos sintéticos -- SOLO para contactos (ver más abajo)
└── scripts/                   # generate_sample_data.py, setup_test_env.sh, check_test_results.py
```

## Cómo correrlo

```bash
pip install -r requirements.txt
cp .env.example .env   # completar credenciales/rutas reales
python main.py                                        # corre contactos, luego isn
python main.py --fecha-inicio 2026-09-06 --fecha-fin 2026-09-06   # rango de TBL_ISN_SF
python main.py --saltar isn                            # solo contactos
python main.py --saltar contactos                      # solo isn
```

Requiere el driver ODBC de SQL Server instalado (`ODBC Driver 18 for SQL Server` o el que corresponda).

## `SSIS_CL_ISN_Contactos.dtsx` — qué hace y cómo se migró

```
TRUNCATE TBL_CONTACTOS_AUTORIZADOS_CHILE
  -> Data Flow: CSV Salesforce -> Data Convert -> OLE DB Destination (carga TBL_CONTACTOS_AUTORIZADOS_CHILE)
  -> UPDATE "_0" (limpia sufijo ".0" de MÓVIL/TELÉFONO)
  -> Contenedor de secuencias:
       TRUNCATE TBL_CONTACTOS_AUTORIZADOS_CHILE_NUMEROS
       -> Data Flow "Números (Local)": OLE DB Source (UNION distinto de TELÉFONO/MÓVIL) -> OLE DB Destination
```

### Hallazgos confirmados contra el archivo real (`Reporte_Contactos_Salesforce_BI.csv`, 402 005 filas)

- **cp1252 estricto falla**: hay al menos un byte fuera de rango (`0x8d`) en algún campo de texto libre. Se cambió el default de `CSV_CONTACTOS_ENCODING` a `latin-1` (mapea 1:1 los 256 valores de byte), mismo hallazgo ya documentado en `10_campaña_termometro/`.
- **La cabecera real no coincide con la que declara el `.dtsx`**: el Connection Manager declara `"No  identificación fiscal"` e `"Id  de contacto"` (con dos espacios), pero el archivo real trae `"No. identificación fiscal"` e `"Id. de contacto"` (con punto). SSIS no usa el texto de la cabecera para mapear columnas cuando `ColumnNamesInFirstDataRow=True` (solo la salta); el mapeo real es **posicional**. Por eso `contactos/extractor.py` ignora la cabecera del archivo y renombra por posición contra `contactos/columns.py::COLUMNAS_ORIGEN`. Se verificaron las 19 columnas, en orden, contra el archivo real.
- **`ÚLTIMA  MODIFICACIÓN POR` tiene DOS espacios** en la tabla destino real (confirmado contra el `externalMetadataColumn` del OLE DB Destination del `.dtsx`) — fácil de tipear mal a mano, quedó documentado en `contactos/columns.py`.
- **`Acceso a Portal Platino` / `Representante legal`**: el Data Convert original las pasa por `r4` (float) pero la columna destino real es `i4` (entero). Se castea directo a entero anulable; se aceptan tanto `"1"/"0"` (lo único visto en el archivo real) como `"True"/"False"` por robustez.
- **Fechas**: formato confirmado `DD-MM-AAAA` (ej. `04-12-2017`).
- Se preservó la tarea `UPDATE "_0"` como paso posterior a la carga (no se intentó limpiar el sufijo `.0` en pandas antes de insertar), igual que el `.dtsx` original — así, si algún archivo futuro sí trae ese sufijo, el comportamiento es idéntico al de SSIS.
- **Un `TELÉFONO` real de 21 caracteres reventó la primera carga en producción** (`"Nelson: 56 9 53068855"`, columna destino de 20). El Data Convert original de `Cargo`/`Teléfono`/`Móvil`/`Última modificación por` tiene `errorRowDisposition`/`truncationRowDisposition="IgnoreFailure"` (verificado en el `.dtsx`, a diferencia de todas las demás columnas de texto que son `FailComponent`) — SSIS trunca esos 4 campos en silencio y sigue. Se replicó exactamente ese comportamiento: `contactos/columns.py::COLUMNAS_TRUNCAR_SILENCIOSO` + `ANCHOS_MAXIMOS_TEXTO` truncan esas 4 columnas en `transformer.py`, y `validator.py` rechaza el archivo completo si cualquier otra columna (`FailComponent`) excede su ancho real, en vez de dejar que reviente más adelante en el `INSERT`.
- **Rendimiento del `INSERT` masivo**: se probaron tres enfoques contra la tabla real (402 088 filas) antes de llegar al actual. `pandas.to_sql` con `fast_executemany=True` fallaba a mitad de carga con `pyodbc.ProgrammingError: String data, right truncation` (mismo problema de fondo que el TELÉFONO de arriba, solo que reportado por pyodbc en vez de por SQL Server). Con `fast_executemany=False`, `to_sql` arma un único `INSERT` multi-fila ("insertmanyvalues" de SQLAlchemy 2.x) envuelto en una sola transacción: una carga de ~9 minutos terminó revirtiendo las 402 088 filas por un error a mitad de camino, dejando la tabla en 0 filas. La solución final (`common/sql_loader.py::load_dataframe`, pyodbc directo) reproduce el diseño del OLE DB Destination original: `INSERT ... WITH (TABLOCK)`, lotes de `ROWS_PER_BATCH=5000`, un solo commit al final (`FastLoadMaxInsertCommitSize=2147483647` del `.dtsx`) y `cursor.fast_executemany=True` — ahora sí seguro, porque las columnas que podían exceder su ancho ya se truncan/validan antes de llegar acá. Resultado confirmado en producción: **402 088 filas cargadas en menos de 1 minuto** (el proceso SSIS original tarda ~5 minutos).

## `SSIS_CL_ISN.dtsx` — árbol de ejecución y qué hace cada rama

Todas las `PrecedenceConstraint` del paquete original son "on Success" (`LogicalAnd=True`), sin expresiones ni ramas de falla — no hay branching condicional que replicar.

```
Contenedor de secuencias (4 ramas EN PARALELO -- el contenedor espera a las 4):
  ├─ DELETE ENVIOS_CONSOLIDADO (LOCAL)                    [SQL, conn CL_ISN]
  ├─ TBLS AUXILIARES                                      [SQL, 8 batches GO, conn CL_ISN]
  ├─ TRUNCATE TBL_ISN_SF_AUX_CONTACTO -> Data Flow (Reporte_isn_aux_contacto.csv -> TBL_ISN_SF_AUX_CONTACTO)
  └─ TRUNCATE TBL_ISN_SF_AUX_CLIENTE  -> Data Flow (Reporte_isn_aux_cliente.csv  -> TBL_ISN_SF_AUX_CLIENTE)
        │ (on success)
        ▼
SECUENCIA NUEVA (secuencial):
  SF: DROP -> TBL_ISN_SF                    (SELECT INTO parametrizado con :fecha_inicio/:fecha_fin)
    -> Contenedor de secuencias: DELETE -> INSERT   (puebla TBL_ISN_SF_CONSOLIDADO)
    -> TBL_ISN_PRE: DROP -> TBL_ISN_PRE      (SELECT INTO con CTE + ROW_NUMBER)
    -> Contenedor de secuencias 1: DELETE -> INSERT (puebla TBL_ISN_PRE_CONSOLIDADO)
        │ (on success, FAN-OUT EN PARALELO)
        ├─────────────────────────────┬──────────────────────────────┐
        ▼                             ▼
  TBL_ISN:                      TBL_ISN_CALIDAD:
    DROP -> TBL_ISN               DROP -> TBL_ISN_CALIDAD
    (SELECT INTO WHERE Indice=1)  (SELECT INTO WHERE Indice=1)
    -> EXPORT CSV (isn.csv)       -> ACTUALIZACION SERVIDOR:
    -> Cambiar nombre archivo         DELETE (conn CL_CALIDAD)
       (copia a PROSPECTOS_          -> Data Flow (cast FECHA_EVENTO /
        EMPRESA_YYYYMMDD.csv)           "Número del caso" a entero ->
                                         TBL_ISN_ENVIOS_CONSOLIDADO)
                                       -> UPDATE (conn CL_CALIDAD)
```

`isn/pipeline.py` reproduce este árbol exactamente: las ramas paralelas se lanzan con `ThreadPoolExecutor` (igual patrón que `10_campaña_termometro/pipeline.py`) y, si cualquiera falla, el paso siguiente no se ejecuta.

### Conexiones

Tres bases en el mismo servidor (`172.17.0.162`): `CL_ANALISIS` (contactos), `CL_ISN` (casi todo ISN) y `CL_CALIDAD` (solo la sub-rama `ACTUALIZACION SERVIDOR`). Las queries de `TBLS AUXILIARES` y `TBL_ISN_SF` además leen, con nombres de 3 partes, `CL_ANALISIS`, `CL_CARTERA`, `CL_VISTAS`, `BBDD_GENERAL` y `CL_CAMPAÑAS` — como están en el mismo servidor, esos nombres de 3 partes quedan tal cual dentro del SQL, no hace falta una conexión Python aparte para cada una.

Dos Connection Manager del `.dtsx` (`Automatizado` tipo FILE y `CLIENTES DETRACTORES CALIDAD` tipo EXCEL) están definidos pero **ningún task los usa** — no se migraron. Si algún otro proceso depende de que ese Excel se actualice, confirmarlo antes de apagar el paquete SSIS original.

### Hallazgos y decisiones a confirmar

- **Mismo problema de cabecera vs. columna real** que en Contactos: `Reporte_isn_aux_cliente.csv` / `Reporte_isn_aux_contacto.csv` declaran `"Id  del cliente"` / `"Id  de contacto"` (dos espacios) en el `.dtsx`, pero el archivo real trae `"Id. del cliente"` / `"Id. de contacto"` (con punto) — se mapea por posición, igual que en contactos.
- **`TBL_TERMOMETRO_<8`**: nombre de tabla literal (con `<8` como texto) dentro de la tarea `TBLS AUXILIARES`. Es casi seguro un error de tipeo/edición en el `.dtsx` original, pero se preservó tal cual en `isn/sql/tbls_auxiliares.sql` para no cambiar el comportamiento funcional (crea y recrea esa tabla con ese nombre exacto en `CL_ISN`).
- **`DELETE ENVIOS_CONSOLIDADO (LOCAL)`** hace lo mismo que el `DELETE` de `ACTUALIZACION SERVIDOR` (borra `CL_CALIDAD.dbo.TBL_ISN_ENVIOS_CONSOLIDADO` de hoy), pero cruzando de base desde la conexión `CL_ISN` en vez de usar la conexión dedicada `CL_CALIDAD`. Se preservó la duplicación tal cual está en el original (`isn/sql/delete_envios_consolidado_local.sql` e `isn/sql/delete_envios_consolidado_calidad.sql`).
- **`FileSystemTask "Cambiar nombre archivo"`**: no trae un atributo `Operation` explícito en el XML (se verificó) → usa el default de SSIS, `CopyFile`. Se implementó como copia (`shutil.copy2`, no destructiva) en vez de mover/renombrar. Si en producción el comportamiento real esperado era mover el archivo (dejando `Source/isn.csv` vacío para la siguiente corrida), cambiar `ISN_ARCHIVE_OPERATION=move` en `.env` — **confirmar contra SSDT** cuál es el comportamiento real antes de decidir.
- **Contraseñas**: ambos `.dtsx` traen la contraseña de conexión cifrada con la clave de usuario/máquina de quien lo guardó — no se puede (ni se debe) extraer. `DB_PASSWORD` siempre se lee de `.env`, nunca queda embebida en el código.
- **`Fecha_inicio`/`Fecha_fin`**: en el paquete quedaron guardadas como los últimos valores editados a mano antes de una corrida manual. Se exponen como `--fecha-inicio`/`--fecha-fin`; si no se pasan, el default es el día anterior a hoy (`config.py`).

## Prueba de paridad (comparar contra el SSIS original)

```bash
# 1. Corre los dos .dtsx originales para el período a validar (como siempre se ha hecho)

# 2. Saca la foto de cada tabla destino tras esa corrida
python -m parity.snapshot --tabla contactos --etiqueta ssis
python -m parity.snapshot --tabla contactos_numeros --etiqueta ssis
python -m parity.snapshot --tabla isn --etiqueta ssis
python -m parity.snapshot --tabla isn_calidad --etiqueta ssis
python -m parity.snapshot --tabla envios_consolidado --etiqueta ssis --where "[FECHA DE CARGA] = '2026-09-06'"

# 3. Corre este pipeline para el mismo período
python main.py --fecha-inicio 2026-09-06 --fecha-fin 2026-09-06

# 4. Saca la foto de cada tabla tras la corrida Python
python -m parity.snapshot --tabla contactos --etiqueta python
# ... (repetir para las demás tablas)

# 5. Compara cada tabla
python -m parity.compare --tabla contactos --base ssis --nuevo python
# ... (repetir para las demás tablas)
```

`parity/compare.py` empareja filas por la clave configurada en `parity/tablas.py`, reporta filas que solo están en un lado y, columna por columna, cuántas filas tienen un valor distinto; genera además `parity/snapshots/<tabla>_diff_report.md` con ejemplos concretos. Termina con código de salida `0` si todo coincide, `1` si hay diferencias.

Se recomienda correr esta prueba contra 2-3 períodos distintos antes de apagar los paquetes SSIS definitivamente.

## Ambiente de pruebas local (solo Contactos)

`contactos/` tiene un ambiente local con Docker + un CSV sintético con 4 casos de borde:

```bash
./scripts/setup_test_env.sh
cp infra/.env.test .env
python main.py --saltar isn   # .env.test define CONTACTOS_CSV_MUESTRA: lee el CSV sintetico local, sin Graph
python scripts/check_test_results.py
```

**`isn/` no tiene un ambiente local equivalente.** Sus queries (`TBLS AUXILIARES`, `TBL_ISN_SF`) leen de 7 bases de datos de producción distintas (`CL_ISN`, `CL_CALIDAD`, `CL_ANALISIS`, `CL_CARTERA`, `CL_VISTAS`, `BBDD_GENERAL`, `CL_CAMPAÑAS`) con vistas y tablas que no están documentadas acá — replicar ese esquema completo localmente sería un proyecto en sí mismo, desproporcionado frente al resto de esta migración. Su equivalencia se valida con `parity/` contra datos reales o una copia restaurada (ver sección anterior), no con datos sintéticos.

## Notas sobre manejo de errores

- Dentro de cada contenedor con ramas paralelas (el `Contenedor de secuencias` inicial y el fan-out final `TBL_ISN` / `TBL_ISN_CALIDAD`), si cualquier rama falla, el paso siguiente **no se ejecuta** — replica el comportamiento de un contenedor SSIS cuyos hijos alimentan a un mismo sucesor "on Success".
- `pipeline.py` (raíz) corre `contactos` y luego `isn`; si `contactos` falla, `isn` no se ejecuta (`TBL_ISN_SF` depende de vistas que leen `TBL_CONTACTOS_AUTORIZADOS_CHILE`).
- Los logs se escriben a consola y a `logs/isn_<timestamp>.log`.
