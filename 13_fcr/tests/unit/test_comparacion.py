"""Comparacion de tools/equivalencia.py (pura, sin base)."""

import mappings
from tools.equivalencia import comparar_filas

N = len(mappings.NOMBRES_DESTINO)


def _fila(loginid, proximo, fcr="1", ani="1", t="2026-09-01 10:00:00.000"):
    valores = dict.fromkeys(mappings.NOMBRES_DESTINO, "x")
    valores.update({"ANI": ani, "LOGINID": loginid, "FECHA/HORA": t, "FECHA/HORA-PROXIMO": proximo, "FCR_30min": fcr})
    return tuple(valores[c] for c in mappings.NOMBRES_DESTINO)


def test_identica():
    a = [_fila("u1", "\\N"), _fila("u2", "\\N")]
    assert comparar_filas(a, list(reversed(a)))["resultado"] == "IDENTICA"


def test_empate_con_otro_emparejamiento_de_loginid_es_equivalente():
    # Dos atenciones del mismo ANI en el mismo instante: SQL puede darle el
    # 'proximo' (diferencia 0) a cualquiera de los dos LOGINID.
    t = "2026-09-01 10:00:00.000"
    sql = [_fila("u1", t, "0"), _fila("u2", "\\N", "1")]
    py = [_fila("u2", t, "0"), _fila("u1", "\\N", "1")]
    assert comparar_filas(sql, py)["resultado"] == "EQUIVALENTE (empates)"


def test_valor_distinto_es_diferente():
    r = comparar_filas([_fila("u1", "\\N")], [_fila("u1", "2026-09-01 10:10:00.000", "0")])
    assert r["resultado"] == "DIFERENTE"
    assert set(r["columnas"]) == {"FECHA/HORA-PROXIMO", "FCR_30min"}
