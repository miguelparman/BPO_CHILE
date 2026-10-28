# Ventas / Señalizaciones — Migración SSIS → Python

Migración a Python (arquitectura modular por componentes) de 2 paquetes
SSIS de Chile:

- **`CROSS 0101 SSIS_CL_Senalizaciones.dtsx`**: carga el funnel de
  señalizaciones (formulario de venta cruzada) hacia `CL_USUARIOS`.
- **`CROSS 0102 SSIS_CL_Ventas.dtsx`**: carga el funnel de ventas
  cross-selling (base, comisiones, metas, consolidado `TBL_FUNNEL_VENTAS2`)
  hacia el mismo servidor.

Se ejecutan **en ese orden** (0101 antes que 0102): Ventas depende de que
`TBL_FUNNEL_SENHALIZACIONES_DNI` ya tenga datos frescos, y ese es uno de los
efectos de correr Señalizaciones primero.

El origen cambió: en vez de archivos de red local (`D:\IRISCENE
ENGINEERING CORPORATION SLU\BPO - Insumos\...`) y una descarga puntual de
Google Drive, ahora se lee **el mismo archivo publicado en SharePoint**
(carpeta `07 CROSS`), vía Microsoft Graph.

## Arquitectura

**"src layout"**: en la raíz del proyecto solo quedan los archivos que
importan de entrada — `README.md`, `.gitignore`, `.env.example`,
`requirements*.txt`, `pyproject.toml` y los puntos de entrada (`main.py`,
`copiar_funnel_ventas.py`, `exportar_senhalizaciones_csv.py`). Todo el
código vive en `src/ventas/`, y ahí sigue siendo modular por componentes,
dividido en 4 capas que replican 1:1 las etapas del proceso original
(extracción, validación, transformación, carga), cada una en su propia
carpeta — sin capas domain/application/infrastructure ni interfaces
`Protocol` de por medio (mismo patrón plano que `08_cartera`/`30_parque`/
`04_usuarios_y_retenciones`, solo que aquí además separado de la raíz del repo):

```
02_ventas/
├── README.md, .gitignore, .env.example, requirements*.txt, pyproject.toml
├── main.py                          CLI + composition root: corre el Paso 0
│                                    que corresponda antes de cada paquete
├── copiar_funnel_ventas.py          Paso 0a (main.py lo llama antes de
│                                    'ventas'/'todos'): copia 'FUNNEL VENTAS
│                                    V2.xlsx' del sitio BPO a '07 CROSS'
├── exportar_senhalizaciones_csv.py Paso 0b (main.py lo llama antes de
│                                    'senalizaciones'/'todos'): descarga el
│                                    formulario de Google Sheets y sube
│                                    'Señalizaciones.csv' a '07 CROSS'
├── tests/unit/                       fakes + tests por capa
└── src/ventas/                        todo el codigo de la aplicacion
    ├── sharepoint/
    │   ├── auth.py     get_graph_token(): OAuth2 client-credentials contra Microsoft Graph
    │   ├── client.py    SharePointClient: resolve_site/resolve_drive/resolve_folder/download_file
    │   │                + upload_file (sube bytes a una carpeta, simple o en chunks)
    │   └── reader.py     SharePointCsvReader (Señalizaciones.csv) y
    │                     SharePointExcelReader (Base Carta Meta.xlsx / FUNNEL VENTAS V2.xlsx, por hoja)
    │
    ├── extraccion/extractor.py       Un extraer_xxx por Origen (CSV/Excel/tabla SQL)
    ├── validacion/validator.py       Columnas esperadas + anchos (FailComponent/IgnoreFailure)
    ├── transformacion/transformer.py 'Conversión de datos' emulada + Execute SQL Tasks
    ├── carga/loader.py                TRUNCATE/DELETE + Destino OLE DB (bulk insert)
    │
    ├── pipeline.py    VentasPipeline: ejecutar_senalizaciones()/ejecutar_ventas()/ejecutar_todo()
    ├── models.py      ColumnaSpec, ResultadoSubPipeline, ResultadoPipeline
    ├── exceptions.py  VentasError y subclases
    ├── mappings.py    Archivos/hojas SharePoint, tablas, columnas, anchos, correcciones literales
    ├── sql.py         SQL migrado literalmente de cada Execute SQL Task
    ├── db.py          DatabaseGateway (pyodbc) + fábrica de conexión (CL_USUARIOS)
    ├── config.py      '.env' -> Settings (sin credenciales embebidas; incluye
    │                  cargar_configuracion_origen() para el tenant de 'BPO', ver "Paso 0")
    └── logging_setup.py Logging (archivo + consola)
```

`pipeline.py` es el único módulo que conoce las 4 capas a la vez; `main.py`
es el único que además conoce `db.py`/`sharepoint/`. Los 3 scripts de la
raíz agregan `src/ventas/` al `sys.path` al arrancar (`sys.path.insert(0,
str(BASE_DIR / "src" / "ventas"))`), así que dentro de `src/ventas/` los
módulos se importan igual que si estuvieran en la raíz (`import mappings`,
`from db import DatabaseGateway`, etc. — sin cambios respecto al layout
plano). Los tests usan la misma configuración vía `pyproject.toml`
(`[tool.pytest.ini_options] pythonpath = ["src/ventas"]`).

## Alcance de orígenes

Ambos `.dtsx` originales leen 4 archivos Excel/CSV distintos, todos
publicados ahora en la **misma carpeta de SharePoint** (`sites/
ReportingFractalia`, drive `Data Reporting`, `REPOSITORIOS DE CRUDOS/CHILE/
BPOCHIPE/07 CROSS`):

| Archivo | Hoja(s) usada(s) | Quién lo usa |
|---|---|---|
| `FUNNEL VENTAS V2.xlsx` | `baseV2`, `Esp`, `Sup` | Ventas |
| `Base Carta Meta.xlsx` | `DNI Senalizaciones`, `Comisiones mes`, `Hoja1` | Señalizaciones (`DNI Senalizaciones`) y Ventas (las 3) |
| `Señalizaciones.csv` | (Flat File) | Señalizaciones |

`Señalizaciones.csv` lo genera `exportar_senhalizaciones_csv.py` (dentro de
este proyecto), que reemplaza al Execute Process Task original
(`Descargar googledrive señalizaciones`, que llamaba a
`Ch_Senhalizaciones.py`, ver `Basurero/02_Cross/`): descarga las respuestas
del formulario publicadas en Google Sheets y las sube directo a `07 CROSS`
vía Microsoft Graph, en vez de escribir a la ruta de red local del script
original. El delimitador de salida es `;` — pendiente de correr este script
una vez para regenerar el archivo real con ese delimitador (ver
`mappings.CSV_DELIMITER`, que debe mantenerse en `,` hasta que eso pase).

`Auditorias Cross Selling - Pusher.xlsx` (usado por
`TBL_VENTAS_CROSSELLING_PUSHER_ABORDABLE` en el `.dtsx` original) **no se
migró**: el usuario confirmó que ese sub-proceso está obsoleto, y de hecho
el `Contenedor de secuencias` completo ya venía con `DTS:Disabled="True"`
en el paquete original — no corría en producción.

### Paso 0a: copiar `FUNNEL VENTAS V2.xlsx` a `07 CROSS`

`copiar_funnel_ventas.py` copia el archivo desde el sitio `BPO`
(`Planificación y Control/Insumos/Chile/Ventas_Chile/FUNNEL VENTAS V2.xlsx`
— ruta relativa a la raíz del drive, **sin** el prefijo `Documentos
compartidos/`) hacia `07 CROSS`. `BPO` y `ReportingFractalia` son
**tenants de Microsoft Entra distintos**, cada uno con su propio App
Registration/credenciales (`TENANT_ID`/... para `ReportingFractalia`,
`SOURCE_TENANT_ID`/... para `BPO`, ver `.env.example`) — por eso no se usa
el endpoint de copia asíncrona nativo de Graph (que solo copia dentro del
mismo tenant/token): se descarga con el token de `BPO`
(`SharePointClient.download_file`) y se sube con el token de
`ReportingFractalia` (`SharePointClient.upload_file`). `main.py` llama a
`copiar_funnel_ventas()` automáticamente antes de correr el paquete
`ventas`/`todos` (equivalente al Execute Process Task que en el `.dtsx`
original corría dentro del propio Control Flow) — no hace falta correrlo
aparte. El script sigue siendo ejecutable suelto (`python
copiar_funnel_ventas.py`) para refrescar el Excel sin correr el resto del
pipeline.

### Paso 0b: exportar `Señalizaciones.csv` a `07 CROSS`

`exportar_senhalizaciones_csv.py` descarga el CSV publicado de Google
Sheets/Forms (mismo link que usaba `Ch_Senhalizaciones.py`) y lo sube a
`07 CROSS` con el token de `ReportingFractalia` (`upload_file`), con `;`
como delimitador de salida. Igual que el paso 0a, `main.py` llama a
`subir_senhalizaciones_csv()` automáticamente antes de correr el paquete
`senalizaciones`/`todos` — no hace falta correrlo aparte. El script sigue
siendo ejecutable suelto (`python exportar_senhalizaciones_csv.py`) para
refrescar el CSV sin correr el resto del pipeline.

## Destino SQL Server

Ambos `.dtsx` originales declaran conexiones OLE DB a `172.17.0.162`.
**Solo `CL_USUARIOS` se usa realmente**: `CROSS 0102 SSIS_CL_Ventas`
declara también una conexión a `CL_DATA` (`162.CL_DATA`), pero ningún
Execute SQL Task ni Data Flow del paquete la referencia — es una conexión
muerta en el `.dtsx` original, y no se migró ninguna configuración para
`CL_DATA`.

## Despliegue

El pipeline se ejecuta y se programa en el **mismo servidor Chile
(`172.17.0.162`)** que hoy corre los paquetes SSIS y hospeda `CL_USUARIOS`
— no en la máquina de desarrollo. `DB_SERVER` en `.env` puede apuntar a
`localhost`/`127.0.0.1` o a `172.17.0.162` (la conexión es local a esa
máquina); el acceso saliente a Microsoft Graph
(`login.microsoftonline.com`, `graph.microsoft.com`) debe estar disponible
desde ahí. La programación periódica (equivalente al Agent Job/Scheduler
original) se hace con Windows Task Scheduler ejecutando `python main.py`.

## Proceso original (Control Flow)

```
CROSS 0101 SSIS_CL_Senalizaciones
├─ Descargar googledrive señalizaciones (fuera de alcance, ver arriba)
├─ TRUNCATE SEÑALIZACIONES -> Data Flow 'TBL_FUNNEL_SENHALIZACIONES' (CSV)
├─ SP_FUNNEL_SENHALIZACIONES
├─ UPDATE (corrige 19 DNIs con cero inicial perdido, pares literales)
└─ Contenedor de secuencias
   ├─ TRUNCATE -> Data Flow 'TBL_FUNNEL_SENHALIZACIONES_DNI' (Excel)
   └─ UPDATE (corrige 'TU DNI' en TBL_FUNNEL_SENHALIZACIONES desde la tabla DNI)

CROSS 0102 SSIS_CL_Ventas
├─ Contenedor de secuencias 2 (sin dependencias entre sus 4 hijos; el 4to
│  ya viene deshabilitado en el .dtsx original)
│  ├─ COMISIONES: TRUNCATE -> Data Flow 'TBL_VENTAS_RANGO_COMISIONES' (Excel)
│  ├─ Contenedor de secuencias 1: TRUNCATE -> Data Flow
│  │  'TBL_FUNNEL_SENHALIZACIONES_DNI' (recarga independiente de la de Señalizaciones)
│  ├─ METAS: TRUNCATE -> Data Flow 'METAS_COMISIONES' (Excel)
│  └─ TBL_VENTAS_CROSSELLING_PUSHER_ABORDABLE (DESHABILITADO, no migrado)
├─ Contenedor de secuencias 1 (BaseV2/Esp/Sup en paralelo; UPDATE espera a los 3)
│  ├─ BaseV2: TRUNCATE -> Data Flow 'basev2_temp' (Excel) -> Tarea Ejecutar SQL
│  │  (limpieza, 5 sentencias) -> update DNI
│  ├─ Contenedor de secuencias (Esp): TRUNCATE -> Data Flow 'Esp_temp'
│  ├─ Sup: TRUNCATE -> Data Flow 'Sup_temp'
│  └─ UPDATE (completa DNI SUPERVISOR/DNI ESPECIALISTA/COD_DNI, 3 sentencias)
└─ LOCAL
   ├─ TRUNCATE TBL_FUNNEL_VENTAS_Temp -> Data Flow 'Temp' (desde basev2_temp)
   ├─ DELETE VENTAS2 >= Fecha
   ├─ DELETE TEMP < Fecha
   └─ INSERT VENTAS2 (desde Temp)
```

`Contenedor de secuencias 1` (BaseV2/Esp/Sup) corre en paralelo en el
`.dtsx` original; aquí se ejecuta en secuencia (BaseV2, Esp, Sup) — el
resultado no cambia porque son independientes entre sí, solo cambia el
tiempo total de corrida.

## Notas de fidelidad

- **`GO` como separador de lotes**: 3 Execute SQL Tasks del `.dtsx`
  original (`UPDATE` de DNI con cero perdido en Señalizaciones,
  `Tarea Ejecutar SQL` de limpieza y `UPDATE` de DNI supervisor/especialista
  en Ventas) traían su texto SQL con varias sentencias separadas por `GO`.
  `GO` **no es una instrucción T-SQL válida** para el proveedor OLE DB que
  usa el Execute SQL Task — es un separador de lotes de SSMS/sqlcmd. Aquí
  cada sentencia se ejecuta por separado (`mappings.CORRECCIONES_DNI_CEROS`
  + `sql.SQL_CORREGIR_DNI_CERO_PERDIDO` parametrizado; tuplas
  `sql.SQL_LIMPIEZA_VENTAS_BASEV2` / `sql.SQL_COMPLETAR_DNI_SUP_ESP_COD`),
  preservando la lógica exacta de cada UPDATE/DELETE sin enviar la palabra
  `GO` a SQL Server.
- **Typo real en la tabla `TBL_FUNNEL_SENHALIZACIONES`**: la columna
  destino de `Número del cual llama` se llama literalmente
  `MÚMERO DEL CUAL LLAMA` (con "MÚ" en vez de "NÚ") en la tabla SQL Server
  — se preserva tal cual, no se corrige.
- **`TBL_FUNNEL_SENHALIZACIONES_DNI` se recarga dos veces**: tanto
  Señalizaciones como Ventas truncan y vuelven a cargar esta misma tabla
  desde la misma hoja Excel, de forma independiente. Se preserva esa
  redundancia (ambas corren, en el orden 0101→0102) en vez de deduplicarla.
- **`METAS_COMISIONES` — cast implícito no documentado**: en el `.dtsx`
  original, `Fibra`/`Voz`/`Total`/`PERIODO` y `Señalizacion Total` (esta
  última además renombrada a `SEÑALIZACIONES TOTAL`) van directo del Origen
  Excel al Destino OLE DB **sin pasar por el componente `Conversión de
  datos`**, pese a que la tabla destino los declara `int`. No hay ninguna
  disposición de error configurada para ese cast implícito — un valor no
  numérico haría fallar el INSERT completo. Aquí se castea explícitamente
  antes de insertar, levantando `ValidacionError` si no es numérico
  (`transformer.convertir_tipos_metas`), en vez de dejar que pyodbc falle
  con un error genérico.
- **`STB`/`BAF`/`TV`/`VOZ`/`BAM`/`TOTAL INGRESADO` — `ColumnaSpec.tipo='entero'`,
  no `'numero'`**: el `.dtsx` original (`BaseV2\Conversión de datos`) declara
  el `outputColumn` de estas 6 columnas como `dataType='i4'` (entero, DT_I4),
  aunque el origen Excel las trae como `r8` (double). La primera versión de
  esta migración las trataba todas como genéricas `tipo='numero'` (float,
  sin redondear) — visto en producción (2026-09), `TOTAL INGRESADO` llegaba
  con decimales a `TBL_FUNNEL_VENTAS2` donde antes (vía SSIS) siempre
  llegaba entero. `tipo='entero'` (`transformer.convertir_tipos`) redondea y
  castea a `Int64` (nullable) antes del INSERT, igual que el DT_I4 original.
- **Disposición de error/truncamiento — `FailComponent` ya NO aborta la
  carga**: el `.dtsx` original abortaba el Data Flow completo si una
  columna de texto `FailComponent` (`ColumnaSpec.estricto=True`, ver
  `models.py`/`mappings.py`) excedía su ancho declarado. Tras la primera
  corrida real (2026-09, ver más abajo) se confirmó que el formulario de
  origen trae respuestas mal llenadas con cierta frecuencia, y bloquear
  todo el funnel por unas pocas filas no es aceptable — a pedido explícito
  del usuario, `transformer.vaciar_valores_que_excedan_ancho()` reemplazó
  ese aborto: el valor que excede el ancho queda `NULL` en esa columna y el
  resto de la fila se carga igual. Solo aplica a columnas `estricto=True`
  (texto) — columnas `estricto=False` (`IgnoreFailure`) ya NO pasan por
  esta función (ver más abajo). `validacion.validar_longitudes()` sigue
  existiendo y probada (documenta el comportamiento `FailComponent`
  original), pero ya no se llama desde `pipeline.py`. Columnas
  numéricas/fecha siguen igual: `estricto=True` aborta si no parsean,
  `estricto=False` queda `NULL`.
- **Columnas de texto `IgnoreFailure` (`estricto=False`) — truncar, no
  vaciar**: `vaciar_valores_que_excedan_ancho()` originalmente vaciaba
  también estas columnas al exceder su ancho, igual que las `FailComponent`
  — pero eso no replica la disposición real de truncamiento
  `IgnoreFailure` del `.dtsx` original (que trunca el valor al ancho
  declarado y sigue, no lo descarta). Visto en producción (2026-09) con
  `SEÑALIZACION // EJECUTIVO DE VENTAS` (ancho 15, `estricto=False`): el
  Excel de origen trae valores más largos con cierta frecuencia (87 de
  ~24.700 filas en una corrida), y quedaban en `NULL` en vez de cargarse
  truncados — a pedido explícito del usuario, tras revisar el Excel de
  origen. Ahora estas columnas no pasan por
  `vaciar_valores_que_excedan_ancho()`: quedan intactas para que
  `convertir_tipos()` las trunque al ancho declarado (comportamiento que ya
  tenía implementado pero quedaba sin efecto, tapado por el vaciado previo).
- **`RUT EJECUTIVO` — `estricto` invertido**: auditoría completa (2026-09-17)
  de las 34 columnas de `COLUMNAS_VENTAS_BASEV2` contra el `outputColumn`
  real del Data Convert en el `.dtsx` encontró que `RUT EJECUTIVO` estaba
  declarado `estricto=False` en `mappings.py`, pero el `.dtsx` original la
  declara `FailComponent` (`errorRowDisposition`/`truncationRowDisposition`),
  igual que el resto de las columnas RUT de esta tabla (`Rut Empresa`,
  `RUT BACK`, `RUT RAC VENTA`, todas `estricto=True`). Con `estricto=False`
  un RUT EJECUTIVO demasiado largo se truncaba y cargaba en silencio (valor
  no confiable, ya no es un RUT válido) en vez de quedar `NULL` como sus
  columnas hermanas — y como `COD_DNI` se copia de `RUT EJECUTIVO` vía SQL
  (`sql.SQL_COMPLETAR_DNI_SUP_ESP_COD`), el valor truncado se propagaba
  también ahí. Corregido a `estricto=True`.
- **`STB`/`BAF`/`TV`/`VOZ`/`BAM`/`TOTAL INGRESADO` seguían llegando como
  `'1.0'` (texto) a `TBL_FUNNEL_VENTAS2` pese al fix de `tipo='entero'`**:
  confirmado contra el esquema real (2026-09-17) que
  `TBL_FUNNEL_VENTAS_Temp`/`TBL_FUNNEL_VENTAS2` declaran estas 6 columnas
  como `nvarchar` (no numéricas) — solo `TBL_FUNNEL_VENTAS_basev2_temp` las
  tiene como `int`. El paso `LOCAL` relee `basev2_temp` completa desde SQL
  Server (`extractor.extraer_ventas_basev2_temp` → `db.read_table` →
  `pd.DataFrame.from_records`); pandas no tiene un entero nulleable nativo,
  así que cualquier columna `int` con al menos un `NULL` sube a `float64` al
  releerla — un valor `1` se vuelve `1.0`, y al insertarse en la columna de
  texto destino queda literalmente `'1.0'` en vez de `'1'`. El
  `tipo='entero'` solo corregía la carga a `basev2_temp`, no este segundo
  viaje. Fix: nuevo paso explícito en `pipeline._local()` que vuelve a
  pasar estas 6 columnas por `transformer.convertir_tipos()`
  (`mappings.COLUMNAS_VENTAS_TEMP_ENTERO`) justo después de releer
  `basev2_temp` y antes de cargar `TBL_FUNNEL_VENTAS_Temp`.
- **`RUT DE LA EMPRESA` / `NOMBRE EMPRESA` invertidos**: visto en
  producción (2026-09) — varias respuestas del formulario tienen el RUT y
  el nombre de la empresa cargados en el campo contrario.
  `transformer.corregir_rut_nombre_invertidos()` detecta el patrón (si
  `NOMBRE EMPRESA` tiene forma de RUT chileno y `RUT DE LA EMPRESA` no) y
  los intercambia antes de cargar — no es lógica del `.dtsx` original, es
  limpieza agregada sobre datos reales. Lo que no se puede recuperar así
  (correo pegado en el campo RUT, texto mezclado de otro caso) cae en la
  regla general de arriba: queda `NULL`, no bloquea la carga.
- **`162.CL_DATA`**: declarado en el `.dtsx` original pero sin ningún
  componente que lo use — no se migró configuración para esa base.
- La corrección exacta de valores (`CORRECCIONES_DNI_CEROS`) incluye un par
  duplicado (`004981615`/`4981615` dos veces) tal como aparecía en el
  `.dtsx` original — es un no-op redundante, se preserva sin limpiar.

## Pruebas

`tests/unit/` usa fakes (`FakeDatabaseGateway`, `FakeSharePointCsvReader`,
`FakeSharePointExcelReader`) para probar cada capa sin una base de datos ni
una conexión Graph real: extracción (lee el archivo/hoja correcto),
validación (columnas/anchos), transformación (casts, renombres, SQL
literal ejecutado en el orden correcto) y el pipeline completo (orden real
de ejecución, fail-fast, `ejecutar_todo` corre 0101 antes que 0102).

```
pip install -r requirements-dev.txt
pytest
```

La corrida real contra `CL_USUARIOS`/SharePoint (`python main.py`) no se
pudo validar desde este entorno de desarrollo (sin acceso de red al
servidor ni credenciales Graph todavía) — queda pendiente para cuando el
usuario la ejecute con su red/credenciales. Es probable que surjan ajustes
de ancho de columna u otros detalles de datos reales no visibles en los
`.dtsx` (mismo patrón que en `30_parque`/`04_usuarios_y_retenciones`); ante un error de
`String data, right truncation` sin evidencia documentada de truncamiento
intencional, preferir ampliar la columna destino (`ALTER TABLE`) antes que
truncar datos.

## Uso

```
python main.py --fecha 2026-08-01                 # corre los 2 paquetes en orden (0101 -> 0102)
python main.py --fecha 2026-08-01 --paquete ventas # corre solo Ventas
python main.py --paquete senalizaciones            # no usa --fecha
python main.py                                     # usa VAR_FECHA de .env (corre tambien el Paso 0 de cada paquete)
python copiar_funnel_ventas.py                      # paso 0a suelto: solo refresca el Excel, sin correr el pipeline
python exportar_senhalizaciones_csv.py              # paso 0b suelto: solo refresca el CSV, sin correr el pipeline
```
