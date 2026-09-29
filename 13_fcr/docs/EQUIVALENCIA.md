# Equivalencia SSIS ↔ Python: `CL_Proc_Trafico_FCR_02.dtsx`

## 1. Matriz de tareas

| Tarea del .dtsx (refId) | Tipo | Python | Cómo se verifica |
|---|---|---|---|
| `Package\Log Inicio` | Execute SQL | `loader.registrar_inicio` → `scripts_sql/00_log_inicio.sql` | T-SQL byte a byte (`test_tsql_identico_al_dtsx`) |
| `Package\Proceso Carga Tabla\Limpia Tabla` | Execute SQL, `? = User::Periodo` | `loader.cargar_fcr` → `scripts_sql/10_limpia_tabla.sql` | T-SQL byte a byte; parámetro único `User::Periodo` |
| `Package\Proceso Carga Tabla\Alimenta Tabla` | Execute SQL, `? = User::Periodo` | `extractor` → `validator` → `transformer` → `loader.bulk_insert` | Constantes extraídas del T-SQL (5 bases, filtro, LEAD, 14 umbrales, CASE del tramo, orden del UNION y de las columnas) y **oráculo** sobre datos reales |
| `Package\Log Fin` | Execute SQL | `loader.registrar_fin` → `scripts_sql/99_log_fin.sql` | T-SQL byte a byte |
| Precedence Constraints | On Success, en serie | `FcrPipeline.run` | `test_orden_del_control_flow` (dtsx) y `test_orden_del_control_flow` (pipeline) |
| `User::Periodo` | Int32 = `202608` (constante) | `models.resolver_periodo` | `test_user_periodo_es_int32_constante` y pruebas de periodo |

No hay Data Flow, Execute Process (scripts `.py`) ni tareas deshabilitadas (`test_todas_las_tareas_estan_migradas_y_no_hay_otros_componentes`).

## 2. Lógica de "Alimenta Tabla" y cómo se reproduce

| T-SQL original | Python (`transformer.py`) |
|---|---|
| 5 bloques `SELECT ... INTO #TBL_TMP_*` | `mappings.BASES` (5 entradas) y una sola función |
| `WHERE CONVERT(VARCHAR(6),[AGENT_START...],112)>=@PERIODO AND SERVICIO IN ('X')` | Mismo filtro, evaluado por SQL Server (`sql.extraccion_base`) |
| `CAST(AGENT_START AS DATE) FECHA` | `.date()` |
| `CAST(CAST(AGENT_START AS TIME) AS VARCHAR(8)) HORA` | `strftime('%H:%M:%S')`: trunca los decimales, no redondea |
| `CAST(AGENT_START AS DATETIME) [FECHA/HORA]` | Identidad: el validador exige que el origen sea `datetime` |
| `'LLAMADAS' / 'WHATSAPP' BASE` | `BaseFCR.base` |
| `LEAD([FECHA/HORA]) OVER (PARTITION BY ANI,SERVICIO ORDER BY [FECHA/HORA])` | `sort_values` estable + `groupby(...).shift(-1)` **por base** |
| `CASE WHEN DATEDIFF(SECOND, a, b) <= s THEN 0 ELSE 1 END` (×14) | `mappings.UMBRALES` + `diferencia_segundos` |
| `UNION ALL` en orden fijo | `pd.concat` en el orden de `BASES` |
| `CASE WHEN FCR_30min = 0 THEN 'Quiebre en 30 Min' ... ELSE 'Sin Quiebre'` | `np.select` en el orden de `UMBRALES` |
| `INSERT INTO TBL_FCR SELECT A.*, ...` (posicional) | `INSERT` con lista explícita de columnas en `mappings.COLUMNAS_DESTINO`. El validador exige que la tabla real tenga ese mismo orden |

### Detalles de SQL Server que se reproducen (con prueba unitaria)

1. **`DATEDIFF(SECOND)` cuenta cambios de segundo**, no tiempo transcurrido. Por ejemplo, de 10:00:00.900 a 10:30:00.100 da 1800 y el resultado es `FCR_30min = 0`. Se calcula como `floor(b) − floor(a)` al segundo.
2. **Si no hay próxima atención (NULL), todos los FCR valen 1**, porque `NULL <= s` es UNKNOWN y cae en la rama `ELSE`.
3. **El filtro de periodo se aplica antes del `LEAD`.** La ventana solo ve filas desde el periodo. Como `LEAD` mira hacia adelante, el mes de inicio no cambia el resultado de las filas posteriores.
4. **La ventana es por base.** La misma ANI en LLAMADAS y en WHATSAPP no se encadena, porque cada base es una tabla temporal distinta.
5. **`PARTITION BY` con collation `Modern_Spanish_CI_AS`:**
   - no distingue mayúsculas ni espacios al final;
   - todos los NULL van en una misma partición;
   - `NULL` y `''` son particiones **distintas**. Esto se detectó en la prueba de estrés desde 202501: una ANI `''` de 2025-03-20 y una ANI NULL de 2026-06-04 en `TBL_CHAT`. La primera versión los agrupaba juntos porque pandas cortaba la clave en el byte nulo del valor centinela. Se corrigió y tiene una prueba de regresión.
6. **Límites exactos de los 14 umbrales:** `s` segundos da 0 y `s+1` segundos da 1.

## 3. Evidencias sobre datos reales (2026-09-29)

Todas se generaron con `tools/equivalencia.py` en **solo lectura**. `evidencias/` está en `.gitignore` porque contiene números de teléfono.

### 3.1 Oráculo: T-SQL original vs Python, mismos datos de origen y misma sesión

`oraculo` ejecuta el literal de Alimenta Tabla sin tocar `TBL_FCR`. Solo cambia el destino del `INSERT`, que pasa a ser `#TBL_FCR_ORACULO`, creada con `SELECT TOP 0 * INTO` a partir de `TBL_FCR`, y se quitan los `DROP` de `##TBL_TMP_FCR`, una tabla global que el script nunca crea. Luego compara las 23 columnas fila a fila, como multiconjunto.

| Periodo | Filas SQL | Filas Python | Resultado |
|---|---:|---:|---|
| ≥ 202609 (automático hoy) | 20.491 | 20.491 | **IDÉNTICA** |
| ≥ 202608 (valor actual del .dtsx) | 43.622 | 43.622 | **IDÉNTICA** |
| ≥ 202501 (prueba de estrés, 21 meses) | 573.773 | 573.773 | **EQUIVALENTE**: 573.771 idénticas; 2 difieren solo por un empate (ver 3.3) |

Distribución de `TRAMO_QUIEBRE` para ≥ 202608: idéntica en los 15 tramos (ver `evidencias/reporte_oraculo_202608.md`).

### 3.2 Contra lo que SSIS escribió en TBL_FCR

Foto `ssis`: `TBL_FCR` con periodo ≥ 202608 tal como la dejó la última corrida de SSIS (2026-09-28 11:48). Se comparó con el resultado de Python para el mismo periodo:

| Filas SSIS | Filas Python | Resultado |
|---:|---:|---|
| 43.622 | 43.622 | **IDÉNTICA** |

### 3.3 Empates (no determinismo del original)

`ORDER BY [FECHA/HORA]` no es único. Si un ANI tiene dos atenciones en el mismo segundo, SQL Server entrega el "próximo" con diferencia 0 a cualquiera de las dos filas, y cuál recibe cada una puede cambiar entre ejecuciones del mismo SQL. Caso real: ANI 966877215, USUARIOS, 2025-03-07 16:26:36, con los LOGINID 51030036 y 51030008. Los valores son los mismos; solo cambia a qué LOGINID le corresponde cada uno. La comparación tolerante a empates (`comparar_filas`) lo detecta y lo informa como "EQUIVALENTE (empates)".

## 4. Diferencias intencionales con SSIS

| # | SSIS | Python | Motivo |
|---|---|---|---|
| 1 | `User::Periodo` = constante `202608` editada a mano | Automático, igual que `12_trafico` (día ≤ 4: mes anterior; si no, mes actual), o `PERIODO` / `--periodo` | Decisión del usuario |
| 2 | Limpia Tabla y Alimenta Tabla en tareas separadas, sin transacción. Si fallaba el INSERT, el periodo quedaba borrado | `DELETE` + `INSERT` en una transacción | Un fallo deja `TBL_FCR` como estaba |
| 3 | Lee los orígenes después del `DELETE` | Lee, transforma y valida **antes** del `DELETE` | Equivalente, porque no lee `TBL_FCR`, y no borra nada si hay errores |
| 4 | `INSERT` posicional sin lista de columnas | Lista explícita, y se valida que el orden real coincida | Evita cargar datos en columnas equivocadas si la tabla cambia |
| 5 | Sin validación | Valida esquema, NULL, valores 0/1 y anchos antes de escribir | Falla temprano y con mensaje claro |

**Efecto del periodo automático:** desde el día 5 del mes, las filas del mes anterior ya no se recalculan. Las atenciones de los últimos días del mes quedan con el FCR calculado hasta el día 4, así que un re-contacto posterior no actualizaría `FCR_7D` o `FCR_15d` de, por ejemplo, el 30 del mes anterior. Pasaba lo mismo en SSIS cada vez que se avanzaba la constante. Para recalcular un mes se usa `--periodo YYYYMM`.

## 5. Cómo repetir la verificación

```bash
python -m pytest                                          # 87 pruebas (unitarias + contra el .dtsx)
python tools/equivalencia.py oraculo --periodo 202608      # T-SQL original vs Python, solo lectura

# antes/después de la primera corrida real:
python tools/equivalencia.py foto ssis --periodo 202608
python main.py --periodo 202608
python tools/equivalencia.py foto python --periodo 202608
python tools/equivalencia.py comparar ssis python
```
