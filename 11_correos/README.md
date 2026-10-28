# 11_correos

Proceso en cuatro etapas (estructura **medallion**), todas desde `main.py`:

1. **ingesta** — copia todos los archivos Excel (`.xlsx`/`.xlsm`/`.xls`) de
   la carpeta **`Control Correos Chile`** del sitio SharePoint **`BPO`**
   hacia la carpeta **`14 CORREOS`** (dentro de `BPOCHIPE`) del sitio
   SharePoint **`ReportingFractalia`**.
2. **bronze** — consolida las hojas `Registro`/`Bandejas` de todos esos
   archivos y las carga tal cual en SQL Server, `CL_MOVIL` en `172.17.0.162`.
3. **silver** — construye `TBL_CORREO_REGISTRO_SILVER` y
   `TBL_CORREO_BANDEJAS_SILVER` leyendo bronze: limpia y agrega columnas
   derivadas (ver "Estructura medallion").
4. **gold** — construye el modelo estrella en el esquema `gold` leyendo
   **solo** silver, y valida que cuadre.

**`python main.py` corre las cuatro etapas, en orden** (ver "Uso" para
correr solo una o reintentar desde una). Es el único ejecutable; el resto
del código vive en `src/correos/`, una carpeta por capa (ver "Estructura").

La ingesta no recorre subcarpetas: `Control Correos Chile` tiene una
subcarpeta `Macros_Coordinadores` con macros `.bas` de los coordinadores que
explícitamente **no** forma parte de esta copia.

## Por qué existe la ingesta

`BPO` y `ReportingFractalia` son sitios en **tenants de Microsoft Entra
distintos**. El endpoint de copia asíncrona nativo de Graph (`POST
/drives/.../copy`) solo copia dentro del mismo tenant/token, así que no
sirve aquí. En su lugar, cada archivo se **descarga** con el token de `BPO`
y se **sube** (reemplazando si ya existe) con el token de
`ReportingFractalia` — mismo patrón que ya usa
`02_ventas/copiar_funnel_ventas.py` para copiar `FUNNEL VENTAS V2.xlsx`
entre los mismos dos tenants.

## Estructura

Una carpeta por capa. Cada capa solo lee de la anterior y de `comun/`
(nunca de una capa posterior); cada una tiene su propio `mappings.py` con
sus tablas y columnas.

```
11_correos/
├── main.py                        # único punto de entrada: --desde / --solo / --completo / --verificar-copia / --sin-validar
├── src/correos/
│   ├── comun/                     # lo que usan todas las capas
│   │   ├── config.py              # .env -> Settings (credenciales SharePoint + SQL Server, periodo)
│   │   ├── db.py                  # DatabaseGateway (fetch_dataframe, execute_script_rowcount, truncate_table, bulk_insert)
│   │   ├── periodo.py             # FECHA_INICIO/FECHA_FIN -> [inicio, fin) en UTC + validación; ahora_local()
│   │   ├── ejecucion.py           # log de ejecuciones: iniciar_ejecucion() / finalizar_ejecucion()
│   │   ├── sharepoint_client.py   # SharePointClient + conectar_destino()
│   │   ├── sharepoint_auth.py     # get_graph_token (OAuth2 client credentials)
│   │   ├── exceptions.py
│   │   └── logging_setup.py       # logs/correos_<timestamp>.log, un archivo por corrida
│   ├── ingesta/                   # SharePoint BPO -> SharePoint ReportingFractalia
│   │   ├── copiar.py              # listar .xlsx del origen, descargar y subir uno por uno
│   │   └── verificar_copia.py     # auditoría posterior: compara columnas de 'Registro'/'Bandejas'
│   ├── bronze/                    # .xlsx de '14 CORREOS' -> dbo.TBL_CORREO_*
│   │   ├── mappings.py            # columnas de las hojas, tablas TBL_CORREO_*
│   │   ├── consolidar.py          # leer/filtrar/validar 'Registro'/'Bandejas', convertir fechas
│   │   └── cargar.py              # descarga + consolida + carga por periodo
│   ├── silver/                    # bronze -> dbo.TBL_CORREO_REGISTRO_SILVER / TBL_CORREO_BANDEJAS_SILVER
│   │   ├── mappings.py            # columnas excluidas + reglas de ASUNTO_AGRUPADO
│   │   └── cargar.py              # agrupar_asunto(), coordinador_desde_origen() + cargas
│   └── gold/                      # silver -> esquema [gold]
│       ├── mappings.py            # esquema y tablas DIM_* / FACT_*
│       ├── sql.py                 # T-SQL de dimensiones, hechos y validación
│       └── cargar.py              # dimensiones -> hechos -> validación
├── infra/sql/
│   ├── 01_bronze.sql              # DDL de TBL_CORREO_REGISTRO / TBL_CORREO_BANDEJAS
│   ├── 02_silver.sql              # DDL de TBL_CORREO_REGISTRO_SILVER / TBL_CORREO_BANDEJAS_SILVER
│   ├── 03_gold.sql                # DDL del esquema [gold]: DIM_* + FACT_MENSAJE
│   └── 04_log_ejecucion.sql       # DDL de dbo.TBL_CORREO_LOG_EJECUCION + FK desde FACT_MENSAJE
├── pyproject.toml                 # pythonpath = ["src/correos"], para tests e imports
└── tests/unit/                    # misma organización: comun/, ingesta/, bronze/, silver/, gold/ + test_main.py
```

## Estructura medallion

| Capa | Tabla (`CL_MOVIL`) | Contenido |
|---|---|---|
| Bronze | `dbo.TBL_CORREO_REGISTRO`, `dbo.TBL_CORREO_BANDEJAS` | Hojas `Registro`/`Bandejas` tal cual + `ORIGEN` (nombre del `.xlsx`) |
| Silver | `dbo.TBL_CORREO_REGISTRO_SILVER` | Columnas de `TBL_CORREO_REGISTRO` **menos** los cálculos del Excel + `ASUNTO_AGRUPADO` + `COORDINADOR` |
| Silver | `dbo.TBL_CORREO_BANDEJAS_SILVER` | `TBL_CORREO_BANDEJAS` + `COORDINADOR` |
| Gold | esquema `gold`: `FACT_MENSAJE` + `DIM_FECHA`, `DIM_BANDEJA`, `DIM_TIPO`, `DIM_ASUNTO_AGRUPADO` | Modelo estrella (ver abajo), construido **solo** desde silver |

### Bronze

Lee todos los `.xlsx` de `14 CORREOS`, consolida `Registro`/`Bandejas` de
forma independiente (nunca se mezclan) y carga:

- **`TBL_CORREO_REGISTRO`**: carga por **periodo** sobre
  `FechaHora_UTC_Texto` (UTC). Solo se **elimina e inserta** ese rango --
  otros periodos ya cargados no se tocan. Repetir la misma corrida no
  duplica filas (se vuelve a borrar e insertar el mismo periodo).
- **`TBL_CORREO_BANDEJAS`**: siempre **reemplazo completo** (`TRUNCATE` +
  `INSERT` de todo lo consolidado), sin filtro de fecha -- no tiene un campo
  de control de periodo, y cada archivo trae el estado *actual* de sus
  bandejas, no un historial.

Cada hoja `Registro` es una plantilla pre-formateada a 5000 filas: solo una
fracción tiene datos reales (el resto tiene `Bandeja` vacío) y se descarta
antes de consolidar. Un archivo con una hoja o columna faltante se omite
(se registra el motivo) sin detener el resto. Antes de insertar se
deduplica defensivamente por `ID_Mensaje`.

### Silver

`EsPrimeraEntrada`, `TieneRespuesta`, `Tiempo_Primera_Respuesta_Horas`,
`Tiempo_Respuesta_Horas` y `Estado` **quedan solo en bronze**: los calcula la
macro del Excel y no son confiables (ej. ~1.110.900 h en 3.832 salidas = el
tiempo desde la fecha 0 de Excel cuando no encuentra la entrada; primeras
respuestas negativas; `Estado` siempre vacío).

Silver se construye **leyendo bronze**, nunca los `.xlsx`. Se carga por el
mismo periodo que bronze (`DELETE` + `INSERT` del rango), o completa con
`python main.py --solo silver --completo` (hay que hacerlo tras cambiar las
reglas, para recalcular lo ya cargado).

`ASUNTO_AGRUPADO` sale de `Asunto`, `Contacto` y `Tipo` con estas reglas
(`silver/mappings.py`, `REGLAS_ASUNTO_AGRUPADO`), **en orden**, gana la
primera que calza, sin distinguir mayúsculas ni tildes:

1. **SEGUIMIENTO COBRANZA**: `Contacto` **contiene** `cobranzas@emailmovistar.cl`
   (Entrada y Salida). Va antes que REBOTE: todo mensaje con esa casilla cuenta
   como cobranza, sea cual sea el asunto.
2. **REBOTE**: `Asunto` contiene `delivery status notification`, `notificacion de estado de entrega`,
   `no entregable:` o `undelivered mail returned to sender`. Va antes que las reglas de asunto
   porque un rebote cita el asunto original (`No entregable: Actualización de correo de contacto…`).
3. **SEGUIMIENTO TÉCNICA**: mensaje de **Entrada** y alguno de los correos de `Contacto`
   es **igual** a `seguimiento.moviles@movistar.cl`.
4. **SEGUIMIENTO VENTAS**: mensaje de **Entrada** y alguno de los correos de `Contacto`
   es **igual** a uno de `CORREOS_SEGUIMIENTO_VENTAS`.
5. **SEGUIMIENTO REMEDY**: `Asunto` contiene `actividad remedy`.
6. **PRESENTACIÓN**: `Asunto` contiene `actualizacion de correo de contacto` o `presentacion`
   como **palabra completa** (`representación` o `presentaciones` no cuentan).
7. **PRUEBA**: `Asunto` contiene `prueba`.
8. **PROMO**: `Asunto` contiene `promo` (cubre `PROMOSEPTIEMBRE`, `PROMOSETIEMBRE`, `PROMO SEPTIEMBRE`, `PROMOCIONES`…).

Si no calza ninguna, queda `NULL`.

`COORDINADOR` sale de `ORIGEN` (cada `.xlsx` es el control de un
coordinador): sin el prefijo `Registro_`, sin extensión y con `_` → espacio
(`Registro_JHON_MORALES_PENA.xlsx` → `JHON MORALES PENA`).

`NUMERO_CASO` cruza `ConversationID` con `[To Addres]` (sin espacios, en
mayúsculas) de `[CL_SEGUIMIENTO_ACTUAL].[dbo].[TBL_SEGUIMIENTO]`, **solo**
casos con `[Tipo del caso] = 'Caso Comercial II'` (`silver/mappings.TIPO_CASO_SEGUIMIENTO`)
y `[To Addres]` con forma de ConversationID (32 caracteres hexadecimales).
Si la conversación tiene varios casos van todos, por apertura, separados por
`; `; sin caso = `NULL`. Es un `UPDATE` sobre **toda** la tabla silver en cada
corrida (un caso suele abrirse después del correo), replicado a
`gold.FACT_MENSAJE` en todos los periodos.

`TBL_CORREO_BANDEJAS_SILVER` se reemplaza **completa** en cada corrida de
silver (con o sin `--completo`), igual que `TBL_CORREO_BANDEJAS` en bronze:
es el estado actual de cada bandeja, no tiene periodo.

### Gold: modelo estrella

```
                  gold.DIM_FECHA
                        │
gold.DIM_TIPO ── gold.FACT_MENSAJE ── gold.DIM_BANDEJA
                        │
             gold.DIM_ASUNTO_AGRUPADO
```

- **`FACT_MENSAJE`** — 1 fila por mensaje. Claves `FECHA_KEY` (AAAAMMDD,
  fecha **local** Perú/Bogotá), `BANDEJA_KEY`, `TIPO_KEY`,
  `ASUNTO_AGRUPADO_KEY`; atributos `ID_MENSAJE`, `CONVERSATION_ID`, `ASUNTO`,
  `CONTACTO`, `FECHA_HORA_UTC`, `FECHA_HORA_LOCAL`, `HORA_LOCAL`; medida
  `CANTIDAD` (= 1, para contar). Columnas de **auditoría**:
  - `TABLA_ORIGEN` — tabla silver de la que sale la fila (`dbo.TBL_CORREO_REGISTRO_SILVER`).
  - `PROCESO_CARGA` — archivo y función que la insertó
    (`…/gold/cargar.py:cargar_periodo_gold` o `…:recargar_gold_completo`).
  - `ID_EJECUCION` — la corrida de `main.py` que la insertó; FK a
    `dbo.TBL_CORREO_LOG_EJECUCION` (ver "Log de ejecuciones").
  - `FECHA_CARGA` — inicio de esa corrida, hora **local** Perú/Bogotá (mismo
    valor para todas las filas de una carga).
- **`DIM_FECHA`** — calendario por años completos (se extiende solo cuando
  llegan datos de un año nuevo), nombres en español, semana ISO, lunes = 1.
- **`DIM_BANDEJA`** — bandeja, asesor (1:1), `COORDINADOR` (ya calculado
  en silver), `ORIGEN` y última revisión entrada/salida, desde
  `TBL_CORREO_BANDEJAS_SILVER`. Se sobrescribe sin historial.
- **`DIM_TIPO`** — Entrada / Salida. **`DIM_ASUNTO_AGRUPADO`** — los grupos
  de las reglas.

Cada dimensión (salvo `DIM_FECHA`) tiene un miembro de **clave 0 con
descripción vacía**: un valor `NULL` en silver apunta ahí (p. ej. los asuntos
sin grupo), así las claves foráneas nunca quedan `NULL`.

Las dimensiones **nunca se truncan** (claves estables); `FACT_MENSAJE` se
carga por periodo igual que bronze/silver, o completa con
`python main.py --solo gold --completo`. Al final se valida que
`FACT_MENSAJE` tenga las mismas filas que silver y ninguna sin bandeja/tipo;
si no cuadra, `main.py` termina con código `1`.

Tras cambiar reglas: `python main.py --desde silver --completo` (reconstruye
silver y luego gold).

### Log de ejecuciones

`dbo.TBL_CORREO_LOG_EJECUCION` (DDL en `infra/sql/04_log_ejecucion.sql`,
código en `comun/ejecucion.py`): **1 fila por corrida** de `main.py` (salvo
`--verificar-copia`). Se abre al empezar con `ESTADO = 'EN_CURSO'` y se
cierra al terminar con `OK` o `ERROR`, más `FILAS_BRONZE`/`FILAS_SILVER`/
`FILAS_GOLD` (filas insertadas por etapa; `NULL` si la etapa no corrió),
`VALIDACION_GOLD`, `MENSAJE_ERROR`, `ETAPAS`, `MODO`, el periodo (UTC),
`USUARIO` y `EQUIPO`. Fechas de inicio/fin en hora local Perú/Bogotá.

Queda `ERROR` si una etapa falla (con el mensaje), si algún archivo no se
copió o si la validación de gold no cuadra. Para ver qué corrida cargó cada
mensaje:

```sql
SELECT l.ID_EJECUCION, l.FECHA_INICIO, l.ESTADO, l.ETAPAS, l.MODO, COUNT(f.MENSAJE_KEY) AS MENSAJES
FROM dbo.TBL_CORREO_LOG_EJECUCION l
LEFT JOIN gold.FACT_MENSAJE f ON f.ID_EJECUCION = l.ID_EJECUCION
GROUP BY l.ID_EJECUCION, l.FECHA_INICIO, l.ESTADO, l.ETAPAS, l.MODO
ORDER BY l.ID_EJECUCION DESC;
```

Como `main.py` registra toda corrida, ahora necesita conexión a SQL Server
desde el inicio, incluso con `--solo ingesta`.

## Configuración

Copiar `.env.example` a `.env` y completar:

- `SOURCE_TENANT_ID` / `SOURCE_CLIENT_ID` / `SOURCE_CLIENT_SECRET`: App
  Registration del tenant **`BPO`** (permiso `Sites.Selected` sobre
  `/sites/BPO`).
- `TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET`: App Registration del tenant
  **`ReportingFractalia`** (permiso `Sites.Selected` sobre
  `/sites/ReportingFractalia`).

Ambos pares de credenciales ya existen y están probados en
`02_ventas/.env` (mismos tenants, mismo sitio de origen `BPO`).

- `DB_SERVER` / `DB_NAME` (`CL_MOVIL`) / `DB_USER` / `DB_PASSWORD`: SQL
  Server `172.17.0.162`, destino de bronze/silver/gold. Mismo login
  `mparedes` ya usado contra ese servidor en `02_ventas`/`04_usuarios_y_retenciones`
  (bases `CL_USUARIOS`/`CL_DATA`). Probado en vivo (con VPN conectada).
- `FECHA_INICIO` / `FECHA_FIN`: periodo por defecto de bronze/silver/gold
  (UTC, sobre `FechaHora_UTC_Texto`). Solo fecha
  (`FECHA_INICIO=2026-09-01`, `FECHA_FIN=2026-09-30`) = días completos, con
  `FECHA_FIN` incluido entero; con hora (`2026-09-01T00:00:00`) = inicio
  inclusivo, fin exclusivo. Permite correr `main.py` sin argumentos (útil
  para un schedule automatizado); `--fecha-inicio`/`--fecha-fin` tienen
  prioridad sobre `.env` si se pasan. Se valida **antes** de empezar: si
  falta o es inválido, no se copia nada.

### Antes de la primera carga

Las tablas **no existían** en `CL_MOVIL` -- ya se crearon (con VPN
conectada) corriendo una vez, en orden:

```
sqlcmd -S 172.17.0.162 -d CL_MOVIL -i infra/sql/01_bronze.sql
sqlcmd -S 172.17.0.162 -d CL_MOVIL -i infra/sql/02_silver.sql
sqlcmd -S 172.17.0.162 -d CL_MOVIL -i infra/sql/03_gold.sql
sqlcmd -S 172.17.0.162 -d CL_MOVIL -i infra/sql/04_log_ejecucion.sql
```

Usan `IF OBJECT_ID(...) IS NULL` (nunca `DROP`), así que correrlos de nuevo
no toca nada si las tablas ya existen.

**Validado en vivo**: primera carga bronze (2026-09-22) y la estructura
completa bronze/silver/gold (2026-09-23, 10.518 mensajes en las tres capas,
validación gold OK). Ajustes que salieron de las pruebas reales:

- `Contacto` se ensanchó a `NVARCHAR(MAX)` -- puede traer varias direcciones
  separadas por `;`, no un solo correo (superaba los 255 caracteres).
- `db.py` reintenta sin `fast_executemany` si pyodbc falla con
  "right truncation": ese modo estima el buffer de cada columna a partir de
  las primeras filas del lote, y con `Asunto`/`Contacto` (`NVARCHAR(MAX)`,
  longitud muy variable entre filas) puede quedarse corto.

## Uso

```
python main.py                              # todo: ingesta -> bronze -> silver -> gold
python main.py --desde silver               # reintentar desde silver (bronze ya cargado)
python main.py --solo gold                  # solo una etapa
python main.py --solo gold --completo       # reconstruir una etapa completa (solo silver/gold)
python main.py --desde silver --completo    # reconstruir silver y gold (tras cambiar reglas)
python main.py --fecha-inicio 2026-09-01 --fecha-fin 2026-09-30   # otro periodo que el de .env
python main.py --verificar-copia            # solo auditar la copia de ingesta
python main.py --sin-validar                # sin validar conexiones al inicio (solo emergencias)
```

### Validación de conexiones

Antes de cualquier etapa se prueban las conexiones que usa la corrida
(`src/correos/comun/conexiones.py`): SQL Server `CL_MOVIL` (siempre), las
tablas cruzadas en silver (`CL_DATA.TBL_HISTORICO_PLACES`,
`CL_SEGUIMIENTO_ACTUAL.TBL_SEGUIMIENTO`) y SharePoint origen/destino según la
etapa. Si alguna no responde **el ETL no se ejecuta** (no se copia, borra ni
carga nada) y la consola pregunta `[R] Reintentar / [C] Cancelar`:

- `R` vuelve a probar solo las que fallaron; si responden, el ETL sigue.
- `C` cancela (código `1`).
- Sin respuesta en 5 min (o sin consola): reintenta solo hasta 3 veces, cada
  5 min, y si sigue fallando cancela.

La cancelación queda solo en `logs/` (no en `TBL_CORREO_LOG_EJECUCION`).

Un fallo en una etapa detiene las siguientes pero **no deshace** las
anteriores (los archivos ya copiados quedan en SharePoint, bronze/silver
quedan cargados): se reintenta con `--desde`. Un archivo que falla al
copiarse **no detiene el resto**. Todo queda en el log
(`logs/correos_<timestamp>.log`, un archivo por corrida). `main.py` termina
con código `1` si falló alguna etapa, algún archivo de la copia, o la
validación de gold; `0` si todo salió bien.

`--completo` no aplica a bronze: bronze siempre carga por periodo (el que
cubren los `.xlsx`).

### Verificar la copia

`python main.py --verificar-copia` compara, para cada `.xlsx`, las columnas
de las hojas `Registro` y `Bandejas` entre origen y destino. **No** compara
el contenido de las filas ni el hash de bytes: los `Registro_*.xlsx` son
controles de bandeja **en vivo** (las macros `ActualizarControlBandejas_*.bas`
los reescriben continuamente durante la jornada), así que su contenido
cambia entre una descarga y otra aunque la copia haya funcionado bien — lo
único que debe mantenerse estable es la estructura (hojas/columnas).

## Informe Power BI

`powerbi/BPO_TCH_Correo.pbip` — proyecto de Power BI (formato PBIP: modelo en
TMDL y reporte en PBIR, texto versionable). Importa **solo el esquema
`gold`** de `CL_MOVIL`; el servidor y la base son parámetros (`Servidor`,
`BaseDatos`, en *Transformar datos → Administrar parámetros*). `ASUNTO` y
`CONTACTO` se importan para la vista de detalle (carpeta *Detalle* de
`FACT_MENSAJE`): son datos de clientes, así que el `.pbix`/la caché no deben
compartirse fuera del equipo.

- **Resumen ejecutivo**: KPIs (mensajes, entradas, salidas, entradas sin
  rebotes, rebotes, % rebote), mensajes por día y tipo, por grupo de asunto,
  salidas por coordinador y resumen por coordinador.
- **Detalle por asesor**: mensajes por hora del día y actividad por asesor
  y bandeja.

Medidas en `FACT_MENSAJE` (carpetas *Volumen*, *Indicadores*, *Auditoría*).
Abrir siempre el `.pbip` (no un `.pbix`); `.pbi/cache.abf` guarda los datos
importados y está en `.gitignore`.

## Tests

```
python -m pytest tests/
```
