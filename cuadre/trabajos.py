# -*- coding: utf-8 -*-
"""Cola de cuadres: estado, resultado y ficheros de cada ejecucion.

Un cuadre de un trimestre tarda unos 30 segundos. Eso es demasiado para una
peticion HTTP sincrona --el proxy la cortaria, y el navegador tampoco deberia
quedarse esperando-- asi que la API acepta la subida, crea un trabajo, y
devuelve su identificador. El cliente pregunta por el estado cuando quiere.

El estado vive en PostgreSQL y no en memoria, para que sobreviva a un reinicio
del servidor y para que se pueda consultar desde cualquier proceso.

Los tres ficheros generados pesan menos de medio mega en total, asi que se
guardan aqui mismo en la base. Asi no hace falta un volumen compartido entre
contenedores, y limpiar es un DELETE en vez de recorrer un directorio.
"""
import json
import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from . import bd

# Los libros son datos de clientes: no se quedan en el servidor para siempre.
DIAS_RETENCION = int(os.environ.get("CUADRE_RETENCION_DIAS", "30"))

# Un trabajo que lleva mas de esto «ejecutando» es que el proceso murio.
MINUTOS_ABANDONO = int(os.environ.get("CUADRE_MINUTOS_ABANDONO", "30"))

EN_COLA, EJECUTANDO, HECHO, FALLIDO = "en_cola", "ejecutando", "hecho", "fallido"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabajos (
  id           TEXT PRIMARY KEY,
  estado       TEXT NOT NULL,
  periodo      TEXT,
  paso         TEXT,
  error        TEXT,
  usuario      TEXT,
  creado_en    TIMESTAMPTZ NOT NULL DEFAULT now(),
  iniciado_en  TIMESTAMPTZ,
  terminado_en TIMESTAMPTZ,
  archivar     BOOLEAN NOT NULL DEFAULT FALSE,
  carga_id     INTEGER,
  resumen      JSONB,
  avisos       JSONB,
  resultado    JSONB
);

CREATE TABLE IF NOT EXISTS ficheros (
  trabajo_id TEXT NOT NULL REFERENCES trabajos(id) ON DELETE CASCADE,
  clave      TEXT NOT NULL,
  nombre     TEXT NOT NULL,
  tipo_mime  TEXT NOT NULL,
  bytes      BYTEA NOT NULL,
  PRIMARY KEY (trabajo_id, clave)
);

CREATE INDEX IF NOT EXISTS ix_trab_estado ON trabajos(estado, creado_en);
"""

_preparado = set()


def _motor(dsn=None):
    eng = bd.motor(dsn)
    if eng.url not in _preparado:
        with eng.begin() as cx:
            cx.execute(text(ESQUEMA))
        _preparado.add(eng.url)
    return eng


def crea(periodo=None, archivar=False, usuario=None, dsn=None):
    """Registra un trabajo en cola y devuelve su id."""
    tid = uuid.uuid4().hex
    with _motor(dsn).begin() as cx:
        cx.execute(text(
            "INSERT INTO trabajos (id, estado, periodo, archivar, usuario, paso)"
            " VALUES (:id, :estado, :periodo, :archivar, :usuario, :paso)"),
            {"id": tid, "estado": EN_COLA, "periodo": periodo, "archivar": bool(archivar),
             "usuario": usuario, "paso": "En cola"})
    return tid


def marca_paso(tid, paso, dsn=None):
    """Deja constancia de por donde va. Es lo que lee la barra de progreso."""
    with _motor(dsn).begin() as cx:
        cx.execute(text("UPDATE trabajos SET paso = :p WHERE id = :id"),
                   {"p": paso, "id": tid})


def empieza(tid, dsn=None):
    with _motor(dsn).begin() as cx:
        cx.execute(text("UPDATE trabajos SET estado = :e, iniciado_en = now(), paso = :p"
                        " WHERE id = :id"),
                   {"e": EJECUTANDO, "p": "Leyendo los libros…", "id": tid})


def termina(tid, resumen, avisos, resultado, ficheros, carga_id=None, dsn=None):
    """Guarda el resultado y los tres ficheros, y marca el trabajo como hecho.

    `ficheros` es [(clave, nombre, tipo_mime, bytes), ...].
    """
    with _motor(dsn).begin() as cx:
        cx.execute(text(
            "UPDATE trabajos SET estado = :e, terminado_en = now(), paso = :p,"
            " resumen = :resumen, avisos = :avisos, resultado = :resultado,"
            " carga_id = :carga WHERE id = :id"),
            {"e": HECHO, "p": "Terminado", "id": tid, "carga": carga_id,
             "resumen": json.dumps(resumen, default=str),
             "avisos": json.dumps(avisos, default=str),
             "resultado": json.dumps(resultado, default=str)})
        for clave, nombre, mime, datos in ficheros:
            cx.execute(text(
                "INSERT INTO ficheros (trabajo_id, clave, nombre, tipo_mime, bytes)"
                " VALUES (:t, :c, :n, :m, :b)"
                " ON CONFLICT (trabajo_id, clave) DO UPDATE SET bytes = EXCLUDED.bytes"),
                {"t": tid, "c": clave, "n": nombre, "m": mime, "b": datos})


def falla(tid, mensaje, dsn=None):
    with _motor(dsn).begin() as cx:
        cx.execute(text("UPDATE trabajos SET estado = :e, terminado_en = now(),"
                        " paso = :p, error = :err WHERE id = :id"),
                   {"e": FALLIDO, "p": "Ha fallado", "err": str(mensaje)[:8000], "id": tid})


_CAMPOS = ("id, estado, periodo, paso, error, usuario, creado_en, iniciado_en,"
           " terminado_en, archivar, carga_id, resumen, avisos")


def estado(tid, dsn=None):
    """Todo menos el resultado completo, que puede ser grande."""
    with _motor(dsn).connect() as cx:
        r = cx.execute(text("SELECT %s FROM trabajos WHERE id = :id" % _CAMPOS),
                       {"id": tid}).mappings().first()
    return dict(r) if r else None


def resultado(tid, dsn=None):
    with _motor(dsn).connect() as cx:
        r = cx.execute(text("SELECT resultado FROM trabajos WHERE id = :id"),
                       {"id": tid}).scalar()
    return r


def lista(limite=50, dsn=None):
    with _motor(dsn).connect() as cx:
        return [dict(r) for r in cx.execute(text(
            "SELECT %s FROM trabajos ORDER BY creado_en DESC LIMIT :n" % _CAMPOS),
            {"n": int(limite)}).mappings()]


def ficheros(tid, dsn=None):
    with _motor(dsn).connect() as cx:
        return [dict(r) for r in cx.execute(text(
            "SELECT clave, nombre, tipo_mime, length(bytes) AS bytes"
            " FROM ficheros WHERE trabajo_id = :t ORDER BY clave"),
            {"t": tid}).mappings()]


def fichero(tid, clave, dsn=None):
    with _motor(dsn).connect() as cx:
        r = cx.execute(text("SELECT nombre, tipo_mime, bytes FROM ficheros"
                            " WHERE trabajo_id = :t AND clave = :c"),
                       {"t": tid, "c": clave}).mappings().first()
    return dict(r) if r else None


def borra(tid, dsn=None):
    with _motor(dsn).begin() as cx:
        n = cx.execute(text("DELETE FROM trabajos WHERE id = :id"), {"id": tid}).rowcount
    return n


def limpia(dias=None, dsn=None):
    """Tira los trabajos viejos y rescata los que se quedaron colgados.

    Lo primero es proteccion de datos: los libros de un cliente no tienen por
    que seguir en el servidor un mes despues. Lo segundo es que si el proceso
    murio a mitad, el trabajo se quedaria en «ejecutando» para siempre y el
    cliente esperando.
    """
    dias = DIAS_RETENCION if dias is None else dias
    limite = datetime.now().astimezone() - timedelta(days=dias)
    colgados = datetime.now().astimezone() - timedelta(minutes=MINUTOS_ABANDONO)
    with _motor(dsn).begin() as cx:
        viejos = cx.execute(text("DELETE FROM trabajos WHERE creado_en < :l"),
                            {"l": limite}).rowcount
        perdidos = cx.execute(text(
            "UPDATE trabajos SET estado = :e, paso = :p, error = :err, terminado_en = now()"
            " WHERE estado IN (:cola, :ejec) AND creado_en < :c"),
            {"e": FALLIDO, "p": "Ha fallado", "cola": EN_COLA, "ejec": EJECUTANDO,
             "err": "El proceso se interrumpio antes de terminar. Vuelve a lanzarlo.",
             "c": colgados}).rowcount
    return {"borrados": viejos, "recuperados": perdidos}
