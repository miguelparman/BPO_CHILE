"""Tipos con los que cada modulo pXX_*.py declara el Control Flow de su .dtsx
como DATOS: la lista ordenada de tareas (Precedence Constraints 'Success'
en serie). El nombre de cada tarea es su refId en el .dtsx."""

from __future__ import annotations

from dataclasses import dataclass

from mappings import ArchivoSpec, FlujoSpec


@dataclass(frozen=True)
class TareaSql:
    """Execute SQL Task (T-SQL literal de scripts_sql/)."""

    nombre: str
    script: str


@dataclass(frozen=True)
class TareaTransaccion:
    """Execute SQL Tasks consecutivas que se ejecutan en UNA transaccion
    (p.ej. 'LIMPIA BASE CHILE' + 'CARGA CASOS CHILE': si el INSERT falla, no
    quedan casos borrados sin reinsertar, cosa que en SSIS si podia pasar)."""

    tareas: tuple[TareaSql, ...]

    @property
    def nombre(self) -> str:
        return " + ".join(t.nombre for t in self.tareas)


@dataclass(frozen=True)
class TareaDataFlow:
    """Data Flow Task: uno o mas OLE DB Destinations hacia la staging
    (#temporal de la sesion del paquete)."""

    nombre: str
    flujos: tuple[FlujoSpec, ...]


@dataclass(frozen=True)
class TareaDescripcionesNC:
    """Execute Process 'Carga Descripciones NC' (script Python migrado a
    transformacion/descripciones_nc.py). FailTaskIfReturnCodeIsNotSuccessValue
    = False y el script atrapa toda excepcion: un error aqui se registra como
    advertencia y el paquete continua."""

    nombre: str


Tarea = TareaSql | TareaTransaccion | TareaDataFlow | TareaDescripcionesNC


@dataclass(frozen=True)
class Bloque:
    """Tareas que dependen de unos archivos: si alguno esta viejo, a medio
    publicar o vacio (frescura.py), se omite el bloque COMPLETO y el resto
    del paquete continua (decision del usuario 2026-10-26)."""

    nombre: str
    archivos: tuple[ArchivoSpec, ...]
    tareas: tuple[str, ...]  # Tarea.nombre de cada tarea del bloque


@dataclass(frozen=True)
class Paquete:
    codigo: str  # '02', '03', ...
    dtsx: str
    tareas: tuple[Tarea, ...]
    # Tareas del .dtsx que no se ejecutan por redundantes: {refId: motivo}
    redundantes: tuple[tuple[str, str], ...] = ()
    bloques: tuple[Bloque, ...] = ()

    def bloque_de(self, tarea) -> Bloque | None:
        return next((b for b in self.bloques if tarea.nombre in b.tareas), None)

    @property
    def refids(self) -> list[str]:
        """refId de cada tarea ejecutada, en orden (las de una transaccion, por separado)."""
        salida = []
        for t in self.tareas:
            salida += [x.nombre for x in t.tareas] if isinstance(t, TareaTransaccion) else [t.nombre]
        return salida
