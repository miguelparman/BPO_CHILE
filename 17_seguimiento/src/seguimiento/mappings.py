"""Constantes de los Data Flows de CL_Seguimiento_02/03/04/06, declaradas como
DATOS (sin logica). Cada valor sale del .dtsx original y lo verifica
tests/equivalencia/test_equivalencia_dtsx.py:

  - ArchivoSpec      Flat File Connection Manager + salida del Flat File
                     Source (orden de columnas, tipo y ancho de salida).
  - ColumnaDestino   linaje de cada columna del OLE DB Destination:
                     columna del archivo -> Derived Column (LEFT) ->
                     Data Conversion (tipo, ancho, disposiciones) -> columna.
  - FlujoSpec        un OLE DB Destination (tabla staging en CL_TEMPORALES).

  - CruceSpec        cruce en Python que reemplaza una staging + un UPDATE
                     (Nombre de Contacto -> 'Agrega Nombre de Contacto').

Las columnas de la tabla que el destino NO mapea quedan en NULL (no se
incluyen en el INSERT), igual que en SSIS.

Optimizacion (mismo resultado): las staging se cargan en tablas #temporales
de la sesion del paquete (TABLAS_TEMPORALES) en vez de las permanentes de
CL_TEMPORALES; las permanentes solo sirven de molde (SELECT TOP 0 INTO). Se
verifico en todas las bases del servidor que ningun objeto las lee, salvo
TBL_DESCRIPCIONES_NC (SP_FOLIOS_NC), que sigue siendo permanente.
Tipificaciones (archivo + TBL_SALESFORCE_CASOS_TIPIFICACIONES) no se migra:
solo la usaba la tarea deshabilitada 'ACTUALIZA TIFICIACIONES'.

El paquete 05 (Historial Asignaciones) esta fuera de alcance.
"""

from __future__ import annotations

from dataclasses import dataclass

BD_STAGING = "CL_TEMPORALES"
ESQUEMA = "dbo"

# --------------------------------------------------------------------------- #
# Carpetas de SharePoint (ReportingFractalia / Data Reporting) donde
# 201_bot_salesforce publica los CSV (ver 201_bot_salesforce/config/reports.py).
# --------------------------------------------------------------------------- #
CARPETA_SEGUIMIENTO = "seguimiento"
CARPETA_AUXILIARES = "auxiliares"
CARPETAS_DEFAULT = {
    CARPETA_SEGUIMIENTO: "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/01 SEGUIMIENTO",
    # El bot publica Nombre_Contacto y Descripciones_NC aqui (sharepoint_folder_path
    # propio); las copias que quedaron en '01 SEGUIMIENTO' no se actualizan
    # desde 2026-09-11.
    CARPETA_AUXILIARES: "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/12 AUXILIARES",
}

# --------------------------------------------------------------------------- #
# Tipos
# --------------------------------------------------------------------------- #
# Salida del Flat File Source
FF_STR = "str"  # DT_STR code page 65001 (ancho = largo de la columna de salida)
FF_TEXT = "text"  # DT_TEXT (sin ancho)
FF_FECHA = "date"  # DT_DATE (el origen ya parsea la fecha)

# Data Conversion (o tipo de la Derived Column)
WSTR = "wstr"  # DT_WSTR(ancho)
STR1252 = "str1252"  # DT_STR(ancho, 1252)
NTEXT = "ntext"  # DT_NTEXT
FECHA = "date"  # DT_DATE
NUMERICO = "numeric"  # DT_NUMERIC(18, 0)


@dataclass(frozen=True)
class ColumnaArchivo:
    nombre: str  # nombre de la columna en el Flat File Connection Manager
    tipo: str = FF_STR
    ancho: int | None = None


@dataclass(frozen=True)
class ArchivoSpec:
    nombre: str  # nombre del CSV
    carpeta: str  # CARPETA_*
    conexion: str  # Flat File Connection Manager del .dtsx
    columnas: tuple[ColumnaArchivo, ...]


@dataclass(frozen=True)
class Conversion:
    tipo: str
    ancho: int | None = None
    error_ignora: bool = False  # errorRowDisposition = IgnoreFailure
    truncamiento_ignora: bool = False  # truncationRowDisposition = IgnoreFailure


@dataclass(frozen=True)
class ColumnaDestino:
    destino: str  # columna de la tabla staging
    origen: int  # posicion de la columna en el archivo
    conversion: Conversion
    left: int | None = None  # Derived Column LEFT([col], n) antes de la conversion


@dataclass(frozen=True)
class CruceSpec:
    """LEFT JOIN por [Numero del caso] contra otro archivo, resuelto en Python.
    Reemplaza: carga de 'flujo' en su staging + UPDATE X0 SET col = CASE WHEN
    X1.col = '' THEN NULL ELSE X1.col END FROM <staging> X0 LEFT JOIN <staging
    de flujo> X1 ON X0.[Numero del caso] = X1.[Numero del caso]."""

    tarea_reemplazada: str  # refId del UPDATE que reemplaza
    flujo: "FlujoSpec"  # Data Flow original del archivo cruzado (conversiones/validaciones)
    clave: str  # columna de cruce (en ambos lados)
    columnas: tuple[str, ...]  # columnas que el UPDATE completa (mismo nombre en ambos lados)


@dataclass(frozen=True)
class FlujoSpec:
    tarea: str  # Data Flow Task (refId en el .dtsx)
    componente: str  # OLE DB Destination
    archivo: ArchivoSpec
    tabla: str  # [CL_TEMPORALES].[dbo].[tabla]
    columnas: tuple[ColumnaDestino, ...]
    tablock: bool  # FastLoadOptions contiene TABLOCK
    # Derived Column "reemplaza columna" sobre una columna del archivo:
    # (posicion, buscar, reemplazar) -> REPLACE([col], buscar, reemplazar)
    reemplazos: tuple[tuple[int, str, str], ...] = ()
    cruce: CruceSpec | None = None
    # Columnas de la #temporal que se definen con otro tipo que la staging:
    # ((columna, tipo SQL), ...). Ver FLUJO_TEMP_COMENTARIOS.
    tipos_temporal: tuple[tuple[str, str], ...] = ()

    @property
    def columnas_insert(self) -> tuple[str, ...]:
        """Columnas del INSERT: las del destino + las que completa el cruce."""
        extra = self.cruce.columnas if self.cruce else ()
        return tuple(c.destino for c in self.columnas) + extra


def _w(ancho: int, **kw) -> Conversion:
    return Conversion(WSTR, ancho, **kw)


def _str(nombres_anchos, tipos=None) -> tuple[ColumnaArchivo, ...]:
    tipos = tipos or {}
    return tuple(
        ColumnaArchivo(n, tipos.get(i, FF_STR), None if tipos.get(i) in (FF_TEXT, FF_FECHA) else a)
        for i, (n, a) in enumerate(nombres_anchos)
    )


# =========================================================================== #
# CL_Seguimiento_02_Proc_Carga_Casos.dtsx
# =========================================================================== #
ARCHIVO_CASOS = ArchivoSpec(
    "Reporte_Casos_Chile.csv",
    CARPETA_SEGUIMIENTO,
    "Casos Chile",
    _str(
        [
            ("Número del caso", 800),
            ("Número de caso principal", 800),
            ("Identificador FS Local", 800),
            ("Cantidad", 800),
            ("Fecha Hora de apertura", 800),
            ("Fecha de recepción", None),
            ("Fecha hora de resolución", 800),
            ("Fecha Hora de cierre", 800),
            ("Abierto", 800),
            ("Estado", 800),
            ("Motivos del estado", 800),
            ("Propietario del caso", 800),
            ("Asesor Postventa", 800),
            ("No  identificación fiscal", 800),
            ("Id  del cliente legado", 800),
            ("Segmento Global", 800),
            ("Nombre del cliente", 800),
            ("Cliente principal", 800),
            ("Subterritorio", 800),
            ("Subsegmento local", 800),
            ("Territorio", 800),
            ("Categoría de cliente", 800),
            ("Asunto", 800),
            ("Tipo del caso", 800),
            ("Motivo de contacto", 800),
            ("Tipología", 800),
            ("Subtipología", 800),
            ("Tipología 1", 800),
            ("Línea de negocio", 800),
            ("Familia de Producto | Servicio", 800),
            ("Origen del caso", 800),
            ("Última fecha hora de modificación de caso", 800),
            ("Última modificación de caso realizada por", 800),
            ("Creado por", 800),
            ("Sector", 800),
            ("Tipo de solicitud", 800),
            ("Departamento", 800),
            ("Confidencial", 800),
            ("SubSegmento Global", 800),
            ("To Address", 800),
            ("Correo electrónico Web", 800),
            ("Asignado a", 800),
        ],
        tipos={5: FF_FECHA},
    ),
)

ARCHIVO_NOMBRE_CONTACTO = ArchivoSpec(
    "Reporte_Nombre_Contacto_Casos_Chile.csv",
    CARPETA_AUXILIARES,
    "Nombre Contacto Chile",
    _str(
        [
            ("Número del caso", 50),
            ("Nombre del contacto", 800),
            ("Contacto  Correo electrónico", 800),
            ("Contacto  Teléfono", 800),
            ("Móvil", 800),
        ]
    ),
)

ARCHIVO_CASOS_B = ArchivoSpec(
    "Reporte_Casos_B_Chile.csv",
    CARPETA_SEGUIMIENTO,
    "Casos B Chile",
    _str(
        [
            ("Número del caso", 400),
            ("Fecha de Solicitud Cliente", 400),
            ("Subtipo de solicitud", 400),
            ("Tipo", 400),
            ("Prioridad", 400),
            ("Tipo de solicitud", 400),
            ("Activo", 400),
            ("Tipo de registro del cliente", 400),
            ("Solución del caso", None),
            ("Complejidad", 400),
            ("Ámbito", 400),
            ("Id de la oportunidad", 400),
            ("Función del propietario del caso", 400),
            ("Etapa de la oportunidad", 400),
        ],
        tipos={8: FF_TEXT},
    ),
)

_DF_CASOS = "Package\\CARGA BASE CASOS SALESFORCE\\CARGA TEMPORAL CASOS"
_DF_CASOS_B = "Package\\CARGA BASE CASOS B SALESFORCE\\CARGA TEMPORAL CASOS B"

FLUJO_TEMP_NOMBRE_CONTACTO = FlujoSpec(
    _DF_CASOS,
    "Temp_Nombre_Contacto",
    ARCHIVO_NOMBRE_CONTACTO,
    "TBL_SALESFORCE_DATOS_CONTACTO",
    (
        ColumnaDestino("Número del caso", 0, _w(15)),
        ColumnaDestino("Nombre de contacto", 1, _w(150)),
        ColumnaDestino("Correo Electrónico Contacto", 2, _w(100)),
        ColumnaDestino("Teléfono Contacto", 3, _w(30)),
        ColumnaDestino("Móvil Contacto", 4, _w(30)),
    ),
    tablock=False,
)

FLUJO_TEMP_REPORTE_CASOS = FlujoSpec(
    _DF_CASOS,
    "Temp_Reporte_Casos",
    ARCHIVO_CASOS,
    "TBL_SALESFORCE_CASOS",
    (
        ColumnaDestino("To Address", 39, _w(800)),
        ColumnaDestino("Identificador FS Local", 2, _w(100)),
        ColumnaDestino("Cantidad", 3, _w(6)),
        ColumnaDestino("Fecha/Hora de apertura", 4, _w(25)),
        ColumnaDestino("Fecha de recepción", 5, _w(25)),
        ColumnaDestino("Fecha/hora de resolución", 6, _w(25)),
        ColumnaDestino("Fecha/Hora de cierre", 7, _w(25)),
        ColumnaDestino("Abierto", 8, _w(10)),
        ColumnaDestino("Estado", 9, _w(50)),
        ColumnaDestino("Motivos del estado", 10, _w(60)),
        ColumnaDestino("Propietario del caso", 11, _w(100)),
        ColumnaDestino("Asesor", 12, _w(100)),
        ColumnaDestino("Asignado a", 41, _w(50)),
        ColumnaDestino("No. identificación fiscal", 13, _w(25)),
        ColumnaDestino("Nombre del cliente", 16, _w(200)),
        ColumnaDestino("Id. del cliente legado", 14, _w(25)),
        ColumnaDestino("Subterritorio", 18, _w(50)),
        ColumnaDestino("Segmento Global", 15, _w(50)),
        ColumnaDestino("Subsegmento local", 19, _w(50)),
        ColumnaDestino("Territorio", 20, _w(100)),
        ColumnaDestino("Categoría del cliente", 21, _w(50)),
        ColumnaDestino("Asunto", 22, _w(400)),
        ColumnaDestino("Tipo del caso", 23, _w(25)),
        ColumnaDestino("Motivo de contacto", 24, _w(50)),
        ColumnaDestino("Tipología", 25, _w(100)),
        ColumnaDestino("Subtipología", 26, _w(150)),
        ColumnaDestino("Línea de negocio", 28, _w(50)),
        ColumnaDestino("Familia de Producto | Servicio", 29, _w(100)),
        ColumnaDestino("Origen del caso", 30, _w(50)),
        ColumnaDestino("Última fecha/hora de modificación de caso", 31, _w(25)),
        ColumnaDestino("Última modificación de caso realizada por", 32, _w(100)),
        ColumnaDestino("Creado por", 33, _w(100)),
        ColumnaDestino("Sector", 34, _w(200)),
        ColumnaDestino("Tipo Solicitud", 35, _w(100)),
        ColumnaDestino("Departamento", 36, _w(50)),
        ColumnaDestino("Confidencialidad", 37, _w(10)),
        ColumnaDestino("Subsegmento Global", 38, _w(50)),
        ColumnaDestino("Tipología 2", 27, _w(100)),
        ColumnaDestino("Cliente principal", 17, _w(150)),
        ColumnaDestino("Número del caso", 0, _w(10)),
        ColumnaDestino("Correo Electronico Web", 40, _w(100)),
        ColumnaDestino("Número de caso principal", 1, _w(15)),
    ),
    tablock=False,
    cruce=CruceSpec(
        "Package\\CARGA BASE CASOS SALESFORCE\\Agrega Nombre de Contacto",
        FLUJO_TEMP_NOMBRE_CONTACTO,
        "Número del caso",
        ("Nombre de contacto", "Correo Electrónico Contacto", "Teléfono Contacto", "Móvil Contacto"),
    ),
)

FLUJO_TEMP_CASOS_B = FlujoSpec(
    _DF_CASOS_B,
    "OLE DB Destination",
    ARCHIVO_CASOS_B,
    "TBL_SALESFORCE_CASOS_B",
    (
        ColumnaDestino("Fecha de Solicitud Cliente", 1, _w(25)),
        ColumnaDestino("Subtipo de solicitud", 2, _w(100)),
        ColumnaDestino("Tipo", 3, _w(40, truncamiento_ignora=True)),
        ColumnaDestino("Prioridad", 4, _w(25)),
        ColumnaDestino("Tipo de solicitud", 5, _w(70)),
        ColumnaDestino("Activo", 6, _w(5)),
        ColumnaDestino("Tipo de registro del cliente", 7, _w(25)),
        ColumnaDestino("Solución del caso", 8, Conversion(NTEXT, error_ignora=True, truncamiento_ignora=True)),
        ColumnaDestino("Id de la oportunidad", 11, _w(80)),
        ColumnaDestino("Complejidad", 9, _w(15)),
        ColumnaDestino("Función del propietario del caso", 12, _w(100)),
        ColumnaDestino("Etapa de la oportunidad", 13, _w(80)),
        ColumnaDestino("Número del caso", 0, Conversion(STR1252, 10), left=10),
        ColumnaDestino("Ámbito", 10, Conversion(NTEXT)),
    ),
    tablock=False,
)

# =========================================================================== #
# CL_Seguimiento_03_Proc_Carga_Correos.dtsx
# =========================================================================== #
ARCHIVO_CORREOS = ArchivoSpec(
    "Reporte_Correos_Chile.csv",
    CARPETA_SEGUIMIENTO,
    "Reporte Correos Perú",
    _str(
        [
            ("Dirección De", 800),
            ("Dirección Para", 800),
            ("Fecha del mensaje de correo electrónico", 50),
            ("Número del caso", 800),
            ("No  identificación fiscal", 800),
            ("Es Entrante", 800),
            ("Asunto del correo electrónico", None),
            ("Origen del caso", 800),
            ("Creado por", 800),
            ("Estado del correo electrónico", 800),
        ],
        tipos={6: FF_TEXT},
    ),
)

FLUJO_TEMP_CORREOS = FlujoSpec(
    "Package\\CARGA BASE CORREOS SALESFORCE\\CARGA TEMPORAL CORREOS",
    "Destino de OLE DB",
    ARCHIVO_CORREOS,
    "TBL_SALESFORCE_REPORTE_CORREOS",
    (
        ColumnaDestino("De", 0, _w(100)),
        ColumnaDestino("Para", 1, _w(400)),
        ColumnaDestino("Fecha correo", 2, Conversion(FECHA)),
        ColumnaDestino("Número del caso", 3, _w(15)),
        ColumnaDestino("RUC", 4, _w(25)),
        ColumnaDestino("Es Entrante", 5, Conversion(NUMERICO)),
        ColumnaDestino("Asunto del correo electrónico", 6, Conversion(NTEXT)),
        ColumnaDestino("Origen del caso", 7, _w(50)),
        ColumnaDestino("Creado por", 8, _w(50)),
        ColumnaDestino("Estado del correo electrónico", 9, _w(15)),
    ),
    tablock=True,
    # 'Columna derivada': REPLACE([Fecha del mensaje de correo electronico], ".<NBSP>m.", "M")
    reemplazos=((2, ".\xa0m.", "M"),),
)

# =========================================================================== #
# CL_Seguimiento_04_Proc_Carga_Historial_Casos.dtsx
# =========================================================================== #
ARCHIVO_HISTORIAL = ArchivoSpec(
    "Reporte_Historial_Casos_Chile.csv",
    CARPETA_SEGUIMIENTO,
    "Historial Casos Chile",
    _str(
        [
            ("Número del caso", 400),
            ("Modificado por", 400),
            ("Fecha de modificación", 400),
            ("Campo   Evento", 400),
            ("Valor anterior", 400),
            ("Valor nuevo", 400),
        ]
    ),
)

FLUJO_TEMP_HISTORIAL = FlujoSpec(
    "Package\\CARGA BASE TEMPORAL HISTORIAL CASOS\\CARGA TEMPORAL HISTORIAL",
    "OLE DB Destination",
    ARCHIVO_HISTORIAL,
    "TBL_SALESFORCE_HISTORIAL_CASOS",
    (
        ColumnaDestino("Número del caso", 0, _w(15)),
        ColumnaDestino("Modificado por", 1, _w(100)),
        ColumnaDestino("Fecha de modificación", 2, Conversion(FECHA)),
        ColumnaDestino("Campo / Evento", 3, _w(50)),
        ColumnaDestino("Valor anterior", 4, _w(300)),
        ColumnaDestino("Valor nuevo", 5, _w(300)),
    ),
    tablock=True,
)

# =========================================================================== #
# CL_Seguimiento_06_Proc_Carga_Historial_Comentarios.dtsx
# =========================================================================== #
ARCHIVO_COMENTARIOS = ArchivoSpec(
    "Reporte_Comentarios_Casos_Chile.csv",
    CARPETA_SEGUIMIENTO,
    "Historial Comentarios Chile",
    _str(
        [
            ("Número del caso", 400),
            ("Comentario del caso creado por", 400),
            ("Fecha de creación de Comentario del caso", 400),
            ("Caso público comentado", 400),
            ("Comentarios del caso", 5000),
        ]
    ),
)

FLUJO_TEMP_COMENTARIOS = FlujoSpec(
    "Package\\CARGA BASE TEMPORAL HISTORIAL COMENTARIOS\\CARGA TEMPORAL COMENTARIOS",
    "OLE DB Destination",
    ARCHIVO_COMENTARIOS,
    "TBL_SALESFORCE_HISTORIAL_COMENTARIOS",
    (
        ColumnaDestino("Comentario del caso creado por", 1, _w(100)),
        ColumnaDestino("Fecha de creación de Comentario del caso", 2, Conversion(FECHA)),
        ColumnaDestino("Comentarios del caso", 4, Conversion(NTEXT)),
        # 'Derived Column' CASO = LEFT([Numero del caso],10) (DT_WSTR 10), sin Data Conversion
        ColumnaDestino("Número del caso", 0, _w(10), left=10),
        # 'Derived Column' Caso comentado = LEFT([Caso publico comentado],5) (DT_WSTR 5)
        ColumnaDestino("Caso público comentado", 3, _w(5), left=5),
    ),
    tablock=True,
    # CORRECCION (pedida por el usuario 2026-10-26; desviacion intencional de
    # SSIS): el MERGE compara la staging nvarchar con el varchar(6000) de
    # TBL_HISTORIAL_COMENTARIOS. Un comentario con un caracter no
    # representable en cp1252 se guarda con '?' y nunca vuelve a coincidir:
    # SSIS lo reinsertaba en cada corrida (437.639 copias al 2026-10-26). La
    # #temporal guarda el texto ya con el tipo/collation del destino, asi el
    # valor comparado es exactamente el que queda guardado. El T-SQL del
    # .dtsx no cambia; lo que se inserta en el destino tampoco (SQL Server
    # hacia esa misma conversion al insertar).
    tipos_temporal=(("Comentarios del caso", "varchar(max) COLLATE Modern_Spanish_CI_AS"),),
)

# Tarea 'Carga Descripciones NC' (Execute Process -> Carga_Reporte_Descripciones_NC_Chile.py).
# El Flat File Connection Manager 'Descripciones NC' existe en el paquete pero
# ningun Data Flow lo usa: el script lee el CSV con pandas.
ARCHIVO_DESCRIPCIONES_NC = ArchivoSpec(
    "Reporte_Descripciones_NC_Chile.csv",
    CARPETA_AUXILIARES,
    "Descripciones NC",
    (ColumnaArchivo("Número del caso", FF_STR, 50), ColumnaArchivo("Descripción", FF_STR, 4000)),
)
TABLA_DESCRIPCIONES_NC = "TBL_DESCRIPCIONES_NC"
COLUMNAS_DESCRIPCIONES_NC = ("Número del caso", "Descripción")  # df.columns = [...] del script
SP_FOLIOS_NC = "EXEC [CL_SEGUIMIENTO_ACTUAL].[dbo].[SP_FOLIOS_NC]"  # cursor.execute("EXEC dbo.SP_FOLIOS_NC") en CL_SEGUIMIENTO_ACTUAL

# Destinos que se cargan (Nombre Contacto entra via el cruce de REPORTE_CASOS).
TODOS_LOS_FLUJOS = (
    FLUJO_TEMP_REPORTE_CASOS,
    FLUJO_TEMP_CASOS_B,
    FLUJO_TEMP_CORREOS,
    FLUJO_TEMP_HISTORIAL,
    FLUJO_TEMP_COMENTARIOS,
)

# Staging que se reemplazan por #temporales de la sesion del paquete.
TABLAS_TEMPORALES = tuple(f.tabla for f in TODOS_LOS_FLUJOS)
# Staging que el .dtsx usa y la migracion ya no necesita (ver EQUIVALENCIA.md).
TABLAS_ELIMINADAS = ("TBL_SALESFORCE_DATOS_CONTACTO", "TBL_SALESFORCE_CASOS_TIPIFICACIONES")
