# Equivalencia SSIS ↔ Python — `CL_Proc_Volumetria_Gerencia.dtsx`

Paquete original: `C:\Desarrollo\CHILE ETL AZURE\CHILE ETL AZURE\CHILE ETL AZURE\CL_Proc_Volumetria_Gerencia.dtsx`.
No invoca scripts `.py`, variables ni expresiones.

## 1. Control Flow

```
Contenedor de secuencias 1
├── GERENCIA        TRUNCATE → TBL_VOLUMETRIA_GERENCIA (Data Flow)        → DELETE
├── ESCALAMIENTO    TRUNCATE → TBL_VOLUMETRIA_ESCALAMIENTO (Data Flow)    → DELETE
├── CLOSE THE LOOP  TRUNCATE → TBL_VOLUMETRIA_CLOSE THE LOOP (Data Flow)  → DELETE
└── T-ATIENDO       TRUNCATE → TBL_VOLUMETRIA_T-ATIENDO (Data Flow)       → DELETE
```

Los 4 contenedores no tienen Precedence Constraints entre sí: corren en paralelo. Dentro de cada uno, las restricciones son *Success*.

| Elemento SSIS | Python |
|---|---|
| Contenedor de secuencias 1 | `pipeline.GerenciaPipeline.run` (recorre `mappings.FLUJOS`) |
| Contenedor por flujo | `GerenciaPipeline._ejecutar_flujo` + un `mappings.FlujoSpec` |
| Execute SQL `TRUNCATE` / `DELETE` (texto literal) | `FlujoSpec.sql_truncate` / `sql_delete` → `carga/loader.py` |
| Excel Connection Manager (archivo local `...\BPO - Insumos\Chile\Especializados\...`) | Copia BPO → ReportingFractalia (`ingesta/copiar.py`) + lectura por Graph (`extraccion/extractor.py`) |
| Excel Source (`Hoja1$`, HDR=YES, ACE) | `extraccion/extractor.leer_hoja` / `valor_ace` |
| Conversión de datos | `transformacion/transformer.py` + `validacion/validator.py` |
| OLE DB Destination | `carga/loader.py` → `db.DatabaseGateway.recargar_tabla` |
| OLE DB CM `162.CL_MOVIL` (password DPAPI) | `DB_*` en `.env` |
| — (nuevo) | `conexiones.py`: validación previa, 3 reintentos cada 5 min |

## 2. Data Flow por flujo

**Tipos en el Excel Source (iguales en los 4):** `Caso SF` DT_R8, `Fecha` DT_DATE y el resto DT_WSTR(255).

**Conversión de datos:**
- `Caso SF` → `[Número del caso]` DT_STR(n).
- `Fecha` → DT_DBDATE.
- Texto → DT_STR(n), code page 1252.

**Disposición:** F = FailComponent, I = IgnoreFailure.

| Columna Excel → tabla | GERENCIA | ESCALAMIENTO | CLOSE THE LOOP | T-ATIENDO |
|---|---|---|---|---|
| Caso SF → Número del caso | 50 F | 15 F | 15 I | 15 F |
| Fecha → Fecha | date I | date F | date I | date F |
| Causa Raiz | 255 F | 30 F | 30 I (**ampliada a 255**, ver §4.5) | 30 F (tabla 256) |
| Motivo C/R | 255 F | 100 F | 255 I | 255 F |
| Derivado → Derivado / Derivado por | 255 F → `Derivado` | 50 F → `Derivado` | 100 I → `Derivado por` | 100 F → `Derivado por` |
| cargo → Cargo | 255 F | 30 **I** (**ampliada a 255**, ver §4.5) | 255 I | 255 F |
| SM Quiebre | 255 F | 50 F | 255 I | 255 F |
| Coordinador de Quiebre → Coordinador Quiebre | 255 F | 50 F | 255 I | 255 F |
| Destino | AccessMode 0 (fila a fila) | fast load, TABLOCK | fast load, TABLOCK | fast load, TABLOCK |

`tests/equivalencia/test_equivalencia_dtsx.py` lee el `.dtsx` y verifica que esta tabla, en `mappings.py`, coincida con el paquete: tipos, anchos, code page, disposiciones, mapeo, SQL y orden.

## 3. Comportamiento de ACE reproducido

| Comportamiento | SSIS (ACE, sin IMEX) | Python |
|---|---|---|
| Celda de otro tipo que su columna (ej. `SIN CASO` en `Caso SF`, `04/0272025` en `Fecha`, número en columna de texto) | NULL | `valor_ace` → `None` |
| Filas vacías del rango usado | se insertan con NULL | se insertan con NULL |
| Filas con `Caso SF` NULL | las borra el `DELETE` | las borra el mismo `DELETE` |
| Fórmulas | valor calculado | `data_only=True` |
| `\xa0` (espacio duro) en textos | se conserva | se conserva |
| DT_R8 → DT_STR | `12239535` | `r8_a_texto` → `"12239535"` |
| DT_DATE → DT_DBDATE | descarta la hora | `datetime.date()` |
| IgnoreFailure con valor más largo que n | valor truncado (confirmado en la tabla SSIS) | truncado a n |
| FailComponent con valor más largo que n o fuera de 1252 | falla el Data Flow (tabla ya truncada) | `ValidacionError` **antes** de tocar la tabla |

## 4. Diferencias deliberadas

1. **Transacción por flujo.** En SSIS, si falla el Data Flow después del TRUNCATE, la tabla queda vacía. En Python, TRUNCATE + INSERT + DELETE van en una transacción: si algo falla hay rollback y la tabla conserva la carga anterior. En una corrida exitosa el resultado es idéntico.
2. **Ejecución en serie.** Los 4 flujos corren uno tras otro, no en paralelo, con la misma semántica: uno que falla no detiene a los demás y el proceso termina en error.
3. **Origen en SharePoint.** Los Excel se copian del sitio BPO a ReportingFractalia (`02 ESPECIALIZADOS/<subcarpeta>/<archivo>`) y se leen desde ahí. La copia se verifica comparando los datos de `Hoja1`, no el tamaño, porque SharePoint reescribe los metadatos del archivo al subirlo.
4. **Validación de conexiones.** Antes de ejecutar se prueban SQL Server, BPO y ReportingFractalia. Si alguna falla, se reintenta cada 5 min hasta 3 veces; si sigue fallando, el proceso termina sin copiar ni cargar nada.
5. **2 columnas ampliadas para no truncar (2026-10-19, a pedido del usuario).** El script es [sql/01_ampliar_columnas.sql](../sql/01_ampliar_columnas.sql), idempotente y sin objetos dependientes.

   | Tabla.columna | .dtsx / tabla antes | Ahora | Máx. real | Fila afectada |
   |---|---|---|---|---|
   | TBL_VOLUMETRIA_ESCALAMIENTO.[Cargo] | DT_STR 30 / varchar(30) | 255 / varchar(255) | 48 | caso 12800100: `...RRSS \|Gerenc` → `...RRSS \|Gerencia Canales Remotos` |
   | TBL_VOLUMETRIA_CLOSE_THE_LOOP.[Causa Raiz] | DT_STR 30 / varchar(30) | 255 / varchar(255) | 33 | caso 18735667: `ERRORES O INCIDENCIAS APLICATI` → `ERRORES O INCIDENCIAS APLICATIVOS` |

   En `mappings.py` estas 2 columnas tienen ancho 255, y `ANCHOS_AMPLIADOS` guarda el ancho original del .dtsx; la prueba de equivalencia compara contra ese valor. Las demás columnas `IgnoreFailure` conservan el ancho del .dtsx y siguen truncando si un valor lo excede, con aviso en el log. Después del cambio, la comparación con la foto SSIS ([evidencias/reporte_ssis_vs_python_ampliado.md](../evidencias/reporte_ssis_vs_python_ampliado.md)) solo difiere en esas 2 filas.

6. **GERENCIA con AccessMode 0 y `FastLoadKeepNulls=false`.** Esa opción solo aplica al fast load y las tablas no tienen defaults (revisado en `INFORMATION_SCHEMA`), así que los NULL se insertan como NULL igual que en SSIS. Python usa un INSERT por lotes.

## 5. Evidencia con datos reales (2026-10-19)

| Tabla | Filas leídas | Borradas por el DELETE | Final SSIS | Final Python | Resultado |
|---|---|---|---|---|---|
| TBL_VOLUMETRIA_GERENCIA | 776 | 12 | 764 | 764 | idénticas |
| TBL_VOLUMETRIA_ESCALAMIENTO | 784 | 7 | 777 | 777 | idénticas |
| TBL_VOLUMETRIA_CLOSE_THE_LOOP | 750 | 120 | 630 | 630 | idénticas |
| TBL_VOLUMETRIA_T_ATIENDO | 783 | 13 | 770 | 770 | idénticas |

La comparación es fila a fila, como multiconjunto, porque las tablas no tienen clave. Los archivos están en `evidencias/ssis/` (foto previa a la primera carga Python), `evidencias/python/` y `evidencias/reporte_ssis_vs_python.md`. Detalle de la corrida en `evidencias/ejecucion_real_20261019.md`.
