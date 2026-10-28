import pandas as pd
import pytest

from exceptions import ExtraccionError
from extraccion import extractor
from models import Periodo
from tests.unit.fakes import FakeSharePointCsvReader

import mappings


# ===========================================================================
# Parque (CSV: pqe_fijtot2023.csv / pqe_movtot2023.csv / RUT_marca_cartera.csv)
# ===========================================================================


def _reader_parque(fijo: pd.DataFrame, movil: pd.DataFrame, marca: pd.DataFrame) -> FakeSharePointCsvReader:
    return FakeSharePointCsvReader(
        {
            mappings.PARQUE_FIJO_ARCHIVO: fijo,
            mappings.PARQUE_MOVIL_ARCHIVO: movil,
            mappings.RUT_MARCA_CARTERA_ARCHIVO: marca,
        }
    )


def test_extraer_parque_filtra_por_mes_anterior_y_mapea_case():
    fijo = pd.DataFrame(
        [
            # periodo=202608 (>= piso 202607): entra.
            {"periodo": "202608", "segme": "Micro", "q_casos": "3", "tpo_prod": "BAF", "tecnologia": "FIBER", "rut": "123456785"},
            # periodo=202606 (< piso 202607): NO entra.
            {"periodo": "202606", "segme": "Micro", "q_casos": "9", "tpo_prod": "BAF", "tecnologia": "FIBER", "rut": "123456785"},
        ]
    )
    movil = pd.DataFrame(columns=["periodo", "segme", "tpo_prod", "rutcli"])
    marca = pd.DataFrame([{"rutcli": "12345678", "marca": "1"}])

    resultado = extractor.extraer_parque(_reader_parque(fijo, movil, marca), Periodo("202608"))

    fila_202608 = resultado[resultado["periodo"] == 202608].iloc[0]
    assert fila_202608["segme"] == "MICRO"
    assert fila_202608["tpo_prod"] == "FO"  # BAF + FIBER -> FO
    assert fila_202608["tipo"] == "FIJO"
    assert fila_202608["SERVICIO"] == "CARTERIZADOS"  # marca=1
    assert fila_202608["pqe"] == 3
    assert (resultado["periodo"] == 202606).sum() == 0


def test_extraer_parque_proyecta_el_periodo_maximo_al_siguiente():
    fijo = pd.DataFrame(
        [{"periodo": "202608", "segme": "Micro", "q_casos": "5", "tpo_prod": "BAF", "tecnologia": "FIBER", "rut": "123456780"}]
    )
    movil = pd.DataFrame(columns=["periodo", "segme", "tpo_prod", "rutcli"])
    marca = pd.DataFrame([{"rutcli": "12345678", "marca": "3"}])

    resultado = extractor.extraer_parque(_reader_parque(fijo, movil, marca), Periodo("202608"))

    # El periodo maximo presente (202608) se proyecta a 202609 ademas de
    # quedar el propio 202608 (UNION ALL de 'ultimo_parque' + CTE2).
    assert sorted(resultado["periodo"].tolist()) == [202608, 202609]
    fila_proyectada = resultado[resultado["periodo"] == 202609].iloc[0]
    assert fila_proyectada["pqe"] == 5
    assert fila_proyectada["SERVICIO"] == "TRIADAS"  # marca=3


def test_extraer_parque_proyecta_diciembre_a_enero_del_anio_siguiente():
    fijo = pd.DataFrame(
        [{"periodo": "202512", "segme": "Micro", "q_casos": "1", "tpo_prod": "BAF", "tecnologia": "FIBER", "rut": "123456780"}]
    )
    movil = pd.DataFrame(columns=["periodo", "segme", "tpo_prod", "rutcli"])
    marca = pd.DataFrame([{"rutcli": "12345678", "marca": "3"}])

    resultado = extractor.extraer_parque(_reader_parque(fijo, movil, marca), Periodo("202601"))

    assert 202601 in resultado["periodo"].tolist()


def test_extraer_parque_movil_pqe_es_siempre_1_y_join_por_rutcli_exacto():
    fijo = pd.DataFrame(columns=["periodo", "segme", "q_casos", "tpo_prod", "tecnologia", "rut"])
    movil = pd.DataFrame([{"periodo": "202608", "segme": "Mediana", "tpo_prod": "MTV", "rutcli": "12345678"}])
    marca = pd.DataFrame([{"rutcli": "12345678", "marca": "4"}])

    resultado = extractor.extraer_parque(_reader_parque(fijo, movil, marca), Periodo("202608"))

    fila = resultado[(resultado["periodo"] == 202608) & (resultado["tipo"] == "MOVIL")].iloc[0]
    assert fila["pqe"] == 1
    assert fila["segme"] == "MEDIANA"
    assert fila["tpo_prod"] == "MTV"  # sin CASE, pasa tal cual
    assert fila["SERVICIO"] == "CARTERIZADOS"  # marca=4


# ===========================================================================
# Retenciones: BAJAS_FRAUDE / BAJAS_POR_ALTA_FO
# ===========================================================================


def _fila_bajas_fraude(periodo: str) -> dict:
    return {col: f"v_{col}" for col in extractor._BAJAS_FRAUDE_COLUMNAS} | {"PERIODO": periodo}


def test_extraer_bajas_fraude_filtra_por_periodo():
    df = pd.DataFrame([_fila_bajas_fraude("202608"), _fila_bajas_fraude("202607")])
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BAJAS_FRAUDE_ARCHIVO: df})

    resultado = extractor.extraer_bajas_fraude(reader, Periodo("202608"))

    assert len(resultado) == 1
    # La columna de salida es el valor CRUDO (texto), el CAST solo se usa
    # para el filtro -- igual que 'SELECT [PERIODO] ... WHERE CAST(PERIODO
    # AS int) >= ?' en el origen original.
    assert resultado.iloc[0]["PERIODO"] == "202608"
    assert list(resultado.columns) == list(extractor._BAJAS_FRAUDE_COLUMNAS)


def _fila_bajas_por_alta(periodo: str) -> dict:
    return {col: f"v_{col}" for col in extractor._BAJAS_POR_ALTA_COLUMNAS} | {"PERIODO": periodo}


def test_extraer_bajas_por_alta_filtra_por_periodo():
    df = pd.DataFrame([_fila_bajas_por_alta("202608"), _fila_bajas_por_alta("202607")])
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BAJAS_POR_ALTA_ARCHIVO: df})

    resultado = extractor.extraer_bajas_por_alta(reader, Periodo("202608"))

    assert len(resultado) == 1
    assert resultado.iloc[0]["PERIODO"] == "202608"
    assert "combinacion origen" in resultado.columns


# ===========================================================================
# Retenciones: BD_RETEN
# ===========================================================================


def _fila_bd_reten(**overrides) -> dict:
    fila = {
        "periodo": "202608",
        "rut": "123456785",
        "nomcli": "CLIENTE X",
        "segme": "MEDIANA",
        "nom_sm": "ASESOR X",
        "nom_sup": "SUPERVISOR X",
        "sub_segme": "SUB X",
        "tpo_serv": "FIJO",
        "tpo_prod": "BAF",
        "tpo_tecno": "FO",
        "q_parque": "1",
        "q_riesgo": "0",
        "q_baja_v": "0",
        "q_baja_p": "0",
        "q_baja_m": "0",
        "motivo": "MOTIVO SIN USO",
        "submotivo": "BAJA SIN RETENCION",
        "submotivo2": "",
        "canal_ing": "CALL",
        "subcan_ing": "IN",
        "canal_res": "CALL",
        "subcan_res": "OUT",
        "cargo_res": "AGENTE",
        "canal_hres": "CALL",
        "fecha_ultima_actualizacion": "2026-08-01 10:00:00",
        "cons_estados": '{"estado":"OK"}',
    }
    fila.update(overrides)
    return fila


def test_extraer_bd_reten_descarta_rowno_y_motivo_y_convierte_evaluacion_y_fecha():
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame([_fila_bd_reten()])})

    resultado = extractor.extraer_bd_reten(reader, Periodo("202608"))

    assert "ROWNO" not in resultado.columns
    assert "motivo" not in resultado.columns
    assert resultado.loc[0, "Evaluacion"] == "1"
    assert str(resultado.loc[0, "last_modified"]) == "2026-08-01"
    assert resultado.loc[0, "rut"] == "123456785"
    # 'rutcli' termina como texto: 'rutcli' esta en
    # mappings.BD_RETEN_TRUNCATION_LENGTHS, y _aplicar_conversion_bd_reten
    # convierte toda columna alli listada a string (Data Conversion).
    assert resultado.loc[0, "rutcli"] == "12345678"
    # SUBSTRING entre '{' y ':' incluye las comillas del JSON -- literal,
    # tal cual el .dtsx original (no se "arregla" a extraer solo la clave).
    assert resultado.loc[0, "case_idnum"] == '"estado"'
    assert resultado.loc[0, "LLAVE"] == "202608" + "12345678" + "FIJO" + "BAF" + "FO"


def test_extraer_bd_reten_aborta_si_una_columna_excede_el_ancho_de_truncamiento():
    fila = _fila_bd_reten(nomcli="X" * 101)  # mappings.BD_RETEN_TRUNCATION_LENGTHS["nomcli"] == 100
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame([fila])})

    with pytest.raises(ExtraccionError):
        extractor.extraer_bd_reten(reader, Periodo("202608"))


def test_extraer_bd_reten_descarta_periodo_bajo_el_piso_202601():
    fila = _fila_bd_reten(periodo="202512")
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_bd_reten(reader, Periodo("202501"))

    assert resultado.empty


def test_extraer_bd_reten_texto_null_en_fecha_ultima_actualizacion_no_aborta():
    """A diferencia del resto de las columnas de texto, 'fecha_ultima_
    actualizacion' nunca pasaba por REPLACE(...,'NULL','') en el SQL
    original (era datetime nativo); en el CSV un valor faltante llega igual
    que en cualquier otra columna: el literal 'NULL'."""
    fila = _fila_bd_reten(fecha_ultima_actualizacion="NULL")
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_bd_reten(reader, Periodo("202608"))

    assert pd.isna(resultado.loc[0, "last_modified"])


def test_extraer_bd_reten_dedup_por_particion_se_queda_con_una_fila():
    filas = [_fila_bd_reten(), _fila_bd_reten(nomcli="OTRO NOMBRE")]  # mismas claves de particion
    reader = FakeSharePointCsvReader({mappings.RETENCIONES_BD_RETEN_ARCHIVO: pd.DataFrame(filas)})

    resultado = extractor.extraer_bd_reten(reader, Periodo("202608"))

    assert len(resultado) == 1


# ===========================================================================
# Intenciones: BAJAS_FIJO / BAJAS_MOVIL / usuarios_retenciones / INTENCIONES_V2
# ===========================================================================


def _fila_bajas_fijo(year_month: str) -> dict:
    return {col: f"v_{col}" for col in extractor._BAJAS_FIJO_COLUMNAS} | {"YEAR_MONTH": year_month}


def test_extraer_bajas_fijo_filtra_por_year_month():
    df = pd.DataFrame([_fila_bajas_fijo("202608"), _fila_bajas_fijo("202607")])
    reader = FakeSharePointCsvReader({mappings.INTENCIONES_BAJAS_FIJO_ARCHIVO: df})

    resultado = extractor.extraer_bajas_fijo(reader, Periodo("202608"))

    assert len(resultado) == 1
    assert resultado.iloc[0]["YEAR_MONTH"] == "202608"


def _fila_bajas_movil(periodo: str) -> dict:
    return {col: f"v_{col}" for col in extractor._BAJAS_MOVIL_COLUMNAS} | {"PERIODO": periodo}


def test_extraer_bajas_movil_filtra_por_periodo():
    df = pd.DataFrame([_fila_bajas_movil("202608"), _fila_bajas_movil("202607")])
    reader = FakeSharePointCsvReader({mappings.INTENCIONES_BAJAS_MOVIL_ARCHIVO: df})

    resultado = extractor.extraer_bajas_movil(reader, Periodo("202608"))

    assert len(resultado) == 1
    assert resultado.iloc[0]["PERIODO"] == "202608"


def test_extraer_intenciones_v2_aborta_si_case_id_number_excede_15():
    fila = {"CASE_ID_NUMBER": "1" * 20, "CASE_OPEN_TIME": "2026-08-01", "CASE_NOTE": "nota"}
    reader = FakeSharePointCsvReader({mappings.INTENCIONES_V2_ARCHIVO: pd.DataFrame([fila])})

    with pytest.raises(ExtraccionError):
        extractor.extraer_intenciones_v2(reader, Periodo("202608"))


def test_extraer_intenciones_v2_no_aborta_si_case_id_number_no_excede_15():
    fila = {"CASE_ID_NUMBER": "12345", "CASE_OPEN_TIME": "2026-08-01", "CASE_NOTE": "nota"}
    reader = FakeSharePointCsvReader({mappings.INTENCIONES_V2_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_intenciones_v2(reader, Periodo("202608"))

    assert resultado.loc[0, "CASE_ID_NUMBER"] == "12345"


def test_extraer_intenciones_v2_filtra_por_anio_mes_de_case_open_time():
    filas = [
        {"CASE_ID_NUMBER": "1", "CASE_OPEN_TIME": "2026-08-15", "CASE_NOTE": "dentro"},
        {"CASE_ID_NUMBER": "2", "CASE_OPEN_TIME": "2026-07-15", "CASE_NOTE": "fuera"},
    ]
    reader = FakeSharePointCsvReader({mappings.INTENCIONES_V2_ARCHIVO: pd.DataFrame(filas)})

    resultado = extractor.extraer_intenciones_v2(reader, Periodo("202608"))

    assert list(resultado["CASE_NOTE"]) == ["dentro"]


# ===========================================================================
# Item Amdocs
# ===========================================================================


def _fila_item_amdocs(**overrides) -> dict:
    fila = {
        "rut": "123456785",
        "case_idnum": "36110065",
        "type1": "TIPO1",
        "type2": "TIPO2",
        "sub_motivo": "SUBMOTIVO",
        "case_desc": "DESCRIPCION",
        "case_resol": "RESOLUCION",
        "case_optim": "2026-08-01 10:00:00",
        "agent_orig": "111",
        "agent_reso": "222",
        "canal_ing": "CALL",
        "subcan_ing": "IN",
        "case_cltim": "01-AUG-26:10.00.00.000 AM",
        "segmento": "MASIVO",
        "subtype": "SUBTIPO",
        "line_buss": "FIJA",
        "motivo": "MOTIVO",
        "servicio": "BAF",
        "cantidad": "1",
        "prod_type": "BAF",
        "ser_stat_r": "OK",
        "periodo": "202608",
        "tpo_serv": "FIJO",
        "rutcli": "12345678",
        "pqe_stb": "0",
        "pqe_baf": "1",
        "pqe_tv": "0",
        "pqe_voz": "0",
        "pqe_bam": "0",
        "tecno_stb": "",
        "tecno_baf": "FO",
        "tecno_tv": "",
        "tpo_t_stb": "",
        "tpo_t_baf": "CO",
        "tpo_t_tv": "",
        "origen": "WEB",
        "canal_res": "CALL",
        "subcan_res": "OUT",
        "cargo_res": "AGENTE",
        "canal_hres": "CALL",
    }
    fila.update(overrides)
    return fila


def test_extraer_item_amdocs_descarta_rutcli_y_renombra_rowno_a_evaluacion():
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([_fila_item_amdocs()])})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert "rutcli" not in resultado.columns
    assert "ROWNO" not in resultado.columns
    assert resultado.loc[0, "Evaluacion"] == 1
    assert resultado.loc[0, "rut"] == 12345678
    assert resultado.loc[0, "case_idnum"] == 36110065


def test_extraer_item_amdocs_parsea_case_cltim_formato_oracle():
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([_fila_item_amdocs()])})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert str(resultado.loc[0, "case_cltim"]) == "2026-08-01 10:00:00"


def test_extraer_item_amdocs_case_cltim_invalido_queda_nat_sin_abortar():
    fila = _fila_item_amdocs(case_cltim="texto-no-valido")
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert pd.isna(resultado.loc[0, "case_cltim"])


def test_extraer_item_amdocs_no_aborta_si_un_entero_no_castea_ignorefailure():
    fila = _fila_item_amdocs(agent_reso="no-numerico")
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert pd.isna(resultado.loc[0, "agent_reso"])


def test_extraer_item_amdocs_trunca_en_silencio_sin_abortar_ignorefailure():
    fila = _fila_item_amdocs(case_desc="X" * 500)  # mappings.ITEM_AMDOCS_TRUNCATION_LENGTHS["case_desc"] == 450
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame([fila])})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert len(resultado.loc[0, "case_desc"]) == 450


def test_extraer_item_amdocs_descarta_case_idnum_vacio_o_cero():
    filas = [_fila_item_amdocs(case_idnum=""), _fila_item_amdocs(case_idnum="0")]
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame(filas)})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert resultado.empty


def test_extraer_item_amdocs_dedup_por_case_idnum_se_queda_con_una_fila():
    filas = [_fila_item_amdocs(), _fila_item_amdocs(type1="OTRO")]  # mismo case_idnum
    reader = FakeSharePointCsvReader({mappings.ITEM_AMDOCS_ARCHIVO: pd.DataFrame(filas)})

    resultado = extractor.extraer_item_amdocs(reader, Periodo("202608"))

    assert len(resultado) == 1


# ===========================================================================
# SAIP
# ===========================================================================


def _fila_saip(**overrides) -> dict:
    fila = {col: f"v_{col}" for col in extractor._SAIP_COLUMNAS_ORIGEN}
    fila["fec_ingr"] = "2020-01-15"
    fila["fec_saip_a"] = "25/01/2022"
    fila["fec_saip_b"] = "26/01/2022"
    fila.update(overrides)
    return fila


def test_extraer_saip_descarta_fec_saip_a_y_b_y_convierte_fechas():
    reader = FakeSharePointCsvReader({mappings.SAIP_ARCHIVO: pd.DataFrame([_fila_saip()])})

    resultado = extractor.extraer_saip(reader)

    assert "fec_saip_a" not in resultado.columns
    assert "fec_saip_b" not in resultado.columns
    assert str(resultado.loc[0, "fec_ingr"]) == "2020-01-15"
    assert str(resultado.loc[0, "FECHA"]) == "2022-01-25"


def test_extraer_saip_incluye_filas_con_fec_saip_a_nulo():
    reader = FakeSharePointCsvReader({mappings.SAIP_ARCHIVO: pd.DataFrame([_fila_saip(fec_saip_a=pd.NA)])})

    resultado = extractor.extraer_saip(reader)

    assert len(resultado) == 1
    assert pd.isna(resultado.loc[0, "FECHA"])


def test_extraer_saip_filtra_por_fecha_real_no_por_comparacion_de_texto():
    """El .dtsx original comparaba el texto 'dd/MM/yyyy' de fec_saip_a
    contra el literal ISO '2022-01-01', lo que excluia por bug los dias
    01-20 de cualquier mes/anio (p.ej. '15/01/2022'), sin relacion con la
    fecha real. Se corrigio a una comparacion de FECHAS real: un dia 15
    de 2022 debe incluirse (es posterior a 2022-01-01) y un dia 15 de 2021
    debe excluirse (es anterior)."""
    reader = FakeSharePointCsvReader(
        {
            mappings.SAIP_ARCHIVO: pd.DataFrame(
                [_fila_saip(fec_saip_a="15/01/2022"), _fila_saip(fec_saip_a="15/01/2021")]
            )
        }
    )

    resultado = extractor.extraer_saip(reader)

    assert len(resultado) == 1
    assert str(resultado.loc[0, "FECHA"]) == "2022-01-15"
