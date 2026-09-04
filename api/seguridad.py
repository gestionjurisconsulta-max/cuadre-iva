# -*- coding: utf-8 -*-
"""Autenticacion de la API.

La sesion viaja en una cookie httpOnly, no en un token guardado por el
navegador. Es la diferencia entre que un fallo de XSS sea una molestia o sea el
robo de la sesion: a una cookie httpOnly el JavaScript de la pagina no llega.

No hay permisos: quien entra ve todo. Lo unico que separa esta funcion es estar
dentro o fuera.
"""
import os
from fastapi import Cookie, HTTPException
from cuadre import usuarios

COOKIE = "cuadre_sesion"

# En el VPS la aplicacion va por https y la cookie debe viajar solo por ahi. En
# local no hay https, asi que Secure la haria inservible.
SEGURA = os.environ.get("CUADRE_COOKIE_SEGURA", "").lower() in ("1", "true", "si", "yes")

# Lax y no None: el frontend y la API se sirven del mismo sitio detras de nginx,
# asi que no hace falta abrirla a peticiones de terceros. Con None habria que
# pensar ademas en CSRF.
MISMO_SITIO = os.environ.get("CUADRE_COOKIE_SAMESITE", "lax")

def pon_cookie(respuesta, testigo):
    respuesta.set_cookie(
        COOKIE, testigo,
        httponly=True, secure=SEGURA, samesite=MISMO_SITIO, path="/",
        max_age=usuarios.DIAS_SESION * 24 * 3600,
    )

def quita_cookie(respuesta):
    respuesta.delete_cookie(COOKIE, path="/", httponly=True,
                            secure=SEGURA, samesite=MISMO_SITIO)

def usuario_actual(cuadre_sesion: str | None = Cookie(default=None)):
    """Dependencia de FastAPI: corta la peticion si no hay sesion viva."""
    u = usuarios.de_testigo(cuadre_sesion)
    if not u:
        raise HTTPException(401, "Hay que iniciar sesión.")
    return u
