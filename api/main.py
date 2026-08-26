# -*- coding: utf-8 -*-
"""API del cuadre de IVA.

    uvicorn api.main:app --reload

Sirve tanto el analisis en JSON como los tres ficheros generados, para que el
frontend pueda pintar los datos por su cuenta o limitarse a ofrecer la descarga.

Todo lo pesado ocurre en api/ejecutor.py: aqui solo se aceptan las subidas y se
consulta el estado.
"""
import io
import logging
import os
import zipfile
from contextlib import asynccontextmanager

from fastapi import (APIRouter, Cookie, Depends, FastAPI, HTTPException, Query,
                     Request, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from cuadre import bd, exporta, trabajos, usuarios
from cuadre.lectura import ErrorDeLectura

from . import ajustes, ejecutor, seguridad

logging.basicConfig(level=os.environ.get("CUADRE_LOG", "INFO"),
                    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s")
log = logging.getLogger("cuadre.api")


@asynccontextmanager
async def ciclo(app):
    # Al arrancar: crear el esquema si falta y recoger lo que quedo a medias de
    # un reinicio anterior, para que nadie se quede esperando un trabajo muerto.
    bd.motor()
    try:
        limpieza = trabajos.limpia()
        if limpieza["borrados"] or limpieza["recuperados"]:
            log.info("limpieza inicial: %s", limpieza)
    except Exception:
        log.exception("no se ha podido limpiar la cola al arrancar")
    yield
    ejecutor.apaga()


app = FastAPI(title="Cuadre de IVA · A3 contra Bilky", version="2.0", lifespan=ciclo)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ajustes.ORIGENES,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# Todo lo que toca datos exige sesion. No hay permisos por encima de eso:
# quien entra ve y hace todo.
protegido = APIRouter(dependencies=[Depends(seguridad.usuario_actual)])


@app.exception_handler(ErrorDeLectura)
async def _error_de_lectura(request, exc):
    # No es un fallo del servidor: el fichero subido no tiene la forma esperada,
    # y el mensaje de lectura ya dice cual y por que.
    return JSONResponse(status_code=422, content={"detalle": str(exc)})


# --------------------------------------------------------------------------
# Cuadres
# --------------------------------------------------------------------------

async def _lee_subidas(ficheros, lado):
    if not ficheros:
        raise HTTPException(400, "No se ha subido ningún fichero de %s." % lado)
    salida, total = [], 0
    for f in ficheros:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ajustes.EXTENSIONES:
            raise HTTPException(
                415, "«%s» no es un fichero admitido. Se aceptan: %s."
                     % (f.filename, ", ".join(ajustes.EXTENSIONES)))
        datos = await f.read()
        total += len(datos)
        if total > ajustes.MAX_SUBIDA:
            raise HTTPException(413, "La subida supera los %d MB."
                                % (ajustes.MAX_SUBIDA // (1024 * 1024)))
        salida.append((os.path.basename(f.filename or "sin-nombre"), datos))
    return salida


@protegido.post("/api/cuadres", status_code=202)
async def crea_cuadre(a3: list[UploadFile], bilky: list[UploadFile],
                      periodo: str | None = Query(None),
                      archivar: bool = Query(False),
                      quien: dict = Depends(seguridad.usuario_actual)):
    """Acepta los dos libros y encola el cuadre. Devuelve el id del trabajo.

    Responde 202 y no 200 a proposito: el trabajo esta aceptado, no terminado.
    """
    libros_a3 = await _lee_subidas(a3, "A3")
    libros_bk = await _lee_subidas(bilky, "Bilky")
    tid = trabajos.crea(periodo=periodo or None, archivar=archivar,
                        usuario=quien["usuario"])
    ejecutor.encola(tid, libros_a3, libros_bk, periodo=periodo or None, archivar=archivar)
    log.info("cuadre %s encolado por %s: %d fichero(s) de A3, %d de Bilky",
             tid, quien["usuario"], len(libros_a3), len(libros_bk))
    return {"id": tid, "estado": trabajos.EN_COLA}


def _trabajo(tid):
    t = trabajos.estado(tid)
    if not t:
        raise HTTPException(404, "No existe el cuadre %s." % tid)
    return t


@protegido.get("/api/cuadres")
def lista_cuadres(limite: int = Query(50, ge=1, le=200)):
    return trabajos.lista(limite)


@protegido.get("/api/cuadres/{tid}")
def estado_cuadre(tid: str):
    """Estado, paso actual, resumen y avisos. Es lo que se consulta en bucle."""
    return _trabajo(tid)


@protegido.get("/api/cuadres/{tid}/resultado")
def resultado_cuadre(tid: str):
    """El analisis completo: lo mismo que pintan los dos informes."""
    t = _trabajo(tid)
    if t["estado"] != trabajos.HECHO:
        raise HTTPException(409, "El cuadre todavía no ha terminado (%s)." % t["estado"])
    return trabajos.resultado(tid)


@protegido.get("/api/cuadres/{tid}/ficheros")
def lista_ficheros(tid: str):
    _trabajo(tid)
    return trabajos.ficheros(tid)


@protegido.get("/api/cuadres/{tid}/ficheros/{clave}")
def descarga(tid: str, clave: str, incrustado: bool = Query(False)):
    """Devuelve uno de los tres ficheros.

    Con incrustado=true los HTML se sirven para verlos en un iframe; si no, se
    descargan.
    """
    _trabajo(tid)
    f = trabajos.fichero(tid, clave)
    if not f:
        raise HTTPException(404, "El cuadre %s no tiene el fichero «%s»." % (tid, clave))
    cabeceras = {}
    if not (incrustado and f["tipo_mime"].startswith("text/html")):
        cabeceras["Content-Disposition"] = 'attachment; filename="%s"' % f["nombre"]
    return Response(content=f["bytes"], media_type=f["tipo_mime"], headers=cabeceras)


@protegido.get("/api/cuadres/{tid}/ficheros.zip")
def descarga_zip(tid: str):
    """Los tres de una vez, que es como se los suele querer."""
    t = _trabajo(tid)
    fs = trabajos.ficheros(tid)
    if not fs:
        raise HTTPException(404, "El cuadre %s no tiene ficheros." % tid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for meta in fs:
            f = trabajos.fichero(tid, meta["clave"])
            z.writestr(f["nombre"], f["bytes"])
    sufijo = (" " + t["periodo"]) if t["periodo"] else ""
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="Cuadre IVA%s.zip"' % sufijo})


@protegido.delete("/api/cuadres/{tid}", status_code=204)
def borra_cuadre(tid: str):
    _trabajo(tid)
    trabajos.borra(tid)
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Historico
# --------------------------------------------------------------------------

def _tabla(df):
    return df.to_dict(orient="records")


@protegido.get("/api/historico/periodos")
def historico_periodos():
    return bd.periodos()


@protegido.get("/api/historico/resumen")
def historico_resumen():
    return _tabla(bd.resumen_por_periodo())


@protegido.get("/api/historico/sociedades")
def historico_sociedades():
    return _tabla(bd.sociedades())


@protegido.get("/api/historico/lineas")
def historico_lineas(desde: str | None = None, hasta: str | None = None,
                     libro: str | None = None, periodos: list[str] | None = Query(None),
                     emps: list[str] | None = Query(None),
                     limite: int = Query(5000, ge=1, le=100000)):
    return _tabla(bd.lineas(desde=desde, hasta=hasta, libro=libro,
                            periodos_=periodos, emps=emps, limite=limite))


@protegido.get("/api/historico/duplicadas")
def historico_duplicadas(desde: str | None = None, hasta: str | None = None,
                         veredictos: list[str] | None = Query(None),
                         periodos: list[str] | None = Query(None),
                         emps: list[str] | None = Query(None)):
    return _tabla(bd.duplicadas(desde=desde, hasta=hasta, veredictos=veredictos,
                                periodos_=periodos, emps=emps))


@protegido.get("/api/historico/descuadres")
def historico_descuadres(desde: str | None = None, hasta: str | None = None,
                         clases: list[str] | None = Query(None),
                         periodos: list[str] | None = Query(None),
                         emps: list[str] | None = Query(None)):
    return _tabla(bd.descuadres(desde=desde, hasta=hasta, clases=clases,
                                periodos_=periodos, emps=emps))


@protegido.get("/api/historico/entre-periodos")
def historico_entre_periodos(desde: str | None = None, hasta: str | None = None,
                             libro: str | None = None,
                             periodos: list[str] | None = Query(None),
                             emps: list[str] | None = Query(None),
                             minimo_iva: float = 0.01,
                             limite: int = Query(500, ge=1, le=5000)):
    """La misma factura declarada en dos trimestres. Solo se ve con historico.

    Los filtros acotan el universo antes de buscar las repeticiones: elegir 1T y
    3T es «mirando solo esos dos, cuales se repiten», no «las repetidas que
    ademas esten ahi».
    """
    return _tabla(bd.duplicadas_entre_periodos(
        desde=desde, hasta=hasta, libro=libro, periodos_=periodos, emps=emps,
        minimo_iva=minimo_iva, limite=limite))


@protegido.get("/api/historico/sospechosos")
def historico_sospechosos(limite: int = Query(1000, ge=1, le=5000)):
    """Numeros que no identifican ninguna factura, sobre todo lo archivado.

    En el informe de un cuadre esto sale del trimestre suelto. Aqui se ve lo
    que solo se nota cruzando: el mismo «numero» en varias sociedades.
    """
    return _tabla(bd.numeros_sospechosos(limite=limite))


@protegido.get("/api/historico/evolucion")
def historico_evolucion():
    return _tabla(bd.evolucion_duplicadas())


@protegido.get("/api/historico/rango")
def historico_rango():
    """La primera y la ultima fecha de factura archivadas, para los valores por defecto."""
    minimo, maximo = bd.rango_fechas()
    return {"desde": minimo, "hasta": maximo}


@protegido.get("/api/historico/resumen-filtrado")
def historico_resumen_filtrado(desde: str | None = None, hasta: str | None = None,
                               libro: str | None = None,
                               periodos: list[str] | None = Query(None),
                               emps: list[str] | None = Query(None)):
    """Cifras del rango y cuota por mes. Se calcula aqui: son ~68.000 lineas."""
    return exporta.resumen(desde=desde, hasta=hasta, libro=libro,
                           periodos=periodos, emps=emps)


@protegido.get("/api/historico/exportar.xlsx")
def historico_excel(desde: str | None = None, hasta: str | None = None,
                    libro: str | None = None,
                    periodos: list[str] | None = Query(None),
                    emps: list[str] | None = Query(None)):
    datos = exporta.excel(desde=desde, hasta=hasta, libro=libro, periodos=periodos, emps=emps)
    nombre = exporta.nombre("Historico IVA", desde, hasta)
    return Response(content=datos, media_type=exporta.MIME_XLSX,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % nombre})


@protegido.get("/api/historico/exportar.csv")
def historico_csv(desde: str | None = None, hasta: str | None = None,
                  libro: str | None = None,
                  periodos: list[str] | None = Query(None),
                  emps: list[str] | None = Query(None)):
    datos = exporta.csv_lineas(desde=desde, hasta=hasta, libro=libro,
                               periodos=periodos, emps=emps)
    nombre = exporta.nombre("Lineas IVA", desde, hasta, "csv")
    return Response(content=datos, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % nombre})


@protegido.delete("/api/historico/{periodo}")
def borra_del_historico(periodo: str, quien: dict = Depends(seguridad.usuario_actual)):
    """Borrar un trimestre entero. Cualquiera con sesion puede: no hay permisos."""
    n = bd.borra_periodo(None, periodo)
    if not n:
        raise HTTPException(404, "No hay ninguna carga del periodo «%s»." % periodo)
    log.warning("%s ha borrado del historico el periodo %s (%d carga)",
                quien["usuario"], periodo, n)
    return {"periodo": periodo, "cargas": n}


# --------------------------------------------------------------------------
# Entrar y salir
# --------------------------------------------------------------------------

@app.post("/api/auth/entrar")
def entrar(datos: dict, respuesta: Response, peticion: Request):
    """Comprueba la pareja y deja la sesion en una cookie httpOnly."""
    testigo, quien = usuarios.entra(
        datos.get("usuario"), datos.get("clave"),
        agente=peticion.headers.get("user-agent"))
    if not testigo:
        # El mismo mensaje tanto si el usuario no existe como si la clave esta
        # mal: distinguirlos diria cuales de los nombres probados son reales.
        log.warning("intento de entrada fallido para «%s» desde %s",
                    str(datos.get("usuario"))[:40],
                    peticion.client.host if peticion.client else "?")
        raise HTTPException(401, "Usuario o contraseña incorrectos.")
    seguridad.pon_cookie(respuesta, testigo)
    log.info("ha entrado %s", quien["usuario"])
    return quien


@app.post("/api/auth/salir", status_code=204)
def salir(respuesta: Response, cuadre_sesion: str | None = Cookie(default=None)):
    usuarios.sale(cuadre_sesion)
    seguridad.quita_cookie(respuesta)
    return Response(status_code=204)


@app.get("/api/auth/yo")
def yo(quien: dict = Depends(seguridad.usuario_actual)):
    """Quien soy. El frontend la usa al cargar para saber si hay sesion."""
    return quien


@protegido.post("/api/auth/clave", status_code=204)
def cambia_clave(datos: dict, respuesta: Response,
                 quien: dict = Depends(seguridad.usuario_actual)):
    """Cambiar la propia contrasena. Cierra las demas sesiones abiertas."""
    if not usuarios.verifica_usuario(quien["usuario"], datos.get("actual") or ""):
        raise HTTPException(400, "La contraseña actual no es correcta.")
    try:
        usuarios.cambia_clave(quien["usuario"], datos.get("nueva") or "")
    except usuarios.ErrorDeUsuario as e:
        raise HTTPException(400, str(e))
    seguridad.quita_cookie(respuesta)
    return Response(status_code=204)


# --------------------------------------------------------------------------
# Servicio
# --------------------------------------------------------------------------

@app.get("/api/salud")
def salud():
    """Para el healthcheck del contenedor y del proxy."""
    try:
        periodos = len(bd.periodos())
    except Exception as e:
        raise HTTPException(503, "Sin base de datos: %s" % e)
    return {"estado": "ok", "periodos": periodos, "local": ajustes.LOCAL,
            "hay_usuarios": usuarios.hay_alguno(),
            "tamano_historico": bd.tamano()}


@protegido.post("/api/mantenimiento/limpieza")
def limpieza(dias: int | None = Query(None, ge=0)):
    """Tira los cuadres viejos. Pensado para llamarlo desde un cron."""
    return trabajos.limpia(dias)


app.include_router(protegido)
