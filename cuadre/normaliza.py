# -*- coding: utf-8 -*-
"""La regla de truncado del numero de factura en A3.

A3 no guarda el numero completo: conserva los 10 ultimos caracteres del original
--espacios y separadores incluidos-- y convierte barras, guiones y puntos en
espacios. Para poder cruzar los dos libros hay que aplicar esa misma regla al
numero de Bilky, que si viene entero.

La regla esta deducida de los datos, no documentada por el fabricante, asi que
`verifica` la vuelve a medir en cada ejecucion y avisa si deja de cumplirse.
"""
import re
import unicodedata

LONGITUD = 10
SEPARADORES = re.compile(r"[/\-_.]")
ESPACIOS = re.compile(r"\s+")
NO_ALFANUM = re.compile(r"[^A-Z0-9]")

UMBRAL_AVISO = 0.95   # por debajo de este acierto, la regla ya no es fiable


def como_a3(numero):
    """Aplica a un numero completo la transformacion que hace A3."""
    s = str(numero).strip()[-LONGITUD:]
    s = SEPARADORES.sub(" ", s)
    return ESPACIOS.sub(" ", s).strip()


def clave(numero):
    """Clave comparable: mayusculas, solo alfanumerico, sin ceros a la izquierda."""
    s = unicodedata.normalize("NFKD", str(numero).upper()).encode("ascii", "ignore").decode()
    return NO_ALFANUM.sub("", s).lstrip("0")


def clave_bilky(numero):
    """Clave de un numero de Bilky, truncado antes como lo haria A3."""
    return clave(como_a3(numero))


def verifica(pares):
    """Mide el acierto de la regla sobre pares (numero_a3, numero_bilky) ya casados.

    Devuelve un dict con el porcentaje de acierto global, el acierto sobre los
    numeros que realmente se truncan (mas de 10 caracteres) y un aviso si baja.
    """
    total = aciertos = largos = aciertos_largos = 0
    fallos = []
    for num_a3, num_bilky in pares:
        a = str(num_a3).strip()
        b = str(num_bilky).strip()
        if not b:
            continue
        total += 1
        ok = como_a3(b).upper() == a.upper()
        aciertos += ok
        if len(b) > LONGITUD:
            largos += 1
            aciertos_largos += ok
        if not ok and len(fallos) < 25:
            fallos.append({"a3": a, "bilky": b, "esperado": como_a3(b)})
    tasa = aciertos / total if total else 0.0
    tasa_largos = aciertos_largos / largos if largos else 0.0
    if not total:
        # Sin facturas en ambos libros no hay nada que medir; no es que la regla falle.
        return {"pares": 0, "aciertos": 0, "tasa": 0.0, "truncados": 0,
                "tasa_truncados": 0.0, "fiable": True, "medible": False,
                "aviso": None, "fallos": []}
    return {
        "pares": total,
        "aciertos": aciertos,
        "tasa": tasa,
        "truncados": largos,
        "tasa_truncados": tasa_largos,
        "fiable": tasa >= UMBRAL_AVISO,
        "medible": True,
        "aviso": None if tasa >= UMBRAL_AVISO else (
            "La regla de truncado solo acierta en el %.1f %% de los numeros (antes: 98,9 %%). "
            "Es probable que A3 haya cambiado el formato de exportacion; revisa los "
            "emparejamientos antes de dar el cuadre por bueno." % (100 * tasa)),
        "fallos": fallos,
    }


def colisiones(bilky):
    """Numeros distintos del mismo proveedor que A3 reduce al mismo texto.

    Es la causa de los falsos duplicados: dos facturas reales que quedan iguales.
    """
    b = bilky.copy()
    b["K"] = b.NUM.map(clave_bilky)
    b["NS"] = b.NUM.astype(str).str.strip()
    g = b.groupby(["EMP", "NIFK", "K"]).NS.nunique()
    out = []
    for (emp, nifk, k) in g[g > 1].index:
        v = b[(b.EMP == emp) & (b.NIFK == nifk) & (b.K == k)]
        out.append({
            "emp": emp, "nifk": nifk,
            "prov": str(v.NOMBRE.iloc[0]),
            "a3": como_a3(v.NUM.iloc[0]),
            "reales": sorted(set(v.NS)),
        })
    return out
