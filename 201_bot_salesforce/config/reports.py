"""
Catalogo de informes de Salesforce a descargar y subir a SharePoint.

Para agregar un nuevo informe, agrega un nuevo diccionario a REPORTS.
No se requiere modificar ningun otro archivo del proyecto.

Claves por informe:
    name (obligatoria): nombre final del archivo CSV.
    url (obligatoria): URL del informe en Salesforce Lightning.
    sharepoint_folder_path (opcional): subcarpeta de SharePoint para ESTE
        informe, dentro del mismo site/drive de siempre (ReportingFractalia
        / Data Reporting). Si se omite, usa el destino global
        (SHAREPOINT_FOLDER_PATH / app/config.py).
    local_copy_dir (opcional): carpeta local/de red para ESTE informe. Si
        se omite, usa el destino global (LOCAL_COPY_DIR / app/config.py).
"""

REPORTS = [
    {
        "name": "Reporte_Casos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I0000021qD1UAI/view",
        # Ejemplo de destino propio (opcional, no necesario para este informe):
        # "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/CL_CASOS",
        # "local_copy_dir": r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\CASOS",
    },
    {
        "name": "Reporte_Tipificaciones_Casos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001EpztUAC/view",
    },
    {
        "name": "Reporte_Nombre_Contacto_Casos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001xlWKUAY/view",
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/12 AUXILIARES",
    },
    {
        "name": "Reporte_Historial_Casos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I0000021qD7UAI/view",
    },
    {
        "name": "Reporte_Comentarios_Casos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I0000021qDBUAY/view",
    },

    {
        "name": "Reporte_Casos_B_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I0000021qETUAY/view",
    },
    {
        "name": "Reporte_Correos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001gu6bUAA/view",
    },
    {
        "name": "Reporte_Descripciones_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00OSd00000Q7taHMAR/view",
    },

    {
        "name": "Reporte_Descripciones_NC_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00OJ8000000O2PGMA0/view",
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/12 AUXILIARES",
    },
    {
        "name": "Reporte_Usuarios_SF.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00OSd00000CwT7gMAF/view",
    },

    {
        "name": "Reporte_Historico_Contactos_Chile.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00OSd00000WRfW5MAL/view",
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/12 AUXILIARES",
    },
    {
        "name": "Chi_cola_reclamo_aux_propietario.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00OSd00000Av0vEMAR/view",
        # Ejemplo de destino propio (opcional, no necesario para este informe):
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/09 RECLAMOS",
        "local_copy_dir": r"D:\OneDrive - IRISCENE ENGINEERING CORPORATION SLU\Insumos Chile\ETL\PYTHON\repository\Reclamos",
    },
    {
        "name": "Reporte_termometros.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I0000028vG9UAI/view",
        # Ejemplo de destino propio (opcional, no necesario para este informe):
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/04 CAMPAÑAS/Termometro/SF",
        "local_copy_dir": r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\Campanhas\Termometro\SF",
    },

    # BLOQUE ISN
    # DESACTIVADOS (2026-11-13): 05_isn ya no carga estos dos archivos (ISN_CARGAR_AUX_CONTACTO / ISN_CARGAR_AUX_CLIENTE
    # = false): sus columnas solo llegan a TBL_ISN_SF, que nadie lee, y no pasan al isn.csv. Para volver a descargarlos,
    # descomentar estos dos informes Y poner esas variables en true en el .env de 05_isn.
    # {
    #     "name": "Reporte_isn_aux_contacto.csv",
    #     "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001EpdYUAS/view",
    #     # Ejemplo de destino propio (opcional, no necesario para este informe):
    #     "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/10 ISN",
    #     "local_copy_dir": r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\ISN\Aux_contacto",
    # },
    # {
    #     "name": "Reporte_isn_aux_cliente.csv",
    #     "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001EpdTUAS/view",
    #     # Ejemplo de destino propio (opcional, no necesario para este informe):
    #     "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/10 ISN",
    #     "local_copy_dir": r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\ISN\Aux_cliente",
    # },
    {
        "name": "Reporte_Contactos_Salesforce_BI.csv",
        "url": "https://telefonicab2b.lightning.force.com/lightning/r/Report/00O5I000001ozbaUAA/view",
        # Ejemplo de destino propio (opcional, no necesario para este informe):
        "sharepoint_folder_path": "REPOSITORIOS DE CRUDOS/CHILE/BPOCHIPE/11 CONTACTOS",
        "local_copy_dir": r"D:\IRISCENE ENGINEERING CORPORATION SLU\BPO - Insumos\Chile\Reporte Contactos Salesforce BI",
    },

]
