# 13_fcr

Migración a Python del paquete SSIS **`CL_Proc_Trafico_FCR_02.dtsx`**: cálculo del **FCR** (First Contact Resolution) de Chile en `CL_TRAFICO.dbo.TBL_FCR`.

Para cada atención de **llamadas** (TRIADAS, CARTERIZADOS, USUARIOS) y de **WhatsApp** (TRIADAS, CARTERIZADOS), el proceso busca la siguiente atención del mismo ANI y servicio. Luego marca con 14 indicadores si el cliente volvió a contactar dentro de 30 min, 1 h, 2 h … 7 días o 15 días, y asigna el `TRAMO_QUIEBRE`.

**Orden de ejecución:** después de `12_trafico` (`CL_Proc_Trafico_01`), que carga `TBL_LLAMADAS_ATENDIDAS_INBOUND` y `TBL_CHAT`.

## Flujo

```
Log Inicio ─► Proceso Carga Tabla (Limpia Tabla ─► Alimenta Tabla) ─► Log Fin
```

| Tarea SSIS | Qué hace | Dónde |
|---|---|---|
| Log Inicio | `INSERT` en `BBDD_GENERAL.dbo.LOGS_PROCESOS` (`Chile_FCR`, `exec...`) | `carga/loader.py` + `scripts_sql/00_log_inicio.sql` |
| Alimenta Tabla (lectura) | 5 `SELECT` de origen desde el periodo | `extraccion/extractor.py` |
| Alimenta Tabla (lógica) | `LEAD` por ANI+SERVICIO, 14 `FCR_x`, `TRAMO_QUIEBRE`, `UNION ALL` | `transformacion/transformer.py` |
| — | Esquema de destino y origen, datos, anchos | `validacion/validator.py` |
| Limpia Tabla + INSERT | `DELETE ... >= periodo` e `INSERT` en **una transacción** | `carga/loader.py` + `scripts_sql/10_limpia_tabla.sql` |
| Log Fin | `UPDATE LOGS_PROCESOS` → `OK` | `carga/loader.py` + `scripts_sql/99_log_fin.sql` |

El paquete no ejecuta scripts `.py` (no tiene Execute Process) ni Data Flow: todo son Execute SQL Task.

## Estructura (src layout)

```
13_fcr/
├── main.py                     composition root + CLI
├── src/fcr/
│   ├── pipeline.py             orquestador (orden del Control Flow)
│   ├── extraccion/extractor.py SELECT de las 5 bases
│   ├── validacion/validator.py esquema real vs mappings; datos; anchos
│   ├── transformacion/transformer.py  LEAD + FCR + TRAMO_QUIEBRE (pandas)
│   ├── carga/loader.py         LOGS_PROCESOS, DELETE + INSERT transaccional
│   ├── mappings.py             5 bases, 14 umbrales, esquema de TBL_FCR (orden posicional)
│   ├── sql.py + scripts_sql/   T-SQL LITERAL de las 4 Execute SQL Task (+ oráculo)
│   ├── db.py                   pyodbc (reutilizado de 12_trafico: lotes GO, transacciones, reconexión)
│   └── config.py, models.py, exceptions.py, logging_setup.py
├── tests/unit/                 pruebas con dobles (sin base)
├── tests/equivalencia/         pruebas contra el .dtsx original
├── tools/equivalencia.py       oráculo SQL vs Python y fotos antes/después sobre datos reales
└── docs/EQUIVALENCIA.md        matriz de equivalencia, detalles de SQL Server y evidencias
```

**Reutilización:** el T-SQL original repite 5 veces el mismo bloque, con más de 20 líneas por bloque. En Python cada bloque es una entrada de `mappings.BASES` y las 5 pasan por la misma función `transformer.calcular_fcr`. Agregar una base (por ejemplo, WhatsApp USUARIOS) es añadir una línea a `mappings.py`.

## Instalación y uso

```bash
pip install -r requirements-dev.txt
cp .env.example .env            # completar credenciales (NUNCA versionar .env)

python main.py --solo-validar   # extrae, transforma y valida; no escribe nada
python main.py                  # corrida normal (periodo automático)
python main.py --periodo 202608 # recalcula desde ese mes
python -m pytest                # 87 pruebas
```

Los logs se escriben en `logs/fcr_YYYYMMDD_HHMMSS.log`. El código de salida es 0 si todo sale bien y 1 si hay un error.

## Configuración (`.env`)

Ver [.env.example](.env.example): servidor, usuario y contraseña de SQL Server, `PERIODO`, `DIA_CIERRE_MES` y `BATCH_SIZE`. **No hay credenciales en el código.** La contraseña del `.dtsx` estaba cifrada con DPAPI y no se puede reutilizar.

**Periodo** (`User::Periodo`, Int32). En el `.dtsx` era la constante `202608`, que se editaba a mano. Ahora usa el mismo criterio que `12_trafico`:

| Variable | Valor | Efecto |
|---|---|---|
| `PERIODO` | vacío (operación diaria) | Automático: si hoy es día ≤ `DIA_CIERRE_MES`, desde el mes anterior; si no, desde el mes actual |
| `PERIODO` | `YYYYMM` | Recalcula desde ese mes (filtro de origen y `DELETE`) |
| `DIA_CIERRE_MES` | `4` | Último día del mes en que se sigue recalculando el mes anterior |

Prioridad: `--periodo`, luego `PERIODO` del `.env` y, si no hay ninguno, el cálculo automático.

## Equivalencia con SSIS

Ver [docs/EQUIVALENCIA.md](docs/EQUIVALENCIA.md). En resumen, sobre datos reales:

- Contra el T-SQL original, ejecutado como oráculo: **idéntico fila a fila** desde 202608 (43.622 filas) y desde 202609 (20.491 filas).
- Contra lo que SSIS dejó en `TBL_FCR`: **idéntico** (43.622 filas).
