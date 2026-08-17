# -*- coding: utf-8 -*-
"""Cuadre de IVA A3 . Bilky desde linea de comandos.

    python cuadre_cli.py --a3 LIBRO_A3.xlsx --bilky LIBRO_BILKY.xlsx --salida CARPETA

Devuelve codigo 0 si la conciliacion cuadra y no hay avisos graves, 1 si no.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# La consola de Windows es cp1252 y no sabe pintar el signo menos tipografico.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from cuadre import pipeline
from cuadre.informes import ent, eur
from cuadre.lectura import ErrorDeLectura


def main():
    p = argparse.ArgumentParser(description="Cuadre de IVA soportado A3 contra Bilky")
    p.add_argument("--a3", required=True, nargs="+",
                   help="Fichero(s) o carpeta del libro de A3 (xlsx o csv)")
    p.add_argument("--bilky", required=True, nargs="+",
                   help="Fichero(s) o carpeta del libro de Bilky (xlsx o csv)")
    p.add_argument("--salida", default=".", help="Carpeta donde escribir los informes")
    p.add_argument("--periodo", default=None, help="P. ej. '3T 2026'. Por defecto se deduce")
    p.add_argument("--bd", action="store_true",
                   help="Archiva la ejecucion en el historico (sustituye la del mismo periodo)")
    p.add_argument("--ruta-bd", default=None, help="Fichero SQLite. Por defecto datos/cuadre.db")
    args = p.parse_args()

    for ruta in list(args.a3) + list(args.bilky):
        if not os.path.exists(ruta):
            print("No existe: %s" % ruta)
            return 2

    a3 = args.a3[0] if len(args.a3) == 1 else args.a3
    bilky = args.bilky[0] if len(args.bilky) == 1 else args.bilky

    try:
        res = pipeline.ejecuta(a3, bilky, args.salida, periodo=args.periodo,
                               progreso=lambda t: print("  " + t),
                               guardar_en_bd=args.bd, ruta_bd=args.ruta_bd)
    except ErrorDeLectura as e:
        print("\nERROR DE LECTURA\n%s" % e)
        return 2

    r = res["resumen"]
    print("\n%s" % ("=" * 72))
    print("CUADRE DE IVA SOPORTADO%s" % ((" - " + res["periodo"]) if res["periodo"] else ""))
    print("=" * 72)
    print("  A3     %9s lineas   %16s EUR de cuota   (%d fichero(s))"
          % (ent(r["lineas_a3"]), eur(r["cuota_a3"]), r.get("ficheros_a3", 1)))
    print("  Bilky  %9s lineas   %16s EUR de cuota   (%d fichero(s))"
          % (ent(r["lineas_bilky"]), eur(r["cuota_bilky"]), r.get("ficheros_bilky", 1)))
    print("  %d sociedades   |   regla de truncado: %.1f%% de acierto"
          % (r["sociedades"], 100 * res["regla"]["tasa"]))
    print("-" * 72)
    print("  Diferencia de cuota            %16s EUR   %s"
          % (eur(res["dif_cuota"]), "CUADRA" if res["cuadra"] else "*** NO CUADRA ***"))
    print("  Facturas comunes que cuadran   %9s de %s" % (ent(r["cuadran"]), ent(r["facturas_comunes"])))
    print("  Solo en A3 / solo en Bilky     %9s / %s" % (ent(r["solo_a3"]), ent(r["solo_bilky"])))
    print("  Duplicadas                     %9s detectadas, %s requieren accion (%s EUR)"
          % (ent(r["duplicadas"]), ent(r["duplicadas_accion"]), eur(r["duplicadas_iva"])))

    graves = [a for a in res["avisos"] if a["nivel"] == "grave"]
    otros = [a for a in res["avisos"] if a["nivel"] != "grave"]
    if graves:
        print("-" * 72)
        for a in graves:
            print("  GRAVE  %s" % a["texto"])
    if otros:
        print("-" * 72)
        for a in otros:
            print("  %-6s %s" % (a["nivel"].upper(), a["texto"]))
    print("-" * 72)
    for f in res["ficheros"]:
        print("  -> %s" % f)
    if res.get("bd"):
        print("  -> historico: carga %d en %s%s"
              % (res["bd"]["carga_id"], res["bd"]["ruta"],
                 " (sustituye %d anterior)" % res["bd"]["sustituidas"]
                 if res["bd"]["sustituidas"] else ""))
    print("=" * 72)
    return 0 if (res["cuadra"] and not graves) else 1


if __name__ == "__main__":
    sys.exit(main())
