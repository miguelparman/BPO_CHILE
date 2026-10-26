# Equivalencia SSIS_CL_Puntualidad.dtsx ↔ Python

Paquete original: `C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\SSIS_CL_Puntualidad.dtsx`
(sin Script Tasks ni archivos `.py`; conexiones OLE DB `162.CL_MOVIL.mparedes` y `162_CL_ANALISIS`, Excel `SLA`).

## 1. Resultado

| Tabla | Resultado | Evidencia |
|---|---|---|
| `TBL_SLA` | **Idéntica** a la que dejó SSIS (530 filas, 9 columnas, `Llave` = NULL) **salvo la decisión de conservar el SLA decimal**: 6 filas con 13,5 (SSIS: 14) y la columna `SLA` en `decimal(10,2)` (SSIS: `int`) | `python main.py --equivalencia` |
| `TBL_PUNTUALIDAD` | **Idéntica** al T-SQL original: 430.107 filas, 43 columnas, 0 filas distintas en ambos sentidos, mismo esquema (tipos, anchos, nulabilidad, orden) | informe `evidencias/equivalencia_*.md` |

Tiempo de `PUNTUALIDAD` sobre los mismos 430.107 casos: **687–787 s con el T-SQL original → ~20–29 s** con Python. La última comparación (informe `evidencias/equivalencia_20261026_171832.md`) se hizo con la tabla SLA **decimal** en ambos lados, así que cubre los 4.337 casos con SLA 13,5.

La comparación de `PUNTUALIDAD` se hace en el servidor sobre una **copia congelada** de los casos (`TBL_PUNTUALIDAD_EQ_SNAP`),
porque los casos "En proceso" toman la hora actual como cierre y cambian entre ejecuciones. Se corre el T-SQL original
(funciones fila por fila) y la versión optimizada sobre esa misma copia, y se comparan con `GROUP BY` de todas las columnas
+ `EXCEPT` en ambos sentidos (así también se detectan filas repetidas). Solo se escriben tablas `*_EQ_*` y `*_PY`.

Además, antes de integrarla se probó la aritmética de calendario contra las funciones originales con 12.000 y 60.000 casos
reales **más fechas sintéticas extremas** (fines de semana, feriados, bordes de horario, cierres anteriores a la apertura):
0 diferencias en ambas.

## 2. Control Flow

```
SLA PRUEBA ── TRUNCA TABLA ── TBL_SLA_CHILE (Data Flow) ── UPDATE ──(Éxito)── PUNTUALIDAD
```

`pipeline.py` ejecuta lo mismo en el mismo orden; si una tarea falla, no corre la siguiente. Verificado por
`tests/equivalencia/test_equivalencia_dtsx.py` contra las restricciones de precedencia del `.dtsx`.

## 3. Data Flow `TBL_SLA_CHILE` (Excel → TBL_SLA)

| Excel (wstr 255 / r8) | Data Conversion | Destino `TBL_SLA` |
|---|---|---|
| Tipología | str(100) cp1252 | Tipología varchar(150) |
| Dia/Hora | str(10) | Día/Hora varchar(10) |
| SLA Real (r8) | numeric(10,2) | SLA **int** |
| Condicion | str(15) | Calendario/Laboral varchar(15) |
| Estado | str(15) | Estado varchar(15) |
| Línea de Negocio | str(15) | Línea de Negocio varchar(15) |
| Motivo de contacto | str(50) | Motivo de contacto varchar(50) |
| Subtipología | str(200) | Subtipología varchar(200) |
| — | — | Llave varchar(500): no se carga, queda NULL |

- Todos los componentes tienen `FailComponent` para errores y truncamientos: un texto más ancho que la columna convertida
  o un número que no convierte detiene la carga (`ValidacionError`), no se trunca en silencio.
- **`SLA Real` se conserva decimal (decisión del usuario, 2026-10-26).** SSIS insertaba el numeric(10,2) en una columna `int` y OLE DB
  lo redondeaba: los 6 valores 13,5 del Excel quedaron en **14** en `TBL_SLA`, lo que se consideró erróneo. Python conserva el valor real
  (`Decimal`, 13,50) y `TBL_SLA.SLA` pasa a `decimal(10,2)` (`scripts_sql/ajustes/10_sla_decimal.sql`, ver sección 5b).
- Sin recorte de espacios: `TBL_SLA` conserva `'Solicitud Comercial '` con el espacio final.
- Fuera de `cp1252` un carácter pasa a `?` con una advertencia (como DT_WSTR → DT_STR); hoy no hay ninguno.
- El `TRUNCATE` y el `UPDATE` son copia literal del `.dtsx` (verificado byte a byte); solo cambia el nombre de la tabla en modo prueba.

## 4. Tarea `PUNTUALIDAD`

Original: `DROP TABLE IF EXISTS` + `SELECT … INTO` + 13 pares `ALTER TABLE ADD` / `UPDATE`, con tres funciones escalares con
`WHILE` de `SERVICIOS_GENERALES` ejecutadas fila por fila: `FUNC_CH_FECHA_INICIO`, `FUNC_CH_FECHA_VENCIMIENTO` y
`FUNC_CH_MINUTOS_VALIDOS_ENTRE_FECHAS` (esta última usa `FUNC_CH_FECHA_FIN`). Cada vuelta del `WHILE` volvía a consultar
`TBL_CALENDARIO_DIAS_FESTIVOS`.

Python (`scripts_sql/puntualidad/`): un solo `SELECT … INTO` con las mismas columnas, orden y tipos.

| Script | Qué hace |
|---|---|
| `10_calendario.sql` | `#cal` / `#calw`: día laboral (no sábado, domingo ni feriado) con contador acumulado de días laborales |
| `20_base.sql` | la consulta original (mismas columnas, `CASE` y `JOIN`) a una `#base`, con las vistas SLA en línea |
| `25_valida_calendario.sql` | aborta si alguna fecha cae fuera del calendario (2020-01-02 a 2034-12-30), en vez de dar NULL en silencio |
| `30_calculo.sql` | `FECHA APERTURA LABORAL`, `FECHA DE VENCIMIENTO` y los minutos, por etapas (una sola sentencia supera el límite de complejidad de expresiones de SQL Server, error 8632) |
| `40_destino.sql` | la tabla final y las columnas restablecidas a `NULL`, como las dejaba el `ALTER TABLE ADD` |

Equivalencias de las funciones, que **no se modificaron** y siguen en el servidor como referencia:

- **INICIO(x):** fuera de horario (antes de 08:30 o desde las 18:00) pasa a las 09:00 del día hábil que corresponde; sábado, domingo o
  feriado avanza al siguiente día hábil. Es idempotente, por eso `FECHA_VENCIMIENTO` no la reaplica.
- **FIN(x):** análogo con las 18:00, y hacia atrás antes de las 08:30 (el lunes retrocede al viernes).
- **VENCIMIENTO:** K = minutos / 540 días hábiles de 9 h, saltando los no laborales con `#calw`. La hora se conserva solo si no se
  cruzó ningún día no laboral; si se cruza, queda 09:00 (comportamiento del original).
- **MINUTOS:** `DATEDIFF − 870 · días hábiles − 1440 · días no hábiles (+870)`, contando los días por diferencia de acumulados.
- El literal `'ATENDIDO DENTRO DE PLAZO<tab>'` del original lleva un tabulador al final; se conserva.

## 5. Decisión: desempate de las vistas SLA

`VIEW_SLA_4TIP`, `VIEW_SLA_3TIP` y `VIEW_SLA_1TIP` numeran con `ROW_NUMBER()` ordenando por **las mismas columnas de la
partición**. Si un grupo tiene filas con SLA distintos, cuál queda como 1 **no está definido**: cambia con el plan de ejecución.
Hoy pasa en 4 grupos de `VIEW_SLA_3TIP` (parejas "Vigente" / "No vigente").

La primera comparación dio 9 filas distintas de 430.107 (3 casos por cada uno de 3 grupos), **todas** en esos grupos: el original
había elegido "Vigente" y la versión nueva "No vigente". Como ni el orden físico explica la elección del original (en todos los
grupos "No vigente" está primero en la tabla), se fijó un desempate determinista, **"Vigente" primero** (`20_base.sql`), que
reproduce lo que SSIS dejó en todos los casos observados. Con eso la comparación dio 0 diferencias.

Esto significa que **el resultado ya no depende del plan de ejecución**; las vistas del servidor no se tocaron. Si prefieres que
un grupo con empate se resuelva de otra forma, es una línea por vista en `20_base.sql`.

## 5b. Decisión: conservar el SLA decimal

El Excel trae **13,5 horas** en 6 filas (Inconformidad de Provisión: CHI Falla masiva fija, Incumplimiento de visita técnica, Problemas
internet, Problemas TV, Problemas voz y Avería de Servicio Privados). SSIS las dejaba en 14. El usuario decidió conservar el valor real.

- `TBL_SLA.SLA`: `int` → `decimal(10,2)`. La columna es un heap sin índices ni restricciones, y solo la usan las 3 vistas `VIEW_SLA_*`
  (sin `SCHEMABINDING`). El `ALTER COLUMN` va **dentro de la transacción de la carga** y es idempotente.
- `TBL_PUNTUALIDAD`: `[SLA (ARBOL)]` queda `decimal(10,2)` y `[SLA HORA]` `decimal(13,2)` en **todas** las filas (24 pasa a 24,00); es el tipo
  que produciría el propio T-SQL original con una `TBL_SLA` decimal. Aviso para Power BI: cambia el tipo de esas dos columnas.
- Impacto medido sobre 430.107 casos: **4.337** casos con SLA 13,5 (vencimiento 30 min antes; 1.157 cambian sus minutos pendientes) y
  **34** casos cerrados que pasan de CUMPLE a NO CUMPLE (20 finalizados, 14 cancelados).
- Las funciones originales aceptan decimales (`FUNC_CH_FECHA_VENCIMIENTO` recibe `decimal(12,2)`), y la comparación de equivalencia se hace
  ahora con la tabla SLA decimal en ambos lados (T-SQL original y Python).
- **Cuidado al pasar a producción:** mientras el job SSIS siga activo, su destino OLE DB tiene `SLA` como `i4`; cambiar la columna a
  decimal puede hacerle fallar la validación de metadatos. Hacer el `--destino produccion` **después de deshabilitar el job SSIS**.

## 6. Diferencias deliberadas respecto de SSIS

| | SSIS | Python | Efecto |
|---|---|---|---|
| Lectura del Excel | después del `TRUNCATE` | antes de tocar la base | un Excel malo ya no deja `TBL_SLA` vacía |
| `SLA PRUEBA` | 3 tareas con commit propio | una sola transacción | `TBL_SLA` nunca queda vacía ni a medio actualizar |
| `PUNTUALIDAD` | `DROP` inmediato y reconstrucción de ~13 min | todo en una transacción (verificado con un fallo inyectado) | si algo falla, la tabla anterior queda intacta; los lectores esperan en vez de ver la tabla borrada |
| Filas totalmente vacías del Excel | llegarían como una fila NULL | se omiten con una advertencia | hoy no hay ninguna |
| Origen del Excel | ruta local | SharePoint (`08 PUNTUALIDAD`) vía Graph | el archivo de SharePoint es más reciente (29-sep) que la copia local (14-ago) |
| `SLA` de `TBL_SLA` | `int` (13,5 → 14) | `decimal(10,2)` (13,5) | 4.337 casos vencen 30 min antes; 34 casos cerrados pasan de CUMPLE a NO CUMPLE; `SLA (ARBOL)` y `SLA HORA` de `TBL_PUNTUALIDAD` pasan a decimal para todas las filas |
| Credenciales | DPAPI en el `.dtsx` | `.env` | — |

## 7. Qué no se migró

Nada del paquete queda fuera. Las funciones `FUNC_CH_*` y las vistas `VIEW_SLA_*` siguen existiendo en el servidor, sin
cambios; el proceso Python ya no las llama (no se revisó si otros procesos las usan).

## 8. Cómo reproducir

```bat
python -m pytest                      :: 46 pruebas; las del .dtsx se omiten si el archivo no está en la máquina
python main.py --verificar            :: conexiones SQL Server y SharePoint
python main.py --solo-validar         :: lee y valida el Excel de SharePoint; no escribe
python main.py                        :: corrida completa en modo prueba (TBL_SLA_PY, TBL_PUNTUALIDAD_PY)
python main.py --equivalencia         :: compara contra el T-SQL original (~14 min); informe en evidencias/
```

Pendiente para pasar a producción (se hace al final de la migración completa): `python main.py --destino produccion`,
la tarea programada y deshabilitar el job SSIS.
