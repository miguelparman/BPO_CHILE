"""Orquestador de los 5 paquetes USUARIOS_*.dtsx migrados.

Llama en orden a las 4 capas del proceso -- extraccion/, validacion/,
transformacion/ y carga/ -- no conoce pyodbc ni ningun otro detalle de
db.py. Cada 'ejecutar_xxx' equivale a UN paquete .dtsx original; 'ejecutar_todo'
los corre en el orden declarado por el usuario (mismo orden que los numeros
de paquete: 0101, 0201, 0300, 0301, 0302), deteniendose en el primero que
falle (fail-fast), igual que una cadena de pasos de un job SQL Agent.

    USUARIOS_0101 Parque
        DELETE -> Data Flow 'PARQUE' (sin transformaciones)

    USUARIOS_0201 Retenciones (3 Sequence Containers independientes entre si)
        BAJAS FRAUDE:    DELETE -> Data Flow 'TBL_SERVCH_BAJAS_FRAUDE'
        BAJAS POR ALTA:  DELETE LOCAL -> Data Flow 'TBL_SERVCH_BAJAS_POR_ALTA_FO'
        Find new records or for updating:
            DELETE BD_RETEN -> Data Flow 'BD_RETEN' -> UPDATE (corrige tilde)

    USUARIOS_0300 ETL_INTENCIONES (3 Sequence Containers activos; CARGA
    BAJAS y TBL_INTENCIONES no dependen entre si. El 4to, 'Contenedor de
    secuencias' / 'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE'
    (TBL_FRACTALIA_USER_RETENCIONES en Externos_Frac), se dio de baja por
    ser un trabajo obsoleto)
        CARGA BAJAS: DELETE FIJO + DELETE MOVIL -> Data Flow 'TBL_CH_BAJAS'
        TBL_INTENCIONES: DELETE -> Data Flow 'INTENCIONES' (IgnoreFailure)
        TABULANDO INTENCIONES: TRUNCATE+TEMP_01 -> TRUNCATE+TEMP_02 ->
            TRUNCATE+TEMP_03 -> TRUNCATE+TEMP_04 -> DELETE+INTENCIONES_TAB

    USUARIOS_0301 Item_amdocs (cadena lineal de 10 tareas, sin ramas)
        DELETE -> Data Flow 'INTEN_AMDOCS' -> 9 UPDATE encadenados
            (PRIMER USUARIO x2, FECHA INICIO CALENDARIO, TIEMPO DE ATENCION
            HABIL x3, TIEMPO DE ATENCION CALENDARIO, ESTADO ATENDIDO x2)

    USUARIOS_0302 ETL_BASE_SAIP (unico sin variable de periodo)
        TRUNCATE SAIP -> Data Flow 'SAIP' -> EXEC SP_RETENCIONES_EFECTIVIDAD_ASESOR

Ver el README para el detalle completo del Control Flow / Data Flow de cada
paquete original.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from carga import loader
from db import DatabaseGateway
from exceptions import PipelineError
from extraccion import extractor
from models import Periodo, ResultadoPipeline, ResultadoSubPipeline
from sharepoint.reader import SharePointCsvReader
from transformacion import transformer

logger = logging.getLogger("usuarios")


@dataclass
class UsuariosPipeline:
    """Orquesta los 5 sub-pipelines. Recibe el DatabaseGateway de
    CL_USUARIOS (unico destino restante de los 5 .dtsx) y el
    SharePointCsvReader que reemplaza a Externos_Frac como ORIGEN (ver
    extraccion/extractor.py). Externos_Frac ya no se usa para nada: como
    origen migro a SharePoint, y su unico destino (TBL_FRACTALIA_USER_
    RETENCIONES, via 'CARGA DE USUARIOS RETENCIONES SERVIDOR CHILE') se dio
    de baja por ser un trabajo obsoleto."""

    db_cl_usuarios: DatabaseGateway
    sharepoint_reader: SharePointCsvReader

    def ejecutar_parque(self, periodo: Periodo) -> ResultadoSubPipeline:
        """USUARIOS_0101 Parque.dtsx: DELETE -> Data Flow 'PARQUE'."""
        nombre = "parque"
        self._step(nombre, "DELETE", lambda: loader.eliminar_parque(self.db_cl_usuarios, periodo))
        df = self._step(nombre, "PARQUE / extraccion", lambda: extractor.extraer_parque(self.sharepoint_reader, periodo))
        filas = self._step(nombre, "PARQUE / carga", lambda: loader.cargar_parque(self.db_cl_usuarios, df))
        logger.info("[parque] Finalizado: %s filas cargadas en ParqueTCH.", filas)
        return ResultadoSubPipeline(nombre=nombre, filas_por_paso={"PARQUE": filas})

    def ejecutar_retenciones(self, periodo: Periodo) -> ResultadoSubPipeline:
        """USUARIOS_0201 SSIS_CL_Retenciones.dtsx: 3 Sequence Containers sin
        dependencia entre si (se corren en el orden en que aparecen en el
        .dtsx original: BAJAS FRAUDE, BAJAS POR ALTA, Find new records or
        for updating)."""
        nombre = "retenciones"
        filas_por_paso: dict[str, int] = {}

        self._step(nombre, "BAJAS FRAUDE / DELETE", lambda: loader.eliminar_bajas_fraude(self.db_cl_usuarios, periodo))
        df_fraude = self._step(
            nombre, "BAJAS FRAUDE / extraccion", lambda: extractor.extraer_bajas_fraude(self.sharepoint_reader, periodo)
        )
        filas_por_paso["TBL_SERVCH_BAJAS_FRAUDE"] = self._step(
            nombre, "BAJAS FRAUDE / carga", lambda: loader.cargar_bajas_fraude(self.db_cl_usuarios, df_fraude)
        )

        self._step(
            nombre, "BAJAS POR ALTA / DELETE LOCAL", lambda: loader.eliminar_bajas_por_alta(self.db_cl_usuarios, periodo)
        )
        df_alta = self._step(
            nombre,
            "BAJAS POR ALTA / extraccion",
            lambda: extractor.extraer_bajas_por_alta(self.sharepoint_reader, periodo),
        )
        filas_por_paso["TBL_SERVCH_BAJAS_POR_ALTA_FO"] = self._step(
            nombre, "BAJAS POR ALTA / carga", lambda: loader.cargar_bajas_por_alta(self.db_cl_usuarios, df_alta)
        )

        self._step(
            nombre, "BD_RETEN / DELETE BD_RETEN", lambda: loader.eliminar_bd_reten(self.db_cl_usuarios, periodo)
        )
        df_bd_reten = self._step(
            nombre, "BD_RETEN / extraccion", lambda: extractor.extraer_bd_reten(self.sharepoint_reader, periodo)
        )
        filas_por_paso["BD_RETEN"] = self._step(
            nombre, "BD_RETEN / carga", lambda: loader.cargar_bd_reten(self.db_cl_usuarios, df_bd_reten)
        )
        self._step(
            nombre, "BD_RETEN / UPDATE", lambda: transformer.corregir_acento_submotivo(self.db_cl_usuarios)
        )

        logger.info("[retenciones] Finalizado: %s", filas_por_paso)
        return ResultadoSubPipeline(nombre=nombre, filas_por_paso=filas_por_paso)

    def ejecutar_intenciones(self, periodo: Periodo) -> ResultadoSubPipeline:
        """USUARIOS_0300 ETL_INTENCIONES.dtsx: 3 Sequence Containers activos
        ('Contenedor de secuencias' se dio de baja, ver docstring de la
        clase). 'CARGA BAJAS' no depende de 'TBL_INTENCIONES' en el .dtsx
        original; se corren aqui en el orden en que aparecen en el paquete."""
        nombre = "intenciones"
        filas_por_paso: dict[str, int] = {}

        # --- CARGA BAJAS ---
        self._step(nombre, "CARGA BAJAS / DELETE FIJO", lambda: loader.eliminar_bajas_fijo(self.db_cl_usuarios, periodo))
        self._step(
            nombre, "CARGA BAJAS / DELETE MOVIL", lambda: loader.eliminar_bajas_movil(self.db_cl_usuarios, periodo)
        )
        df_fijo = self._step(
            nombre, "CARGA BAJAS / TBL_CH_BAJAS (fijo) / extraccion",
            lambda: extractor.extraer_bajas_fijo(self.sharepoint_reader, periodo),
        )
        filas_por_paso["TBL_CH_BAJAS_FIJO"] = self._step(
            nombre, "CARGA BAJAS / TBL_CH_BAJAS (fijo) / carga",
            lambda: loader.cargar_bajas_fijo(self.db_cl_usuarios, df_fijo),
        )
        df_movil = self._step(
            nombre, "CARGA BAJAS / TBL_CH_BAJAS (movil) / extraccion",
            lambda: extractor.extraer_bajas_movil(self.sharepoint_reader, periodo),
        )
        filas_por_paso["TBL_CH_BAJAS_MOVIL"] = self._step(
            nombre, "CARGA BAJAS / TBL_CH_BAJAS (movil) / carga",
            lambda: loader.cargar_bajas_movil(self.db_cl_usuarios, df_movil),
        )

        # --- TBL_INTENCIONES ---
        self._step(nombre, "TBL_INTENCIONES / DELETE", lambda: loader.eliminar_intenciones(self.db_cl_usuarios, periodo))
        df_v2 = self._step(
            nombre, "TBL_INTENCIONES / extraccion", lambda: extractor.extraer_intenciones_v2(self.sharepoint_reader, periodo)
        )
        filas_por_paso["INTENCIONES"] = self._step(
            nombre, "TBL_INTENCIONES / carga", lambda: loader.cargar_intenciones_local(self.db_cl_usuarios, df_v2)
        )

        # --- TABULANDO INTENCIONES ---
        self._step(nombre, "TABULANDO INTENCIONES / TRUNCATE TEMP_01", lambda: loader.truncar_temp01(self.db_cl_usuarios))
        self._step(
            nombre, "TABULANDO INTENCIONES / TEMP_01",
            lambda: transformer.poblar_temp01_notas_limpias(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TRUNCATE TABLE TEMP_02", lambda: loader.truncar_temp02(self.db_cl_usuarios)
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TEMP_02",
            lambda: transformer.poblar_temp02_notas_divididas(self.db_cl_usuarios),
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TRUNCATE TABLE TEMP_03", lambda: loader.truncar_temp03(self.db_cl_usuarios)
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TEMP_03",
            lambda: transformer.poblar_temp03_notas_separadas(self.db_cl_usuarios),
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TRUNCATE TABLE TEMP_04", lambda: loader.truncar_temp04(self.db_cl_usuarios)
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / TEMP_04",
            lambda: transformer.poblar_temp04_notas_con_fecha_usuario(self.db_cl_usuarios),
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / DELETE INTENCIONES_TAB",
            lambda: loader.eliminar_intenciones_tab(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "TABULANDO INTENCIONES / INTENCIONES_TAB",
            lambda: transformer.poblar_intenciones_tab(self.db_cl_usuarios),
        )

        logger.info("[intenciones] Finalizado: %s", filas_por_paso)
        return ResultadoSubPipeline(nombre=nombre, filas_por_paso=filas_por_paso)

    def ejecutar_item_amdocs(self, periodo: Periodo) -> ResultadoSubPipeline:
        """USUARIOS_0301 SSIS_CL_Item_amdocs.dtsx: cadena lineal sin ramas,
        DELETE -> Data Flow 'INTEN_AMDOCS' -> 9 UPDATE encadenados."""
        nombre = "item_amdocs"

        self._step(nombre, "Loading to the Staging / DELETE", lambda: loader.eliminar_item_amdocs(self.db_cl_usuarios, periodo))
        df = self._step(
            nombre, "Loading to the Staging / INTEN_AMDOCS / extraccion",
            lambda: extractor.extraer_item_amdocs(self.sharepoint_reader, periodo),
        )
        filas = self._step(
            nombre, "Loading to the Staging / INTEN_AMDOCS / carga",
            lambda: loader.cargar_item_amdocs(self.db_cl_usuarios, df),
        )

        self._step(
            nombre, "UPDATE - PRIMER USUARIO POR BASE INTENCION",
            lambda: transformer.actualizar_primer_usuario(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "UPDATE - FECHA INICIO CALENDARIO",
            lambda: transformer.actualizar_fecha_inicio_calendario(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "UPDATE - TIEMPO DE ATENCION HABIL",
            lambda: transformer.actualizar_tiempo_atencion_habil(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "UPDATE - TIEMPO DE ATENCION CALENDARIO (DIAS)",
            lambda: transformer.actualizar_tiempo_atencion_calendario(self.db_cl_usuarios, periodo),
        )
        self._step(
            nombre, "UPDATE - ESTADO ATENDIDO", lambda: transformer.actualizar_estado_atendido(self.db_cl_usuarios, periodo)
        )

        logger.info("[item_amdocs] Finalizado: %s filas cargadas en INTEN_AMDOCS.", filas)
        return ResultadoSubPipeline(nombre=nombre, filas_por_paso={"INTEN_AMDOCS": filas})

    def ejecutar_saip(self) -> ResultadoSubPipeline:
        """USUARIOS_0302 ETL_BASE_SAIP.dtsx: TRUNCATE SAIP -> Data Flow
        'SAIP' -> EXEC SP_RETENCIONES_EFECTIVIDAD_ASESOR. Unico de los 5
        paquetes sin variable de periodo."""
        nombre = "saip"

        self._step(nombre, "TRUNCATE SAIP", lambda: loader.truncar_saip(self.db_cl_usuarios))
        df = self._step(nombre, "SAIP / extraccion", lambda: extractor.extraer_saip(self.sharepoint_reader))
        filas = self._step(nombre, "SAIP / carga", lambda: loader.cargar_saip(self.db_cl_usuarios, df))
        self._step(
            nombre,
            "SP_RETENCIONES_EFECTIVIDAD_ASESOR",
            lambda: transformer.ejecutar_sp_retenciones_efectividad_asesor(self.db_cl_usuarios),
        )

        logger.info("[saip] Finalizado: %s filas cargadas en BASE_SAIP.", filas)
        return ResultadoSubPipeline(nombre=nombre, filas_por_paso={"BASE_SAIP": filas})

    def ejecutar_todo(self, periodo: Periodo) -> ResultadoPipeline:
        """Corre los 5 sub-pipelines en el orden declarado. Se detiene (sin
        continuar con el siguiente) si alguno lanza PipelineError."""
        resultados = (
            self.ejecutar_parque(periodo),
            self.ejecutar_retenciones(periodo),
            self.ejecutar_intenciones(periodo),
            self.ejecutar_item_amdocs(periodo),
            self.ejecutar_saip(),
        )
        return ResultadoPipeline(periodo=periodo, resultados=resultados)

    def _step(self, pipeline: str, descripcion: str, accion: Callable):
        logger.info("[%s] %s", pipeline, descripcion)
        try:
            return accion()
        except Exception as exc:  # noqa: BLE001 - se re-lanza tipado como PipelineError
            raise PipelineError(pipeline, descripcion, exc) from exc
