# Parque — Migración SSIS → Python

Migración a Python (arquitectura modular por componentes) del paquete SSIS
`SSIS_Chile_parque.dtsx`: carga periódica del parque de activos fijo y móvil
(Chile) hacia SQL Server (`CL_PLANTA`), tanto la tabla vigente (`_ACTUAL`)
como el histórico (`_HISTORICO`). El origen cambió: en vez de leer
`Externos_Frac.dbo.pqe_fijtot2023` / `pqe_movtot2023` directamente desde SQL
Server, ahora se lee el mismo archivo publicado como CSV en SharePoint, vía
Microsoft Graph.

La migración se hizo en 2 fases dentro de este mismo proyecto:

- **Fase 1** (`TBL_PARQUE_FIJO_ACTUAL` / `TBL_PARQUE_MOVIL_ACTUAL`): validada
  en ambiente real contra SharePoint y `CL_PLANTA` — ver "Notas de fidelidad".
- **Fase 2** (`TBL_PARQUE_FIJO_HISTORICO` / `TBL_PARQUE_MOVIL_HISTORICO`):
  implementada a continuación de la Fase 1, con un diseño distinto al
  `.dtsx` original — ver sección "Fase 2" más abajo.

## Arquitectura

**"src layout"**: en la raíz del proyecto solo quedan `README.md`,
`.gitignore`, `.env.example`, `requirements*.txt`, `pyproject.toml` y
`main.py`. El código vive en `src/parque/`, modular por componentes,
dividido en 4 capas que replican 1:1 las etapas del proceso original
(extracción, validación, transformación, carga), cada una en su propia
carpeta — sin capas domain/application/infrastructure ni interfaces
`Protocol` de por medio (mismo patrón plano que `08_cartera`/`04_usuarios_y_retenciones`/
`02_ventas`, solo que aquí además separado de la raíz del repo):

```
30_parque/
├── README.md, .gitignore, .env.example, requirements*.txt, pyproject.toml
├── main.py                     CLI + composition root
├── tests/unit/                  fakes + tests por capa
└── src/parque/                   todo el codigo de la aplicacion
    ├── sharepoint/
    │   ├── auth.py              get_graph_token(): OAuth2 client-credentials contra Microsoft Graph
    │   ├── client.py             SharePointClient: resolve_site/resolve_drive + download_file
    │   └── reader.py              SharePointCsvReader.leer_csv(): descarga y parsea el CSV a DataFrame
    │
    ├── extraccion/extractor.py     extraer(): descarga el CSV del flujo (Origen OLE DB 'PQE_FIJO'/'PQE_MO')
    ├── validacion/validator.py     columnas esperadas, filtro 'WHERE periodo = ?', largos máximos (FailComponent)
    ├── transformacion/transformer.py reordena columnas al orden del Destino OLE DB
    ├── carga/loader.py              Fase 1: TRUNCATE + inserción masiva (_ACTUAL)
    │                                Fase 2: DELETE por periodo + INSERT...SELECT desde _ACTUAL (_HISTORICO)
    │
    ├── pipeline.py                  ParquePipeline: orquesta las 2 ramas (FIJO, MOVIL),
    │                                cada una independiente; dentro de cada rama,
    │                                _HISTORICO depende de que _ACTUAL cargue sin error
    ├── models.py                    Value objects: ColumnaSpec, ParqueFlowSpec, ResultadoFlujo,
    │                                ResultadoHistorico, ResultadoRama, ResultadoPipeline
    ├── exceptions.py                Excepciones del proceso (ExtraccionError, ValidacionError, ...)
    ├── mappings.py                  Columnas/anchos/tablas de cada rama, incl. tabla/SQL de HISTORICO
    ├── sql.py                       SQL literal migrado (TRUNCATE, DELETE de HISTORICO)
    ├── db.py                        DatabaseGateway (pyodbc) + fábrica de conexiones (Connection Manager 'CL_PLANTA')
    ├── config.py                    Carga de '.env' -> Settings (sin credenciales embebidas)
    └── logging_setup.py             Logging (archivo + consola)
```

`main.py` agrega `src/parque/` al `sys.path` al arrancar
(`sys.path.insert(0, str(BASE_DIR / "src" / "parque"))`), así que dentro de
`src/parque/` los módulos se importan igual que si estuvieran en la raíz
(`import mappings`, `from db import DatabaseGateway`, etc. — sin cambios
respecto al layout plano). Los tests usan la misma configuración vía
`pyproject.toml` (`[tool.pytest.ini_options] pythonpath = ["src/parque"]`).

`extractor.py`, `validator.py`, `transformer.py` y `loader.py` reciben un
`DatabaseGateway`/`SharePointCsvReader` (o duck-types equivalentes, como los
*fakes* de `tests/unit/fakes.py`) como parámetro, parametrizados siempre por
un `ParqueFlowSpec` (`mappings.FIJO_SPEC` / `mappings.MOVIL_SPEC`) — así el
mismo código se reutiliza para ambas ramas en vez de duplicarlo.
`pipeline.py` es el único módulo que conoce las 4 capas a la vez; `main.py`
es el único que además conoce `db.py` y `sharepoint/`.

## Proceso original (Control Flow de `SSIS_Chile_parque.dtsx`)

```
SERVIDOR (Sequence)
├─ PQ FIJO I    TRUNCATE -> Data Flow (Origen 'PQE_FIJO' -> Destino TBL_PARQUE_FIJO_ACTUAL)
├─ PQ MOVIL I   TRUNCATE -> Data Flow (Origen 'PQE_MO'    -> Destino TBL_PARQUE_MOVIL_ACTUAL)
├─ PQ FIJO II   (depende de PQ FIJO I)  DELETE WHERE PERIODO=? -> Data Flow -> TBL_PARQUE_FIJO_HISTORICO
└─ PQ MOVIL II  (depende de PQ MOVIL I) DELETE WHERE PERIODO=? -> Data Flow -> TBL_PARQUE_MOVIL_HISTORICO
```

`PQ FIJO I`/`PQ MOVIL I` no tienen precedence constraint entre sí: corren en
paralelo (`ThreadHint` 0/1) y son totalmente independientes (sin join/lookup
cruzado). `PQ FIJO II`/`PQ MOVIL II` sí dependen de que la `I`
correspondiente termine en éxito — esa dependencia se preserva en
`pipeline.ParquePipeline._ejecutar_rama` (ver más abajo).

- **Conexiones OLE DB**: `srv_chile` → `Externos_Frac` (origen, **reemplazado
  por SharePoint/Graph**, solo para _ACTUAL), `CL_PLANTA` (destino, se
  mantiene vía `pyodbc`).
- **Variable de paquete**: `Periodo` (string, ej. `202607`), usada como
  `WHERE periodo = ?` / `WHERE PERIODO = ?` en ambas sub-ramas.
- Ningún Data Flow tiene transformaciones de negocio (sin Derived Column,
  Data Conversion, Lookup, Conditional Split, Merge, Aggregate, Sort): es
  extract/load puro, toda la lógica vive en el filtro por periodo y en los
  anchos de columna.

## Tabla de equivalencia SSIS → Python

| Tarea / componente SSIS original | Función Python |
|---|---|
| Connection Manager `srv_chile` (Externos_Frac) | `sharepoint/auth.py` + `sharepoint/client.py` + `sharepoint/reader.py` |
| Connection Manager `CL_PLANTA` | `db.crear_conexion` + `db.DatabaseGateway` |
| Variable `Periodo` | `Settings.periodo` (`config.py`, `.env` `VAR_PERIODO` o `--periodo`) |
| `PQ FIJO I` / `TRUNCATE` | `carga/loader.truncar_tabla` con `mappings.FIJO_SPEC` |
| `PQ MOVIL I` / `TRUNCATE` | `carga/loader.truncar_tabla` con `mappings.MOVIL_SPEC` |
| Origen OLE DB `PQE_FIJO` / `PQE_MO` (`SELECT ... WHERE periodo = ?`) | `extraccion/extractor.extraer` (descarga completa) + `validacion/validator.filtrar_periodo` (filtro, ahora en pandas) |
| Disposición `FailComponent` (error/truncamiento) en todas las columnas | `validacion/validator.validar_longitudes` (lanza `ValidacionError`) |
| Destino OLE DB `TBL_PARQUE_FIJO_ACTUAL` / `TBL_PARQUE_MOVIL_ACTUAL` (fast-load) | `transformacion/transformer.reordenar_columnas` + `carga/loader.cargar_actual` (`db.bulk_insert`, `fast_executemany`, lotes de `BATCH_SIZE`) |
| `PQ FIJO II` / `PQ MOVIL II` — `DELETE ... WHERE PERIODO = ?` | `carga/loader.borrar_historico_periodo` (`mappings.FIJO_SPEC.sql_delete_historico` / `MOVIL_SPEC...`, literal migrado de `sql.py`) |
| `PQ FIJO II` / `PQ MOVIL II` — Data Flow (releía `Externos_Frac`) | `carga/loader.insertar_historico_desde_actual` — **rediseñado**: `INSERT ... SELECT` desde `TBL_PARQUE_*_ACTUAL` (ya cargada por la Fase 1), no desde SharePoint de nuevo |

## Requisitos

- Python 3.11+
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Acceso de red al servidor SQL Server (`CL_PLANTA`)
- Un **App Registration en Microsoft Entra ID** con permiso de aplicación
  **`Sites.Selected`**, concedido únicamente sobre el sitio
  `ReportingFractalia` (mismo modelo ya usado en `201_bot_salesforce`) — sin
  esto, `sharepoint/auth.py` no puede obtener un token válido para leer los
  CSV.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
```

Edite `.env` con las credenciales reales (ver `.env.example`).

## Ejecución

```bash
python main.py --periodo 202607
python main.py                    # usa VAR_PERIODO de .env
```

Cada corrida procesa, por cada rama (FIJO, MOVIL): TRUNCATE + carga de
`_ACTUAL` y, si eso tiene éxito, DELETE + carga de `_HISTORICO` a partir de
la `_ACTUAL` recién cargada.

## Tests

```bash
pytest
```

Los tests usan *fakes* de `DatabaseGateway`/`SharePointCsvReader`
(`tests/unit/fakes.py`), por lo que no requieren base de datos ni conexión a
SharePoint/Graph reales. Cubren:

- `test_extractor.py`: la extracción descarga el CSV declarado en el spec,
  sin filtrar ni validar.
- `test_validator.py`: columnas faltantes, filtro por periodo, largos
  máximos por columna (incluida la diferencia `rutcli` 50 vs 10 entre FIJO y
  MOVIL), y el orden columnas → filtro → largos.
- `test_transformer.py`: reordenamiento de columnas al orden del destino.
- `test_loader.py`: `truncar_tabla`/`cargar_actual` usan la tabla del spec;
  `borrar_historico_periodo` ejecuta el `DELETE` literal del spec con el
  periodo como parámetro; `insertar_historico_desde_actual` arma el
  `INSERT ... SELECT` correcto (tabla histórico, tabla actual, columnas,
  filtro por periodo).
- `test_pipeline.py`:
  - TRUNCATE antes que la carga de `_ACTUAL`, filtro de periodo correcto.
  - `_HISTORICO` se ejecuta **después** de `_ACTUAL` y lee desde ella.
  - Si `_ACTUAL` falla, `_HISTORICO` de esa misma rama **no se intenta**
    (dependencia "On Success" preservada del `.dtsx` original).
  - **Que un fallo en la rama FIJO (completa) no impide que MOVIL se
    ejecute completo (_ACTUAL + _HISTORICO)**, igual que en SSIS donde
    ambas ramas corren en paralelo sin precedence constraint entre ellas.

## Notas de fidelidad con el paquete SSIS original

- **Credenciales**: la password del Connection Manager `CL_PLANTA` y el
  App Registration de Graph (que reemplaza a `srv_chile`) se declaran en
  `.env` (no versionado), nunca embebidas en el código.
- **Cambio de origen (solo _ACTUAL)**: `srv_chile`/`Externos_Frac` se
  reemplaza por SharePoint/Graph. El filtro `WHERE periodo = ?`, que en SSIS
  resolvía SQL Server antes de que el Data Flow viera una sola fila, ahora
  se aplica en `validacion.validator.filtrar_periodo` sobre el CSV completo
  descargado — se confirmó con el usuario que el CSV puede traer varios
  periodos mezclados, a diferencia de la tabla SQL original.
- **Orden truncate-primero preservado**: en el `.dtsx` original, `TRUNCATE`
  es una tarea separada e incondicional que corre *antes* del Data Flow
  (precedence "On Success"). Si el Data Flow fallaba después, la tabla
  quedaba **vacía** (el truncate ya se había confirmado en su propia
  transacción). `pipeline.ParquePipeline._ejecutar_actual` reproduce
  exactamente ese orden (truncar → extraer → validar/filtrar → cargar); no
  es un defecto introducido en la migración.
- **`errorRowDisposition`/`truncationRowDisposition` = `FailComponent` en
  TODAS las columnas**: ninguna columna tiene disposición tolerante (a
  diferencia de, por ejemplo, `NOMCLI` en `08_cartera`). Cualquier valor que
  exceda el largo declarado aborta el flujo completo
  (`validacion.validator.validar_longitudes` lanza `ValidacionError`), nunca
  se trunca en silencio.
- **`rutcli` con largos distintos por tabla**: 50 caracteres en FIJO, 10 en
  MOVIL — se preserva la diferencia tal cual venía del `.dtsx` original (ver
  `mappings.py`).
- **Ejecución de FIJO y MOVIL**: el `.dtsx` original las corre en paralelo
  (`ThreadHint` 0/1), sin precedence constraint entre ellas — son
  independientes. Aquí se ejecutan en secuencia (no hay necesidad de
  paralelismo real para 2 archivos), pero **cada rama se intenta por
  completo de forma aislada**: un fallo en FIJO no impide que MOVIL corra y
  cargue (ver `pipeline.py` y `test_pipeline.py`). Si en el futuro el
  volumen de datos lo justifica, ambas ramas podrían correr en hilos/
  procesos separados sin cambiar esta lógica.
- **`PQ FIJO II`/`PQ MOVIL II` sí dependen de `PQ FIJO I`/`PQ MOVIL I`**: a
  diferencia de la independencia entre FIJO y MOVIL, dentro de una misma
  rama `_HISTORICO` solo se ejecuta si `_ACTUAL` cargó sin error
  (`pipeline._ejecutar_rama`: si `_ejecutar_actual` lanza, `_ejecutar_historico`
  no se llega a invocar) — igual que la precedence "On Success" del `.dtsx`
  original entre `PQ FIJO I` → `PQ FIJO II`.
- **Sin manejadores de error, Script Tasks ni logging propio** en el paquete
  original — no hay nada de eso que migrar; el logging de este proyecto
  (`logging_setup.py`) es una adición nueva, no una migración de un
  componente SSIS.
- **Formato del CSV — confirmado contra el archivo real**: delimitador
  `;` (no `,` como se había asumido inicialmente; el `.dtsx` original no
  declara delimitador porque el origen era SQL Server, no un archivo plano).
  Los encabezados sí coincidían exactamente con los nombres de columna
  esperados a partir del análisis del `.dtsx` (`mappings.CSV_DELIMITER`).

## Fase 2 — HISTORICO: diseño distinto al `.dtsx` original

El `.dtsx` original vuelve a consultar `Externos_Frac` una segunda vez por
cada tabla (`PQ FIJO II`/`PQ MOVIL II`, misma query que `PQ FIJO I`/`PQ MOVIL
I`). El usuario pidió explícitamente que, en esta migración, `_HISTORICO` se
alimente en cambio desde las tablas `_ACTUAL` **ya cargadas por la Fase 1**
en la misma corrida — evita leer SharePoint/Graph dos veces y usa el mismo
dato que ya se validó:

```sql
DELETE [dbo].[TBL_PARQUE_*_HISTORICO] WHERE PERIODO = ?        -- carga/loader.borrar_historico_periodo
INSERT INTO [dbo].[TBL_PARQUE_*_HISTORICO] (...)
SELECT ... FROM [dbo].[TBL_PARQUE_*_ACTUAL] WHERE periodo = ?  -- carga/loader.insertar_historico_desde_actual
```

El `DELETE` es el texto literal migrado del `.dtsx` (`sql.DELETE_FIJO_
HISTORICO` / `sql.DELETE_MOVIL_HISTORICO`, ejecutado vía `mappings.*_SPEC.
sql_delete_historico`). El `INSERT ... SELECT` se arma en Python a partir de
`ParqueFlowSpec.nombres_columnas` (mismas columnas que `_ACTUAL`, ya que
ambas tablas provienen del mismo origen histórico) en vez de ser un texto
fijo, para que la misma función sirva a FIJO y a MOVIL sin duplicar código.

**Nota**: como `_ACTUAL` se trunca y recarga con el filtro de periodo en
cada corrida (Fase 1), el `WHERE periodo = ?` del `SELECT` sobre `_ACTUAL`
es, en la práctica, redundante si `_ACTUAL` solo contiene ese periodo — se
mantiene explícito de todas formas por si en el futuro `_ACTUAL` llegara a
acumular más de un periodo, y para que la equivalencia con el `.dtsx`
original (que también filtraba explícitamente) sea exacta.
