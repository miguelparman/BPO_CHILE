"""Coherencia de los bloques de frescura (paquetes/base.Bloque): omitir un
bloque nunca debe dejar una tarea que use datos que no se cargaron."""

from __future__ import annotations

import mappings as m
import sql
from paquetes import PAQUETES
from paquetes.base import TareaDataFlow, TareaDescripcionesNC, TareaSql, TareaTransaccion

LOGS = ("Package\\Log Inicio", "Package\\Log Fin")


def _scripts(tarea) -> list[str]:
    if isinstance(tarea, TareaSql):
        return [tarea.script]
    if isinstance(tarea, TareaTransaccion):
        return [t.script for t in tarea.tareas]
    return []


def test_cada_tarea_esta_en_un_solo_bloque_salvo_los_logs_y_el_07():
    for p in PAQUETES:
        nombres = [t.nombre for t in p.tareas]
        en_bloques = [n for b in p.bloques for n in b.tareas]
        assert len(en_bloques) == len(set(en_bloques)), f"{p.codigo}: tarea en dos bloques"
        assert set(en_bloques) <= set(nombres), f"{p.codigo}: bloque con una tarea que no existe"
        if p.codigo == "07":
            assert p.bloques == ()  # los SP corren siempre
            continue
        assert set(nombres) - set(en_bloques) == set(LOGS), p.codigo


def test_el_bloque_incluye_todos_los_archivos_que_leen_sus_tareas():
    for p in PAQUETES:
        for t in p.tareas:
            b = p.bloque_de(t)
            if isinstance(t, TareaDataFlow):
                for f in t.flujos:
                    assert f.archivo in b.archivos
                    if f.cruce:
                        assert f.cruce.flujo.archivo in b.archivos
            elif isinstance(t, TareaDescripcionesNC):
                assert m.ARCHIVO_DESCRIPCIONES_NC in b.archivos


def test_el_sql_que_usa_una_temporal_va_en_el_bloque_que_la_carga():
    for p in PAQUETES:
        carga = {f.tabla: p.bloque_de(t).nombre for t in p.tareas if isinstance(t, TareaDataFlow) for f in t.flujos}
        for t in p.tareas:
            for script in _scripts(t):
                for tabla in m.TABLAS_TEMPORALES:
                    if f"#{tabla} " in sql.a_temporal(script):
                        assert p.bloque_de(t) is not None and p.bloque_de(t).nombre == carga[tabla], (p.codigo, t.nombre)


def test_el_truncate_de_descripciones_nc_se_omite_con_su_carga():
    p06 = next(p for p in PAQUETES if p.codigo == "06")
    truncate = next(t for t in p06.tareas if isinstance(t, TareaSql) and "TBL_DESCRIPCIONES_NC" in t.script)
    nc = next(t for t in p06.tareas if isinstance(t, TareaDescripcionesNC))
    assert p06.bloque_de(truncate) is p06.bloque_de(nc)
