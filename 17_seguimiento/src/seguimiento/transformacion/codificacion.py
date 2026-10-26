"""Reparacion de tildes mal codificadas en los textos que exporta Salesforce
(desviacion INTENCIONAL de SSIS, pedida por el usuario el 2026-10-26: las
cargas nuevas deben quedar bien; lo ya cargado no se toca).

El dato de origen trae letras con tilde que en algun momento se codificaron
en UTF-8 (2 bytes: C3 xx / C2 xx) y luego se trataron como si fuera otro
formato. En el CSV del bot quedan asi:

    'AGRA' 0x8D 'COLAS'        -> la 'A' reemplazo al byte C3   -> AGRICOLAS con I acentuada
    'IRARR' 'Ã' 0x81 'ZABAL'   -> C3 81 intacto                 -> IRARRAZABAL con A acentuada
    'CAFETER' 'Í' 0x8D 'A'     -> letra ya correcta + byte de sobra -> CAFETERIA (se quita el byte)
    'MU' 'Ã' '‘' 'OZ'          -> C3 91 (0x91 si existe en cp1252) -> MUNOZ con N con tilde

Los bytes 0x81, 0x8D, 0x8F, 0x90 y 0x9D no existen en cp1252: el extractor
los conserva (extractor.CONSERVAR_BYTES) para poder repararlos; SSIS los
convertia en U+FFFD y en la tabla quedaban como '?'.

Reglas, en orden:
  1. 'Ã'/'Â' + un byte 0x80-0xBF que juntos forman un caracter UTF-8 valido
     -> ese caracter.
  2. 'A' + byte no definido en cp1252 -> la letra UTF-8 C3 + byte
     (0x81 -> A acentuada, 0x8D -> I acentuada, 0x8F -> I dieresis,
     0x90 -> ETH, 0x9D -> Y acentuada). Si justo antes esta la misma letra
     SIN tilde, sobra y se quita: 'ASESORI' + 'A'0x8D + 'AS' -> ASESORIAS
     con I acentuada (no 'ASESORI' + I acentuada + 'AS').
  3. Cualquier byte no definido que quede (p.ej. tras una letra ya
     acentuada) se elimina.
"""

from __future__ import annotations

import re
import unicodedata

REPARAR = True  # tools/equivalencia.py lo apaga para la comparacion estricta con SSIS

_NO_DEFINIDOS = "\x81\x8d\x8f\x90\x9d"  # bytes sin caracter en cp1252, conservados como U+0081...


def _byte(caracter: str) -> int | None:
    """Byte cp1252 (o latin-1 para los conservados) de un caracter."""
    try:
        return caracter.encode("cp1252")[0]
    except UnicodeEncodeError:
        return ord(caracter) if ord(caracter) < 0x100 else None


_PAR_UTF8 = re.compile("([ÃÂ])(.)", re.DOTALL)
_A_MAS_BYTE = re.compile(f"(.?)A([{_NO_DEFINIDOS}])", re.DOTALL)


def _base(letra: str) -> str:
    """Letra sin tilde ('Í' -> 'I')."""
    return unicodedata.normalize("NFD", letra)[0]


def _a_mas_byte(m: re.Match) -> str:
    anterior, letra = m.group(1), bytes([0xC3, ord(m.group(2))]).decode("utf-8")
    if anterior and anterior == _base(letra):
        return letra  # la misma letra sin tilde, repetida antes: sobra
    return anterior + letra
_SUELTO = re.compile(f"[{_NO_DEFINIDOS}]")


def _par_utf8(m: re.Match) -> str:
    segundo = _byte(m.group(2))
    if segundo is None or not 0x80 <= segundo <= 0xBF:
        return m.group(0)
    return bytes([0xC3 if m.group(1) == "Ã" else 0xC2, segundo]).decode("utf-8")


def reparar_codificacion(valor: str) -> str:
    """Texto con las tildes mal codificadas reparadas (ver reglas arriba).
    Con REPARAR = False se comporta como SSIS: los bytes no definidos quedan
    como U+FFFD (y en las columnas varchar, como '?')."""
    if not REPARAR:
        return sin_reparar_como_ssis(valor) if valor else valor
    if not valor or not ("Ã" in valor or "Â" in valor or _SUELTO.search(valor)):
        return valor
    valor = _PAR_UTF8.sub(_par_utf8, valor)
    valor = _A_MAS_BYTE.sub(_a_mas_byte, valor)
    return _SUELTO.sub("", valor)


def sin_reparar_como_ssis(valor: str) -> str:
    """Lo que veia SSIS: los bytes no definidos como U+FFFD (Transforma_archivos_csv errors='replace')."""
    return _SUELTO.sub("�", valor)
