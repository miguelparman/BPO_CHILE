# 19_places — Carga Places (Chile)

Migración a Python del paquete SSIS `CL_Proc_Carga_Places.dtsx`. Recarga completa de `[CL_DATA].[dbo].[TBL_PLACES]` desde el Excel `Place utilizados.xlsx` (hoja `Hoja1`), la completa con datos de `[BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO]` y guarda la foto del día en `[TBL_HISTORICO_PLACES]`.

El Excel estaba en una ruta física (`D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO\`). Ahora se lee por Microsoft Graph desde `ReportingFractalia / Data Reporting / REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/05 CARTERA/Place utilizados.xlsx`.

## Flujo

```
0. Validar conexiones: SQL Server (172.17.0.162) y Microsoft Graph (existe el Excel)
   └─ si alguna falla: reintento cada 5 min (máx. 3); si sigue fallando → FIN (exit 1), sin tocar nada
1. Log Inicio            INSERT en BBDD_GENERAL.dbo.LOGS_PROCESOS (Estado 'exec...')
2. CARGA PLACES          leer Excel → validar → convertir → TRUNCATE + INSERT + LIMPIA TABLA (1 transacción)
3. CARGA PLACES HISTORICO  DELETE [Fecha Impacto] = hoy + INSERT desde TBL_PLACES (1 transacción)
4. Log Fin               UPDATE LOGS_PROCESOS → 'OK'
```

Si una etapa falla, las siguientes no corren y no hay Log Fin (la fila queda en `exec...`), igual que en SSIS.

## Estructura (src layout)

```
main.py                         composition root / CLI / título de consola
src/places/
  pipeline.py                   orquestador
  conexiones.py                 validación previa con reintentos
  extraccion/extractor.py       Excel Source (emula tipos de ACE; DT_WSTR(255))
  validacion/validator.py       puntos FailComponent de la Conversión de datos
  transformacion/transformer.py Conversión de datos (DT_STR cp1252)
  carga/loader.py               TRUNCA TABLA → CARGA TABLA → LIMPIA TABLA
  carga/historico.py            CARGA PLACES HISTORICO
  logs_proceso.py               Log Inicio / Log Fin
  mappings.py                   constantes del .dtsx (columnas, anchos, T-SQL literal)
  db.py, sharepoint/            adaptadores pyodbc / Microsoft Graph
  config.py, logging_setup.py, exceptions.py
tests/unit/                     pruebas por componente (sin red ni BD)
tests/equivalencia/             verifica mappings.py contra el .dtsx original
tools/equivalencia.py           foto / simulación / comparación SSIS vs Python
docs/EQUIVALENCIA.md            matriz SSIS ↔ Python y diferencias deliberadas
evidencias/                     fotos de las tablas y reportes
```

## Instalación y configuración

```
pip install -r requirements-dev.txt
copy .env.example .env    # completar credenciales (no se versiona)
```

Variables: `TENANT_ID/CLIENT_ID/CLIENT_SECRET` (Graph, ReportingFractalia), `DB_SERVER/DB_NAME/DB_USER/DB_PASSWORD` (SQL Server). Ver `.env.example`. Ninguna credencial está en el código.

## Uso

```
python main.py                           # corrida normal
python main.py --solo-validar            # lee, valida y convierte; no escribe en SQL
python main.py --archivo "D:\...\Place utilizados.xlsx"   # contingencia sin SharePoint
python main.py --sin-validar-conexiones  # emergencia
scripts\ejecutar_places.cmd              # para el Programador de tareas
```

Cada corrida deja su log en `logs/places_YYYYMMDD_HHMMSS.log`. La consola y la ventana muestran el nombre del proyecto (`19_places`).

## Pruebas y equivalencia

```
python -m pytest                                          # unitarias + equivalencia estructural con el .dtsx
python -m tools.equivalencia foto ssis                    # foto de las tablas (antes de cargar con Python)
python -m tools.equivalencia simular python_simulado      # resultado esperado sin escribir en SQL
python -m tools.equivalencia comparar ssis python_simulado --columnas base
python -m tools.equivalencia foto python                  # foto después de la carga Python
python -m tools.equivalencia comparar ssis python         # reporte en evidencias/
```

Resultado del 2026-10-29: `TBL_PLACES` (203 filas) y `TBL_HISTORICO_PLACES` (286 282 filas) **idénticas fila a fila** entre SSIS y Python (`evidencias/reporte_ssis_vs_python.md`).
