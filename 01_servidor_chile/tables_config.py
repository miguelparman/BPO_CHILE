"""
Tablas a extraer del servidor y su campo de fecha para filtrar los ultimos
periodos (meses) que contenga cada tabla (por defecto los 2 ultimos, ver
"periods").

Para agregar una tabla nueva, suma una entrada con:
  - table:      nombre completo y calificado, entre corchetes
  - date_field: campo (entre corchetes) que se usa para determinar el mes.
                Dejar "" (vacio) para descargar la tabla completa, sin
                filtrar por periodos (ej. base_saip).
  - is_datetime: True cuando date_field es un datetime completo (con hora/
                segundos) en vez de un codigo YYYYMM. En ese caso se agrupa
                por mes (FORMAT(campo, 'yyyyMM')) antes de tomar los ultimos
                periodos, porque los valores exactos casi nunca se
                repiten y "2 valores distintos" no equivaldria a "2 meses"
                (ej. CALLBACK.[FECHA]). Se puede omitir; por defecto es False.
  - periods:    cantidad de periodos (meses) distintos mas recientes a
                descargar. Se puede omitir; por defecto son 2. No aplica
                cuando date_field esta vacio (se descarga la tabla completa).
"""

TABLES = [

    {"table": "[Externos_Frac].[dbo].[ENCUESTA]", "date_field": "[periodo_evento]"},
    {"table": "[Externos_Frac].[dbo].[WS_MEDALLIA_2]", "date_field": "[Periodo]"},
    {"table": "[Externos_Frac].[dbo].[ABANDONO]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[ATENDIDA]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[CALLBACK]", "date_field": "[FECHA]", "is_datetime": True},
    {"table": "[Externos_Frac].[dbo].[CLEARED]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[OUTBOUND]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[RECIBIDA]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[TRANSFER]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[cross_inbound]", "date_field": "[DATE_YYYYMM]"},
    {"table": "[Externos_Frac].[dbo].[INTEN_AMDOCS]", "date_field": "[periodo]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[RUT_marca_cartera]", "date_field": ""},
    {"table": "[Externos_Frac].[dbo].[BAJAS_FIJO]", "date_field": "[YEAR_MONTH]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[BAJAS_FRAUDE]", "date_field": "[PERIODO]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[BAJAS_MOVIL]", "date_field": "[PERIODO]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[BAJAS_POR_ALTA_FO]", "date_field": "[PERIODO]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[BD_RETEN_V2]", "date_field": "[periodo]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[INTENCIONES_V2]", "date_field": "[PERIODO]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[pqe_fijtot2023]", "date_field": "[periodo]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[pqe_movtot2023]", "date_field": "[periodo]", "periods": 3},
    {"table": "[Externos_Frac].[dbo].[base_saip]", "date_field": ""},
    
]
