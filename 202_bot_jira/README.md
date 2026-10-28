# Bot Jira — Registro de worklogs desde Excel

Registra horas trabajadas (worklogs) en Jira a partir de una plantilla
Excel. Cada fila del Excel es un worklog a crear (o actualizar) mediante la
API REST de Jira.

## Arquitectura

Capas `domain`/`application`/`infrastructure` (a diferencia del patrón
plano usado en `02_ventas`/`08_cartera`/`30_parque`/`04_usuarios_y_retenciones`):

```
202_bot_jira/
├── main.py                    Composition root: cablea infraestructura + caso de uso, ejecuta
├── .env / .env.example        Credenciales Jira (no versionar .env)
├── worklog.xlsx                Plantilla de entrada/salida por defecto
└── src/
    ├── config.py               .env + argv -> Settings (JIRA_BASE_URL/USER/PASSWORD, tz, template_path)
    ├── domain/
    │   ├── models.py            WorklogRow (fila leída) y WorklogOutcome (resultado a escribir)
    │   ├── value_objects.py     Ticket (valida formato), time_spent_from_raw, started_from_raw
    │   └── exceptions.py        DomainError y subclases (InvalidTicketError, InvalidTimeFormatError)
    ├── application/
    │   ├── ports.py              Protocols: WorklogRepository, JiraWorklogGateway
    │   └── use_cases.py          RegistrarWorklogsUseCase: crea o actualiza cada fila, arma el resumen
    └── infrastructure/
        ├── excel_repository.py   ExcelWorklogRepository: lee la plantilla, escribe solo las columnas rastreadas
        └── jira_gateway.py        JiraRestWorklogGateway: POST/PUT contra rest/api/2/issue/{ticket}/worklog
```

`main.py` es el único módulo que conoce tanto `infrastructure` como
`application`; `use_cases.py` solo depende de los `Protocol` de `ports.py`,
no de las implementaciones concretas (Excel/Jira son intercambiables por
fakes en tests).

## Configuración

Variables de entorno (`.env`, ver `.env.example`):

```
JIRA_BASE_URL=https://itsm.fractalia.es
JIRA_USER=tu_usuario
JIRA_PASSWORD=tu_password
```

La zona horaria de los worklogs está fija en código
(`src/config.py:load_settings`) a `America/Lima` (UTC-5): debe coincidir
con la zona horaria configurada en el perfil de Jira del usuario que
registra las horas, no con la del servidor donde corre el script — un
desfase aquí hace que Jira guarde las horas en un día distinto al que dice
el Excel.

## Plantilla Excel

Columnas de entrada (leídas por `ExcelWorklogRepository.load`):

| Columna | Uso |
|---|---|
| `Ticket` | Código de issue Jira (p. ej. `PROJ-123`) |
| `Fecha` | Fecha/hora del worklog (`datetime` de Excel o texto `dd/mm/aaaa[ HH:MM[:SS]]`) |
| `Horas` | Tiempo trabajado (`time`/`datetime` de Excel o texto `HH:MM`) |
| `Comentario` | Comentario del worklog (opcional) |
| `Accion` | `Actualizar` para actualizar un worklog ya creado; vacío/cualquier otro valor = crear uno nuevo |

Columnas de salida, rastreadas y escritas de vuelta al mismo archivo tras
cada corrida (`ExcelWorklogRepository.save`, preservando el resto del
formato del Excel):

| Columna | Contenido |
|---|---|
| `Registrado` | `Sí (<fecha/hora>)`, `Sí (actualizado <fecha/hora>)`, o `Error: ...` |
| `Accion` | Se conserva tal cual (no se limpia después de crear) |
| `WorklogID` | Id que devuelve Jira al crear el worklog — necesario para poder actualizarlo después |

### Crear vs. actualizar

- **Crear** (`Accion` vacío o distinto de `Actualizar`): se salta la fila
  si `Registrado` ya empieza con "Sí" (evita duplicar worklogs si se
  vuelve a correr el script sobre el mismo Excel).
- **Actualizar** (`Accion = Actualizar`): reemplaza `started`/`timeSpent`/
  `comment` del worklog existente vía `PUT`. Requiere que la fila tenga un
  `WorklogID` guardado (el que quedó al crearlo la primera vez); si falta,
  se reporta error sin llamar a Jira. A diferencia de crear, **no** se
  salta aunque `Registrado` ya diga "Sí" — así se puede reintentar o
  corregir una fila ya registrada.

## Uso

```
python main.py                    # usa worklog.xlsx en la raíz del proyecto
python main.py ruta\otra_plantilla.xlsx   # usa otra plantilla
```

Al terminar imprime, por fila no salteada, el resultado (`OK`/error), y al
final un resumen: `Registrados: N | Errores: N | Ya registrados (saltados): N`.

```
pip install -r requirements.txt
```
