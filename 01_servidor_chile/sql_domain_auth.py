"""
Conexion a SQL Server con credenciales de dominio remoto (equivalente a runas /netonly).

Replica exactamente el comportamiento de:
  runas /netonly /user:DOMINIO\\usuario "programa"

La clave es LogonUserW con LOGON32_LOGON_NEW_CREDENTIALS: el proceso sigue corriendo
como el usuario local, pero todas las conexiones de red usan las credenciales del
dominio remoto. Despues se impersona ese token para que pyodbc herede las credenciales
al hacer Trusted_Connection=yes.
"""

import ctypes
import ctypes.wintypes
import contextlib
import pyodbc

_DRIVERS_PREFERIDOS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")


def _resolver_driver(configurado: str = "ODBC Driver 17 for SQL Server") -> str:
    """Devuelve el driver ODBC a usar: el indicado si esta instalado en esta
    maquina; si no, el mas nuevo de los instalados (varia entre equipos)."""
    instalados = pyodbc.drivers()
    nombre = configurado.strip().strip("{}")
    if nombre in instalados:
        return nombre
    for candidato in _DRIVERS_PREFERIDOS:
        if candidato in instalados:
            return candidato
    return nombre


# ── Win32 constantes ──────────────────────────────────────────────────────────
LOGON32_LOGON_NEW_CREDENTIALS = 9   # equivalente al flag /netonly
LOGON32_PROVIDER_WINNT50      = 3

_advapi32 = ctypes.windll.advapi32
_kernel32  = ctypes.windll.kernel32

_advapi32.LogonUserW.restype       = ctypes.wintypes.BOOL
_advapi32.LogonUserW.argtypes      = [
    ctypes.wintypes.LPCWSTR,   # lpszUsername
    ctypes.wintypes.LPCWSTR,   # lpszDomain
    ctypes.wintypes.LPCWSTR,   # lpszPassword
    ctypes.wintypes.DWORD,     # dwLogonType
    ctypes.wintypes.DWORD,     # dwLogonProvider
    ctypes.POINTER(ctypes.wintypes.HANDLE),  # phToken (out)
]

_advapi32.ImpersonateLoggedOnUser.restype  = ctypes.wintypes.BOOL
_advapi32.ImpersonateLoggedOnUser.argtypes = [ctypes.wintypes.HANDLE]

_advapi32.RevertToSelf.restype  = ctypes.wintypes.BOOL
_advapi32.RevertToSelf.argtypes = []

_kernel32.CloseHandle.restype  = ctypes.wintypes.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]


# ── Context manager ───────────────────────────────────────────────────────────
@contextlib.contextmanager
def impersonate_domain_user(domain: str, username: str, password: str):
    """
    Context manager que impersona un usuario de dominio remoto usando
    LOGON32_LOGON_NEW_CREDENTIALS (identico a runas /netonly).

    Uso:
        with impersonate_domain_user("TCHILE", "frp_apared", "mi_password"):
            conn = pyodbc.connect("...;Trusted_Connection=yes;")
    """
    token = ctypes.wintypes.HANDLE()

    ok = _advapi32.LogonUserW(
        username,
        domain,
        password,
        LOGON32_LOGON_NEW_CREDENTIALS,
        LOGON32_PROVIDER_WINNT50,
        ctypes.byref(token),
    )
    if not ok:
        error_code = _kernel32.GetLastError()
        raise OSError(f"LogonUserW fallo para {domain}\\{username} — error Win32: {error_code}")

    try:
        ok = _advapi32.ImpersonateLoggedOnUser(token)
        if not ok:
            error_code = _kernel32.GetLastError()
            raise OSError(f"ImpersonateLoggedOnUser fallo — error Win32: {error_code}")
        try:
            yield
        finally:
            _advapi32.RevertToSelf()
    finally:
        _kernel32.CloseHandle(token)


# ── Funcion de conexion ───────────────────────────────────────────────────────
def conectar_dominio(
    server:   str,
    database: str,
    domain:   str,
    username: str,
    password: str,
    driver:   str = "ODBC Driver 17 for SQL Server",
    extra:    str = "TrustServerCertificate=yes;",
) -> pyodbc.Connection:
    """
    Abre una conexion pyodbc usando Trusted_Connection (Kerberos/NTLM) bajo
    las credenciales de red del dominio remoto, sin necesidad de runas /netonly.

    Parametros
    ----------
    server   : nombre o IP del servidor SQL Server
    database : base de datos inicial
    domain   : nombre NetBIOS del dominio (ej. "TCHILE")
    username : usuario del dominio (ej. "frp_apared")
    password : contrasena del usuario
    driver   : ODBC driver instalado en el sistema
    extra    : opciones adicionales del connection string

    Retorna
    -------
    pyodbc.Connection lista para usar
    """
    conn_str = (
        f"DRIVER={{{_resolver_driver(driver)}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Trusted_Connection=yes;"
        f"{extra}"
    )

    with impersonate_domain_user(domain, username, password):
        conn = pyodbc.connect(conn_str)

    # La conexion ya esta autenticada; la impersonacion puede revertirse.
    return conn
