from io import BytesIO

import pandas as pd

from extraccion.csv_extractor import read_salesforce_csv
from extraccion.excel_extractor import read_excel_sheet
from extraccion.fuentes import FuenteLocal


def test_csv_desde_bytes_latin1_y_vacios_nulos():
    contenido = '"No. identificación fiscal","Comentarios"\n"123","Sí"\n"456",""\n'.encode("latin-1")
    df = read_salesforce_csv(contenido)
    assert list(df.columns) == ["No. identificación fiscal", "Comentarios"]
    assert df.iloc[0]["Comentarios"] == "Sí"
    assert pd.isna(df.iloc[1]["Comentarios"])
    assert df.iloc[0]["No. identificación fiscal"] == "123"  # todo como texto


def test_excel_desde_bytes_lee_la_hoja_pedida():
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"RUT_DV": ["1-9"]}).to_excel(writer, sheet_name="DB", index=False)
        pd.DataFrame({"PERIODO": [202609], "RUT_SIN_DV": ["19"]}).to_excel(writer, sheet_name="DB_DETRACTOR", index=False)
    df = read_excel_sheet(buffer.getvalue(), "DB_DETRACTOR")
    assert list(df.columns) == ["PERIODO", "RUT_SIN_DV"]


def test_fuente_local_devuelve_bytes(tmp_path):
    archivo = tmp_path / "x.csv"
    archivo.write_bytes(b"abc")
    fuente = FuenteLocal(archivo)
    assert fuente.leer() == b"abc"
    assert fuente.descripcion == str(archivo)
