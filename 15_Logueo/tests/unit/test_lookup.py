import pandas as pd

from transformacion.lookup import construir_cache, filas_no_coincidentes


def _flujo(*claves):
    return pd.DataFrame(
        [{"FECHA ANSI": f, "HORA": h, "ID CONEXION": i, "AGENT_NOMBRE": f"n{n}"} for n, (f, h, i) in enumerate(claves)],
        dtype=object,
    )


def _ref(*claves):
    return pd.DataFrame(list(claves), columns=["FECHA ANSI", "HORA", "ID CONEXION"], dtype=object)


def test_solo_pasan_las_no_coincidentes():
    cache = construir_cache(_ref(("20260923", "08:30", "51030151")))
    out = filas_no_coincidentes(_flujo(("20260923", "08:30", "51030151"), ("20260923", "09:00", "51030151")), cache)
    assert out["HORA"].tolist() == ["09:00"]


def test_comparacion_exacta_mayusculas_y_espacios():
    cache = construir_cache(_ref(("20260923", "08:30", "ABC")))
    out = filas_no_coincidentes(_flujo(("20260923", "08:30", "abc"), ("20260923", "08:30", "ABC ")), cache)
    assert len(out) == 2


def test_null_coincide_con_null_en_full_cache():
    cache = construir_cache(_ref(("20260923", None, "51030151")))
    assert filas_no_coincidentes(_flujo(("20260923", None, "51030151")), cache).empty


def test_duplicados_del_archivo_pasan_ambos():
    cache = construir_cache(_ref())
    out = filas_no_coincidentes(_flujo(("20260923", "08:30", "1"), ("20260923", "08:30", "1")), cache)
    assert len(out) == 2


def test_conserva_el_indice_para_reportar_lineas():
    cache = construir_cache(_ref(("20260923", "08:30", "1")))
    out = filas_no_coincidentes(_flujo(("20260923", "08:30", "1"), ("20260924", "08:30", "1")), cache)
    assert out.index.tolist() == [1]
