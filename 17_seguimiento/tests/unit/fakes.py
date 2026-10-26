"""Dobles de prueba (sin SQL Server ni SharePoint)."""

from __future__ import annotations

from mappings import ArchivoSpec


class FuenteFalsa:
    """Devuelve bytes 'crudos' (cp1252, como los publica el bot) por nombre de archivo."""

    def __init__(self, archivos: dict[str, bytes], falla: set[str] | None = None) -> None:
        self.archivos = archivos
        self.falla = falla or set()
        self.leidos: list[str] = []

    def leer(self, archivo: ArchivoSpec) -> bytes:
        self.leidos.append(archivo.nombre)
        if archivo.nombre in self.falla:
            raise RuntimeError(f"no se pudo leer {archivo.nombre}")
        return self.archivos[archivo.nombre]

    def describir(self, archivo: ArchivoSpec) -> str:
        return f"falsa://{archivo.nombre}"


class LoaderFalso:
    """Registra lo que se ejecutaria; 'esquemas' simula INFORMATION_SCHEMA."""

    def __init__(self, esquemas: dict[str, dict], falla_sql: str | None = None, falla_nc: bool = False) -> None:
        self.esquemas = esquemas
        self.falla_sql = falla_sql
        self.falla_nc = falla_nc
        self.eventos: list[tuple] = []
        self.cargas: dict[str, list[tuple]] = {}

    def esquema(self, tabla):
        return self.esquemas.get(tabla, {})

    def iniciar_paquete(self):
        self.eventos.append(("sesion",))

    def ejecutar_sql(self, script):
        self.eventos.append(("sql", script))
        if self.falla_sql and self.falla_sql in script:
            raise RuntimeError("fallo T-SQL simulado")
        return 1

    def ejecutar_transaccion(self, scripts):
        self.eventos.append(("transaccion", tuple(scripts)))
        if self.falla_sql and any(self.falla_sql in s for s in scripts):
            raise RuntimeError("fallo T-SQL simulado")
        return [1] * len(scripts)

    def cargar_temporal(self, flujo, filas):
        self.eventos.append(("temporal", flujo.tabla, len(filas)))
        self.cargas[flujo.tabla] = list(filas)
        return len(filas)

    def cargar_descripciones_nc(self, filas):
        self.eventos.append(("nc", len(filas)))
        if self.falla_nc:
            raise RuntimeError("fallo carga NC simulado")
        return len(filas)

    def ejecutar_sp_folios_nc(self):
        self.eventos.append(("sp_folios_nc",))

    def scripts(self) -> list[str]:
        """T-SQL ejecutado, en orden (las transacciones desplegadas)."""
        salida = []
        for e in self.eventos:
            if e[0] == "sql":
                salida.append(e[1])
            elif e[0] == "transaccion":
                salida += list(e[1])
        return salida


def csv_crudo(encabezado: list[str], filas: list[list[str]]) -> bytes:
    """CSV como lo publica 201_bot_salesforce: comillas, ',', LF, cp1252."""

    def linea(valores):
        return ",".join('"' + v.replace('"', '""') + '"' for v in valores)

    return ("\n".join([linea(encabezado)] + [linea(f) for f in filas]) + "\n").encode("cp1252")


def esquema_de(flujo, largo: int | None = 4000) -> dict:
    """Esquema permisivo (nvarchar ancho) para cada columna que inserta el flujo."""
    tipos = {"date": ("datetime", None), "numeric": ("numeric", None)}
    esquema = {c.destino: tipos.get(c.conversion.tipo, ("nvarchar", largo)) for c in flujo.columnas}
    for c in flujo.columnas_insert:
        esquema.setdefault(c, ("nvarchar", largo))
    return esquema
