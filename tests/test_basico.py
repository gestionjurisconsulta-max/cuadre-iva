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
sys.path.insert(0, os.path.join(RAIZ, "tests"))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import entorno
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


def escribe(ruta, cabecera, filas, enc="cp1252"):
    """Los CSV de A3 salen en cp1252, no en UTF-8. Se escriben asi a proposito.

    Los de Bilky si son UTF-8, y hace falta para las letras que no caben en
    cp1252 --la «К» cirilica, por ejemplo--.
    """
    with open(ruta, "w", encoding=enc) as f:
        f.write("\n".join([cabecera] + filas) + "\n")


def prepara(carpeta):
    a3, bk = os.path.join(carpeta, "a3"), os.path.join(carpeta, "bk")
    os.makedirs(a3)
    os.makedirs(bk)
    escribe(os.path.join(a3, "2026B01709237GACMESERVICIOSSL.csv"), CAB_A3, A3_ACME)
    escribe(os.path.join(a3, "202638092900RGCISNEROSMULLERVICTOR.csv"), CAB_A3, A3_PF)
    escribe(os.path.join(a3, "libro de compras revisado.csv"), CAB_A3, A3_HUERFANO)
    # Sociedad durmiente: el libro sale con la cabecera y ni una factura. No es
    # un error --puede no haber tenido movimiento-- pero no puede tumbar la
    # carga de las demas, que es lo que hacia antes.
    escribe(os.path.join(a3, "2026B12345678GSOCIEDADDURMIENTESL.csv"), CAB_A3, [])
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


# --------------------------------------------------------------------------
# Segundo juego: los problemas que no dependen de A3
# --------------------------------------------------------------------------
# Cada linea de aqui reproduce un caso real del 1T o el 2T de 2026, en pequeno.

# Misma factura capturada dos veces en Bilky, con un centimo de diferencia entre
# las dos copias. A3 la tiene una sola vez, asi que el criterio que parte de A3
# no la ve. Es el caso TUC EXPRESS: 2.719,03 € que se escapaban por 0,01 €.
D_A3_UNO = [
    "F1;05/05/2026;DOSVECES 1;B11111111;CAPTURADA DOS VECES SL;1210,00;1000,00;21;210,00;",
    "F1;06/05/2026;MAL 999;B22222222;NUMERO QUE NO COINCIDE SL;605,00;500,00;21;105,00;",
    "F1;07/05/2026;CRUZADA 01;B33333333;LA MISMA EN DOS SOCIEDADES SL;242,00;200,00;21;42,00;",
    "F1;08/05/2026;TIPOMALO 1;B44444444;TIPO QUE NO EXISTE SL;110,50;100,00;10,5;10,50;",
    # La K de aqui es la del teclado (U+004B). La de Bilky, no.
    "F1;09/05/2026;K123456789;B55555555;LETRA QUE PARECE LATINA SL;121,00;100,00;21;21,00;",
    # Un NIF en el campo del numero. Una sola factura, que es justo lo que se
    # colaba: el criterio antiguo pedia cinco repeticiones.
    "F1;10/05/2026;A28647451;A28647451;EL NIF DEL PROVEEDOR SL;242,00;200,00;21;42,00;",
    "F1;11/05/2026;647451;A28647451;UN TROZO DEL NIF SL;121,00;100,00;21;21,00;",
    "F1;12/05/2026;B10994051;B66666666;EL NIF DE OTRA NUESTRA SL;363,00;300,00;21;63,00;",
    # Y un numero que se repite en varios dias, en A3. Antes esto era invisible:
    # se contaban documentos por el identificador de Bilky, que A3 no tiene.
    "F1;13/05/2026;REPE 0001;B77777777;NUMERO QUE SE REPITE SL;121,00;100,00;21;21,00;",
    "F1;14/05/2026;REPE 0001;B77777777;NUMERO QUE SE REPITE SL;242,00;200,00;21;42,00;",
    "F1;15/05/2026;REPE 0001;B77777777;NUMERO QUE SE REPITE SL;605,00;500,00;21;105,00;",
    # La misma factura con el numero mal en A3. El cotejo la rescata por importe
    # y fecha, y las cuotas NO coinciden: 21,00 aqui contra 20,00 en Bilky. Ese
    # euro tiene que aparecer en la conciliacion, que es lo que no pasaba.
    "F1;12/05/2026;RESC A 001;B10101010;NUMERO MAL EN A3 SL;121,00;100,00;21;21,00;",
    # La fecha metida en el campo del numero. A3 convierte los puntos en
    # espacios, asi que «10.02.2026» le llega como «10 02 2026».
    "F1;10/02/2026;10 02 2026;B88888888;LA FECHA COMO NUMERO SL;3571,70;3247,00;10;324,70;",
    # Y dos que NO deben saltar: la primera se lee como fecha pero no es la de
    # la factura; la segunda no llega a fecha porque «846» no es un ano.
    "F1;01/04/2026;2026092;B99999999;NUMERO DE SERIE NORMAL SL;121,00;100,00;21;21,00;",
    "F1;26/01/2026;26 01 846;B99999999;NUMERO DE SERIE NORMAL SL;121,00;100,00;21;21,00;",
]
D_BK_UNO = [
    "05/05/2026;B11111111;CAPTURADA DOS VECES SL;1000,00;210,00;21;1210,00;"
    "DOSVECES-1;DD1;https://app.bilky.com/documento/DD1",
    "05/05/2026;B11111111;CAPTURADA DOS VECES SL;1000,00;210,01;21;1210,01;"
    "DOSVECES-1;DD2;https://app.bilky.com/documento/DD2",
    "06/05/2026;B22222222;NUMERO QUE NO COINCIDE SL;500,00;105,00;21;605,00;"
    "BIEN-1234;DD3;https://app.bilky.com/documento/DD3",
    "07/05/2026;B33333333;LA MISMA EN DOS SOCIEDADES SL;200,00;42,00;21;242,00;"
    "CRUZADA-01;DD4;https://app.bilky.com/documento/DD4",
    "08/05/2026;B44444444;TIPO QUE NO EXISTE SL;100,00;10,50;10,5;110,50;"
    "TIPOMALO-1;DD5;https://app.bilky.com/documento/DD5",
    # El caso BIMBO: la primera letra es la «K» cirilica (U+041A), que en
    # pantalla es identica a la latina. Sin traducirla la factura no casa, y
    # ademas `clave` la borraba al normalizar a ASCII.
    "09/05/2026;B55555555;LETRA QUE PARECE LATINA SL;100,00;21,00;21;121,00;"
    "К123456789;DD7;https://app.bilky.com/documento/DD7",
    "12/05/2026;B10101010;NUMERO MAL EN A3 SL;100,00;20,00;21;120,00;"
    "RESC-B-001;DD9;https://app.bilky.com/documento/DD9",
    # El NIF del proveedor como numero, tambien en Bilky: la comprobacion tiene
    # que saltar en los dos libros, no solo en uno.
    "10/05/2026;A28647451;EL NIF DEL PROVEEDOR SL;200,00;42,00;21;242,00;"
    "A28647451;DD8;https://app.bilky.com/documento/DD8",
]
# La segunda sociedad se lleva la misma factura del mismo proveedor: mismo
# numero, misma fecha y mismo importe. Una de las dos la tiene mal asignada.
D_A3_DOS = [
    "F1;07/05/2026;CRUZADA 01;B33333333;LA MISMA EN DOS SOCIEDADES SL;242,00;200,00;21;42,00;",
]
D_BK_DOS = [
    "07/05/2026;B33333333;LA MISMA EN DOS SOCIEDADES SL;200,00;42,00;21;242,00;"
    "CRUZADA-01;DD6;https://app.bilky.com/documento/DD6",
]
# El mismo libro exportado sin coma decimal: todo x100 y el tipo de IVA en 2.100.
D_A3_X100 = [
    "F1;05/05/2026;ESCALA 001;B11111111;IMPORTES SIN COMA SL;121000;100000;2100;21000;",
    "F1;06/05/2026;ESCALA 002;B11111111;IMPORTES SIN COMA SL;11000;10000;1000;1000;",
    "F1;07/05/2026;ESCALA 003;B11111111;IMPORTES SIN COMA SL;10400;10000;400;400;",
] * 8


def detecciones(raiz):
    """Los problemas que el cuadre no veia: duplicados solo en Bilky, la misma
    factura en dos sociedades, tipos de IVA inexistentes, numeros que no
    coinciden entre libros y ficheros importados sin coma decimal."""
    fallos = 0
    carpeta = os.path.join(raiz, "det")
    a3d, bkd = os.path.join(carpeta, "a3"), os.path.join(carpeta, "bk")
    os.makedirs(a3d)
    os.makedirs(bkd)
    escribe(os.path.join(a3d, "2026B01709237GSOCIEDADUNASL.csv"), CAB_A3, D_A3_UNO)
    escribe(os.path.join(a3d, "2026B10994051GSOCIEDADDOSSL.csv"), CAB_A3, D_A3_DOS)
    escribe(os.path.join(bkd, "B01709237-SOCIEDAD-UNA-SL-libro-de-iva-facturas-"
                              "recibidas-Trimestre-2-2026.csv"), CAB_BK, D_BK_UNO,
            enc="utf-8")
    escribe(os.path.join(bkd, "B10994051-SOCIEDAD-DOS-SL-libro-de-iva-facturas-"
                              "recibidas-Trimestre-2-2026.csv"), CAB_BK, D_BK_DOS)
    a3 = lectura.lee_a3(a3d)
    bk = lectura.lee_bilky(bkd)
    cot = analisis.coteja(a3, bk)
    sosp = analisis.numeros_sospechosos(bk)

    print("\nDUPLICADA QUE SOLO SE VE EN BILKY")
    db = analisis.duplicadas_en_bilky(bk, sosp)
    iguales = [f for f in db if f["clase"] == "igual"]
    fallos += not comprueba("detectada", len(iguales), 1)
    if iguales:
        # A3 la tiene una vez y Bilky dos: el criterio de A3 no la marca.
        fallos += not comprueba("  documentos", iguales[0]["docs"], 2)
        fallos += not comprueba("  IVA que sobra", iguales[0]["sobrante"], 210.01)
        fallos += not comprueba("  el centimo no la parte",
                                len(set(iguales[0]["totales"])) == 2, True)
    fallos += not comprueba("no la ve el criterio de A3",
                            analisis.duplicadas(a3, bk)["meta"]["fras"], 0)

    print("\nLA MISMA FACTURA EN DOS SOCIEDADES")
    cruz = analisis.misma_factura_dos_sociedades(a3, bk, sosp)
    fallos += not comprueba("detectada", len(cruz), 1)
    if cruz:
        fallos += not comprueba("  sociedades", cruz[0]["emps"], ["B01709237", "B10994051"])
        fallos += not comprueba("  importe", cruz[0]["total"], 242.00)

    print("\nTIPO DE IVA QUE NO EXISTE")
    tipos = analisis.tipos_invalidos(a3)
    fallos += not comprueba("detectado", [t["tipo"] for t in tipos], [10.5])
    fallos += not comprueba("tipos legales no saltan", analisis.tipos_invalidos(bk[bk.TIPO == 21]), [])

    print("\nNUMERO DISTINTO EN CADA LIBRO")
    disc = analisis.numeros_discrepantes(cot)
    fallos += not comprueba("detectados", len(disc), 2)
    if disc:
        fallos += not comprueba("  numero en A3", disc[0]["num_a3"], "MAL 999")
        fallos += not comprueba("  numero en Bilky", disc[0]["num_bilky"], "BIEN-1234")

    print("\nUN NIF EN EL CAMPO DEL NUMERO DE FACTURA")
    # Se le pasan las dos sociedades del juego como si fueran las del despacho.
    propias = {"B01709237": "SOCIEDAD UNA SL", "B10994051": "SOCIEDAD DOS SL"}
    sa = analisis.numeros_sospechosos(a3, min_docs=3, min_dias=3,
                                      nifs_propios=propias, lado="A3")
    por_num = {x["num"]: x for x in sa}
    fallos += not comprueba("detectados en A3", sorted(por_num),
                            ["647451", "A28647451", "B10994051", "REPE 0001"])
    if "A28647451" in por_num:
        fallos += not comprueba("  el NIF del proveedor",
                                por_num["A28647451"]["en_nif_prov"], True)
        fallos += not comprueba("  basta con una factura",
                                por_num["A28647451"]["lineas"], 1)
    if "647451" in por_num:
        fallos += not comprueba("  un trozo largo del NIF tambien",
                                por_num["647451"]["en_nif_prov"], True)
    if "B10994051" in por_num:
        fallos += not comprueba("  el NIF de otra sociedad nuestra",
                                por_num["B10994051"]["en_nif_propio"], True)
    # Lo que no se podia hacer antes: contar documentos en A3, que no trae
    # identificador. Sin esto el umbral no se cumplia nunca y A3 no se miraba.
    if "REPE 0001" in por_num:
        fallos += not comprueba("  documentos contados en A3",
                                por_num["REPE 0001"]["docs"], 3)
        fallos += not comprueba("  y por repetirse, no por el NIF",
                                por_num["REPE 0001"]["motivo"], "repetido")
    # Un trozo corto de NIF no acusa a nadie: «451» cabe en demasiados numeros.
    corto = [x for x in analisis.numeros_sospechosos(
        a3, min_docs=99, min_dias=99, lado="A3") if len(x["num"]) < 6]
    fallos += not comprueba("un trozo corto no salta", corto, [])

    print("\nLA FECHA METIDA EN EL NUMERO DE FACTURA")
    fec = analisis.numeros_que_son_fecha(a3, bk)
    fallos += not comprueba("detectada", len(fec), 1)
    if fec:
        fallos += not comprueba("  numero", fec[0]["num"], "10 02 2026")
        fallos += not comprueba("  fecha de la factura", fec[0]["fecha"], "10/02/2026")
        fallos += not comprueba("  cuota", fec[0]["cuota"], 324.70)
    # Lo que de verdad hace util la regla es lo que NO marca. Sin exigir que la
    # fecha sea la de la propia factura, sobre el 2026 real marcaba 47 numeros
    # de serie buenos y ninguno malo.
    fallos += not comprueba("un numero de serie no salta",
                            [f["num"] for f in fec if f["num"] == "2026092"], [])
    fallos += not comprueba("y «846» no es un ano",
                            N.fecha_en_numero("26 01 846"), None)
    fallos += not comprueba("aunque suelto si se lea como fecha",
                            str(N.fecha_en_numero("2026092")), "2026-09-02")

    print("\nLETRA QUE PARECE LATINA Y NO LO ES")
    conf = analisis.numeros_confundibles(a3, bk)
    fallos += not comprueba("detectado", len(conf), 1)
    if conf:
        fallos += not comprueba("  en que libro", conf[0]["libro"], "Bilky")
        fallos += not comprueba("  codigo del caracter",
                                conf[0]["caracteres"][0]["codigo"], "U+041A")
        fallos += not comprueba("  como deberia ser", conf[0]["limpio"], "K123456789")
    # Y lo que importa: que aun asi la factura case, en vez de salir a la vez
    # como solo en A3 y solo en Bilky.
    casada = cot.comunes[cot.comunes.K == N.clave("K123456789")]
    fallos += not comprueba("la factura casa igual", len(casada), 1)
    if len(casada):
        fallos += not comprueba("  y por el mismo importe",
                                float(casada.iloc[0].cuota_a), float(casada.iloc[0].cuota_b))
    # Sin la traduccion, `clave` no es que no coincidiera: se comia la letra.
    fallos += not comprueba("antes se perdia la letra",
                            N.clave("К123456789"), "K123456789")
    fallos += not comprueba("un numero normal no se toca", N.homoglifos("FA-2026/001"), [])

    print("\nLA CONCILIACION NO PUEDE PERDER DINERO")
    # Las rescatadas salen de «solo en A3» y de «solo en Bilky» --no son
    # huerfanas, estan en los dos libros-- pero antes no entraban en ninguna
    # partida y su diferencia desaparecia. En el 1T de 2026 eran 470,96 €.
    con = analisis.concilia(a3, bk, cot)
    fallos += not comprueba("cuadra", con["cuadra"], True)
    fallos += not comprueba("suma = diferencia real", round(con["suma"], 2),
                            round(con["total"], 2))
    resc = [p for p in con["partidas"] if p["clave"] == "rescatadas"]
    fallos += not comprueba("hay partida de rescatadas", len(resc), 1)
    if resc:
        fallos += not comprueba("  el euro que faltaba", resc[0]["valor"], 1.00)

    print("\nFICHERO IMPORTADO SIN COMA DECIMAL")
    escribe(os.path.join(carpeta, "2026B01709237GSOCIEDADUNASL.csv"), CAB_A3, D_A3_X100)
    malo = lectura.lee_a3(os.path.join(carpeta, "2026B01709237GSOCIEDADUNASL.csv"))
    esc = analisis.escala(malo)
    fallos += not comprueba("detectado", esc is not None, True)
    if esc:
        fallos += not comprueba("  factor", esc["factor"], 100)
        fallos += not comprueba("  tipos que ve", sorted(esc["tipos"]), [400.0, 1000.0, 2100.0])
    fallos += not comprueba("el libro bueno no salta", analisis.escala(a3), None)

    print("\nNUMEROS SOSPECHOSOS, YA ARCHIVADOS")
    # Lo mismo pero sobre el historico, que es donde se ve lo que no cabe en un
    # solo cuadre: el mismo numero del mismo proveedor en varias sociedades.
    ruta_bd = entorno.base_limpia("cuadre_test_sospechosos")
    pipeline.ejecuta(a3d, bkd, os.path.join(carpeta, "sal"), periodo="2T 2026",
                     guardar_en_bd=True, ruta_bd=ruta_bd)
    sos = bd.numeros_sospechosos(ruta_bd)
    por = {(r.libro, r.num): r for r in sos.itertuples()}
    for libro in ("A3", "BILKY"):
        fallos += not comprueba("%s: el NIF del proveedor" % libro,
                                por[(libro, "A28647451")].motivo
                                if (libro, "A28647451") in por else None,
                                "nif del proveedor")
    fallos += not comprueba("un trozo largo del NIF", ("A3", "647451") in por, True)
    # La fecha en el numero se comprueba en SQL, no en pandas: hay que probarla
    # aparte. num_clave llega sin separadores y sin ceros por la izquierda.
    fallos += not comprueba("la fecha en el numero",
                            por[("A3", "10 02 2026")].motivo
                            if ("A3", "10 02 2026") in por else None,
                            "es la fecha de la factura")
    fallos += not comprueba("y un numero de serie no",
                            [n for l, n in por if n in ("2026092", "26 01 846")], [])
    # «CRUZADA 01» es la misma factura en las dos sociedades del juego. Eso solo
    # se ve cruzando: dentro de un cuadre por sociedad no hay nada raro. Se
    # agrupa por el numero tal cual lo escribe cada libro, asi que A3 y Bilky
    # van por separado --A3 lo trunca y Bilky no--.
    for libro, texto in (("A3", "CRUZADA 01"), ("BILKY", "CRUZADA-01")):
        cruz = [r for r in sos.itertuples() if r.libro == libro and r.num == texto]
        fallos += not comprueba("%s: el mismo numero en dos sociedades" % libro,
                                len(cruz), 2)
        if cruz:
            fallos += not comprueba("  cuantas sociedades", cruz[0].sociedades, 2)
            fallos += not comprueba("  motivo", cruz[0].motivo,
                                    "el mismo en varias sociedades")
    return fallos


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

    print("\nFICHERO VACIO")
    vac = a3.attrs.get("vacios", [])
    fallos += not comprueba("ficheros sin ninguna linea", len(vac), 1)
    if vac:
        fallos += not comprueba("cual", "DURMIENTE" in vac[0].upper(), True)
    # Y con un solo fichero, y vacio, si tiene que fallar: no habria nada que
    # cuadrar y callarselo dejaria al usuario mirando una pantalla en blanco.
    solo = os.path.join(os.path.dirname(ruta_a3), "solo_vacio.csv")
    escribe(solo, CAB_A3, [])
    try:
        lectura.lee_a3(solo)
        salta = False
    except lectura.FicheroVacio:
        salta = True
    fallos += not comprueba("uno solo y vacio si falla", salta, True)

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
    ruta_bd = entorno.base_limpia("cuadre_test_basico")
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

    print("\nNUMEROS SOSPECHOSOS SOBRE EL HISTORICO")
    sos = bd.numeros_sospechosos(ruta_bd)
    # Sobre este juego no hay ninguno: «B26 033375» sale dos veces en A3 pero
    # son dos facturas reales distintas --colision del truncado--, en una sola
    # sociedad y en dos dias. No debe acusarse a nadie.
    fallos += not comprueba("no inventa sospechosos", len(sos), 0)

    print("\nLA MISMA FACTURA EN DOS TRIMESTRES")
    # El mismo libro archivado como 1T: todas las facturas pasan a estar en dos
    # trimestres. Es el riesgo que solo aparece cuando hay historico.
    pipeline.ejecuta(ruta_a3, ruta_bk, salida, periodo="1T 2026",
                     guardar_en_bd=True, ruta_bd=ruta_bd)
    ent = bd.duplicadas_entre_periodos(ruta_bd)
    libros = sorted(ent.libro.unique())
    # Se mira en los dos libros, no solo en A3: en Bilky es una captura repetida
    # que todavia no ha llegado a A3, y no la ve nadie mas.
    fallos += not comprueba("mira los dos libros", libros, ["A3", "BILKY"])
    fallos += not comprueba("trimestres", sorted(ent.periodos.unique()), ["1T 2026, 2T 2026"])

    # Los filtros acotan ANTES de buscar las repeticiones, no despues. Con un
    # solo trimestre no puede salir nada: no hay dos entre los que repetirse.
    fallos += not comprueba("filtrado a un trimestre",
                            len(bd.duplicadas_entre_periodos(ruta_bd, periodos_=["1T 2026"])), 0)
    fallos += not comprueba("filtrado a los dos",
                            len(bd.duplicadas_entre_periodos(
                                ruta_bd, periodos_=["1T 2026", "2T 2026"])), len(ent))
    solo_a3 = bd.duplicadas_entre_periodos(ruta_bd, libro="A3")
    fallos += not comprueba("filtrado por libro", sorted(solo_a3.libro.unique()), ["A3"])
    una = sorted(ent.emp.unique())[0]
    por_soc = bd.duplicadas_entre_periodos(ruta_bd, emps=[una])
    fallos += not comprueba("filtrado por sociedad", sorted(por_soc.emp.unique()), [una])
    fallos += not comprueba("  y deja fuera a las demas", len(por_soc) < len(ent), True)

    # El numero que se enseña es el real, no la clave truncada: nadie encontraria
    # «260107604» buscando en Bilky, donde la factura es «2026FA / 260107604».
    fila_bk = ent[(ent.libro == "BILKY") & (ent.nif_prov == "B11111111")
                  & (ent.num_clave == N.clave("260107604"))]
    fallos += not comprueba("hay fila en Bilky", len(fila_bk), 1)
    if len(fila_bk):
        fallos += not comprueba("numero real", fila_bk.iloc[0]["numeros"], "2026FA / 260107604")
        fallos += not comprueba("fecha en ISO", fila_bk.iloc[0]["fechas"], "2026-05-15")

    # Y la colision se separa del duplicado: dos facturas distintas que la regla
    # de truncado de A3 deja iguales no son la misma repetida.
    choque = ent[ent.nif_prov == "B66666666"]
    fallos += not comprueba("colision marcada", bool(choque.colision.all()), True)
    real = ent[ent.nif_prov == "B55555555"]
    fallos += not comprueba("duplicado real no marcado", bool(real.colision.any()), False)

    fallos += detecciones(carpeta)

    print("\n%s" % ("=" * 74))
    print("BASICO: %s (%d comprobaciones fallidas)"
          % ("TODO CORRECTO" if fallos == 0 else "HAY FALLOS", fallos))
    print("=" * 74)
    return 0 if fallos == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
