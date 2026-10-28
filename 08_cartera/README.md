# Cartera — Migración SSIS → Python

Migración a Python (arquitectura modular por componentes) del paquete SSIS
`CL_Proc_Carga_Cartera.dtsx`: carga mensual/periódica de la cartera de
clientes vigente (Chile) desde un Excel mantenido manualmente hacia SQL
Server, con reclasificación de estado (`NUEVO` / `SE MANTIENE` / `REINGRESO`)
contra el histórico acumulado.

## Arquitectura

**"src layout"**: en la raíz del proyecto solo quedan `README.md`,
`.gitignore`, `.env.example`, `requirements*.txt`, `pyproject.toml` y
`main.py`. El código vive en `src/cartera/`, modular por componentes,
dividido en 4 capas que replican 1:1 las 4 etapas del proceso original
(extracción, validación, transformación, carga), cada una en su propia
carpeta — sin capas domain/application/infrastructure ni interfaces
`Protocol` de por medio:

```
08_cartera/
├── README.md, .gitignore, .env.example, requirements*.txt, pyproject.toml
├── main.py                     CLI + composition root: arma db.py/spreadsheet.py
│                              e inyecta en CarteraPipeline
├── tests/unit/                  fakes + tests por capa
└── src/cartera/                   todo el codigo de la aplicacion
    ├── extraccion/extractor.py     extraer(): Origen Excel + Conversión de datos + Columna derivada
    ├── validacion/validator.py     validar_cartera_temporal(): tarea 'VALIDA' (4 controles de calidad)
    ├── transformacion/transformer.py CARGA DNI, ACTUALIZA STATUS, LIMITA CLIENTES, LIMPIA TEMPORAL
    ├── carga/loader.py              truncados, inserciones y copia entre bases de datos
    │
    ├── pipeline.py                  CarteraPipeline: orquesta las 4 capas anteriores en el
    │                              orden del Control Flow original
    ├── models.py                    Value objects: Periodo, ResultadoPipeline
    ├── exceptions.py                Excepciones del proceso (ExtraccionError, ValidacionError, ...)
    ├── mappings.py                  Columnas/tablas/anchos de truncamiento (constantes de negocio)
    ├── sql.py                       Sentencias T-SQL migradas literalmente de cada Execute SQL Task
    ├── db.py                        DatabaseGateway (pyodbc) + fábrica de conexiones
    │                              (una por Connection Manager OLE DB del .dtsx original)
    ├── spreadsheet.py               SpreadsheetReader: descarga el Excel de SharePoint y lo lee (pandas/openpyxl)
    ├── sharepoint/                  auth.py (token Graph client credentials) + client.py (site/drive/descarga)
    └── config.py, logging_setup.py Carga de '.env' -> Settings + logging (archivo + consola)
```

`extractor.py`, `validator.py`, `transformer.py` y `loader.py` reciben un
`DatabaseGateway`/`SpreadsheetReader` (o duck-types equivalentes, como los
*fakes* de `tests/unit/fakes.py`) como parámetro — no importan `db.py` ni
`spreadsheet.py` para nada más que el type hint, así que se pueden probar sin
base de datos ni Excel reales. `pipeline.py` es el único módulo que conoce
las 4 capas a la vez; `main.py` es el único que además conoce `db.py` y
`spreadsheet.py`. `main.py` agrega `src/cartera/` al `sys.path` al arrancar
(`sys.path.insert(0, str(BASE_DIR / "src" / "cartera"))`), así que dentro de
`src/cartera/` los módulos se importan igual que si estuvieran en la raíz
(sin cambios respecto al layout plano). Los tests usan la misma
configuración vía `pyproject.toml` (`[tool.pytest.ini_options] pythonpath =
["src/cartera"]`).

## Proceso original (Control Flow de `CL_Proc_Carga_Cartera.dtsx`)

3 Sequence Containers encadenados "On Success", sin ramas condicionales:

```
CARGA CARTERA TEMPORAL   TRUNCA TABLA -> Data Flow (Excel -> TBL_CARTERA) -> CARGA DNI -> VALIDA
        |
        v
CARGA CARTERA ACTUAL     TRUNCA TABLA -> Data Flow (TBL_CARTERA -> TBL_CARTERA_ACTUAL)
        |
        v
HISTORICO CARTERA        ACTUALIZA STATUS -> LIMITA CLIENTES -> LIMPIA TEMPORAL -> CARGA
```

- **Excel de origen**: `CARTERA_FRACTALIA.xlsx`, hoja `Hoja1` (mantenido
  manualmente por el equipo comercial). Se descarga de SharePoint vía
  Microsoft Graph: sitio `ReportingFractalia`, biblioteca `Data Reporting`,
  carpeta `REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/05 CARTERA` (antes se leía de
  la ruta local `BPO - Insumos\Chile\CARTERA`).
- **Bases de datos** (mismo servidor SQL Server, 2 Connection Managers OLE DB
  distintos en el `.dtsx` original): `CL_TEMPORALES` (staging, tabla
  `TBL_CARTERA`) y `CL_CARTERA` (`TBL_CARTERA_ACTUAL`, `TBL_HISTORIAL_CARTERA`).
- **Lectura de solo lectura, cross-database**: `CL_DATA.dbo.TBL_PLACES`
  (maestro de asesores/ejecutivos), consultada desde la conexión de
  `CL_TEMPORALES` con nombre de 3 partes — debe estar en el mismo servidor.

## Requisitos

- Python 3.11+
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Acceso de red al servidor SQL Server
- App Registration de Microsoft Graph con `Sites.Selected` sobre el sitio
  `ReportingFractalia` (mismas credenciales que `04_usuarios_y_retenciones`/`30_parque`:
  `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` en `.env`)

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
```

Edite `.env` con las credenciales reales (SQL Server y Microsoft Graph) y,
si aplica, ajuste sitio/carpeta/archivo de SharePoint (ver `.env.example`).

## Ejecución

```bash
python main.py --fecha-inicio 20260827
python main.py                          # usa VAR_FECHA_INICIO de .env
```

## Tests

```bash
pytest
```

Los tests usan *fakes* de `DatabaseGateway`/`SpreadsheetReader`
(`tests/unit/fakes.py`), por lo que no requieren base de datos ni archivo
Excel reales. Cubren:

- `test_extractor.py`: truncamiento de columnas (incl. el caso `SEGME`) y su
  disposición de error (`FailComponent` vs. `IgnoreFailure` en `NOMCLI`),
  columnas descartadas (`RUTCLI`, `RUT10`), columnas de período agregadas.
- `test_validator.py`: los 4 controles de calidad, y que el pipeline se
  detiene en el primero que falla (mismo comportamiento que el `RAISERROR`
  original).
- `test_loader.py`: selección/renombrado de columnas al copiar de staging a
  `TBL_CARTERA_ACTUAL`.
- `test_pipeline.py`: las 3 Sequence Containers se ejecutan en orden y tocan
  las tablas/sentencias esperadas, incluido el orden exacto dentro de
  `HISTORICO CARTERA` (`ACTUALIZA STATUS -> LIMITA CLIENTES -> LIMPIA
  TEMPORAL -> CARGA`, donde `CARGA` corre después de que `LIMPIA TEMPORAL`
  vacía la staging); una validación fallida aborta el pipeline antes de
  `CARGA CARTERA ACTUAL` (equivalente a que SSIS no siga la Precedence
  Constraint "On Success").

## Notas de fidelidad con el paquete SSIS original

- **Credenciales**: los 2 Connection Managers OLE DB (`CL_CARTERA`,
  `CL_TEMPORALES`) tenían password DPAPI-encriptado por usuario/máquina en el
  `.dtsx` — no son recuperables ni se intentó descifrarlas. Se reemplazaron
  por variables de entorno en `.env` (no versionado).
- **`User::Fecha_Inicio` era un valor literal fijo**, no una fórmula: se
  editaba a mano en el paquete original antes de cada corrida. Aquí se
  declara explícitamente en `.env` (`VAR_FECHA_INICIO`) o se pasa con
  `--fecha-inicio`; no se calcula solo.
- **`User::Fecha_Fin`** sí era dinámico (`GETDATE()` como entero `YYYYMMDD`):
  se replica igual en `models.hoy_yyyymmdd()`.
- **Truncamiento de `SEGME` a 30 caracteres**: el componente "Conversión de
  datos" del Data Flow original truncaba `SEGME` a 30 aunque la columna
  destino real admite 255 — se conserva tal cual, aunque parezca un defecto.
- **Disposición de error del truncamiento (`FailComponent` vs. `IgnoreFailure`)**:
  en el `.dtsx` original, el componente "Conversión de datos" tiene
  `errorRowDisposition="FailComponent"` para todas las columnas de
  `mappings.TRUNCATION_LENGTHS` salvo `NOMCLI`, que tiene `IgnoreFailure`. Es
  decir: si `RUT_DV`, `SEGME`, etc. exceden su ancho, SSIS aborta todo el
  Data Flow; solo `NOMCLI` se trunca en silencio. `extraccion/extractor.py::_truncar`
  replica esta asimetría (`mappings.TRUNCATION_TOLERANT_COLUMN`): lanza
  `ExtraccionError` si una columna no tolerante excede su ancho, en vez de
  truncarla sin avisar.
- **Bug preexistente en `CARGA DNI`**: la rama `ELSE` de `RUT_SMTRDV`
  reasigna `X0.[RUT_SMTRIO]` en lugar de `X0.[RUT_SMTRDV]`. Se replica
  exactamente el comportamiento actual (ver comentario en `sql.py`); no se
  corrige salvo que se solicite explícitamente.
- **Validación con corto-circuito**: los 4 controles de la tarea `VALIDA`
  (RUT duplicado, asesor/RUT/nombre no asignado) se evalúan en el mismo
  orden que el `.dtsx` original y el pipeline se detiene en el primero que
  falla, sin evaluar los siguientes — igual que un `RAISERROR` de severidad
  16 abortaba el paquete SSIS.
- **`TBL_HISTORIAL_CARTERA` — esquema no confirmado en el `.dtsx`**: la
  tarea `CARGA` hace un `INSERT` posicional (sin lista de columnas) porque
  esa tabla nunca es destino de un componente Data Flow con metadata
  explícita en el paquete original. **Antes de operar en producción, verificar
  contra el DDL real de SQL Server que el orden de columnas de
  `sql.CARGA_HISTORICO` coincide con el de la tabla.**
- **Bloques de código muerto** (SQL comentado dentro de `ACTUALIZA STATUS
  TEMP CARTERA` y `LIMITA CLIENTES` en el `.dtsx` original) no se migraron:
  nunca se ejecutaban.
- El paquete original **no tiene** Script Tasks, Script Components,
  Conditional Split, Lookup, Merge Join ni Event Handlers — toda su lógica de
  negocio vive en las 8 sentencias T-SQL y los 2 Data Flows simples descritos
  arriba; no hay nada de eso que migrar.
