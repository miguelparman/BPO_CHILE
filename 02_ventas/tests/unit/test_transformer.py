import pandas as pd
import pytest

import mappings
import transformacion.transformer as transformer
from exceptions import ValidacionError
from models import ColumnaSpec
from tests.unit.fakes import FakeDatabaseGateway


def test_seleccionar_columnas_descarta_columnas_no_esperadas():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    resultado = transformer.seleccionar_columnas(df, ("A", "C"))
    assert list(resultado.columns) == ["A", "C"]


def test_convertir_tipos_numero_estricto_levanta_si_no_parsea():
    columnas = (ColumnaSpec("N", estricto=True, tipo="numero"),)
    df = pd.DataFrame({"N": ["12", "no-numero"]})
    with pytest.raises(ValidacionError):
        transformer.convertir_tipos(df, columnas)


def test_convertir_tipos_numero_no_estricto_coerciona_a_null():
    columnas = (ColumnaSpec("N", estricto=False, tipo="numero"),)
    df = pd.DataFrame({"N": ["12", "no-numero"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["N"].iloc[0] == 12
    assert pd.isna(resultado["N"].iloc[1])


def test_convertir_tipos_entero_redondea_y_descarta_decimales():
    columnas = (ColumnaSpec("N", estricto=True, tipo="entero"),)
    df = pd.DataFrame({"N": ["12.4", "12.6"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["N"].iloc[0] == 12
    assert resultado["N"].iloc[1] == 13
    assert resultado["N"].dtype == "Int64"


def test_convertir_tipos_entero_no_estricto_coerciona_a_null():
    columnas = (ColumnaSpec("N", estricto=False, tipo="entero"),)
    df = pd.DataFrame({"N": ["12", "no-numero"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["N"].iloc[0] == 12
    assert pd.isna(resultado["N"].iloc[1])


def test_convertir_tipos_fecha_no_estricto_coerciona_a_null():
    columnas = (ColumnaSpec("F", estricto=False, tipo="fecha"),)
    df = pd.DataFrame({"F": ["2026-01-01", "no-fecha"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert not pd.isna(resultado["F"].iloc[0])
    assert pd.isna(resultado["F"].iloc[1])


def test_convertir_tipos_fecha_iso_con_primer_dia_menor_a_13_no_invierte_dia_mes():
    # Caso real 2026-10-02: primeras filas de octubre (dia <=12) hacian que
    # pandas infiriera '%Y-%d-%m' con dayfirst=True.
    columnas = (ColumnaSpec("F", estricto=True, tipo="fecha"),)
    df = pd.DataFrame({"F": [None, "2026-10-02 00:00:00", "2026-09-30 00:00:00"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["F"].iloc[1] == pd.Timestamp("2026-10-02").date()
    assert resultado["F"].iloc[2] == pd.Timestamp("2026-09-30").date()
    assert pd.isna(resultado["F"].iloc[0])


def test_convertir_tipos_fecha_texto_chileno_es_dia_primero():
    columnas = (ColumnaSpec("F", estricto=True, tipo="fecha"),)
    df = pd.DataFrame({"F": ["2/10/2026", "22/7/2026"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["F"].iloc[0] == pd.Timestamp("2026-10-02").date()
    assert resultado["F"].iloc[1] == pd.Timestamp("2026-07-22").date()


def test_convertir_tipos_texto_no_estricto_trunca_en_silencio():
    columnas = (ColumnaSpec("T", 3, estricto=False),)
    df = pd.DataFrame({"T": ["abcdef"]})
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["T"].iloc[0] == "abc"


def test_seleccionar_y_renombrar_senhalizaciones_descarta_columnas_no_mapeadas():
    columnas_csv = {origen for origen, _destino in mappings.MAPEO_SENHALIZACIONES}
    fila = {c: "x" for c in columnas_csv}
    fila["TOTAL INGRESADO"] = "999"  # no mapeada, debe descartarse
    df = pd.DataFrame([fila])

    resultado = transformer.seleccionar_y_renombrar_senhalizaciones(df)

    assert "TOTAL INGRESADO" not in resultado.columns
    assert "TU DNI" in resultado.columns
    assert "MÚMERO DEL CUAL LLAMA" in resultado.columns  # typo real de la tabla, preservado


def test_corregir_rut_nombre_invertidos_intercambia_cuando_nombre_parece_rut():
    df = pd.DataFrame(
        {
            "RUT DE LA EMPRESA": ["SOCIEDAD INTEGRADORA DE TECNOLOGIAS GLOBALES CHILE S A", "12345678-9"],
            "NOMBRE EMPRESA": ["76065418-3", "EMPRESA NORMAL SPA"],
        }
    )
    resultado = transformer.corregir_rut_nombre_invertidos(df)
    assert resultado["RUT DE LA EMPRESA"].iloc[0] == "76065418-3"
    assert resultado["NOMBRE EMPRESA"].iloc[0] == "SOCIEDAD INTEGRADORA DE TECNOLOGIAS GLOBALES CHILE S A"
    # La segunda fila ya estaba correcta (RUT parece RUT) -- no se toca.
    assert resultado["RUT DE LA EMPRESA"].iloc[1] == "12345678-9"
    assert resultado["NOMBRE EMPRESA"].iloc[1] == "EMPRESA NORMAL SPA"


def test_vaciar_valores_que_excedan_ancho_deja_vacio_sin_descartar_la_fila():
    columnas = (ColumnaSpec("RUT DE LA EMPRESA", 15, estricto=True),)
    df = pd.DataFrame(
        {
            "RUT DE LA EMPRESA": ["12345678-9", "alejandramotato12@gmail.com"],
            "otra": ["x", "y"],
        }
    )
    resultado = transformer.vaciar_valores_que_excedan_ancho(df, columnas, "test")
    assert len(resultado) == 2  # no se descarta ninguna fila
    assert resultado["RUT DE LA EMPRESA"].iloc[0] == "12345678-9"
    assert pd.isna(resultado["RUT DE LA EMPRESA"].iloc[1])
    assert resultado["otra"].iloc[1] == "y"  # el resto de la fila se conserva


def test_vaciar_valores_que_excedan_ancho_ignora_columnas_numericas_y_fecha():
    columnas = (ColumnaSpec("N", estricto=True, tipo="numero"),)
    df = pd.DataFrame({"N": ["123456789012345678901234567890"]})
    resultado = transformer.vaciar_valores_que_excedan_ancho(df, columnas, "test")
    assert resultado["N"].iloc[0] == "123456789012345678901234567890"  # no se toca


def test_vaciar_valores_que_excedan_ancho_ignora_columnas_no_estrictas():
    """Las columnas 'estricto=False' (IgnoreFailure) no se vacian aqui --
    quedan intactas para que convertir_tipos() las trunque al ancho
    declarado en vez de perder el valor completo (ver
    'SEÑALIZACION // EJECUTIVO DE VENTAS', README)."""
    columnas = (ColumnaSpec("T", 3, estricto=False),)
    df = pd.DataFrame({"T": ["abcdef"]})
    resultado = transformer.vaciar_valores_que_excedan_ancho(df, columnas, "test")
    assert resultado["T"].iloc[0] == "abcdef"  # no se toca aqui


def test_convertir_tipos_texto_no_estricto_trunca_en_vez_de_vaciar_tras_vaciar_valores():
    """Reproduce el flujo real del pipeline: vaciar_valores_que_excedan_ancho()
    seguido de convertir_tipos() -- el valor de una columna IgnoreFailure
    debe llegar truncado, no vacio."""
    columnas = (ColumnaSpec("SEÑALIZACION // EJECUTIVO DE VENTAS", 15, estricto=False),)
    df = pd.DataFrame({"SEÑALIZACION // EJECUTIVO DE VENTAS": ["Juan Carlos Perez Soto"]})
    df = transformer.vaciar_valores_que_excedan_ancho(df, columnas, "test")
    resultado = transformer.convertir_tipos(df, columnas)
    assert resultado["SEÑALIZACION // EJECUTIVO DE VENTAS"].iloc[0] == "Juan Carlos Per"


def test_corregir_dni_cero_perdido_ejecuta_un_update_por_par():
    db = FakeDatabaseGateway()
    transformer.corregir_dni_cero_perdido(db)
    assert len(db.executed_scripts) == len(mappings.CORRECCIONES_DNI_CEROS)
    primer_sql, primeros_params = db.executed_scripts[0]
    assert "GO" not in primer_sql  # 'GO' no es SQL valido, se elimino al parametrizar
    assert primeros_params == mappings.CORRECCIONES_DNI_CEROS[0]


def test_renombrar_basev2_a_temp_descarta_tramo_ingreso_y_renombra():
    df = pd.DataFrame(
        {
            "Tramo Ingreso": ["A"],
            "Pusher": ["p"],
            "DNI SUPERVISOR": ["1"],
            "DNI ESPECIALISTA": ["2"],
            "COD_DNI": ["3"],
            "Fecha Ingreso": ["2026-01-01"],
        }
    )
    resultado = transformer.renombrar_basev2_a_temp(df)
    assert "Tramo Ingreso" not in resultado.columns
    assert "PUSHER" in resultado.columns and "Pusher" not in resultado.columns
    assert "DNI supervisor" in resultado.columns
    assert "DNI Especialista" in resultado.columns
    assert "DNI EJECUTIVO" in resultado.columns
    assert "Fecha Ingreso" in resultado.columns  # columna sin renombre, se mantiene


def test_limpiar_y_completar_basev2_ejecuta_las_5_sentencias_en_orden():
    db = FakeDatabaseGateway()
    transformer.limpiar_y_completar_basev2(db)
    assert len(db.executed_scripts) == 5
    assert "DELETE" in db.executed_scripts[0][0]
    assert "FECHA DE EVALUACION" in db.executed_scripts[4][0]


def test_completar_dni_sup_esp_cod_ejecuta_las_3_sentencias_en_orden():
    db = FakeDatabaseGateway()
    transformer.completar_dni_sup_esp_cod(db)
    assert len(db.executed_scripts) == 3
    assert "DNI SUPERVISOR" in db.executed_scripts[0][0]
    assert "DNI ESPECIALISTA" in db.executed_scripts[1][0]
    assert "COD_DNI" in db.executed_scripts[2][0]


def test_convertir_tipos_metas_castea_senalizacion_total_y_renombra():
    df = pd.DataFrame(
        {
            "Plataforma": ["p"], "Cargo": ["c"], "Nombre": ["n"], "BG_DNI": ["1"], "DNI": ["1"],
            "PUSHER A CARGO": ["x"], "Fibra": [1.0], "Voz": [2.0], "Total": [3.0], "PERIODO": [202608.0],
            "Señalizacion Total": ["4"],
        }
    )
    resultado = transformer.convertir_tipos_metas(df)
    assert "Señalizacion Total" not in resultado.columns
    assert resultado["SEÑALIZACIONES TOTAL"].iloc[0] == 4


def test_convertir_tipos_metas_levanta_si_senalizacion_total_no_es_numerico():
    df = pd.DataFrame(
        {
            "Plataforma": ["p"], "Cargo": ["c"], "Nombre": ["n"], "BG_DNI": ["1"], "DNI": ["1"],
            "PUSHER A CARGO": ["x"], "Fibra": [1.0], "Voz": [2.0], "Total": [3.0], "PERIODO": [202608.0],
            "Señalizacion Total": ["no-numero"],
        }
    )
    with pytest.raises(ValidacionError):
        transformer.convertir_tipos_metas(df)
