# 14_EPA_WSP

Migración a Python del paquete SSIS **`CL_Proc_EPA_WSP.dtsx`**: carga diaria de las encuestas de calidad de Chile y su proceso en `CL_CALIDAD`. Cubre tres fuentes:

- **EPA/ISN**, desde `ENCUESTA`, hacia `TBL_ENCUESTAS_CHILE`.
- **WhatsApp Medallia**, desde `WS_MEDALLIA_2`, hacia `TBL_ENCUESTAS_WSP_MEDALLIA`.
- **Portal Medallia**, desde el export CSV, hacia `TBL_ENCUESTAS_MEDALLIA`.

El paquete no tiene Data Flow: orquesta 5 scripts `.py` de `102_calidad/` y 2 procedimientos almacenados. Los 5 scripts se migraron a este proyecto.

**Cambio de origen:** `[Externos_Frac]` (`sqlclu01lis01.tchile.local`) se reemplaza por los CSV `ENCUESTA.csv` y `WS_MEDALLIA_2.csv` de SharePoint (`…/BPOCHIPE/13 SERVIDOR CHILE`), que se leen vía Microsoft Graph. Los publica `01_servidor_chile`, que debe correr antes. Medallia sigue saliendo del portal web.

**Archivos que genera el proceso:** `Encuestas_Medallia.csv` (export del portal) y `resultado.txt` (alerta para Power Automate) se guardan vía Graph en SharePoint, en [`Data Reporting/REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA`](https://fractaliagroup.sharepoint.com/sites/ReportingFractalia/Data%20Reporting/REPOSITORIOS%20DE%20CRUDOS/CHILE/BPOCHIPE/16%20MEDALLIA). Antes estaban en carpetas locales: `…\Data Analytics Reporting Fractalia - Medallia` y `…\Gestión Indicadores MDS - Cl_encuesta`, esta última sincronizada con el OneDrive de `gestionindicadoresmds`. **El flujo de Power Automate que vigila `resultado.txt` debe apuntar a la nueva ubicación.**

## Flujo (en serie: cada paso espera al anterior)

```
1 Log_Inicio ─► 2 alerta ─► 3 WSP ─► 4 EPA_ISN ─► 5 SP_EPA_ISN_CHILE ─► [6 Carga Azure: deshabilitada]
            ─► 7 MEDALIA (descarga ─► carga ─► SP_PROCESO_ENCUESTAS_MEDALLIA) ─► 8 Log_Fin
```

| Tarea SSIS | Qué hace | Dónde |
|---|---|---|
| Log_Inicio / Log_Fin | `LOGS_PROCESOS` (`Update_Chile_Calidad_Epa`) | `carga/loader.py` + `scripts_sql/00_*.sql`, `99_*.sql` |
| `enviar_alerta_encuesta.py` | MAX(`fecha_de_evento`+`hora_evento`) ≥ 17:00 del día hábil anterior. Escribe `resultado.txt` en `16 MEDALLIA`: lo borra, espera 30 s y lo recrea | `alerta.py` |
| WSP: TRUNCATE + `Traslado_…_EPA_WSP_MEDALLIA.py` | `WS_MEDALLIA_2.csv` → `clean_row` → `TBL_ENCUESTAS_WSP_MEDALLIA` | `extraccion/` → `transformacion/` → `carga/` |
| EPA_ISN: TRUNCATE + `Traslado_…_EPA_ISN.py` | `ENCUESTA.csv` (`periodo_evento >= 202601`) → `TBL_ENCUESTAS_CHILE` | ídem |
| SP_EPA_ISN_CHILE | `EXEC SP.EPA_ISN_CHILE`, literal | `scripts_sql/30_*.sql` |
| Carga Azure | `Disabled=True` en el .dtsx, y su script no existe | No se migra |
| `CL_Descarga_encuestas_Medallia.py` | Playwright/Firefox (antes Selenium): login, export CSV y `Encuestas_Medallia.csv` en `16 MEDALLIA` | `extraccion/medallia_descarga.py` |
| `CL_Carga_de_encuestas_MEDALLIA.py` | Lee el CSV desde `16 MEDALLIA`; TRUNCATE + INSERT; omite las filas que fallan | `transformacion/` + `carga/loader.py` |
| SP_PROCESO_ENCUESTAS_MEDALLIA | `EXEC`, literal | `scripts_sql/40_*.sql` |

### Cambio acordado (decisión (a) del plan): ventana por periodo en lugar de TRUNCATE

Los CSV de SharePoint solo traen los **2 últimos meses** de cada tabla. El original copiaba `ENCUESTA` desde 202601 y `WS_MEDALLIA_2` completa. Además, `SP.EPA_ISN_CHILE` usa la historia: por ejemplo, reconstruye `TBL_CALIDAD_RETENCIONES` con `PERIODO_ENCUESTA >= 202401`.

Por eso, cada traslado hace lo siguiente en **una sola transacción**:

1. `DELETE` de los periodos presentes en el CSV.
2. `INSERT` de las filas del CSV.
3. En EPA_ISN, además, `DELETE` de los periodos anteriores a `PERIODO_DESDE_ENCUESTA`.

El resto del histórico se conserva tal cual. Si algo falla, la tabla queda como estaba. Antes, el TRUNCATE la dejaba vacía y el SP corría igual.

### Manejo de fallos (igual que el .dtsx)

- **Execute Process** (alerta, traslados y Medallia) tienen `FailTaskIfReturnCodeIsNotSuccessValue=False` en SSIS. Aquí se registra el error y el proceso continúa.
- **Execute SQL**: si falla `Log_Inicio`, no corre nada más. Si falla un SP, no se ejecuta `Log_Fin` y el log queda en `exec...`, pero la rama Medallia corre igual.
- `--estricto` detiene el proceso en el primer fallo.
- El código de salida es 1 si cualquier paso falló, aunque sea tolerante.

## Estructura (src layout)

```
14_EPA_WSP/
├── main.py                          composition root + CLI
├── src/epa_wsp/
│   ├── pipeline.py                  orquestador (orden y política de fallos del Control Flow)
│   ├── extraccion/extractor.py      CSV de SharePoint (13 SERVIDOR CHILE y 16 MEDALLIA)
│   ├── extraccion/medallia_descarga.py  portal Medallia (Playwright)
│   ├── validacion/validator.py      esquema real vs mappings; anchos; periodos
│   ├── transformacion/transformer.py    tipos, clean_row, reglas de Medallia
│   ├── carga/loader.py              LOGS_PROCESOS, ventana por periodo, Medallia, SPs
│   ├── alerta.py                    enviar_alerta_encuesta.py
│   ├── mappings.py                  las 3 tablas: columnas, tipos y reglas
│   ├── sql.py + scripts_sql/        T-SQL literal del .dtsx
│   ├── db.py, sharepoint/           adaptadores reutilizados de 12_trafico (+ subida/borrado y carpeta.py)
│   └── config.py, models.py, exceptions.py, logging_setup.py
├── tests/unit/                      pruebas con dobles (sin base ni SharePoint)
├── tests/equivalencia/              pruebas contra el .dtsx y los scripts de 102_calidad
├── tools/oraculos.py                copias literales de la lógica original (oráculos)
├── tools/equivalencia.py            simulación, oráculo Medallia y fotos SSIS vs Python
└── docs/EQUIVALENCIA.md, docs/referencia_sp/
```

**Reutilización:** `db.py` y `sharepoint/` vienen de `12_trafico`. Los 3 traslados comparten la misma validación de esquema, anchos y periodos, y la misma carga por ventana. Cada traslado es una entrada `Traslado` en `mappings.py`.

## Instalación y uso

```bash
pip install -r requirements-dev.txt
python -m playwright install firefox  # una sola vez: navegador de Playwright para Medallia
cp .env.example .env                  # completar credenciales (NUNCA versionar .env)

python main.py --solo-validar         # lee SharePoint y valida; no escribe nada ni descarga Medallia
python main.py                        # corrida normal
python main.py --estricto             # se detiene en el primer fallo
python -m pytest                      # 103 pruebas
```

Los logs quedan en `logs/epa_wsp_YYYYMMDD_HHMMSS.log`.

## Configuración (`.env`)

Ver [.env.example](.env.example). **No hay credenciales en el código.**

- Las passwords del .dtsx estaban cifradas con DPAPI y no se pueden reutilizar.
- Los scripts de `102_calidad/` tenían en texto plano la password SQL de `palermo.reyes` y la cuenta del portal Medallia. **Recomendación: rotar ambas.**

Variables propias de este proceso:

- `PERIODO_DESDE_ENCUESTA` (202601)
- `SHAREPOINT_FOLDER_MEDALLIA` (`REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/16 MEDALLIA`)
- `ALERTA_ARCHIVO` (`resultado.txt`)
- `MEDALLIA_USER` / `MEDALLIA_PASSWORD`
- `MEDALLIA_ARCHIVO` (`Encuestas_Medallia.csv`)
- `MEDALLIA_NAVEGADOR` (firefox, chromium o webkit)
- `MEDALLIA_SEGUNDOS_ESPERA_DESCARGA`

## Equivalencia con SSIS

Ver [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md). Corrida real del 2026-09-29, 11:22, que terminó OK en 2 min 12 s:

- Las **76.871 + 3.211** filas que SSIS dejó en las 2 temporales se reproducen **idénticas**, sin ninguna columna distinta. La historia fuera de la ventana queda intacta y la ventana solo suma las 500 + 2 encuestas nuevas del origen.
- **Medallia:** 50/50 filas idénticas al oráculo literal de `CL_Carga_de_encuestas_MEDALLIA.py`.
- Los 2 SP y sus 5 logs internos terminan en `OK`.
- Corrida del 2026-09-29 12:15, ya guardando en SharePoint: exit 0. `Encuestas_Medallia.csv` (94.610 bytes) y `resultado.txt` (con BOM, texto idéntico) quedaron en `16 MEDALLIA`. La secuencia borrar → esperar 30 s → recrear se verificó en real, y el oráculo de Medallia leído desde SharePoint sale 50/50.
