# -*- coding: utf-8 -*-
"""Pruebas de la API, con el mismo juego de datos inventado del test basico.

    docker compose up -d db
    python tests/test_api.py

Recorre el camino entero como lo hara el frontend: subir los dos libros, esperar
a que el trabajo termine, leer el resultado en JSON, descargar los tres ficheros
y consultar el historico. No comprueba las cifras del cuadre --de eso ya se
encargan los otros dos tests-- sino que la capa HTTP no se pierda nada por el
camino y que los errores se cuenten como tales.
"""
import io
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import entorno
import test_basico as TB

ESPERA = 180          # segundos como mucho por cuadre


def comprueba(nombre, obtenido, esperado, tol=0.005):
    ok = (abs(obtenido - esperado) <= tol if isinstance(esperado, float)
          else obtenido == esperado)
    print("  %-38s %-22s %s" % (nombre, str(obtenido)[:22],
                                "OK" if ok else "FALLA (esperado %s)" % esperado))
    return ok


def _sube(cliente, a3, bk, **params):
    ficheros = [("a3", (n, open(os.path.join(a3, n), "rb"), "text/csv"))
                for n in sorted(os.listdir(a3))]
    ficheros += [("bilky", (n, open(os.path.join(bk, n), "rb"), "text/csv"))
                 for n in sorted(os.listdir(bk))]
    return cliente.post("/api/cuadres", files=ficheros, params=params)


def _espera(cliente, tid):
    t0 = time.time()
    while time.time() - t0 < ESPERA:
        d = cliente.get("/api/cuadres/%s" % tid).json()
        if d["estado"] in ("hecho", "fallido"):
            return d
        time.sleep(0.5)
    raise AssertionError("el cuadre %s no ha terminado en %d s" % (tid, ESPERA))


def main():
    if not entorno.disponible():
        print(entorno.AVISO)
        return 3

    os.environ["CUADRE_BD"] = entorno.base_limpia("cuadre_test_api")
    from cuadre import bd
    bd.cierra_motores()

    from fastapi.testclient import TestClient
    from api.main import app

    carpeta = tempfile.mkdtemp(prefix="cuadre-api-")
    fallos = 0
    try:
        a3, bk = TB.prepara(carpeta)
        with TestClient(app) as cliente:
            print("\nSALUD")
            r = cliente.get("/api/salud")
            fallos += not comprueba("responde", r.status_code, 200)
            fallos += not comprueba("estado", r.json()["estado"], "ok")

            print("\nUN CUADRE DE PUNTA A PUNTA")
            r = _sube(cliente, a3, bk, periodo="2T 2026", archivar=True)
            # 202 y no 200: el trabajo esta aceptado, no terminado.
            fallos += not comprueba("aceptado (202)", r.status_code, 202)
            tid = r.json()["id"]
            d = _espera(cliente, tid)
            fallos += not comprueba("termina bien", d["estado"], "hecho")
            if d["estado"] == "fallido":
                print("     error:", d["error"])
            fallos += not comprueba("periodo", d["periodo"], "2T 2026")
            fallos += not comprueba("lineas de A3", d["resumen"]["lineas_a3"], TB.LINEAS_A3)
            fallos += not comprueba("lineas de Bilky", d["resumen"]["lineas_bilky"], TB.LINEAS_BK)
            fallos += not comprueba("archivado en el historico", bool(d["carga_id"]), True)
            # El fichero sin NIF en el nombre se descarta, y eso es un aviso grave.
            graves = [a for a in d["avisos"] if a["nivel"] == "grave"]
            fallos += not comprueba("avisos graves", len(graves), 1)

            print("\nEL RESULTADO EN JSON")
            res = cliente.get("/api/cuadres/%s/resultado" % tid).json()
            fallos += not comprueba("diferencia de cuota", res["comparativa"]["dif"]["cuota"],
                                    TB.DIF_CUOTA)
            fallos += not comprueba("duplicadas", len(res["duplicadas"]["facturas"]), 2)
            fallos += not comprueba("trae las detecciones",
                                    sorted(res["detecciones"])[:3],
                                    ["cruzadas", "discrepantes", "dup_bilky"])
            fallos += not comprueba("nombres de sociedad", len(res["sociedades"]), 2)

            print("\nLOS TRES FICHEROS")
            fs = cliente.get("/api/cuadres/%s/ficheros" % tid).json()
            fallos += not comprueba("cuantos", len(fs), 3)
            fallos += not comprueba("claves", sorted(f["clave"] for f in fs),
                                    ["comparativa", "duplicadas", "excel"])
            for f in fs:
                r = cliente.get("/api/cuadres/%s/ficheros/%s" % (tid, f["clave"]))
                ok = r.status_code == 200 and len(r.content) == f["bytes"] > 1000
                fallos += not comprueba("  descarga %s" % f["clave"], ok, True)
            # El Excel tiene que salir como Excel, no como texto plano.
            r = cliente.get("/api/cuadres/%s/ficheros/excel" % tid)
            fallos += not comprueba("  el Excel es un xlsx", r.content[:2], b"PK")
            fallos += not comprueba("  se descarga adjunto",
                                    "attachment" in r.headers.get("content-disposition", ""), True)
            r = cliente.get("/api/cuadres/%s/ficheros/comparativa?incrustado=true" % tid)
            fallos += not comprueba("  el HTML incrustado no se adjunta",
                                    "content-disposition" not in r.headers, True)

            print("\nEL HISTORICO")
            fallos += not comprueba("periodos", cliente.get("/api/historico/periodos").json(),
                                    ["2T 2026"])
            soc = cliente.get("/api/historico/sociedades").json()
            fallos += not comprueba("sociedades", len(soc), 2)
            lin = cliente.get("/api/historico/lineas", params={"libro": "A3"}).json()
            fallos += not comprueba("lineas de A3 archivadas", len(lin), TB.LINEAS_A3)
            dup = cliente.get("/api/historico/duplicadas").json()
            fallos += not comprueba("duplicadas archivadas", len(dup), 2)

            print("\nLO QUE TIENE QUE FALLAR")
            r = cliente.get("/api/cuadres/noexiste")
            fallos += not comprueba("cuadre inventado -> 404", r.status_code, 404)
            r = cliente.get("/api/cuadres/%s/ficheros/inventado" % tid)
            fallos += not comprueba("fichero inventado -> 404", r.status_code, 404)
            r = cliente.post("/api/cuadres", files=[
                ("a3", ("libro.txt", io.BytesIO(b"no soy un libro"), "text/plain")),
                ("bilky", ("libro.csv", io.BytesIO(b"a;b\n1;2\n"), "text/csv"))])
            fallos += not comprueba("extension no admitida -> 415", r.status_code, 415)
            # Un CSV con las columnas que no son: tiene que ser 422 y no un 500.
            r = _sube(cliente, bk, bk, periodo="2T 2026")
            d = _espera(cliente, r.json()["id"])
            fallos += not comprueba("libro con columnas de otro", d["estado"], "fallido")
            fallos += not comprueba("  y dice cuales faltan",
                                    "faltan columnas" in (d["error"] or "").lower(), True)
            r = cliente.get("/api/cuadres/%s/resultado" % r.json()["id"])
            fallos += not comprueba("sin resultado si fallo -> 409", r.status_code, 409)

            print("\nBORRADO")
            fallos += not comprueba("borra el cuadre",
                                    cliente.delete("/api/cuadres/%s" % tid).status_code, 204)
            fallos += not comprueba("y ya no esta",
                                    cliente.get("/api/cuadres/%s" % tid).status_code, 404)
            r = cliente.delete("/api/historico/2T 2026")
            fallos += not comprueba("borra el periodo del historico", r.status_code, 200)
            fallos += not comprueba("historico vacio",
                                    cliente.get("/api/historico/periodos").json(), [])
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    print("\n%s" % ("=" * 70))
    print("API: %s (%d comprobaciones fallidas)"
          % ("TODO CORRECTO" if fallos == 0 else "HAY FALLOS", fallos))
    print("=" * 70)
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
