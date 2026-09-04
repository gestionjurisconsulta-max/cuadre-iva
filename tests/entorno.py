# -*- coding: utf-8 -*-
"""Bases de datos desechables para los tests.

Los dos tests archivan en el historico, y tienen que hacerlo sobre una base
vacia: si arrastraran datos de una ejecucion anterior, los recuentos no
significarian nada. Antes eso era borrar un fichero .db; con PostgreSQL es
crear y tirar una base entera.

Hace falta el motor levantado:

    docker compose up -d db

El servidor se indica con CUADRE_BD_TESTS, o se usa el de docker-compose.yml.
"""
import os

BASE_TESTS = os.environ.get(
    "CUADRE_BD_TESTS", "postgresql+psycopg://cuadre:cuadre@localhost:5433/postgres")

def _servidor():
    """El DSN de mantenimiento, sin nombre de base."""
    return BASE_TESTS.rsplit("/", 1)[0]

def dsn(nombre):
    return "%s/%s" % (_servidor(), nombre)

def base_limpia(nombre):
    """Deja `nombre` reci n creada y vacia, y devuelve su DSN.

    WITH (FORCE) echa las conexiones que hayan quedado abiertas de una ejecucion
    anterior; sin eso, un DROP se queda esperando para siempre.
    """
    from sqlalchemy import create_engine, text
    from cuadre import bd

    bd.cierra_motores()
    eng = create_engine(BASE_TESTS, isolation_level="AUTOCOMMIT", future=True)
    try:
        with eng.connect() as cx:
            cx.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % nombre))
            cx.execute(text('CREATE DATABASE "%s"' % nombre))
    finally:
        eng.dispose()
    return dsn(nombre)

def disponible():
    """¿Hay un PostgreSQL escuchando? Los tests avisan en vez de reventar."""
    from sqlalchemy import create_engine, text

    eng = create_engine(BASE_TESTS, future=True)
    try:
        with eng.connect() as cx:
            cx.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        eng.dispose()

AVISO = (
    "No hay un PostgreSQL escuchando en %s.\n"
    "Levanta el motor con:  docker compose up -d db\n"
    "O indica otro servidor con la variable de entorno CUADRE_BD_TESTS."
    % BASE_TESTS.rsplit("@", 1)[-1])
