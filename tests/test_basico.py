# -*- coding: utf-8 -*-
"""Pruebas del motor con datos sinteticos. Corren en cualquier equipo.

    python tests/test_basico.py

No sustituyen a tests/test_regresion.py, que contrasta contra el 2T 2026 revisado
a mano y es la prueba que de verdad dice si las cifras son buenas. Esta de aqui
cubre lo otro: que el motor siga funcionando despues de cambiar de version de
pandas o de tocar el codigo, sin necesitar datos de ningun cliente.

El juego de datos es minimo pero ejercita cada camino del cuadre: factura comun,
numero truncado, solo en A3, solo en Bilky, diferencia de importe, rectificativa
huerfana, duplicada real, falso duplicado por colision y fichero descartado por
no llevar el NIF en el nombre. Las cifras estan calculadas a mano abajo.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from cuadre import analisis, bd, lectura, normaliza as N, pipeline

# --------------------------------------------------------------------------
# El juego de datos
# --------------------------------------------------------------------------
# Los numeros de A3 van tal como los deja A3: ya truncados a 10 caracteres y con
# los separadores convertidos en espacios. Los de Bilky van enteros.

CAB_A3 = ("Tipo de factura;Fecha expedicion;Serie-Numero;Identificacion NIF expedidor;"
          "Nombre expedidor;Total factura;Base imponible;Tipo de IVA;Cuota IVA soportado")
CAB_BK = ("Fecha;NIF;Nombre legal;Base imponible;IVA;Tipo de IVA;Total;"
          "Numero de factura;Identificador Bilky;Vinculo fra")

# Las filas de A3 llevan un ';' de mas al final, como las exporta de verdad. Si
# la lectura pierde el index_col=False, todas las columnas se desplazan.
A3_ACME = [
    "F1;15/05/2026;260107604;B11111111;CONSTRUCCIONES ÁVILA SL;1210,00;1000,00;21;210,00;",
    "F1;16/05/2026;000 009950;B11111111;CONSTRUCCIONES ÁVILA SL;242,00;200,00;21;42,00;",
    "F1;17/05/2026;SOLOA3 001;B22222222;PROVEEDOR SOLO EN A3 SL;605,00;500,00;21;105,00;",
    "F1;18/05/2026;DIFIMP 001;B33333333;IMPORTES DISTINTOS SL;1210,00;1000,00;21;210,00;",
    "R4;19/05/2026;RECT 001;B44444444;ABONOS Y RECTIFICATIVAS SL;-121,00;-100,00;21;-21,00;",
    "F1;20/05/2026;DUP 001;B55555555;DUPLICADA SL;363,00;300,00;21;63,00;",
    "F1;20/05/2026;DUP 001;B55555555;DUPLICADA SL;363,00;300,00;21;63,00;",
    "F1;21/05/2026;B26 033375;B66666666;COLISION SL;1210,00;1000,00;21;210,00;",
    "F1;22/05/2026;B26 033375;B66666666;COLISION SL;1210,00;1000,00;21;210,00;",
    "F1;23/05/2026;TIPO10 001;B77777777;TIPO REDUCIDO SL;110,00;100,00;10;10,00;",
]
BK_ACME = [
    "15/05/2026;B11111111;CONSTRUCCIONES ÁVILA SL;1000,00;210,00;21;1210,00;"
    "2026FA / 260107604;DOC1;https://app.bilky.com/documento/DOC1",
    "16/05/2026;B11111111;CONSTRUCCIONES ÁVILA SL;200,00;42,00;21;242,00;"
    "26/000/009950;DOC2;https://app.bilky.com/documento/DOC2",
    "18/05/2026;B33333333;IMPORTES DISTINTOS SL;900,00;189,00;21;1089,00;"
    "DIFIMP-001;DOC3;https://app.bilky.com/documento/DOC3",
    "20/05/2026;B55555555;DUPLICADA SL;300,00;63,00;21;363,00;"
    "DUP-001;DOC4;https://app.bilky.com/documento/DOC4",
    "21/05/2026;B66666666;COLISION SL;1000,00;210,00;21;1210,00;"
    "FNB26/033375;DOC5;https://app.bilky.com/documento/DOC5",
    "22/05/2026;B66666666;COLISION SL;1000,00;210,00;21;1210,00;"
    "XYB26/033375;DOC6;https://app.bilky.com/documento/DOC6",
    "23/05/2026;B77777777;TIPO REDUCIDO SL;100,00;10,00;10;110,00;"
    "TIPO10-001;DOC7;https://app.bilky.com/documento/DOC7",
    "24/05/2026;B88888888;SOLO EN BILKY SL;400,00;84,00;21;484,00;"
    "SOLOBK-001;DOC8;https://app.bilky.com/documento/DOC8",
]
# Segunda sociedad, persona fisica, con una factura que cuadra en los dos libros.
# Sirve para probar la union de varios ficheros y los patrones de nombre.
A3_PF = ["F1;25/05/2026;PF 001;B99999999;PROVEEDOR DE LA PERSONA FISICA SL;121,00;100,00;21;21,00;"]
BK_PF = ["25/05/2026;B99999999;PROVEEDOR DE LA PERSONA FISICA SL;100,00;21,00;21;121,00;"
         "PF-001;DOC9;https://app.bilky.com/documento/DOC9"]
# Fichero cuyo nombre no lleva NIF: sus dos lineas no se pueden atribuir a
# ninguna sociedad, se descartan, y el cuadre tiene que decirlo.
A3_HUERFANO = [
    "F1;10/05/2026;FX 001;B33333333;PROVEEDOR PERDIDO SL;1815,00;1500,00;21;315,00;",
    "F1;11/05/2026;FX 002;B33333333;PROVEEDOR PERDIDO SL;242,00;200,00;21;42,00;",
]

# Cifras calculadas a mano sobre lo anterior.
CUOTA_A3 = 1123.00      # 210+42+105+210-21+63+63+210+210+10 (ACME) + 21 (PF)
CUOTA_BK = 1039.00      # 210+42+189+63+210+210+10+84 (ACME) + 21 (PF)
DIF_CUOTA = 84.00       # 1123,00 - 1039,00
CONCILIACION = [
    105.00,             # solo en A3: SOLOA3 001
    -21.00,             # rectificativa huerfana: RECT 001, tipo R4
    -84.00,             # solo en Bilky: SOLOBK-001
    84.00,              # importes: DIFIMP (+21) y DUP capturada dos veces (+63)
]
LINEAS_A3 = 11          # 10 de ACME + 1 de la persona fisica; las 2 huerfanas fuera
LINEAS_BK = 9
CUOTA_DESCARTADA = 357.00   # 315,00 + 42,00


def escribe(ruta, cabecera, filas):
    """Los CSV de A3 salen en cp1252, no en UTF-8. Se escriben asi a proposito."""
    with open(ruta, "w", encoding="cp1252") as f:
        f.write("\n".join([cabecera] + filas) + "\n")


def prepara(carpeta):
    a3, bk = os.path.join(carpeta, "a3"), os.path.join(carpeta, "bk")
    os.makedirs(a3)
    os.makedirs(bk)
    escribe(os.path.join(a3, "2026B01709237GACMESERVICIOSSL.csv"), CAB_A3, A3_ACME)
    escribe(os.path.join(a3, "202638092900RGCISNEROSMULLERVICTOR.csv"), CAB_A3, A3_PF)
    escribe(os.path.join(a3, "libro de compras revisado.csv"), CAB_A3, A3_HUERFANO)
    escribe(os.path.join(bk, "B01709237-ACME-SERVICIOS-SL-libro-de-iva-facturas-"
                             "recibidas-Trimestre-2-2026.csv"), CAB_BK, BK_ACME)
    escribe(os.path.join(bk, "38092900R-CISNEROS-MULLER-VICTOR-libro-de-iva-facturas-"
                             "recibidas-Trimestre-2-2026.csv"), CAB_BK, BK_PF)
    return a3, bk


# --------------------------------------------------------------------------

def comprueba(nombre, obtenido, esperado, tol=0.005):
    ok = (abs(obtenido - esperado) <= tol if isinstance(esperado, float)
          else obtenido == esperado)
    print("  %-34s %-24s %s" % (nombre, obtenido, "OK" if ok else "FALLA (esperado %s)" % esperado))
    return ok


def main():
    carpeta = tempfile.mkdtemp(prefix="cuadre-basico-")
    try:
        return corre(carpeta)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def corre(carpeta):
    fallos = 0
    ruta_a3, ruta_bk = prepara(carpeta)

    print("\nLA REGLA DE TRUNCADO")
    # Los tres ejemplos que documenta el README.
    for entero, truncado in (("2026FA / 260107604", "260107604"),
                             ("26/000/009950", "000 009950"),
                             ("FNB26/033375", "B26 033375")):
        fallos += not comprueba(entero, N.como_a3(entero), truncado)
    # La clave tiene que igualar lo que A3 muestra con lo que Bilky guarda entero.
    fallos += not comprueba("clave A3 == clave Bilky",
                            N.clave("000 009950") == N.clave_bilky("26/000/009950"), True)

    print("\nEL NIF SALE DEL NOMBRE DEL FICHERO")
    for nombre, esperado in (
            ("2026B01709237GPAKSPASERVICIOSINTEGRALESSL.csv", "B01709237"),
            ("202638092900RGCISNEROSMULLERVICTOR.csv", "38092900R"),
            ("Export-Bilky-Factura-recibida-B01709237-Trimestre-2-2026.xlsx", "B01709237"),
            ("B10994051-ALADDIN-786-SL-libro-de-iva-facturas-recibidas-Trimestre-1-2026.xlsx",
             "B10994051"),
            ("libro de compras revisado.csv", None)):
        fallos += not comprueba(nombre[:32], lectura.nif_de_nombre(nombre), esperado)

    print("\nIMPORTES EN FORMATO ESPANOL")
    for crudo, esperado in (("1.234,56", 1234.56), ("1234,56", 1234.56), ("-121,00", -121.0),
                            ("(121,00)", -121.0), ("100,00 EUR", 100.0), ("1.234", 1234.0)):
        fallos += not comprueba(repr(crudo), lectura.importe(crudo), esperado)

    print("\nLECTURA")
    a3 = lectura.lee_a3(ruta_a3)
    bk = lectura.lee_bilky(ruta_bk)
    fallos += not comprueba("lineas de A3", len(a3), LINEAS_A3)
    fallos += not comprueba("lineas de Bilky", len(bk), LINEAS_BK)
    fallos += not comprueba("sociedades", a3.EMP.nunique(), 2)
    fallos += not comprueba("cuota de A3", round(float(a3.CUOTA.sum()), 2), CUOTA_A3)
    fallos += not comprueba("cuota de Bilky", round(float(bk.CUOTA.sum()), 2), CUOTA_BK)
    # El ';' de mas al final de cada fila de A3 no debe desplazar las columnas.
    # Se busca la fila por su numero, porque el orden de lectura es el alfabetico
    # de los nombres de fichero, no el que se lea aqui arriba.
    fila = a3[a3.NUM == "260107604"].iloc[0]
    fallos += not comprueba("columnas sin desplazar: base", float(fila.BASE), 1000.0)
    fallos += not comprueba("columnas sin desplazar: cuota", float(fila.CUOTA), 210.0)
    fallos += not comprueba("columnas sin desplazar: tipo", float(fila.TIPO), 21.0)
    fallos += not comprueba("columnas sin desplazar: tipo fra", str(fila.TIPOFRA), "F1")
    # Los CSV vienen en cp1252, no en UTF-8: la tilde tiene que sobrevivir.
    fallos += not comprueba("acento leido en cp1252", "ÁVILA" in str(fila.NOMBRE), True)
    nombres = lectura.nombres_sociedades(bk, a3)
    fallos += not comprueba("nombre de la sociedad", nombres.get("B01709237"), "ACME SERVICIOS SL")

    print("\nFICHERO DESCARTADO")
    desc = a3.attrs.get("descartadas", [])
    fallos += not comprueba("ficheros con lineas descartadas", len(desc), 1)
    if desc:
        fallos += not comprueba("lineas descartadas", desc[0]["lineas"], 2)
        fallos += not comprueba("cuota descartada", round(desc[0]["cuota"], 2), CUOTA_DESCARTADA)

    print("\nCOTEJO")
    cot = analisis.coteja(a3, bk)
    fallos += not comprueba("tasa de la regla", round(cot.regla["tasa"], 4), 1.0)
    fallos += not comprueba("la regla es fiable", cot.regla["fiable"], True)
    fallos += not comprueba("solo en A3", len(cot.solo_a), 2)          # SOLOA3 001 y RECT 001
    fallos += not comprueba("solo en Bilky", len(cot.solo_b), 1)       # SOLOBK-001
    fallos += not comprueba("diferencias de importe", len(cot.dif_comunes), 2)
    fallos += not comprueba("colisiones de numero", len(cot.colisiones), 1)

    print("\nCONCILIACION")
    con = analisis.concilia(a3, bk, cot)
    fallos += not comprueba("diferencia total de cuota", con["total"], DIF_CUOTA)
    fallos += not comprueba("cuadra", con["cuadra"], True)
    fallos += not comprueba("suma de las partidas", con["suma"], DIF_CUOTA)
    valores = [p["valor"] for p in con["partidas"]]
    fallos += not comprueba("numero de partidas", len(valores), len(CONCILIACION))
    for i, esperado in enumerate(CONCILIACION):
        if i < len(valores):
            fallos += not comprueba("  %s" % con["partidas"][i]["clave"], valores[i], esperado)

    print("\nDUPLICADAS")
    dup = analisis.duplicadas(a3, bk)
    fallos += not comprueba("detectadas", dup["meta"]["fras"], 2)
    fallos += not comprueba("requieren accion", dup["meta"]["accion_fras"], 1)
    fallos += not comprueba("IVA a revisar", dup["meta"]["accion_iva"], 63.00)
    # En A3 dos veces, en Bilky una: sobra una linea y hay que corregirla en A3.
    fallos += not comprueba("veredicto solo_a3", dup["resumen"]["solo_a3"]["fras"], 1)
    # Dos facturas distintas de Bilky que A3 reduce al mismo numero: no es duplicado.
    fallos += not comprueba("veredicto falso", dup["resumen"]["falso"]["fras"], 1)
    fallos += not comprueba("IVA del falso positivo", dup["resumen"]["falso"]["iva"], 210.00)

    print("\nEJECUCION COMPLETA")
    salida = os.path.join(carpeta, "salida")
    res = pipeline.ejecuta(ruta_a3, ruta_bk, salida, periodo="2T 2026")
    fallos += not comprueba("cuadra", res["cuadra"], True)
    fallos += not comprueba("diferencia de cuota", res["dif_cuota"], DIF_CUOTA)
    fallos += not comprueba("periodo", res["periodo"], "2T 2026")
    for f in res["ficheros"]:
        existe = os.path.exists(f) and os.path.getsize(f) > 1000
        fallos += not comprueba("  " + os.path.basename(f)[:30], existe, True)

    print("\nAVISOS")
    graves = [a for a in res["avisos"] if a["nivel"] == "grave"]
    for a in res["avisos"]:
        print("  [%-5s] %s" % (a["nivel"], a["texto"][:100]))
    # El unico grave debe ser el del fichero descartado: todo lo demas cuadra.
    fallos += not comprueba("avisos graves", len(graves), 1)
    if graves:
        fallos += not comprueba("habla del descarte", "descartado" in graves[0]["texto"], True)
        fallos += not comprueba("dice cuanta cuota se va", "357,00" in graves[0]["texto"], True)

    print("\nNOMBRES DE PROVEEDOR EN LOS INFORMES")
    # La posicion 1 del itertuple es el NIF, no el nombre: si se accede por
    # posicion, la columna de proveedor acaba repitiendo el NIF.
    top = pipeline._top_proveedores(cot.solo_a, "a")
    fallos += not comprueba("proveedores solo en A3", len(top), 1)
    if top:
        fallos += not comprueba("nombre", top[0]["nom"], "PROVEEDOR SOLO EN A3 SL")
        fallos += not comprueba("NIF", top[0]["nif"], "B22222222")

    print("\nHISTORICO")
    ruta_bd = os.path.join(carpeta, "basico.db")
    pipeline.ejecuta(ruta_a3, ruta_bk, salida, periodo="2T 2026",
                     guardar_en_bd=True, ruta_bd=ruta_bd)
    fallos += not comprueba("periodos", len(bd.periodos(ruta_bd)), 1)
    fallos += not comprueba("lineas archivadas", len(bd.lineas(ruta_bd)), LINEAS_A3 + LINEAS_BK)
    fallos += not comprueba("duplicadas archivadas", len(bd.duplicadas(ruta_bd)), 2)
    fallos += not comprueba("descuadres archivados", len(bd.descuadres(ruta_bd)), 5)
    en_rango = bd.lineas(ruta_bd, desde="2026-05-16", hasta="2026-05-31", libro="A3")
    fallos += not comprueba("filtro por fecha", len(en_rango), LINEAS_A3 - 1)
    # Volver a cargar el mismo trimestre sustituye, no acumula.
    pipeline.ejecuta(ruta_a3, ruta_bk, salida, periodo="2T 2026",
                     guardar_en_bd=True, ruta_bd=ruta_bd)
    fallos += not comprueba("recarga no acumula", len(bd.lineas(ruta_bd)), LINEAS_A3 + LINEAS_BK)
    fallos += not comprueba("sigue habiendo 1 carga", len(bd.cargas(ruta_bd)), 1)

    print("\n%s" % ("=" * 74))
    print("BASICO: %s (%d comprobaciones fallidas)"
          % ("TODO CORRECTO" if fallos == 0 else "HAY FALLOS", fallos))
    print("=" * 74)
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
