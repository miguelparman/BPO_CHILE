# 15_Logueo

Migración a Python del paquete SSIS `Cl_Proc_Logueo.dtsx`. El proceso:

1. lee el logueo de agentes de Chile (`REPORTE_AGENTES_FRACTALIA_SEM.csv`, que publica `203_bot_portal_comercial`) desde **SharePoint**, mediante Microsoft Graph;
2. carga en `[CL_LOGUEO].[dbo].[TBL_CONEXIONES]` solo las filas nuevas;
3. completa el DNI;
4. ejecuta `SP_LOGUEO`.

```
Log Inicio -> CARGA TABLA -> AGREGA DNI -> Log Fin -> SP        (BK: deshabilitada en el .dtsx)
```

## Estructura (src layout, modular por componentes)

```
main.py                         composition root (CLI)
src/logueo/
  pipeline.py                   orquestador: Control Flow del .dtsx
  extraccion/extractor.py       Flat File Source (SharePoint / archivo local)
  validacion/validator.py       puntos FailComponent del Data Flow + controles previos
  transformacion/transformer.py Derived Columns 'Dia_mes', 'FechaAnsi' + Data Conversion
  transformacion/lookup.py      Lookup 'Búsqueda' (Full Cache, no coincidentes)
  carga/loader.py               LOGS_PROCESOS, INSERT, AGREGA DNI, SP_LOGUEO
  periodo.py                    variable User::Periodo
  mappings.py, sql.py           constantes del .dtsx y T-SQL literal (scripts_sql/)
  db.py, sharepoint/            adaptadores pyodbc y Microsoft Graph (reutilizados de 14_EPA_WSP)
  config.py, logging_setup.py   .env y logging
tests/unit/                     pruebas por componente (con fakes)
tests/equivalencia/             equivalencia estructural contra el .dtsx original
tools/equivalencia.py           equivalencia de datos SSIS vs Python (solo lectura)
docs/EQUIVALENCIA.md            mapeo tarea a tarea, diferencias deliberadas, evidencias
docs/referencia_sp/SP_LOGUEO.sql
```

## Instalación

```
pip install -r requirements-dev.txt
copy .env.example .env      # completar credenciales (nunca en el código)
```

## Uso

```
python main.py                        # corrida normal
python main.py --periodo 202609       # fuerza User::Periodo (prioridad sobre PERIODO del .env)
python main.py --solo-validar         # extrae, valida, transforma y cruza con TBL_CONEXIONES; no escribe
python main.py --archivo-local RUTA   # contingencia: CSV desde disco
python tools/equivalencia.py          # compara con lo cargado por SSIS y simula la inserción en #SIM
python -m pytest                      # pruebas unitarias y de equivalencia estructural
```

### Variable `Periodo`

La usa solo la tarea `AGREGA DNI`. Su valor se toma de la primera fuente disponible:

1. `--periodo` en la línea de comandos;
2. `PERIODO=` en el `.env`;
3. la regla del .dtsx: si el día es ≤ 4 se toma el mes anterior; si no, el mes actual.

## Estado

El 2026-10-01 se validó con datos reales:

- 25.763 de 25.763 filas idénticas a lo que cargó SSIS;
- la ejecución real terminó con todos los pasos en OK.

El detalle está en [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md).
