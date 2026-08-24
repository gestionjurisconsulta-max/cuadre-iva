# -*- coding: utf-8 -*-
"""Regresion contra el 2T 2026, que esta revisado a mano.

Si cambia algo del motor y estas cifras dejan de salir, es que se ha roto.

    python tests/test_regresion.py

Los ficheros del trimestre se buscan en la carpeta indicada por la variable de
entorno CUADRE_DATOS, o en la ruta por defecto de OneDrive.
"""
import os
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
from cuadre import pipeline

POR_DEFECTO = os.path.join(
    os.path.expanduser("~"), "OneDrive - Victor Cisneros", "Contabilidad - 2024",
    "LIBROS DE IVA 2T 2026", "prueba de libros 2t")
CARPETA = os.environ.get("CUADRE_DATOS", POR_DEFECTO)
A3 = os.path.join(CARPETA, "REVISION FACTURA A3 2T 2026.xlsx")
BILKY = os.path.join(CARPETA, "REVISION FACTURA BILKY 2T 2026.xlsx")

# Cifras verificadas a mano sobre el 2T 2026.
#
# Las de duplicadas subieron de 51 a 54 al dar un margen de TOL_DUP entre las
# dos capturas de un mismo documento: antes un centimo de diferencia las partia
# en dos grupos y no se marcaban. Las tres que aparecieron estan comprobadas
# contra Bilky: TUC EXPRESS 003196 (2.719,03 €), ELECCIO BELLA 2026000012
# (145,68 €) y una linea mas de MERCADONA 0001698087 (0,50 €).
ESPERADO = {
    "lineas_a3": 34768,
    "lineas_bilky": 33401,
    "sociedades": 93,
    "cuota_a3": 2216121.79,
    "cuota_bilky": 2141803.48,
    "facturas_comunes": 32947,
    "cuadran": 32901,
    "solo_a3": 603,
    "solo_bilky": 155,
    "duplicadas": 54,
    "duplicadas_accion": 50,
    "duplicadas_iva": 4879.20,
}
DIF_CUOTA = 74318.31
CONCILIACION = [163850.72, -80025.85, -9550.71, 44.15]
VEREDICTOS = {"solo_a3": (33, 10.17), "doc_repetido": (16, 4854.14),
              "sincontraste": (1, 14.89), "falso": (4, 441.00),
              "linea_repetida": (0, 0.0)}
COLISIONES = 7
TASA_MINIMA = 0.99

# Detecciones que no dependen de A3 ni del criterio de coincidencia exacta.
# Revisadas a mano una a una sobre el 2T 2026.
DUP_BILKY_IGUAL = 18          # facturas capturadas dos veces en Bilky por el mismo importe
DUP_BILKY_IVA = 5123.81       # IVA que sobra por esas duplicaciones
DUP_BILKY_REVISAR = 21        # mismo numero y fecha con importes que no cuadran
CRUZADAS = 0                  # ninguna factura del 2T esta en dos sociedades
TIPOS_INVALIDOS = {12.0, 2.0, 10.5}   # tipos que no existen en el impuesto
DISCREPANTES_MINIMO = 1       # al menos la de ORCONSA: ES20 en A3, CB150 en Bilky


def comprueba(nombre, obtenido, esperado, tol=0.005):
    ok = (abs(obtenido - esperado) <= tol if isinstance(esperado, float)
          else obtenido == esperado)
    print("  %-26s %-16s %s" % (nombre, obtenido, "OK" if ok else "FALLA (esperado %s)" % esperado))
    return ok


def main():
    if not (os.path.exists(A3) and os.path.exists(BILKY)):
        print("No se encuentran los ficheros del 2T 2026 en:\n  %s\n"
              "Indica la carpeta con la variable de entorno CUADRE_DATOS." % CARPETA)
        return 3

    salida = os.path.join(tempfile.gettempdir(), "cuadre-regresion")
    res = pipeline.ejecuta(A3, BILKY, salida, periodo="2T 2026")
    r = res["resumen"]
    fallos = 0

    print("\nRESUMEN")
    for k, v in ESPERADO.items():
        fallos += not comprueba(k, r[k], v)

    print("\nCONCILIACION")
    fallos += not comprueba("diferencia de cuota", res["dif_cuota"], DIF_CUOTA)
    fallos += not comprueba("cuadra", res["cuadra"], True)

    from cuadre import analisis, lectura
    a3 = lectura.lee_a3(A3)
    bk = lectura.lee_bilky(BILKY)
    cot = analisis.coteja(a3, bk)
    con = analisis.concilia(a3, bk, cot)
    valores = [p["valor"] for p in con["partidas"]]
    fallos += not comprueba("partidas", len(valores), len(CONCILIACION))
    for i, esperado in enumerate(CONCILIACION):
        if i < len(valores):
            fallos += not comprueba("  partida %d" % (i + 1), valores[i], esperado)

    print("\nDUPLICADAS")
    dup = analisis.duplicadas(a3, bk)
    for v, (n, iva) in VEREDICTOS.items():
        fallos += not comprueba(v + " (facturas)", dup["resumen"][v]["fras"], n)
        fallos += not comprueba(v + " (IVA)", dup["resumen"][v]["iva"], iva)

    print("\nDETECCIONES QUE NO DEPENDEN DE A3")
    sosp = analisis.numeros_sospechosos(bk)
    db = analisis.duplicadas_en_bilky(bk, sosp)
    iguales = [f for f in db if f["clase"] == "igual"]
    fallos += not comprueba("duplicadas en Bilky", len(iguales), DUP_BILKY_IGUAL)
    fallos += not comprueba("IVA que sobra", round(sum(f["sobrante"] for f in iguales), 2),
                            DUP_BILKY_IVA)
    fallos += not comprueba("a revisar en Bilky",
                            len([f for f in db if f["clase"] == "distinto"]), DUP_BILKY_REVISAR)
    # La mas cara del trimestre, y se le escapaba al criterio anterior por 0,01 €.
    tuc = [f for f in iguales if f["num"] == "003196"]
    fallos += not comprueba("TUC EXPRESS detectada", len(tuc), 1)
    if tuc:
        fallos += not comprueba("  IVA de TUC EXPRESS", tuc[0]["sobrante"], 2719.03)
    fallos += not comprueba("misma factura en 2 soc.",
                            len(analisis.misma_factura_dos_sociedades(a3, bk, sosp)), CRUZADAS)
    tipos = set(t["tipo"] for t in analisis.tipos_invalidos(a3) + analisis.tipos_invalidos(bk))
    fallos += not comprueba("tipos de IVA invalidos", tipos, TIPOS_INVALIDOS)
    disc = analisis.numeros_discrepantes(cot)
    fallos += not comprueba("numeros discrepantes", len(disc) >= DISCREPANTES_MINIMO, True)
    orconsa = [d for d in disc if d["num_a3"] == "ES20"]
    fallos += not comprueba("  ORCONSA ES20 -> CB150",
                            orconsa[0]["num_bilky"] if orconsa else "", "CB150")
    # Los dos libros del 2T estan bien exportados: ninguno viene x100.
    fallos += not comprueba("escala A3", analisis.escala(a3), None)
    fallos += not comprueba("escala Bilky", analisis.escala(bk), None)

    print("\nREGLA DE TRUNCADO")
    fallos += not comprueba("colisiones", len(cot.colisiones), COLISIONES)
    ok = cot.regla["tasa"] >= TASA_MINIMA
    print("  %-26s %-16s %s" % ("tasa de acierto", "%.4f" % cot.regla["tasa"],
                                "OK" if ok else "FALLA (minimo %.2f)" % TASA_MINIMA))
    fallos += not ok

    print("\nFICHEROS")
    for f in res["ficheros"]:
        existe = os.path.exists(f) and os.path.getsize(f) > 1000
        print("  %-58s %s" % (os.path.basename(f), "OK" if existe else "FALLA"))
        fallos += not existe

    print("\nHISTORICO")
    from cuadre import bd
    ruta_bd = entorno.base_limpia("cuadre_test_regresion")
    pipeline.ejecuta(A3, BILKY, salida, periodo="2T 2026", guardar_en_bd=True, ruta_bd=ruta_bd)
    fallos += not comprueba("periodos", len(bd.periodos(ruta_bd)), 1)
    lineas_todas = bd.lineas(ruta_bd)
    fallos += not comprueba("lineas archivadas", len(lineas_todas),
                            ESPERADO["lineas_a3"] + ESPERADO["lineas_bilky"])
    a3l = lineas_todas[lineas_todas.libro == "A3"]
    fallos += not comprueba("cuota A3 en bd", round(float(a3l.cuota.sum()), 2),
                            ESPERADO["cuota_a3"], tol=0.02)
    fallos += not comprueba("duplicadas archivadas", len(bd.duplicadas(ruta_bd)),
                            ESPERADO["duplicadas"])
    # Las fechas se guardan como texto y se filtran comparando texto: si alguna
    # tabla las escribe en dd/mm/aaaa, su filtro por rango devuelve cero en
    # silencio. Le paso a las duplicadas el rango del propio trimestre.
    dup_rango = bd.duplicadas(ruta_bd, desde="2026-01-01", hasta="2026-12-31")
    fallos += not comprueba("duplicadas filtradas por fecha", len(dup_rango),
                            ESPERADO["duplicadas"])
    q2 = bd.lineas(ruta_bd, desde="2026-04-01", hasta="2026-06-30", libro="A3")
    fallos += not comprueba("A3 con fecha dentro del 2T", len(q2), len(a3l) - 1912)
    fallos += not comprueba("sin duplicados entre trimestres",
                            len(bd.duplicadas_entre_periodos(ruta_bd)), 0)
    # una segunda carga del mismo periodo sustituye, no acumula
    pipeline.ejecuta(A3, BILKY, salida, periodo="2T 2026", guardar_en_bd=True, ruta_bd=ruta_bd)
    fallos += not comprueba("recarga no acumula", len(bd.lineas(ruta_bd)),
                            ESPERADO["lineas_a3"] + ESPERADO["lineas_bilky"])
    fallos += not comprueba("sigue habiendo 1 carga", len(bd.cargas(ruta_bd)), 1)

    print("\nSUBIDA DESDE LA INTERFAZ")
    # La interfaz manda listas de (nombre, buffer), no rutas. Es un camino
    # distinto al del CLI y ya se rompio una vez, asi que se prueba aparte.
    import io as _io

    def par(ruta):
        with open(ruta, "rb") as f:
            return (os.path.basename(ruta), _io.BytesIO(f.read()))

    ruta_bd2 = entorno.base_limpia("cuadre_test_interfaz")
    rui = pipeline.ejecuta([par(A3)], [par(BILKY)], salida, periodo="2T 2026",
                           guardar_en_bd=True, ruta_bd=ruta_bd2)
    fallos += not comprueba("diferencia de cuota", rui["dif_cuota"], DIF_CUOTA)
    fallos += not comprueba("lineas A3", rui["resumen"]["lineas_a3"], ESPERADO["lineas_a3"])
    fallos += not comprueba("archivado", len(bd.lineas(ruta_bd2)),
                            ESPERADO["lineas_a3"] + ESPERADO["lineas_bilky"])

    print("\nENTRADAS ADMITIDAS")
    from cuadre import lectura
    casos = [
        ("2026B01709237GPAKSPASERVICIOSINTEGRALESSL.csv", "B01709237"),
        ("202638092900RGCISNEROSMULLERVICTOR.csv", "38092900R"),
        ("202624491408LGROJASDELACRUZGROVER.csv", "24491408L"),
        ("Export-Bilky-Factura-recibida-B01709237-Trimestre-2-2026.xlsx", "B01709237"),
        ("B10994051-ALADDIN-786-SL-libro-de-iva-facturas-recibidas-Trimestre-1-2026.xlsx",
         "B10994051"),
    ]
    for nombre, esperado in casos:
        fallos += not comprueba(nombre[:26], lectura.nif_de_nombre(nombre), esperado)

    print("\n%s" % ("=" * 60))
    print("REGRESION: %s (%d comprobaciones fallidas)"
          % ("TODO CORRECTO" if fallos == 0 else "HAY FALLOS", fallos))
    print("=" * 60)
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
