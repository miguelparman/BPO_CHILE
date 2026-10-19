# 16_Gerencia — Volumetría Gerencia (Chile)

Migración a Python del paquete SSIS `CL_Proc_Volumetria_Gerencia.dtsx`. Recarga completa de 4 tablas de `[CL_MOVIL].[dbo]` a partir de 4 Excel de casos especializados:

| Flujo | Excel (`Hoja1`) | Tabla |
|---|---|---|
| GERENCIA | `ALTA GERENCIA TCH/ALTA GERENCIA_NVO ARCHIVO.xlsx` | `TBL_VOLUMETRIA_GERENCIA` |
| ESCALAMIENTO | `ALTA GERENCIA TCH/Escalamiento.xlsx` | `TBL_VOLUMETRIA_ESCALAMIENTO` |
| CLOSE THE LOOP | `CLOSE THE LOOP/CASOS SALESFORCE - CLOSE THE LOOP.xlsx` | `TBL_VOLUMETRIA_CLOSE_THE_LOOP` |
| T-ATIENDO | `T-ATIENDO/CASOS SALESFORCE - T-ATIENDO.xlsx` | `TBL_VOLUMETRIA_T_ATIENDO` |

## Flujo

```
0. Validar conexiones: SQL Server, SharePoint BPO, SharePoint ReportingFractalia
   └─ si alguna falla: reintento cada 5 min (máx. 3); si sigue fallando → FIN (exit 1)
1. Copiar los 4 Excel
   de:  BPO / Documentos compartidos / Planificación y Control/Insumos/Chile/Especializados/<subcarpeta>
   a:   ReportingFractalia / Data Reporting / REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/02 ESPECIALIZADOS/<subcarpeta>
2. Por flujo: extraer (Reporting) → validar → transformar → TRUNCATE + INSERT + DELETE IS NULL (1 transacción)
3. Resumen; exit 1 si falló alguna copia o algún flujo
```

## Estructura (src layout)

```
main.py                         composition root / CLI
src/gerencia/
  pipeline.py                   orquestador
  conexiones.py                 validación previa con reintentos
  ingesta/copiar.py             copia BPO → ReportingFractalia (Graph, tenants distintos)
  extraccion/extractor.py       Excel Source (emula tipos de ACE)
  validacion/validator.py       puntos FailComponent de la Conversión de datos
  transformacion/transformer.py Conversión de datos
  carga/loader.py               TRUNCATE → INSERT → DELETE
  mappings.py                   especificación de los 4 flujos (constantes del .dtsx)
  db.py, sharepoint/            adaptadores pyodbc / Microsoft Graph
  config.py, logging_setup.py, exceptions.py
tests/unit/                     pruebas por componente (sin red ni BD)
tests/equivalencia/             verifica mappings.py contra el .dtsx original
tools/equivalencia.py           foto / simulación / comparación SSIS vs Python
docs/EQUIVALENCIA.md            matriz SSIS ↔ Python y diferencias deliberadas
evidencias/                     fotos de las tablas y reportes de la corrida real
```

Los 4 flujos usan **los mismos componentes**; lo que cambia entre ellos está declarado como datos en `mappings.py`.

## Instalación y configuración

```
pip install -r requirements-dev.txt
copy .env.example .env    # completar credenciales (no se versiona)
```

## Uso

```
python main.py                           # corrida normal
python main.py --flujo GERENCIA          # solo un flujo (repetible)
python main.py --solo-copia              # solo copia BPO → ReportingFractalia
python main.py --sin-copia               # carga desde ReportingFractalia sin copiar
python main.py --solo-validar            # copia, lee, valida y transforma; no escribe en SQL
python main.py --archivo-dir "D:\...\BPO - Insumos\Chile\Especializados"   # contingencia sin SharePoint
python main.py --sin-validar-conexiones  # emergencia
scripts\ejecutar_gerencia.cmd            # para el Programador de tareas
```

Cada corrida deja su log en `logs/gerencia_YYYYMMDD_HHMMSS.log`.

## Pruebas y equivalencia

```
python -m pytest                                   # unitarias + equivalencia estructural con el .dtsx
python -m tools.equivalencia foto ssis             # foto de las tablas (antes de cargar con Python)
python -m tools.equivalencia simular sim --archivo-dir "<carpeta>"   # resultado esperado sin escribir
python -m tools.equivalencia foto python           # foto después de la carga Python
python -m tools.equivalencia comparar ssis python  # reporte en evidencias/
```

Resultado del 2026-10-19: las 4 tablas son **idénticas fila a fila** entre SSIS y Python (`evidencias/reporte_ssis_vs_python.md`).
