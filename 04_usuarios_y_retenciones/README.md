# USUARIOS — Migración SSIS → Python

Migración a Python (arquitectura modular por componentes) de 5 paquetes SSIS
de la carpeta `CHILE ETL AZURE`, migrados **en el orden declarado** (uno
completo, con pruebas, antes de empezar el siguiente):

1. `USUARIOS_0101 Parque.dtsx` — parque de clientes (fijo + móvil).
2. `USUARIOS_0201 SSIS_CL_Retenciones.dtsx` — bajas por fraude, bajas por
   alta y base de retenciones (`BD_RETEN`).
3. `USUARIOS_0300 ETL_INTENCIONES.dtsx` — bajas cargadas, usuarios de
   retenciones, e intenciones de baja (con extracción de fecha/usuario desde
   notas de texto libre).
4. `USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx` — items Amdocs con cálculo de
   tiempos de atención hábil/calendario.
5. `USUARIOS_0302 ETL_BASE_SAIP.dtsx` — base SAIP (única sin variable de
   periodo) + efectividad de asesor.

## Arquitectura

**"src layout"**: en la raíz del proyecto solo quedan `README.md`,
`.gitignore`, `.env.example`, `requirements*.txt`, `pyproject.toml` y
`main.py`. El código vive en `src/usuarios/`, modular por componentes,
dividido en 4 capas que replican 1:1 las 4 etapas del proceso original
(extracción, validación, transformación, carga), cada una en su propia
carpeta — sin capas domain/application/infrastructure ni interfaces
`Protocol` de por medio:

```
04_usuarios_y_retenciones/
├── README.md, .gitignore, .env.example, requirements*.txt, pyproject.toml
├── main.py                       CLI + composition root (--periodo, --paquete)
├── tests/unit/                    fakes + tests por capa
└── src/usuarios/                   todo el codigo de la aplicacion
    ├── sharepoint/
    │   ├── auth.py                Token Microsoft Graph (OAuth2 client credentials)
    │   ├── client.py               Resuelve site/drive y descarga archivos (Graph)
    │   └── reader.py               CSV -> DataFrame (reemplaza, como ORIGEN, al
    │                              Connection Manager OLE DB 'Externos_Frac')
    │
    ├── extraccion/extractor.py     un extraer_xxx(reader, periodo) por Origen: lee el
    │                              CSV de SharePoint y replica en pandas el filtro/
    │                              JOIN/dedup que antes hacia la consulta SQL contra
    │                              Externos_Frac (ver sql.py para la consulta
    │                              original, conservada como referencia); incluye la
    │                              emulación de los componentes 'Data Conversion'/
    │                              'Conversión de datos'.
    │
    ├── validacion/validator.py     ninguno de los 5 .dtsx tiene una tarea de calidad
    │                              de datos como la 'VALIDA' de 08_cartera; queda
    │                              como punto de extensión
    │
    ├── transformacion/transformer.py tareas Execute SQL / Data Flow que corren
    │                              enteramente dentro de CL_USUARIOS (mismo origen y
    │                              destino): se ejecutan como script T-SQL literal
    │
    ├── carga/loader.py             deletes/truncados y Destinos OLE DB (todos en
    │                              CL_USUARIOS)
    │
    ├── pipeline.py                  UsuariosPipeline: un 'ejecutar_xxx' por paquete
    │                              .dtsx + 'ejecutar_todo' (orden 0101→0201→0300→0301→0302)
    ├── models.py                    Periodo (YYYYMM), ResultadoSubPipeline/ResultadoPipeline
    ├── exceptions.py                ExtraccionError, ValidacionError, CargaError, PipelineError
    ├── mappings.py                  tablas/columnas/anchos de truncamiento, nombres de
    │                              archivo CSV en SharePoint (constantes de negocio)
    ├── sql.py                       sentencias T-SQL migradas literalmente, por paquete
    │                              (los SELECT que leian Externos_Frac ya no se
    │                              ejecutan, quedan solo como referencia -- ver
    │                              extraccion/extractor.py)
    ├── db.py                        DatabaseGateway (pyodbc) + fábrica de conexiones
    │                              (SQL Server auth o Windows integrada según el Connection Manager)
    └── config.py, logging_setup.py Carga de '.env' -> Settings + logging (archivo + consola)
```

`main.py` agrega `src/usuarios/` al `sys.path` al arrancar
(`sys.path.insert(0, str(BASE_DIR / "src" / "usuarios"))`), así que dentro
de `src/usuarios/` los módulos se importan igual que si estuvieran en la
raíz (`import mappings`, `from db import DatabaseGateway`, etc. — sin
cambios respecto al layout plano). Los tests usan la misma configuración
vía `pyproject.toml` (`[tool.pytest.ini_options] pythonpath =
["src/usuarios"]`).

`extractor.py`, `validator.py`, `transformer.py` y `loader.py` reciben un
`DatabaseGateway` (o un duck-type equivalente, como `tests/unit/fakes.py`)
como parámetro — no importan `db.py` para nada más que el type hint, así que
se prueban sin base de datos real. `pipeline.py` es el único módulo que
conoce las 4 capas a la vez; `main.py` es el único que además conoce `db.py`.

## Conexiones (Connection Managers originales)

Los 5 `.dtsx` originales compartían los mismos 2 Connection Managers OLE DB:

| Connection Manager | Servidor | Base de datos | Autenticación |
|---|---|---|---|
| `CL_USUARIOS` (`LocalHost.CL_USUARIOS` / `162.CL_USUARIOS`) | `172.17.0.162` | `CL_USUARIOS` | SQL Server (`mparedes`) |
| `Externos_Frac` (`223.Externos_Frac...`) | `sqlclu01lis01.tchile.local` | `Externos_Frac` | Windows integrada (SSPI) |

`CL_USUARIOS` era siempre el destino final; `Externos_Frac` era siempre el
origen (salvo el Data Flow "CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE" de
Intenciones, que iba en sentido contrario: origen `CL_USUARIOS`/`CL_DATA`,
destino `Externos_Frac`). Varias tareas SQL hacen referencias cross-database
de 3 partes contra el **mismo servidor** que `CL_USUARIOS` (172.17.0.162):
`SERVICIOS_GENERALES` (UDFs de fecha/días hábiles y limpieza XML, y el
stored procedure `SP_RETENCIONES_EFECTIVIDAD_ASESOR`) y `CL_DATA` (vista de
usuarios).

**`Externos_Frac` ya no se usa para nada** (ni como origen ni como destino),
por 2 cambios distintos:

1. **Origen migrado a SharePoint (Microsoft Graph):** todos los orígenes que
   leían `Externos_Frac` se reemplazaron por CSV publicados en SharePoint,
   uno por tabla, con el mismo nombre que la tabla que reemplazan
   (`pqe_fijtot2023.csv`, `BAJAS_FRAUDE.csv`, `BD_RETEN_V2.csv`, etc. — ver
   `mappings.py`). El acceso es via un App Registration de Microsoft Graph
   (`Sites.Selected` sobre el sitio `ReportingFractalia`, carpeta `Data
   Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/13 SERVIDOR CHILE`) —
   idéntico al patrón ya usado en `30_parque` (que lee el mismo folder para
   `pqe_fijtot2023.csv`/`pqe_movtot2023.csv`). La lógica de negocio de cada
   consulta original (filtros, JOINs, dedup por `ROW_NUMBER()`) se preserva
   tal cual, ahora en pandas — ver `extraccion/extractor.py` y `sql.py`
   (que conserva los `SELECT` originales, ya no ejecutados, como referencia
   literal).
2. **Destino dado de baja por obsoleto:** el Sequence Container "Contenedor
   de secuencias" (Data Flow "CARGA DE USUARIOS RETENCIONES SERVIDOR
   CHILE", que truncaba y cargaba `TBL_FRACTALIA_USER_RETENCIONES` en
   `Externos_Frac` desde `CL_DATA.VIEW_USUARIOS_CON_DETALLE`) se eliminó por
   completo del sub-pipeline `intenciones` — a pedido, ese trabajo ya no es
   necesario. No queda ninguna conexión SQL Server hacia `Externos_Frac`;
   `CL_USUARIOS` es el único destino de los 5 paquetes.

## Proceso original — Control Flow de cada paquete

```
USUARIOS_0101 Parque
    DELETE -> Data Flow 'PARQUE' (sin transformaciones)

USUARIOS_0201 Retenciones (3 Sequence Containers sin dependencia entre si)
    BAJAS FRAUDE:   DELETE -> Data Flow 'TBL_SERVCH_BAJAS_FRAUDE'
    BAJAS POR ALTA: DELETE LOCAL -> Data Flow 'TBL_SERVCH_BAJAS_POR_ALTA_FO'
    Find new records or for updating:
        DELETE BD_RETEN -> Data Flow 'BD_RETEN' -> UPDATE (corrige tilde) x2

USUARIOS_0300 ETL_INTENCIONES (4 Sequence Containers; CARGA BAJAS y
Contenedor de secuencias no dependen entre si, ambos deben terminar antes de
TBL_INTENCIONES)
    CARGA BAJAS:               DELETE FIJO + DELETE MOVIL -> Data Flow 'TBL_CH_BAJAS'
    Contenedor de secuencias:  TRUNCATE -> Data Flow 'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE'
    TBL_INTENCIONES:           DELETE -> Data Flow 'INTENCIONES' (IgnoreFailure)
    TABULANDO INTENCIONES:     TRUNCATE+TEMP_01 -> TRUNCATE+TEMP_02 ->
                                TRUNCATE+TEMP_03 -> TRUNCATE+TEMP_04 -> DELETE+INTENCIONES_TAB

USUARIOS_0301 Item_amdocs (cadena lineal de 10 tareas, sin ramas)
    DELETE -> Data Flow 'INTEN_AMDOCS' -> 9 UPDATE encadenados:
        PRIMER USUARIO (NULL, luego join) -> FECHA INICIO CALENDARIO ->
        TIEMPO DE ATENCION HABIL (MINUTOS, seteo, dias/horas) ->
        TIEMPO DE ATENCION CALENDARIO (DIAS) -> ESTADO ATENDIDO (2 dias, 15 dias)

USUARIOS_0302 ETL_BASE_SAIP (unico sin variable de periodo)
    TRUNCATE SAIP -> Data Flow 'SAIP' -> EXEC SP_RETENCIONES_EFECTIVIDAD_ASESOR
```

Todas las precedencias son "On Success" simples (`LogicalAnd`, sin
expresiones) — ningún paquete tiene ramas condicionales basadas en
expresiones, Script Tasks, Conditional Split, Lookup, Merge Join,
Aggregate ni Event Handlers con lógica propia.

> **Nota:** el diagrama de arriba documenta el Control Flow **original** de
> los 5 `.dtsx`, tal cual eran en SSIS. En esta migración a Python, el
> Sequence Container "Contenedor de secuencias" de `USUARIOS_0300
> ETL_INTENCIONES` (TRUNCATE + Data Flow "CARGA DE USUARIOS RETENCIONES
> SERVIDOR CHILE") se dio de baja por completo — ver "Conexiones" arriba.
> `pipeline.ejecutar_intenciones()` corre hoy solo 3 Sequence Containers
> (`CARGA BAJAS`, `TBL_INTENCIONES`, `TABULANDO INTENCIONES`), no 4.

## Requisitos

- Python 3.11+
- [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Acceso de red a `172.17.0.162` (`CL_USUARIOS`, único destino SQL Server)
- Un App Registration de Microsoft Entra ID con permiso `Sites.Selected`
  concedido sobre el sitio `ReportingFractalia` (Graph), para leer los CSV
  origen en SharePoint — mismo App Registration que usa `30_parque`.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
```

Complete `.env` con la contraseña real de `CL_USUARIOS_DB_USER`, las
credenciales del App Registration de Microsoft Graph (`TENANT_ID`,
`CLIENT_ID`, `CLIENT_SECRET`) y el periodo a procesar (ver `.env.example`).

## Ejecución

```bash
python main.py --periodo 202608                    # los 5 paquetes, en orden
python main.py --periodo 202608 --paquete parque    # solo un paquete
python main.py --paquete saip                       # SAIP no usa periodo
python main.py                                      # usa PERIODO de .env
```

`--paquete` acepta: `parque`, `retenciones`, `intenciones`, `item_amdocs`,
`saip`, `todos` (default).

## Tests

```bash
pytest
```

Los tests usan un *fake* de `DatabaseGateway` y de `SharePointCsvReader`
(`tests/unit/fakes.py`), por lo que no requieren una base de datos ni una
conexión Graph/SharePoint reales. Cubren, por paquete:

- **Parque**: filtro por el mes anterior al periodo (equivalente a
  `FORMAT(DATEADD(MONTH,-1,...),'yyyyMM')`); el `CASE` de `segme`/`tpo_prod`/
  `SERVICIO`; el `LEFT JOIN` con `RUT_marca_cartera` (distinto para FIJO
  -recorta el DV del rut- y MOVIL -match exacto por `rutcli`-); la proyección
  del periodo máximo presente al periodo siguiente (`ultimo_parque`,
  incluido el rollover de diciembre a enero).
- **Retenciones**: los 3 sub-flujos independientes; el dedup por
  `ROW_NUMBER()` de `BD_RETEN` (mismas claves de partición, sin desempate
  real -- se documenta la ambigüedad preservada); la emulación del
  componente `Data Conversion` de `BD_RETEN` (descarta `ROWNO`/`motivo`,
  castea `Evaluacion`/`last_modified`, aborta si una columna excede su
  ancho — `FailComponent`); las 2 sentencias de corrección de tilde.
- **Intenciones**: los 3 Sequence Containers activos en orden (el 4to,
  "Contenedor de secuencias", se dio de baja — ver "Conexiones" arriba); el
  filtro de
  `INTENCIONES_V2` por año/mes derivado de `CASE_OPEN_TIME` (no una columna
  de periodo plana); el truncamiento `FailComponent` de `CASE_ID_NUMBER` a
  15; la carga `IgnoreFailure` de `INTENCIONES LOCAL`; la cadena `TABULANDO
  INTENCIONES` ejecutada como SQL literal (sin cambios, sigue siendo
  origen+destino en `CL_USUARIOS`).
- **Item_amdocs**: el dedup por `ROW_NUMBER()` sobre `case_idnum` (ordenado
  por `case_optim`, sí desempata de forma determinista); el parseo de
  `case_cltim` (formato origen tipo Oracle, deducido de los índices de
  `SUBSTRING`/`RIGHT` del `.dtsx`); el descarte de `rutcli` y el renombre
  `ROWNO`→`Evaluacion`; la disposición `IgnoreFailure` (casteos tolerantes
  que no abortan la fila, a diferencia de Retenciones/Intenciones); el orden
  exacto de los 9 UPDATE.
- **SAIP**: descarte de `fec_saip_a`/`fec_saip_b`; conversión de
  `fec_ingr`/`FECHA` a fecha; el filtro de `fec_saip_a` >= 2022-01-01 como
  comparación de FECHAS real (el `.dtsx` original comparaba texto
  `dd/MM/yyyy` contra un literal ISO, un bug que excluía los días 01-20 de
  cualquier mes/año -- corregido a pedido, con test dedicado); orden
  TRUNCATE → extracción → carga → EXEC SP.
- **`test_pipeline.py`**: orden de ejecución de cada sub-pipeline y de
  `ejecutar_todo` (los 5, en el orden declarado); que un fallo en cualquier
  paso se propaga como `PipelineError` sin continuar con los pasos
  siguientes (fail-fast).

No hay forma de ejecutar contra las bases/SharePoint reales en este entorno
(las contraseñas del `.dtsx` original están cifradas por usuario/máquina
—DPAPI— y son irrecuperables, y el App Registration de Microsoft Graph
requiere credenciales propias). **Antes de operar en producción**, se
debe validar la equivalencia final (conteos de filas, diffs de tablas)
corriendo ambos procesos —el `.dtsx` original y este proyecto— contra el
mismo periodo en un entorno de prueba, y confirmar contra los archivos
reales el delimitador de los CSV (se asume `;` por consistencia con
`30_parque`, ver `mappings.CSV_DELIMITER`) y que sus columnas coinciden con
las que `extraccion/extractor.py` espera.

## Notas de fidelidad con los paquetes SSIS originales

- **Credenciales**: el Connection Manager `CL_USUARIOS` tenía, en los 5
  `.dtsx`, un password DPAPI-encriptado por usuario/máquina — irrecuperable
  fuera de la máquina original. Se reemplazó por una variable de entorno en
  `.env` (no versionado). `Externos_Frac` no tenía contraseña embebida
  (Windows integrada).
- **Origen migrado a SharePoint (Microsoft Graph)**: los 9 Orígenes OLE DB
  que leían `Externos_Frac` se reemplazaron por CSV en SharePoint, con la
  lógica de filtro/JOIN/dedup de cada consulta portada literalmente a
  pandas (ver `extraccion/extractor.py`; `sql.py` conserva los `SELECT`
  originales, ya no ejecutados, como referencia). Una ambigüedad propia del
  SQL original se preserva explícitamente en vez de "corregirse": el
  `ROW_NUMBER() OVER(... ORDER BY periodo)` de `BD_RETEN` particiona por una
  clave que incluye a `periodo`, por lo que el `ORDER BY` no desempata nada
  — qué fila "gana" no estaba definido en el `.dtsx` original tampoco, aquí
  se resuelve por orden de aparición en el CSV (sort estable).
- **"Contenedor de secuencias" (Intenciones) dado de baja, no migrado**: a
  diferencia del resto de esta lista (que documenta comportamiento
  preservado), este Sequence Container completo — TRUNCATE + Data Flow
  "CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE" (`CL_DATA.
  VIEW_USUARIOS_CON_DETALLE` → `TBL_FRACTALIA_USER_RETENCIONES` en
  `Externos_Frac`) — se eliminó del sub-pipeline `intenciones` a pedido, por
  ser un trabajo obsoleto. No quedan `loader.truncar_usuarios_retenciones`/
  `cargar_usuarios_retenciones` ni `extractor.extraer_usuarios_retenciones`;
  sus constantes SQL tambien se eliminaron de `sql.py` (no se conservaron
  como referencia, a diferencia de los `SELECT` migrados a SharePoint).
- **Filtro de `fec_saip_a` en SAIP corregido (no preservado)**: el `.dtsx`
  original comparaba el texto `dd/MM/yyyy` de `fec_saip_a` contra un literal
  ISO (`'2022-01-01'`), lo que por un bug de comparación lexicográfica
  excluía los días 01-20 de cualquier mes/año sin relación con la fecha
  real. A diferencia del resto de las "Notas de fidelidad" de este archivo,
  este caso se corrigió a pedido a una comparación de FECHAS real (ver
  `extraccion/extractor.py::extraer_saip` y
  `test_extraer_saip_filtra_por_fecha_real_no_por_comparacion_de_texto`).
- **Data Flows con origen y destino en la misma instancia SQL Server se
  ejecutan como script T-SQL literal, no como extracción+carga en Python**:
  toda la cadena `TABULANDO INTENCIONES` (`TEMP_01`→`TEMP_04`→`INTENCIONES_TAB`,
  con shredding XML vía `CROSS APPLY .nodes('/nota')` y parseo de
  fecha/usuario vía `PATINDEX`/`SUBSTRING`) y las 9 tareas `UPDATE` de
  Item_amdocs corren íntegramente contra `CL_USUARIOS` en ambos extremos.
  Reimplementar esa lógica en pandas (patrones `PATINDEX` con clases de
  caracteres, shredding XML, UDFs desconocidas) sería el mayor riesgo de
  fidelidad del proyecto sin ningún beneficio real, dado que SSIS tampoco
  movía esos datos entre servidores. Ver `transformacion/transformer.py` y
  las secciones correspondientes de `sql.py`.
- **UDFs y vistas que no forman parte de ningún `.dtsx`** (ejecutadas tal
  cual, sin conocer su lógica interna): `SERVICIOS_GENERALES.dbo.FUNC_CH_FECHA_INICIO`,
  `FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS`, `FUNC_CH_DIAS_LABORABLES`,
  `FUNC_CH_limpiacaracteresXML`; `SERVICIOS_GENERALES.dbo.SP_RETENCIONES_EFECTIVIDAD_ASESOR`;
  la vista `CL_USUARIOS.dbo.VIEW_INTENCIONES_TAB_PRIMER_USUARIO_RETENCIONES`;
  y la vista `CL_DATA.dbo.VIEW_USUARIOS_CON_DETALLE`. El usuario de
  `CL_USUARIOS_DB_USER` debe tener permiso de lectura/ejecución sobre las 3
  bases de datos involucradas (`CL_USUARIOS`, `SERVICIOS_GENERALES`, `CL_DATA`).
- **Disposición de error de los componentes `Data Conversion`/`Conversión de
  datos`** — distinta entre paquetes, preservada tal cual:
  - `BD_RETEN` (Retenciones) e `INTENCIONES` (Intenciones): sin evidencia de
    `IgnoreFailure` en el `.dtsx`, se asume el default de SSIS
    (`FailComponent`) — `extraccion/extractor.py` **aborta** (`ExtraccionError`)
    si una columna excede su ancho de truncamiento, igual que abortaría el
    Data Flow original.
  - `INTEN_AMDOCS` (Item_amdocs): `errorRowDisposition`/`truncationRowDisposition="IgnoreFailure"`
    explícito en el `.dtsx` — los casteos son **tolerantes**: un valor que no
    convierte queda `NULL`/`NaT` en vez de abortar la fila, y los
    truncamientos son silenciosos.
  - El Destino OLE DB `INTENCIONES LOCAL` (no el componente `Data
    Conversion` que lo precede) es el **único destino** de los 5 paquetes
    con disposición de error `IgnoreFailure`: `db.bulk_insert_ignorando_errores`
    reintenta fila por fila y descarta (logueando) las que fallen, en vez de
    abortar todo el lote.
- **Filtros de periodo duplicados/hardcodeados**: además del parámetro
  `?` (`User::Periodo`/`User::Periodo01`), tanto `BD_RETEN` (Retenciones)
  como `INTEN_AMDOCS` (Item_amdocs) tienen un piso fijo `periodo >= 202601`
  escrito directamente en el CTE de origen — se preserva tal cual, ambos
  filtros aplican a la vez.
- **`ROWNO` → `Evaluacion` (Item_amdocs)**: el rango de deduplicación
  (`ROW_NUMBER()`, siempre `1` dado el filtro `WHERE ROWNO=1`) se mapea, en
  el Destino OLE DB original, a una columna llamada `Evaluacion` — un nombre
  de columna reutilizado/legado que se preserva tal cual. La columna
  `rutcli` se convierte pero nunca se mapea a ningún destino (se descarta).
  De forma análoga, en `BD_RETEN` (Retenciones) el `motivo` del CTE tampoco
  llega al destino, y su `Evaluacion` es un literal entero `1` convertido a
  `string(5)` por el `Data Conversion` (no el mismo mecanismo que en
  Item_amdocs, pero el mismo nombre de columna).
- **Bug de tilde preexistente ('BAJA SIN RETENCIÓN')**: `BD_RETEN`
  (Retenciones) corrige, después de la carga, `'BAJA SIN RETENCION'` (sin
  tilde) → `'BAJA SIN RETENCIÓN'` en `submotivo`/`submotivo2` — se preserva
  la corrección posterior tal cual el `.dtsx` original, no se arregla en el
  origen.
- **`FECHA`/`case_cltim` con parseo no estándar**: en Intenciones, el
  `Fecha`/`Usuario` de cada nota (`TEMP_04`) se extraen con `PATINDEX`
  buscando literales `AM`/`PM`/`frp_...`; en Item_amdocs, `case_cltim` se
  reconstruye desde un formato tipo Oracle (`DDMONYY:HH.MI.SS.mmmAM/PM`) con
  una tabla de meses hardcodeada. Ambos casos son 100% T-SQL server-side (no
  hay Data Conversion ni lógica Python involucrada) y se preservan
  literalmente en `sql.py`.
- **`TBL_SERVCH_BAJAS_POR_ALTA_FO`**: el componente Destino OLE DB del
  `.dtsx` original se llama `BAJAS_POR_ALTA_FO` pero apunta a la tabla
  `TBL_SERVCH_BAJAS_POR_ALTA_FO` — es solo una etiqueta de componente, no
  una discrepancia de tabla real.
- **`fec_saip_a`/`fec_saip_b` (SAIP)**: se seleccionan del origen (la
  primera para derivar `FECHA` vía `FORMAT`/`CONVERT` en el propio query)
  pero ninguna de las dos llega al destino `BASE_SAIP`.
- **`SP_RETENCIONES_EFECTIVIDAD_ASESOR` y `GO` final**: el `.dtsx` original
  incluye un `GO` después del `EXEC` — no es un separador de batch real para
  un Execute SQL Task (SSIS envía el texto completo como una sola sentencia)
  y se omite, igual que los `GO` de los 2 `UPDATE` de corrección de tilde de
  `BD_RETEN` (que sí se ejecutan como 2 sentencias independientes porque son
  2 `UPDATE` distintos, no 1 solo con `GO` de por medio).
