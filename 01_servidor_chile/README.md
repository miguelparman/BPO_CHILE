# 01_servidor_chile

Extrae tablas de `[Externos_Frac]` desde el servidor SQL Server del dominio remoto
(`sqlclu01lis01.tchile.local`) y las sube como CSV a SharePoint (via Microsoft Graph).

## Que hace `main.py`

1. Se conecta al SQL Server con credenciales de dominio (`sql_domain_auth.py`),
   impersonando un usuario `TCHILE\...` sin necesidad de `runas /netonly`.
2. Se autentica contra Microsoft Graph con credenciales de aplicacion (client
   credentials) para obtener acceso al site de SharePoint.
3. Para cada tabla listada en `tables_config.py`:
   - Si tiene `date_field`, detecta los ultimos `periods` meses con datos
     (2 por defecto) y descarga solo esas filas.
   - Si `date_field` esta vacio, descarga la tabla completa (ej. `base_saip`).
   - Escribe el resultado en `exports/<TABLA>.csv` (`;` como separador,
     `utf-8-sig`) y lo sube a la carpeta de SharePoint configurada.
4. Imprime un resumen final por tabla: estado, filas y duracion.

## Configuracion de tablas (`tables_config.py`)

Cada entrada define:

- `table`: nombre completo y calificado, entre corchetes.
- `date_field`: campo (entre corchetes) usado para determinar el mes.
  Vacio (`""`) para descargar la tabla completa sin filtrar.
- `is_datetime` (opcional, default `False`): marcar `True` cuando
  `date_field` es un `datetime` completo (con hora), no un codigo `YYYYMM`.
  En ese caso se agrupa por mes con `FORMAT(campo, 'yyyyMM')` antes de tomar
  los ultimos periodos; si no se marca, el filtro compara timestamps
  exactos y puede traer casi ninguna fila (ver caso `CALLBACK.[FECHA]`).
- `periods` (opcional, default `2`): cantidad de periodos (meses) distintos
  mas recientes a descargar. Debe ser un entero >= 1; si no lo es, la tabla
  queda en `ERROR` en el resumen. No aplica si `date_field` esta vacio. Si la
  tabla tiene menos periodos que los pedidos, descarga los que haya.

## Variables de entorno (`.env`)

Ver `.env.example` para la lista completa:

- `SQL_SERVER`, `SQL_DATABASE`, `SQL_DOMAIN`, `SQL_USER`, `SQL_PASSWORD`,
  `SQL_DRIVER`: conexion al SQL Server.
- `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`, `GRAPH_TIMEOUT`: app registrada
  en Microsoft Entra ID para llamar a Graph.
- `SHAREPOINT_HOSTNAME`, `SHAREPOINT_SITE_PATH`, `SHAREPOINT_DRIVE_NAME`,
  `SHAREPOINT_FOLDER_PATH`: destino en SharePoint donde se suben los CSV.

## Uso

```bash
pip install -r requirements.txt
python main.py
```

## Otros scripts

- `listar_bpo_horarios.py`: utilidad de diagnostico que lista el contenido de
  una carpeta del site `BPO` en SharePoint via Graph, usando el mismo
  tenant/app de este proyecto.

## Estructura

```
main.py                Orquesta la extraccion SQL -> CSV -> SharePoint
tables_config.py        Lista de tablas a extraer y su campo de fecha
sql_domain_auth.py       Conexion pyodbc con impersonacion de dominio
sharepoint/
  auth.py                Obtiene token de Microsoft Graph (client credentials)
  client.py              Resuelve site/drive/folder y lista contenido
  uploader.py            Sube archivos a una carpeta de SharePoint
exports/                 CSV generados (no versionados)
```
