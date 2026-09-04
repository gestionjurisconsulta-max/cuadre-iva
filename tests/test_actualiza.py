# -*- coding: utf-8 -*-
"""Subir una sociedad no puede borrar las demas del trimestre.

    docker compose up -d db
    python tests/test_actualiza.py

Cubre los dos modos de archivado. El que importa es «actualiza»: el despacho
corrige el libro de una sociedad y sube ese fichero solo, sin volver a subir las
otras setenta. Antes de que existiera este modo, esa subida dejaba el trimestre
con una sola sociedad y sin forma de deshacerlo, que es como se perdio el 3T
2026 una vez.

Reusa el juego de datos inventado de test_basico: dos sociedades, con lo justo
para distinguir cual se toca y cual no.
"""
import os
import shutil
import sys
import tempfile

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
from sqlalchemy import text

# Las dos sociedades del juego de datos, y cuantas lineas archiva cada una.
ACME, OTRA = "B01709237", "38092900R"
LINEAS_ACME, LINEAS_OTRA = 18, 2

fallos = 0

def comprueba(nombre, obtenido, esperado):
    global fallos
    ok = obtenido == esperado
    fallos += not ok
    print("  %-46s %-24s %s" % (nombre, str(obtenido)[:24],
                                "OK" if ok else "FALLA (esperado %s)" % esperado))

def _carga(cx):
    return cx.execute(text(
        "SELECT id, sociedades, lineas_a3, lineas_bilky, cuota_a3, cuota_bilky,"
        " dif_cuota, cuadra, tasa_regla FROM cargas ORDER BY id")).all()

def _por_sociedad(cx):
    return dict(cx.execute(text("SELECT emp, count(*) FROM lineas GROUP BY emp")).all())

def _solo_acme(a3d, bkd):
    """Los dos ficheros de una sola sociedad, como los subiria el despacho."""
    return ([os.path.join(a3d, "2026B01709237GACMESERVICIOSSL.csv")],
            [os.path.join(bkd, "B01709237-ACME-SERVICIOS-SL-libro-de-iva-facturas-"
                               "recibidas-Trimestre-2-2026.csv")])

def main():
    global fallos
    if not entorno.disponible():
        print(entorno.AVISO)
        return 3

    os.environ["CUADRE_BD"] = entorno.base_limpia("cuadre_test_actualiza")
    from cuadre import bd, pipeline
    bd.cierra_motores()

    raiz = tempfile.mkdtemp(prefix="cuadre-act-")
    try:
        TB.prepara(raiz)
        a3d, bkd = os.path.join(raiz, "a3"), os.path.join(raiz, "bk")
        una_a3, una_bk = _solo_acme(a3d, bkd)

        print("\nEL TRIMESTRE COMPLETO, ARCHIVADO")
        c = pipeline.analiza(a3d, bkd)
        pipeline.archiva(c, modo=pipeline.SUSTITUYE)
        with bd.motor().connect() as cx:
            cargas, por_emp = _carga(cx), _por_sociedad(cx)
        comprueba("una carga", len(cargas), 1)
        comprueba("dos sociedades", cargas[0][1], 2)
        comprueba("lineas de la que se va a corregir", por_emp.get(ACME), LINEAS_ACME)
        comprueba("lineas de la que no se toca", por_emp.get(OTRA), LINEAS_OTRA)
        cid, la3, cbk = cargas[0][0], cargas[0][2], cargas[0][5]

        print("\nSE SUBE SOLO UNA SOCIEDAD, MODO ACTUALIZA")
        c2 = pipeline.analiza(una_a3, una_bk)
        r2 = pipeline.archiva(c2, modo=pipeline.ACTUALIZA)
        comprueba("reutiliza la carga, no crea otra", r2["carga_id"], cid)
        comprueba("dice que sociedades ha tocado", r2["sociedades"], [ACME])
        with bd.motor().connect() as cx:
            cargas, por_emp = _carga(cx), _por_sociedad(cx)
        comprueba("sigue habiendo una sola carga", len(cargas), 1)
        # Lo que se perdia antes:
        comprueba("LA OTRA SOCIEDAD SIGUE ARCHIVADA", por_emp.get(OTRA), LINEAS_OTRA)
        comprueba("y la corregida, con sus lineas", por_emp.get(ACME), LINEAS_ACME)

        print("\n  el resumen se recalcula desde el detalle")
        comprueba("sociedades", cargas[0][1], 2)
        comprueba("lineas_a3, como antes de la subida parcial", cargas[0][2], la3)
        comprueba("cuota_bilky, como antes", cargas[0][5], cbk)
        comprueba("dif_cuota = cuota_a3 - cuota_bilky",
                  round(float(cargas[0][6]), 2),
                  round(float(cargas[0][4]) - float(cargas[0][5]), 2))
        # No son derivables de una subida parcial: mejor un hueco que un numero
        # heredado que ya no describe lo que hay archivado.
        comprueba("cuadra se queda vacio", cargas[0][7], None)
        comprueba("tasa_regla se queda vacia", cargas[0][8], None)

        with bd.motor().connect() as cx:
            d = cx.execute(text(
                "SELECT (SELECT count(*) FROM lineas WHERE libro='A3'),"
                " (SELECT count(*) FROM lineas WHERE libro='BILKY'),"
                " (SELECT count(DISTINCT emp) FROM lineas),"
                " (SELECT round(sum(cuota)::numeric,2) FROM lineas WHERE libro='A3')")).first()
        comprueba("lineas_a3 = las que hay", cargas[0][2], d[0])
        comprueba("lineas_bilky = las que hay", cargas[0][3], d[1])
        comprueba("sociedades = las que hay", cargas[0][1], d[2])
        comprueba("cuota_a3 = la suma de las lineas", round(float(cargas[0][4]), 2), float(d[3]))

        print("\nSUSTITUIR SIGUE SUSTITUYENDO")
        c3 = pipeline.analiza(una_a3, una_bk)
        pipeline.archiva(c3, modo=pipeline.SUSTITUYE)
        with bd.motor().connect() as cx:
            cargas, por_emp = _carga(cx), _por_sociedad(cx)
        comprueba("la sociedad que no venia, fuera", por_emp.get(OTRA), None)
        comprueba("el trimestre es solo lo subido", cargas[0][1], 1)

        print("\nACTUALIZAR UN PERIODO VACIO ES CREARLO")
        os.environ["CUADRE_BD"] = entorno.base_limpia("cuadre_test_actualiza_nuevo")
        bd.cierra_motores()
        c4 = pipeline.analiza(una_a3, una_bk)
        r4 = pipeline.archiva(c4, modo=pipeline.ACTUALIZA)
        comprueba("dice que la ha creado", r4["carga_id"] is not None, True)
        with bd.motor().connect() as cx:
            cargas, por_emp = _carga(cx), _por_sociedad(cx)
        comprueba("con la sociedad subida", por_emp.get(ACME), LINEAS_ACME)
        comprueba("y el resumen puesto", cargas[0][1], 1)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("\n" + "=" * 70)
    print("ACTUALIZA: %s (%d comprobaciones fallidas)"
          % ("TODO CORRECTO" if not fallos else "HAY FALLOS", fallos))
    print("=" * 70)
    return 1 if fallos else 0

if __name__ == "__main__":
    sys.exit(main())
