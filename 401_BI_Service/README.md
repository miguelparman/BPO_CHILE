# 401_BI_Service — Actualizaciones de datasets de Power BI Service

Trae el **historial de actualizaciones (refresh)** de todos los datasets (modelos semánticos) de Power BI Service, usando la API REST con el App Registration de `Repositorio.bi@fractaliasystems.es` (client credentials, sin usuario interactivo).

## Flujo

```
0. Validar conexiones: token + API Power BI, carpeta de salida
   └─ si alguna falla: reintento cada 5 min (máx. 3); si sigue fallando → FIN (exit 1)
1. GET /groups                                   workspaces donde la app es miembro
2. Por workspace: GET datasets + GET reports
3. Por dataset actualizable: GET refreshes?$top=PBI_TOP_ACTUALIZACIONES + GET refreshSchedule
4. salida/historico_actualizaciones.csv          acumula sin duplicar (DATASET_ID + REQUEST_ID + REFRESH_ID)
   salida/BI_Service_Actualizaciones.xlsx        foto de la corrida
```

Un 403/404 en un workspace o dataset **no corta la corrida**: queda en la hoja `Errores` y en el log.

## Salida (`salida/BI_Service_Actualizaciones.xlsx`)

Todas las horas están en `ZONA_HORARIA` (America/Lima). Las programaciones de Power BI vienen cada una en su zona (en BPO_TCH hay `SA Pacific`, `UTC` y `Pacific SA`) y se convierten todas a esa zona para poder compararlas. El análisis usa los últimos `DIAS_ANALISIS` días (60).

| Hoja | Contenido |
|---|---|
| Programacion | Informe, dataset, hora y días programados, y para **ese horario**: duración mediana / p90 / máx, retraso de inicio, fin estimado, ejecuciones y % de fallos |
| Mapa_cruces | Bloques de 15 min × día: cuántos datasets se actualizan a la vez (inicio + retraso mediano, duración p90) |
| Cruces | Bloques con 2+ datasets a la vez y cuáles son |
| Concurrencia_hora | Según el historial real: por hora de inicio, ejecuciones, fallos y cuántas otras actualizaciones corrían en paralelo |
| Fallos | Cada actualización fallida, su error y con qué otras se cruzó |
| Datasets | Un registro por dataset: último estado, inicio/fin, duración, último error, última actualización OK, nº de informes |
| Actualizaciones | Histórico completo (igual al CSV): tipo, estado, inicio/fin UTC y local, duración (min), intentos, código y detalle de error |
| Informes | Informes por workspace y el dataset que usan |
| Workspaces | Workspaces visibles, nº de datasets e informes |
| Errores | Workspaces/datasets a los que la app no pudo acceder |

`ESTADO`: `Completed`, `Failed`, `Disabled`, `Cancelled` o `Unknown` (en curso; se actualiza en la siguiente corrida).
Power BI conserva un historial limitado por dataset: el CSV histórico guarda lo que la API ya no devuelve.

## Requisitos en Power BI / Entra ID

1. **Portal de administración → Configuración del inquilino → Configuración para desarrolladores**: habilitar *"Las entidades de servicio pueden usar las API de Fabric"* (para todo el tenant o para un grupo de seguridad que contenga la app).
2. Agregar la app como **Miembro** (o Administrador/Colaborador) en **cada workspace** a leer. La app no ve *Mi área de trabajo*.
3. El App Registration **no** necesita permisos de API de Power BI en Entra: con client credentials el acceso lo dan los roles en cada workspace.

Si la corrida termina con `Workspaces=0`, falta el punto 1 o el 2.

## Estructura (src layout)

```
main.py                    composition root / CLI
src/bi_service/
  pipeline.py              orquestador
  conexiones.py            validación previa con reintentos
  powerbi/auth.py          token client credentials (scope Power BI)
  powerbi/client.py        API REST (renovación de token, reintentos 429/5xx, paginado)
  extractor.py             workspaces → datasets / informes → refreshes
  transformer.py           tablas del Excel (fechas UTC/local, errores de servicio, programación)
  zonas.py                 zonas de Windows de las programaciones -> ZONA_HORARIA
  analisis.py              duración por horario, mapa de cruces, concurrencia real, fallos
  salida.py                CSV histórico + Excel (escritura atómica)
  config.py, logging_setup.py, exceptions.py
tests/unit/                pruebas por componente (sin red)
```

## Instalación y configuración

```
pip install -r requirements-dev.txt
copy .env.example .env    # completar PBI_TENANT_ID / PBI_CLIENT_ID / PBI_CLIENT_SECRET
```

## Uso

```
python main.py                            # workspaces de PBI_WORKSPACES (.env; hoy BPO_TCH), vacio = todos
python main.py --workspace "Chile"        # ese workspace en vez de PBI_WORKSPACES, por nombre o id (repetible)
python main.py --solo-leer                # consulta la API y muestra el resumen; no escribe archivos
python main.py --sin-validar-conexiones   # emergencia
scripts\ejecutar_bi_service.cmd           # para el Programador de tareas
```

Cada corrida deja su log en `logs/bi_service_YYYYMMDD_HHMMSS.log`. Si el Excel está abierto al momento de escribir, la corrida falla con un mensaje claro y no deja archivos a medias.

## Pruebas

```
python -m pytest
```
