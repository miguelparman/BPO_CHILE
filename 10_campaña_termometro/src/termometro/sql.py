"""
Rutas de los scripts T-SQL del proceso (carpeta scripts_sql/).

Cada script reemplaza un Execute SQL Task del .dtsx y usa parámetros nombrados
(:param) que se bindean con SQLAlchemy en db.run_sql_file. El prefijo numérico
indica el orden en que se ejecutan.
"""
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent / "scripts_sql"

# Execute SQL Task del .dtsx                                     -> script
DELETE_PERIODO_SF = SQL_DIR / "10_delete_periodo_sf.sql"  # SALESFORCE 1\DELETE PERIODO
DELETE_FUERA_RANGO = SQL_DIR / "20_delete_fuera_rango.sql"  # SALESFORCE 1\DELETE FUERA DE RANGO
UPDATE_ESTADO = SQL_DIR / "30_update_estado.sql"  # SALESFORCE 1\UPDATE ESTADO
UPDATE_PESO = SQL_DIR / "40_update_peso.sql"  # SALESFORCE 1\UPDATE PESO
DELETE_PERIODO_EVALUACION = SQL_DIR / "50_delete_periodo_evaluacion.sql"  # 162\DELETE PERIODO EN EVALUACION
INSERT_FINAL = SQL_DIR / "60_insert_final.sql"  # 162\TBL_CAMPAÑA_TERMOMETRO

# No es parte del .dtsx: lo usa tools/parity/snapshot.py
SELECT_PERIODO_FINAL = SQL_DIR / "90_select_periodo_final.sql"
