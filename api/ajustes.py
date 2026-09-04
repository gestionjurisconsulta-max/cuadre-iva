# -*- coding: utf-8 -*-
"""Configuracion de la API, toda por variables de entorno.

Nada de esto se versiona con valores de produccion: los de aqui son los de
desarrollo. En el VPS se pasan por el entorno del contenedor.
"""
import os

def _lista(valor, defecto):
    v = os.environ.get(valor, "")
    return [x.strip() for x in v.split(",") if x.strip()] or defecto

# Donde escucha. En el contenedor 0.0.0.0; en local da igual.
HOST = os.environ.get("CUADRE_API_HOST", "127.0.0.1")
PUERTO = int(os.environ.get("CUADRE_API_PUERTO", "8000"))

# Origenes que pueden llamar a la API desde el navegador. El de desarrollo de
# Vite es el 5173. En produccion se pone el dominio real y punto.
ORIGENES = _lista("CUADRE_ORIGENES", ["http://localhost:5173", "http://127.0.0.1:5173"])

# Cuantos cuadres a la vez. Cada uno tarda ~30 s y se come una CPU entera, asi
# que subirlo por encima de los nucleos disponibles solo empeora la espera.
TRABAJADORES = int(os.environ.get("CUADRE_TRABAJADORES", "2"))

# Tope de subida por peticion. Los libros de un trimestre son ~5 MB cada uno;
# 200 MB deja margen de sobra para subir los sueltos de todas las sociedades.
MAX_SUBIDA = int(os.environ.get("CUADRE_MAX_SUBIDA_MB", "200")) * 1024 * 1024

EXTENSIONES = (".xlsx", ".xlsm", ".xls", ".csv")

# Se usa en el aviso de la interfaz: en un servidor compartido la frase de que
# «los ficheros no salen de aqui» deja de ser verdad.
LOCAL = os.environ.get("CUADRE_LOCAL", "").lower() in ("1", "true", "si", "yes")
