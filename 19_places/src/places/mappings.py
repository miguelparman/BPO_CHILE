"""Especificacion declarativa de CL_Proc_Carga_Places.dtsx (constantes del paquete).

Control Flow (Precedence Constraints, todas Success):

    Log Inicio -> CARGA PLACES [TRUNCA TABLA -> CARGA TABLA -> LIMPIA TABLA]
               -> CARGA PLACES HISTORICO [ELIMINA FECHA ACTUAL TABLA -> CARGA TABLA]
               -> Log Fin

Tipos del .dtsx:
  - Excel Source 'Hoja1$' (HDR=YES): las 7 columnas son DT_WSTR(255).
  - Conversion de datos: 6 columnas -> DT_STR(n) code page 1252, con
    FailComponent en error y en truncamiento. 'Correo Electronico' se lee
    pero no se convierte ni se carga.
  - OLE DB Destination [dbo].[TBL_PLACES] (fast load, TABLOCK,CHECK_CONSTRAINTS).
    'Fecha Ingeso Empresa' y 'Fecha Baja Empresa' (DT_STR(8)) no se mapean:
    llegan NULL y las completa 'LIMPIA TABLA'.
  - Variable User::Fecha_Actual (yyyy-mm-dd de GETDATE()), enlazada como
    DT_DATE al parametro de las dos tareas del historico.
"""

from __future__ import annotations

from dataclasses import dataclass

HOJA = "Hoja1"  # OpenRowset 'Hoja1$' (HDR=YES)
CODE_PAGE = "cp1252"

# Excel Source: archivo (antes en disco, ahora en SharePoint ReportingFractalia).
RUTA_ORIGINAL = r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\SEGUIMIENTO\Place utilizados.xlsx"
CARPETA_REPORTING = "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/05 CARTERA"
ARCHIVO = "Place utilizados.xlsx"
RUTA_REPORTING = f"{CARPETA_REPORTING}/{ARCHIVO}"

# Tablas usadas por el paquete.
TABLA_PLACES = "TBL_PLACES"
TABLA_HISTORICO = "TBL_HISTORICO_PLACES"
TABLA_PERSONAL = ("BBDD_GENERAL", "TBL_PERSONAL_CONSOLIDADO")
TABLA_LOGS = ("BBDD_GENERAL", "LOGS_PROCESOS")

NOMBRE_PROCESO = "Proc_Carga_Places"  # [Nombre] en LOGS_PROCESOS


@dataclass(frozen=True)
class ColumnaSpec:
    origen: str  # columna del Excel (Excel Source)
    destino: str  # columna de TBL_PLACES (OLE DB Destination)
    ancho: int  # DT_STR(n), code page 1252


# Orden = orden de columnas del INSERT. Todas FailComponent (error y truncamiento).
COLUMNAS: tuple[ColumnaSpec, ...] = (
    ColumnaSpec("id", "ID", 8),
    ColumnaSpec("Etiqueta", "Etiqueta", 30),
    ColumnaSpec("plataforma", "Plataforma", 30),
    ColumnaSpec("RUT", "Rut", 50),
    ColumnaSpec("Asesor", "Asesor", 100),
    ColumnaSpec("DNI", "DNI", 15),
)
# Columnas que el Excel Source entrega al Data Flow (la ultima no se carga).
COLUMNAS_ORIGEN: tuple[str, ...] = tuple(c.origen for c in COLUMNAS) + ("Correo Electronico",)
COLUMNAS_DESTINO: tuple[str, ...] = tuple(c.destino for c in COLUMNAS)
# Columnas de TBL_PLACES completadas por 'LIMPIA TABLA'.
COLUMNAS_LIMPIA: tuple[str, ...] = ("Fecha Ingeso Empresa", "Fecha Baja Empresa")

# --- Execute SQL Tasks: T-SQL literal del .dtsx -------------------------------------------------
SQL_TRUNCATE = "TRUNCATE TABLE [CL_DATA].[dbo].[TBL_PLACES]"

SQL_LIMPIA = """DELETE FROM [CL_DATA].[dbo].[TBL_PLACES]
WHERE ID IS NULL

UPDATE X0
SET 
[ID] = LTRIM(RTRIM([ID])),
[Etiqueta] = LTRIM(RTRIM([Etiqueta])),
[Plataforma] = LTRIM(RTRIM([Plataforma])),
[Rut] = CASE WHEN [Rut] = '' THEN NULL ELSE LTRIM(RTRIM([Rut]))END,
[Asesor] = LTRIM(RTRIM([Asesor])),
DNI=X1.DNI,
[Fecha Ingeso Empresa]=CONVERT(VARCHAR(8),X1.[Fecha Ingreso a la Empresa],112),
[Fecha Baja Empresa]= CASE WHEN x1.[Fecha de Baja] is not null then CONVERT(VARCHAR(8),x1.[Fecha de Baja],112) ELSE CONVERT(VARCHAR(8),GETDATE(),112) END
FROM [CL_DATA].[dbo].[TBL_PLACES] X0
LEFT JOIN (SELECT XA.* FROM(SELECT *,ROW_NUMBER() OVER(PARTITION BY DNI ORDER BY PERIODO DESC)Orden
FROM [BBDD_GENERAL].[dbo].[TBL_PERSONAL_CONSOLIDADO])XA WHERE Orden = 1) X1
ON CAST(X0.DNI AS INT) = CAST(X1.DNI AS INT)

/*SELECT [DNI], COUNT(*) FROM [CL_DATA].[dbo].[TBL_PLACES]
GROUP BY [DNI]
HAVING COUNT([DNI])>1*/"""

SQL_HISTORICO_ELIMINA = """DELETE [CL_DATA].[dbo].[TBL_HISTORICO_PLACES]
WHERE [Fecha Impacto] = ?"""  # ? = User::Fecha_Actual (DT_DATE)

SQL_HISTORICO_INSERTA = """INSERT INTO [CL_DATA].[dbo].[TBL_HISTORICO_PLACES]
SELECT 
[ID]
,[DNI]
,[Fecha Ingeso Empresa]
,[Fecha Baja Empresa]
,[Asesor]
,[Etiqueta]
,[Plataforma]
,[Rut]
,?
FROM [CL_DATA].[dbo].[TBL_PLACES]"""  # ? = User::Fecha_Actual (DT_DATE)

SQL_LOG_INICIO = """DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE() 

SET DATEFORMAT DMY

INSERT  INTO [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] (Proceso,Nombre,Estado,[Fecha Inicio],[Fecha Fin])
(
  SELECT 'ETL','Proc_Carga_Places','exec...',@FECHA_EJECUCION_ETL,NULL
)"""

SQL_LOG_FIN = """DECLARE @FECHA_EJECUCION_ETL DATETIME
SET @FECHA_EJECUCION_ETL = GETDATE() 

SET DATEFORMAT DMY

UPDATE [BBDD_GENERAL].[dbo].[LOGS_PROCESOS]
SET [Estado] = 'OK',
    [Fecha Fin] = @FECHA_EJECUCION_ETL
WHERE [Fecha Inicio] = (SELECT MAX([Fecha Inicio]) FROM [BBDD_GENERAL].[dbo].[LOGS_PROCESOS] WHERE [Nombre] = 'Proc_Carga_Places')
AND [Nombre] = 'Proc_Carga_Places'"""
