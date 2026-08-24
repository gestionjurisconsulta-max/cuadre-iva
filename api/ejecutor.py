# -*- coding: utf-8 -*-
"""Ejecucion de los cuadres fuera de la peticion HTTP.

Un cuadre tarda unos 30 segundos y consume una CPU entera. No puede correr
dentro de la peticion, asi que se lanza aqui y el cliente pregunta luego por el
estado del trabajo.

Es un pool de hilos, no una cola distribuida. Da para varias personas del
despacho trabajando a la vez, que es el caso. Si algun dia hicieran falta varias
replicas de la API habria que sustituirlo por una cola de verdad, porque cada
proceso solo atiende los trabajos que ha aceptado el.
"""
import io
import logging
import os
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor

from cuadre import pipeline, trabajos

from . import ajustes

log = logging.getLogger("cuadre.api")

_pool = ThreadPoolExecutor(max_workers=ajustes.TRABAJADORES,
                           thread_name_prefix="cuadre")

MIMES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".html": "text/html; charset=utf-8",
}

# clave estable con la que el frontend pide cada fichero
CLAVES = ("excel", "comparativa", "duplicadas")


def encola(tid, a3, bilky, periodo=None, archivar=False):
    """a3 y bilky son [(nombre, bytes), ...] ya leidos de la subida."""
    _pool.submit(_corre, tid, a3, bilky, periodo, archivar)


def _corre(tid, a3, bilky, periodo, archivar):
    try:
        trabajos.empieza(tid)

        def paso(txt):
            trabajos.marca_paso(tid, txt)

        entradas_a3 = [(n, io.BytesIO(b)) for n, b in a3]
        entradas_bk = [(n, io.BytesIO(b)) for n, b in bilky]

        c = pipeline.analiza(entradas_a3, entradas_bk, periodo=periodo, progreso=paso)

        # Los informes se escriben en un temporal y se guardan en la base: son
        # menos de medio mega y asi no hace falta volumen compartido ni limpieza
        # de directorios.
        with tempfile.TemporaryDirectory(prefix="cuadre-") as tmp:
            rutas = pipeline.escribe(c, tmp, progreso=paso)
            ficheros = []
            for clave, ruta in zip(CLAVES, rutas):
                with open(ruta, "rb") as f:
                    datos = f.read()
                ext = os.path.splitext(ruta)[1].lower()
                ficheros.append((clave, os.path.basename(ruta),
                                 MIMES.get(ext, "application/octet-stream"), datos))

        # Un libro leido sin coma decimal trae los importes multiplicados por
        # cien. Los informes se generan igual --sirven para ver el problema--
        # pero al historico no entran: se quedarian ahi para siempre, ensuciando
        # la comparacion entre trimestres, y sin nada que avise despues.
        mal = [lado for lado, esc in c.escalas.items() if esc]
        carga = None
        if archivar and mal:
            c.avisos.insert(0, {"nivel": "grave", "texto":
                "NO se ha archivado en el histórico: el fichero de %s viene con los importes "
                "multiplicados por cien. Archivarlo dejaría esas cifras ahí para siempre. "
                "Corrige la exportación y vuelve a lanzarlo." % " y ".join(mal)})
            log.warning("cuadre %s no archivado: escala x100 en %s", tid, ", ".join(mal))
        elif archivar:
            paso("Archivando en el histórico…")
            carga = pipeline.archiva(c)["carga_id"]

        trabajos.termina(tid, c.resumen, c.avisos, c.a_json(), ficheros, carga_id=carga)
        log.info("cuadre %s terminado (%s)", tid, c.periodo or "sin periodo")
    except Exception as e:
        # El detalle tecnico va al log del servidor, no al navegador: ahi solo
        # viaja el mensaje. Un traceback en pantalla enseña rutas del servidor.
        log.exception("cuadre %s ha fallado", tid)
        trabajos.falla(tid, "%s: %s" % (type(e).__name__, e))


def apaga(espera=True):
    _pool.shutdown(wait=espera)
