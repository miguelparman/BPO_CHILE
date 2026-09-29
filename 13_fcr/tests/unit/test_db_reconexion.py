"""Reconexion del DatabaseGateway ante conexiones cortadas por inactividad
(error real de la primera corrida: 08S01 / 10054 en el TRUNCATE)."""

import pyodbc
import pytest

from db import DatabaseGateway
from exceptions import CargaError


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, *params):
        if self.conn.caida:
            raise pyodbc.OperationalError("08S01", "Communication link failure (10054)")
        self.conn.ejecutadas.append(sql)
        return self

    def fetchall(self):
        return [(1,)]

    def fetchone(self):
        return (1,)

    def nextset(self):
        return False

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.caida = False
        self.ejecutadas = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        if self.caida:
            raise pyodbc.OperationalError("08S01", "Communication link failure")
        self.commits += 1

    def rollback(self):
        if self.caida:
            raise pyodbc.OperationalError("08S01", "Communication link failure (SQLEndTran)")

    def close(self):
        pass


def _gateway():
    creadas = []

    def fabrica():
        creadas.append(_Conn())
        return creadas[-1]

    return DatabaseGateway(fabrica, nombre="CL_TRAFICO"), creadas


def test_conexion_caida_entre_operaciones_se_reabre():
    db, creadas = _gateway()
    db.execute_script("UPDATE a SET x = 1")
    creadas[0].caida = True  # el servidor corto la conexion inactiva
    db.execute_script("TRUNCATE TABLE t")
    assert len(creadas) == 2
    assert creadas[1].ejecutadas[-1] == "TRUNCATE TABLE t"


def test_dentro_de_una_transaccion_no_reconecta_y_falla_con_el_error_original():
    db, creadas = _gateway()
    with pytest.raises(CargaError, match="10054"):
        with db.transaccion():
            db.execute_script("TRUNCATE TABLE t")
            creadas[0].caida = True
            db.execute_script("INSERT ...")  # no debe continuar en otra conexion
    assert len(creadas) == 1


def test_la_conexion_se_abre_recien_al_usarse():
    db, creadas = _gateway()
    assert creadas == []
    db.fetch_scalar("SELECT 1")
    assert len(creadas) == 1
