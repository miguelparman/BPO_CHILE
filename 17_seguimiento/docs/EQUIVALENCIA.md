# Equivalencia SSIS → Python — CL_Seguimiento (Chile)

Paquetes migrados, en el orden en que se ejecutan:

| # | Paquete SSIS | Módulo Python | Tareas SSIS → pasos Python |
|---|---|---|---|
| 02 | `CL_Seguimiento_02_Proc_Carga_Casos.dtsx` | `paquetes/p02_casos.py` | 13 → 7 |
| 03 | `CL_Seguimiento_03_Proc_Carga_Correos.dtsx` | `paquetes/p03_correos.py` | 7 → 5 |
| 04 | `CL_Seguimiento_04_Proc_Carga_Historial_Casos.dtsx` | `paquetes/p04_historial_casos.py` | 7 → 5 |
| 06 | `CL_Seguimiento_06_Proc_Carga_Historial_Comentarios.dtsx` | `paquetes/p06_historial_comentarios.py` | 9 → 7 |
| 07 | `CL_Seguimiento_07_Proc_Seguimiento.dtsx` | `paquetes/p07_seguimiento.py` | 9 → 9 |

El **01** (`Proc_Descarga_Bases`) no se migra como paquete. Sus descargas de Salesforce están deshabilitadas, porque
ya las hace `201_bot_salesforce`. Su paso activo "Convierte CSV" pasaba los crudos a la carpeta `Nuevo`, y ya no hace
falta porque los crudos se leen tal cual (sección 1).

El **05** (`Historial_Asignaciones`) queda **fuera de alcance**. Su insumo `Reporte_Asignaciones_Casos_Chile.csv` no
existe en ningún lado.

## 1. Fuentes: los CSV crudos del bot, tal cual

| | SSIS | Python |
|---|---|---|
| Origen | `...\SEGUIMIENTO\*.csv` → paquete 01 → `...\SEGUIMIENTO\Nuevo\*.csv` | SharePoint ReportingFractalia: `01 SEGUIMIENTO`, y `12 AUXILIARES` para Nombre_Contacto y Descripciones_NC, que el bot publica ahí |
| Archivo intermedio | Sí (`Nuevo`, UTF-8 con BOM, CRLF) | **No**. Se lee el crudo directamente (`extractor.leer_csv`: cp1252, `,`, `"`). |
| Descarga | Un archivo por paquete | Todos **en paralelo** al iniciar (`FuentePrecargada`, unos 8 s) |

Qué hacía el paso del 01 sobre los crudos actuales y qué quedó de cada regla:

| Regla de `Transforma_archivos_csv` | Efecto real | En Python |
|---|---|---|
| `";"` → `","` y `";\n` → `"\n` | Ninguno: el bot publica con coma | Se elimina. Si el bot volviera a `;`, la validación de columnas lo detecta y detiene el proceso. |
| `\r` suelto → salto | Ninguno: no hay `\r` en los crudos | Cubierto por la regla de saltos. |
| cp1252 → UTF-8 | No cambia caracteres. Un byte inválido queda como U+FFFD y se guarda como `?`. | Se lee en cp1252 **conservando** los bytes inválidos, para repararlos (sección 8). |
| LF → CRLF | **Sí**, en los textos de varias líneas | **Regla por columna** `saltos_crlf` en la transformación. Es necesaria: sin ella el LIMPIA de Comentarios daría 1 espacio en vez de 2 y el MERGE duplicaría esos comentarios. Además SP_FOLIOS_NC corta en `CHAR(13)`. |

## 2. Pasos redundantes eliminados (mismo resultado)

Se verificó en **todas** las bases del servidor (`sys.sql_modules`) que ningún objeto lee las staging. La única
excepción es `TBL_DESCRIPCIONES_NC`, que la usa `SP_FOLIOS_NC`.

| Paquete | Tarea(s) SSIS | Por qué es redundante |
|---|---|---|
| 02 | TRUNCA TEMPORAL CASOS, TRUNCAR TEMPORALES, TRUNCA TEMPORAL CASOS B | Las staging de Casos y Casos B pasan a **#temporales de la sesión del paquete**, que nacen vacías y se descartan al cerrar la sesión. |
| 02 | Carga de Tipificaciones (archivo + `TBL_SALESFORCE_CASOS_TIPIFICACIONES`) | Solo la leía "ACTUALIZA TIFICIACIONES", que está **deshabilitada**. Se elimina un archivo completo. |
| 02 | Carga de Nombre Contacto en `TBL_SALESFORCE_DATOS_CONTACTO` + UPDATE "Agrega Nombre de Contacto" | El cruce se hace en Python antes de cargar Casos (`transformacion/cruce.py`): LEFT JOIN, `''`→NULL, igualdad sin distinguir mayúsculas ni contar espacios finales, como SQL Server. |
| 03 | TRUNCA TEMPORAL CORREOS (×2) | #temporal |
| 04 | TRUNCA TEMPORAL HISTORIAL, TRUNCA TEMPORA HISTORICO | #temporal |
| 06 | TRUNCATE TEMPORAL COMENTARIOS, TRUNCA TEMPORAL HISTORICO | #temporal. La carga de Descripciones NC no cambia: su tabla sigue permanente porque la lee SP_FOLIOS_NC. |

Lo que **se mantiene igual**:
- El T-SQL de negocio, byte a byte: LIMPIA, MERGE, INSERT…SELECT, FECHA BASE y SP. La única diferencia al ejecutarlo
  es `sql.a_temporal()`, que cambia `[CL_TEMPORALES].[dbo].[TBL_X]` por `#TBL_X`; la prueba estructural lo comprueba.
- Los Log Inicio y Log Fin con los mismos nombres.
- El orden, el corte ante fallos y la validación previa de conexiones.

**Mejora de robustez (mismo resultado cuando todo va bien).** `LIMPIA BASE CHILE` + `CARGA CASOS CHILE`, y
`LIMPIA CASOS B CHILE` + `CARGA CASOS B CHILE`, se ejecutan **en una transacción**. En SSIS, si fallaba el INSERT,
los casos ya borrados quedaban sin reinsertar hasta la siguiente corrida.

**Sesión por paquete.** Las #temporales existen solo en su sesión. En SSIS cada tarea abría su propia conexión, así
que aquí se restablece el `DATEFORMAT` de la sesión antes de cada tarea, para que un `SET` de una tarea no afecte a la
siguiente. Si la conexión se cae a mitad de paquete, se detecta y el paquete falla (las #temporales se habrían
perdido).

Las staging permanentes que ya no se usan (Casos, Contacto, Tipificaciones, Correos, Historial y Comentarios) **no se
borran**. Sirven de molde para la #temporal (`SELECT TOP 0 * INTO`). `TBL_SALESFORCE_CASOS_B` conserva la última
carga de SSIS.

## 3. Componente SSIS → componente Python

| SSIS | Python |
|---|---|
| Flat File Connection Manager / Flat File Source | `extraccion/extractor.py`: `FuenteSharePoint` + `FuentePrecargada` + `leer_csv` |
| Derived Column (`LEFT`, `REPLACE ".\xa0m." → "M"`) | `transformacion/transformer.py` |
| Data Conversion (DT_WSTR/DT_STR 1252/DT_NTEXT/DT_DATE/DT_NUMERIC + disposiciones) | `transformacion/transformer.py`, `transformacion/fechas.py` |
| FailComponent (truncamiento, error de conversión, fila mal formada) | `ValidacionError`: el paquete se detiene **antes** de cargar |
| OLE DB Destination (fast load, un solo commit) | `loader.cargar_temporal` → #temporal |
| Execute SQL Task | `loader.ejecutar_sql` / `ejecutar_transaccion` con el T-SQL literal de `scripts_sql/pXX/` |
| Execute Process `Carga_Reporte_Descripciones_NC_Chile.py` | `transformacion/descripciones_nc.py` (pandas sobre el crudo) + `SP_FOLIOS_NC` |
| Precedence Constraints / contenedores | Lista ordenada de tareas en `paquetes/pXX_*.py`, ejecutada por `pipeline.py` |
| Connection Managers OLE DB (172.17.0.162) | `config.DbSettings` (`.env`), una sesión por paquete, idioma `us_english` |

El linaje columna a columna está declarado en `mappings.py`. La prueba estructural lo vuelve a derivar desde el XML
de cada `.dtsx`, incluido el destino de Nombre Contacto que ahora entra por el cruce.

## 4. Decisiones del usuario

| Decisión | Implementación |
|---|---|
| Fuentes de SharePoint ReportingFractalia, **tomadas tal cual** | Crudos del bot, sin archivo intermedio ni conversión del archivo (sección 1). |
| Optimizar quitando pasos redundantes con el mismo resultado | Sección 2. |
| A (a): migrar `Carga_Reporte_Descripciones_NC_Chile.py` dentro del 06 | Usa la conexión del `.env`. Si falla, queda como **advertencia** y el paquete continúa, como hoy. |
| B: si un paquete falla, se corta todo | No se ejecutan las tareas ni los paquetes siguientes; el `Log Fin` queda en `exec...`. Se retoma con `--desde XX`. |
| C (c): excluir "ACTUALIZA CASOS OTRO PAIS" | No se migra; el proceso no toca `PE_SALESFORCE_ACTUAL`. El SQL quedó en `docs/no_migrado/`. |

## 5. Tareas no migradas

| Paquete | Tarea | Motivo | SQL |
|---|---|---|---|
| 02 | ACTUALIZA CASOS OTRO PAIS | Excluida (decisión C) | `docs/no_migrado/p02_ACTUALIZA_CASOS_OTRO_PAIS_excluida.sql` |
| 02 | ACTUALIZA TIFICIACIONES | Deshabilitada | `docs/no_migrado/p02_ACTUALIZA_TIFICIACIONES_deshabilitada.sql` |
| 07 | BK (BACKUP DATABASE ×3) | Deshabilitada | `docs/no_migrado/p07_BK_deshabilitada.sql` |
| 07 | CARGA ESPEJO AZURE | Deshabilitada | — |

Los SP (`SP_INSUMOS_SEGUIMIENTO`, `SP_ASESOR_RESPONSABLE`, `SP_PROCESO_SEGUIMIENTO`, `SP_FOLIOS_NC`) siguen en SQL
Server. Su definición queda como referencia en `docs/referencia_sp/`.

## 6. Otras decisiones técnicas

1. **Idioma de la sesión.** El login tiene idioma Español, pero las sesiones de SSIS corren en **us_english**:
   `FORMAT(..., 'hh:mm tt')` da `PM`, y en español sale vacío. La conexión fija `Language=us_english` (`DB_LANGUAGE`).
2. **Anchos contra la base real.** Varias Data Conversion son más anchas que la columna; por ejemplo `Estado` es
   DT_WSTR 50 y la staging `nvarchar(25)`. Python se detiene en la validación con fila y columna, en vez de fallar en
   el fast load.
3. **`Fecha de recepción` (Casos)**: es DT_DATE en el Flat File Source. Se envía en ISO, que
   `CAST(... AS datetime2)` interpreta igual. Hoy llega siempre vacía y queda NULL.
4. **Descripciones NC**: `to_sql` enviaba el texto como VARCHAR (cp1252), así que U+FFFD llegaba como `?`. Python
   hace lo mismo.
5. **Paquete 06**: sus dos ramas paralelas no comparten tablas y se ejecutan en serie.

## 7. Comentarios duplicados: corrección y limpieza (2026-10-26, a pedido del usuario)

**Causa (SSIS).** El MERGE de `[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS]` compara el comentario de la
staging (`nvarchar`) con el `varchar(6000)` guardado. Si el texto trae un carácter no representable en cp1252
(normalmente `U+FFFD`, un byte inválido del export de Salesforce), se guarda con `?` y nunca vuelve a coincidir. Por
eso SSIS lo **reinsertaba en cada corrida**.

**Corrección (desviación intencional de SSIS).** En la #temporal de Comentarios, la columna `[Comentarios del caso]`
se define como `varchar(max) COLLATE Modern_Spanish_CI_AS`, igual que el destino (`mappings.FLUJO_TEMP_COMENTARIOS.
tipos_temporal`). El texto queda convertido igual que se guarda, y el MERGE lo reconoce. El T-SQL del `.dtsx` no
cambia, y lo que se inserta tampoco: SQL Server hacía esa misma conversión al insertar. Verificado con el archivo del
2026-10-26 08:00: sin la corrección el MERGE reinsertaría 3 comentarios ya cargados, y con ella 0. Los otros MERGE no
tienen el problema: Historial compara con `CAST(... AS VARCHAR(300))` en ambos lados y Correos no compara texto.

**Limpieza** (`tools/limpiar_duplicados_comentarios.py`). Por cada comentario (caso + fecha + texto, la clave del
MERGE) se conservan todas las filas de su **primera** carga y se borran las de cargas posteriores.

| Medida | Valor |
|---|---:|
| Filas antes | 2.137.062 |
| Comentarios con reinserciones | 19.944 |
| **Filas borradas** (respaldadas en `[CL_SALESFORCE_ACTUAL].[dbo].[TBL_HISTORIAL_COMENTARIOS_DUPLICADOS_BK]`, `Fecha de Limpieza = 2026-10-26 09:30:38`) | **437.639** |
| Filas después | 1.699.423 |
| Repetidos dentro de una **misma** carga (vinieron así de Salesforce; no se tocan) | 2.553 comentarios / 3.677 filas |

Controles dentro de la transacción: todos OK (borradas = previstas, total cuadra, respaldadas = borradas, 0 comentarios
con reinserciones).

**Mientras SSIS siga activo**, seguirá reinsertando estos comentarios en cada corrida (07, 10, 13 y 16 h). Después
de pasar a Python, vuelve a ejecutar `python tools/limpiar_duplicados_comentarios.py --aplicar`: es idempotente y solo
borra lo nuevo. Si alguna vez hiciera falta, las filas se recuperan con
`INSERT INTO ...TBL_HISTORIAL_COMENTARIOS SELECT <columnas> FROM ...TBL_HISTORIAL_COMENTARIOS_DUPLICADOS_BK`.

## 8. Reparación de tildes mal codificadas (2026-10-26, a pedido del usuario)

**Pedido:** las cargas nuevas deben quedar bien escritas; lo ya cargado no se toca. Es una desviación intencional de
SSIS (`transformacion/codificacion.py`). Se aplica a todos los textos de todos los archivos, antes de cualquier
validación o conversión.

**Causa (en el dato de Salesforce).** Letras con tilde que se codificaron en UTF-8 (2 bytes) y luego se trataron
como si fueran otro formato. En el CSV quedan como `A` + byte inválido (`AGRA␣8D␣COLAS`), como `Ã` + byte
(`MUÃ‘OZ`) o como la letra correcta seguida de un byte sobrante (`CAFETERÍ␣8D␣A`). SSIS dejaba `?` o los caracteres
raros. El resto de las tildes del archivo llegan bien, así que el bot no es el origen.

**Reglas:**
1. `Ã` o `Â` seguido de un byte 0x80–0xBF que juntos forman UTF-8 → esa letra (`MUÃ‘OZ`→MUÑOZ, `JosÃ©`→José,
   `NÂ°`→N°).
2. `A` + byte inválido (0x81, 0x8D, 0x8F, 0x90, 0x9D) → la letra que forman (`AGRA␣8D␣COLAS`→AGRÍCOLAS,
   `BELTRA␣81␣N`→BELTRÁN). Si justo antes está la misma letra sin tilde, sobra: `ASESORIA␣8D␣AS`→ASESORÍAS.
3. Cualquier byte inválido que quede se elimina (`CAFETERÍ␣8D␣A`→CAFETERÍA).

Cada corrida deja en el log cuántos valores reparó por archivo y columna, con un ejemplo.

**Reparados con los archivos del 2026-10-26 10:00:** 34 valores. Casos `Nombre del cliente` 11 y `Asunto` 1,
Historial `Valor nuevo` 1, Comentarios 3, Descripciones NC 18. Palabras: AGRÍCOLAS, ARTÍCULOS, ASESORÍAS, AVENDAÑO,
BELTRÁN, CAFETERÍA, DISEÑO, FERRETERÍA, FÁBRICA, INFORMÁTICOS, IRARRÁZABAL, José, MINERÍA, MUÑOZ, Muñoz, NUÑEZ, N°,
RAMÍREZ, Santibañez, Técnicos, Yañez.

**No se puede reparar:** `ADMINISTRACIÃ?N`, `PEÃ?A`, `SUBSECRETARÃ?A`. El segundo byte ya llegó como un `?` literal
desde Salesforce y la letra original varía (Ó, Ñ, Í), así que se dejan tal como vienen. Corregirlos requiere hacerlo
en Salesforce.

**Efecto en las tablas** (lo antiguo no se toca):

| Tabla | Efecto |
|---|---|
| TBL_CASOS, TBL_CASOS_B, TBL_DESCRIPCIONES_NC | Se reemplazan los casos del archivo: quedan corregidos. |
| TBL_HISTORIAL_COMENTARIOS, TBL_HISTORIAL_CASOS (MERGE por texto) | La versión corregida no coincide con la guardada con `?`, así que se inserta **una vez** y la antigua queda (decisión del usuario). Con el archivo del 2026-10-26: 3 comentarios y 1 evento de historial. |

**Verificación.** La equivalencia estricta con SSIS se ejecuta con la reparación **apagada** (`codificacion.REPARAR =
False`, que reproduce el `�`→`?` de SSIS) y da **EQUIVALENTE**. Lo que la reparación cambia se lista aparte en el
reporte.

## 9. Frescura de las fuentes (2026-10-26, a pedido del usuario)

SSIS cargaba lo que encontrara, aunque fuera viejo: por ejemplo, las copias de `01 SEGUIMIENTO` de Nombre_Contacto y
Descripciones NC estaban detenidas desde el 11/09 sin ningún aviso. Ahora `frescura.py` revisa los metadatos de los 7
archivos en SharePoint (fecha y tamaño, sin descargarlos) antes de cargar:

| Situación | Regla | Acción |
|---|---|---|
| No actualizado | Más de `FRESCURA_MAX_MIN` = **150** min (tolera que se pierda una publicación del bot; lo normal son ~30 min) | Se omite |
| Vacío | 0 bytes, o sin filas de datos al descargarlo | Se omite |
| El bot está publicando en ese momento, o hay archivos de publicaciones distintas | — | **No se espera**: se toma lo que haya si está dentro de los 150 min (decisión del usuario). SharePoint reemplaza el archivo completo al terminar de subirlo, así que nunca se lee uno a medio escribir. |

**Decisión del usuario: omitir esa carga y continuar con las demás.** Se omite solo el bloque de tareas que usa el
archivo (`paquetes/base.Bloque`):

| Paquete | Bloque | Archivos |
|---|---|---|
| 02 | Casos (carga, FECHA BASE, borrado + carga de TBL_CASOS) | Casos + Nombre Contacto |
| 02 | Casos B | Casos B |
| 03 | Correos | Correos |
| 04 | Historial | Historial |
| 06 | Comentarios | Comentarios |
| 06 | Descripciones NC (**incluye el TRUNCATE**, para no vaciar la tabla; y SP_FOLIOS_NC) | Descripciones NC |
| 07 | — (los SP corren siempre) | — |

Si se omiten todos los bloques de un paquete, el paquete completo no corre y no escribe sus Log Inicio/Fin en
`LOGS_PROCESOS`. Si se omite Casos, igual corren 03, 04 y 06 contra el `TBL_CASOS` ya existente; lo que dependa de
casos nuevos entra en la siguiente corrida, porque el archivo lo vuelve a traer y el MERGE lo inserta.
`tests/unit/test_bloques.py` comprueba que ninguna tarea use una #temporal de un bloque que podría omitirse.

`python main.py --verificar` ejecuta solo la validación de conexiones y de frescura (exit 0 listo, 1 conexión, 2 alguna
carga se omitiría). La tarea programada pasó a **lunes a viernes**, igual que el bot, con las mismas horas. Verificado
el 2026-10-26 contra SharePoint real: con los archivos de las 11:01–11:05 todo queda OK; forzando `FRESCURA_MAX_MIN=30`,
se omiten 02, 03, 04 y 06 y el 07 corre.

## 10. Otros hallazgos del proceso original

* Correos: de las filas del archivo, solo cruzan con `TBL_CASOS` unas pocas (`INNER JOIN` del MERGE), igual que en
  SSIS.

## 11. Pruebas y evidencia

| Prueba | Cómo | Resultado (2026-10-26) |
|---|---|---|
| Unitarias + estructurales | `python -m pytest` | **155 passed** |
| Estructural vs `.dtsx` | SQL byte a byte; redirección a #temporales sin otros cambios; cada tarea migrada, redundante (con la redundancia verificada) o no migrada; orden; linaje; tipos; anchos; credenciales | OK |
| Mecánica del loader contra SQL Server (solo #temporales) | Sesión `us_english`/`mdy`, carga en #temporal, redirección, restablecer `DATEFORMAT`, rollback de transacción, detección de reconexión | OK |
| Solo validar con SharePoint | `python main.py --solo-validar` | 33 tareas, 0 errores. Descarga paralela 8,4 s; transformación < 2 s. |
| Datos SSIS vs Python | `python tools/equivalencia.py` (solo lectura, #temporales + ROLLBACK; reparación de tildes apagada) | **EQUIVALENTE** (tabla siguiente; repetida el 2026-10-26 contra la corrida SSIS de las 10:00, también EQUIVALENTE) |

Base de comparación: los crudos locales que usó la corrida SSIS del 2026-10-26 07:00 (`LOGS_PROCESOS`:
Update_Carga_Casos_Chile OK).

| Prueba | Filas Python | Filas SSIS | Solo Python | Solo SSIS | MERGE: nuevas / reinserciones como SSIS | |
|---|---:|---:|---:|---:|---:|:---:|
| Entradas: crudo (Python) vs `Nuevo` (SSIS), valor a valor, 7 archivos | 6.163 / 6.163 / 6.164 / 199 / 23.211 / 8.545 / 24.650 | iguales | 0 | 0 | | SÍ |
| staging TBL_SALESFORCE_CASOS_B | 6.164 | 6.164 | 0 | 0 | | SÍ |
| staging TBL_DESCRIPCIONES_NC | 24.650 | 24.650 | 0 | 0 | | SÍ |
| TBL_SEGUIMIENTO_FECHA_BASE | `26/10/2026 08:35 AM` | `26/10/2026 08:35 AM` | | | | SÍ |
| TBL_CASOS (DELETE + INSERT; contacto por cruce en Python) | 6.097 | 6.097 | 0 | 0 | | SÍ |
| TBL_CASOS_B (DELETE + INSERT) | 6.097 | 6.097 | 0 | 0 | | SÍ |
| TBL_CORREOS (MERGE) | 4 | 4 | 0 | n/a | 0 / 0 | SÍ |
| TBL_HISTORIAL_CASOS (MERGE) | 23.153 | 34.366* | 0 | n/a | 0 / 0 | SÍ |
| TBL_HISTORIAL_COMENTARIOS (MERGE) | 8.545 | 20.126* | 0 | n/a | 0 / 3 (antes de la corrección de la sección 7) | SÍ |

\* Las tablas con MERGE acumulan historia: son las filas de la tabla para los casos del archivo. El criterio es que
cada fila de Python ya esté idéntica (Solo Python = 0) y que el MERGE de Python no inserte nada que SSIS no haya
insertado.

El detalle con datos está en `evidencias/` (en `.gitignore` porque contiene RUT).
