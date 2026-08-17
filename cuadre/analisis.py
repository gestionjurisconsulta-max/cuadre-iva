# -*- coding: utf-8 -*-
"""Cotejo de los dos libros y deteccion de facturas duplicadas.

El cotejo se hace a nivel *factura x tipo de IVA*, no linea a linea: Bilky
desglosa rappels y descuentos en lineas aparte que A3 contabiliza netos, y
compararlos uno a uno generaria diferencias que no existen.
"""
import numpy as np
import pandas as pd

from . import normaliza as N

TOL = 0.005          # tolerancia en euros para considerar que algo cuadra
DEC = 2


class Resultado(object):
    """Todo lo que producen el cotejo y la deteccion de duplicadas."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


# --------------------------------------------------------------------------
# Cotejo
# --------------------------------------------------------------------------

def _claves(a3, bilky):
    a = a3.copy()
    b = bilky.copy()
    a["K"] = a.NUM.map(N.clave)
    b["K"] = b.NUM.map(N.clave_bilky)
    return a, b


def _pares_para_verificar(a, b):
    """Facturas casadas por proveedor + fecha + tipo + base, sin mirar el numero.

    Sirve para medir la regla de truncado sin razonar en circulo.
    """
    cols = ["EMP", "NIFK", "FECHA", "TIPO", "B2"]
    ga = a.groupby(cols).NUM.agg(["first", "nunique"])
    gb = b.groupby(cols).NUM.agg(["first", "nunique"])
    j = ga.join(gb, how="inner", lsuffix="_a", rsuffix="_b")
    j = j[(j["nunique_a"] == 1) & (j["nunique_b"] == 1)]
    return list(zip(j["first_a"], j["first_b"]))


def coteja(a3, bilky):
    a, b = _claves(a3, bilky)
    grupo = ["EMP", "NIFK", "K", "TIPO"]

    ga = a.groupby(grupo).agg(
        base_a=("BASE", "sum"), cuota_a=("CUOTA", "sum"), lin_a=("BASE", "size"),
        fec_a=("FECHA", "min"), nom_a=("NOMBRE", "first"), num_a=("NUM", "first"))
    gb = b.groupby(grupo).agg(
        base_b=("BASE", "sum"), cuota_b=("CUOTA", "sum"), lin_b=("BASE", "size"),
        fec_b=("FECHA", "min"), nom_b=("NOMBRE", "first"), num_b=("NUM", "first"))
    g = ga.join(gb, how="outer")
    g["en_a"] = g.base_a.notna()
    g["en_b"] = g.base_b.notna()
    for c in ("base_a", "cuota_a", "base_b", "cuota_b", "lin_a", "lin_b"):
        g[c] = g[c].fillna(0)
    g["d_base"] = (g.base_a - g.base_b).round(DEC)
    g["d_cuota"] = (g.cuota_a - g.cuota_b).round(DEC)
    g = g.reset_index()

    comunes = g[g.en_a & g.en_b].copy()
    solo_a = g[g.en_a & ~g.en_b].copy()
    solo_b = g[~g.en_a & g.en_b].copy()

    # Rescate: misma factura con el numero mal capturado en uno de los dos libros.
    solo_a["F"] = solo_a.fec_a.dt.strftime("%Y-%m-%d")
    solo_b["F"] = solo_b.fec_b.dt.strftime("%Y-%m-%d")
    solo_a["BB"] = solo_a.base_a.round(DEC)
    solo_b["BB"] = solo_b.base_b.round(DEC)
    llaves = ["EMP", "NIFK", "TIPO", "BB", "F"]
    resc = solo_a.merge(solo_b[llaves + ["K", "num_b"]], on=llaves, suffixes=("", "_b"))
    ka = set(zip(resc.EMP, resc.NIFK, resc.K, resc.TIPO))
    kb = set(zip(resc.EMP, resc.NIFK, resc.K_b, resc.TIPO))
    rescatadas = [{"emp": r.EMP, "prov": str(r.nom_a), "num_a3": str(r.num_a),
                   "num_bilky": str(r.num_b), "fecha": r.F, "tipo": float(r.TIPO),
                   "base": float(r.BB), "cuota": float(r.cuota_a)}
                  for r in resc.itertuples()]
    solo_a = solo_a[~solo_a.set_index(["EMP", "NIFK", "K", "TIPO"]).index.isin(ka)]
    solo_b = solo_b[~solo_b.set_index(["EMP", "NIFK", "K", "TIPO"]).index.isin(kb)]

    dif_comunes = comunes[comunes.d_cuota.abs() >= 0.01].copy()
    ratio = np.where(dif_comunes.base_b != 0, dif_comunes.base_a / dif_comunes.base_b, np.nan)
    dif_comunes["motivo"] = np.where(np.round(ratio, 2) == 2, "dup_a3",
                             np.where(np.round(ratio, 2) == 0.5, "dup_bilky", "importe"))

    regla = N.verifica(_pares_para_verificar(a, b))

    return Resultado(
        a=a, b=b, todas=g, comunes=comunes, solo_a=solo_a, solo_b=solo_b,
        dif_comunes=dif_comunes, rescatadas=rescatadas, regla=regla,
        colisiones=N.colisiones(b),
    )


def concilia(a3, bilky, cot):
    """Descompone la diferencia de cuota en sus componentes. Debe cuadrar a cero."""
    rect_tipos = ("R0", "R1", "R2", "R3", "R4", "R5")
    rect = a3[a3.TIPOFRA.isin(rect_tipos)]
    # Solo cuentan las rectificativas que no tienen pareja en Bilky.
    claves_solo_a = set(zip(cot.solo_a.EMP, cot.solo_a.NIFK, cot.solo_a.K, cot.solo_a.TIPO))
    ra = cot.a[cot.a.TIPOFRA.isin(rect_tipos)]
    # Ojo: con una lista vacia pandas seleccionaria columnas, no filas.
    mascara = pd.Series([t in claves_solo_a for t in zip(ra.EMP, ra.NIFK, ra.K, ra.TIPO)],
                        index=ra.index, dtype=bool)
    huerfanas = ra[mascara]
    cuota_rect = round(float(huerfanas.CUOTA.sum()), DEC)

    cuota_solo_a = round(float(cot.solo_a.cuota_a.sum()), DEC)
    cuota_solo_b = round(float(cot.solo_b.cuota_b.sum()), DEC)
    dif_com = round(float(cot.dif_comunes.d_cuota.sum()), DEC)
    total = round(float(a3.CUOTA.sum() - bilky.CUOTA.sum()), DEC)
    normales = round(cuota_solo_a - cuota_rect, DEC)

    partidas = [
        {"clave": "solo_a3", "titulo": "Facturas registradas solo en A3",
         "detalle": "%d facturas que Bilky no ha capturado" % int((cot.solo_a.cuota_a != 0).sum()
                                                                 or len(cot.solo_a)),
         "valor": normales},
        {"clave": "rectificativas", "titulo": "Rectificativas solo en A3",
         "detalle": "%d apuntes de tipo %s" % (len(huerfanas),
                                               "/".join(sorted(set(huerfanas.TIPOFRA))) or "R"),
         "valor": cuota_rect},
        {"clave": "solo_bilky", "titulo": "Facturas registradas solo en Bilky",
         "detalle": "%d facturas sin contabilizar en A3" % len(cot.solo_b),
         "valor": -cuota_solo_b},
        {"clave": "importes", "titulo": "Diferencias de importe en facturas comunes",
         "detalle": "%d facturas de %s" % (len(cot.dif_comunes), f"{len(cot.comunes):,}".replace(",", ".")),
         "valor": dif_com},
    ]
    if not cuota_rect:
        partidas = [p for p in partidas if p["clave"] != "rectificativas"]
        partidas[0]["valor"] = cuota_solo_a
    suma = round(sum(p["valor"] for p in partidas), DEC)
    return {"partidas": partidas, "suma": suma, "total": total,
            "cuadra": abs(suma - total) < 0.02, "rectificativas": huerfanas}


# --------------------------------------------------------------------------
# Duplicadas
# --------------------------------------------------------------------------

VEREDICTOS = ("solo_a3", "doc_repetido", "sincontraste", "linea_repetida", "falso")


def duplicadas(a3, bilky):
    """Lineas repetidas dentro del libro de una sociedad, con veredicto vs Bilky.

    Criterio: mismo NIF de expedidor, mismo numero tal cual lo muestra A3, mismo
    tipo de IVA, misma base y mismo total, dentro del libro de la misma sociedad.
    """
    a = a3.copy()
    b = bilky.copy()
    a["NUM_A3"] = a.NUM.astype(str).str.strip()
    b["NS"] = b.NUM.astype(str).str.strip()
    b["K"] = b.NS.map(N.clave_bilky)

    clave = ["EMP", "EMPRESA", "NIFK", "NUM_A3", "TIPO", "B2", "T2"]
    viva = a[(a.B2 != 0) | (a.T2 != 0)]          # descarta lineas a cero
    cuenta = viva.groupby(clave).size()
    repetidas = cuenta[cuenta > 1]

    filas = []
    for llave, n in repetidas.items():
        emp, empresa, nifk, num, tipo, b2, t2 = llave
        L = viva[(viva.EMP == emp) & (viva.NIFK == nifk) & (viva.NUM_A3 == num) &
                 (viva.TIPO == tipo) & (viva.B2 == b2) & (viva.T2 == t2)]
        cand = b[(b.EMP == emp) & (b.NIFK == nifk) & (b.K == N.clave(num))]
        reales = sorted(set(cand.NS))
        misma = cand[(cand.TIPO == tipo) & (cand.B2 == b2)]
        rep_b = len(misma)
        docs = sorted(set(misma.IDDOC)) if rep_b else []
        if len(reales) > 1:
            v = "falso"
        elif rep_b == 0:
            v = "sincontraste"
        elif rep_b < n:
            v = "solo_a3"
        elif len(docs) > 1:
            v = "doc_repetido"
        else:
            v = "linea_repetida"
        enlaces = []
        vistos = set()
        for _, r in (misma if rep_b else cand).iterrows():
            if r.IDDOC in vistos:
                continue
            vistos.add(r.IDDOC)
            url = str(r.LINK) if isinstance(r.LINK, str) else ""
            if url.startswith("http"):
                enlaces.append({"id": r.IDDOC, "num": r.NS, "url": url})
        cuota = float(L.C2.iloc[0])
        fechas = sorted(set(L.FECHA.dt.strftime("%d/%m/%Y")))
        filas.append({
            "emp": emp, "empresa": empresa, "nifp": nifk, "prov": str(L.NOMBRE.iloc[0]),
            "num_a3": num, "tipo": float(tipo), "base": float(b2), "total": float(t2),
            "cuota": cuota, "rep_a3": int(n), "rep_bilky": int(rep_b),
            "docs_bilky": len(docs), "reales": reales,
            "sobrante": round(cuota * (n - 1), DEC), "v": v,
            "multifecha": len(fechas) > 1, "fechas": fechas,
            "lineas": [{"fecha": r.FECHA.strftime("%d/%m/%Y"), "tf": str(r.TIPOFRA),
                        "base": float(r.B2), "tipo": float(r.TIPO),
                        "cuota": float(r.C2), "total": float(r.T2)}
                       for _, r in L.iterrows()],
            "links": enlaces[:4],
        })

    orden = {v: i for i, v in enumerate(VEREDICTOS)}
    filas.sort(key=lambda f: (orden[f["v"]], -f["sobrante"]))
    for i, f in enumerate(filas, 1):
        f["i"] = i

    resumen = {}
    for v in VEREDICTOS:
        s = [f for f in filas if f["v"] == v]
        resumen[v] = {
            "fras": len(s),
            "lineas": sum(f["rep_a3"] for f in s),
            "sobrantes": sum(f["rep_a3"] - 1 for f in s),
            "iva": round(sum(f["sobrante"] for f in s), DEC),
            "pos": round(sum(f["sobrante"] for f in s if f["sobrante"] > 0), DEC),
            "neg": round(sum(f["sobrante"] for f in s if f["sobrante"] < 0), DEC),
            "emp": len(set(f["emp"] for f in s)),
        }

    accion = [f for f in filas if f["v"] in ("solo_a3", "doc_repetido", "sincontraste")]
    poremp = {}
    for f in filas:
        e = poremp.setdefault(f["emp"], {"emp": f["emp"], "empresa": f["empresa"], "fras": 0,
                                         "lineas": 0, "sobrantes": 0, "iva": 0.0,
                                         "accion": 0, "iva_accion": 0.0})
        e["fras"] += 1
        e["lineas"] += f["rep_a3"]
        e["sobrantes"] += f["rep_a3"] - 1
        e["iva"] += f["sobrante"]
        if f["v"] in ("solo_a3", "doc_repetido", "sincontraste"):
            e["accion"] += 1
            e["iva_accion"] += f["sobrante"]
    for e in poremp.values():
        e["iva"] = round(e["iva"], DEC)
        e["iva_accion"] = round(e["iva_accion"], DEC)
    empresas = sorted(poremp.values(), key=lambda e: -e["iva_accion"])

    return {
        "facturas": filas,
        "resumen": resumen,
        "empresas": empresas,
        "meta": {
            "fras": len(filas),
            "lineas": sum(f["rep_a3"] for f in filas),
            "sobrantes": sum(f["rep_a3"] - 1 for f in filas),
            "emp": len(set(f["emp"] for f in filas)),
            "iva": round(sum(f["sobrante"] for f in filas), DEC),
            "accion_fras": len(accion),
            "accion_iva": round(sum(f["sobrante"] for f in accion), DEC),
        },
    }


def numeros_sospechosos(bilky, min_docs=5, min_dias=5):
    """Numeros que no pueden ser numeros de factura.

    Si el mismo 'numero' respalda muchos documentos distintos en muchos dias, no
    identifica nada: suele ser un campo mal capturado. El caso tipico es que se
    haya colado parte del NIF del proveedor.
    """
    b = bilky.copy()
    b["NS"] = b.NUM.astype(str).str.strip()
    b = b[b.NS != ""]
    g = b.groupby(["EMP", "NIFK", "NS"]).agg(
        docs=("IDDOC", "nunique"), dias=("FECHA", "nunique"),
        lineas=("NS", "size"), prov=("NOMBRE", "first"))
    g = g[(g.docs >= min_docs) & (g.dias >= min_dias)].reset_index()
    if not len(g):
        return []
    g["en_nif_prov"] = [len(ns) > 3 and ns in nifk for ns, nifk in zip(g.NS, g.NIFK)]
    g["en_nif_emp"] = [len(ns) > 3 and ns in emp for ns, emp in zip(g.NS, g.EMP)]
    return [{"emp": r.EMP, "nifk": r.NIFK, "prov": str(r.prov), "num": r.NS,
             "docs": int(r.docs), "dias": int(r.dias), "lineas": int(r.lineas),
             "en_nif_prov": bool(r.en_nif_prov), "en_nif_emp": bool(r.en_nif_emp),
             "en_nif": bool(r.en_nif_prov or r.en_nif_emp)}
            for r in g.sort_values("docs", ascending=False).itertuples()]


def duplicadas_no_detectadas(a3, bilky):
    """Duplicados reales que el criterio de coincidencia exacta no ve.

    Misma factura capturada dos veces en Bilky con el numero escrito de forma
    distinta --una coma, un espacio de mas--, mismo importe y mismo tipo. Al
    quitar los signos los dos numeros son el mismo, asi que no son dos facturas
    distintas; pero en A3 llegan como cadenas diferentes y no se marcan.
    """
    b = bilky.copy()
    b["NS"] = b.NUM.astype(str).str.strip()
    b = b[(b.NS != "") & ((b.B2 != 0) | (b.T2 != 0))]
    b["KF"] = b.NS.map(N.clave)               # numero COMPLETO normalizado, sin truncar
    b = b[b.KF != ""]
    g = b.groupby(["EMP", "NIFK", "KF", "TIPO", "B2", "T2"]).agg(
        docs=("IDDOC", "nunique"), nums=("NS", "nunique"),
        prov=("NOMBRE", "first"), cuota=("C2", "first"))
    g = g[(g.docs > 1) & (g.nums > 1)].reset_index()

    a = a3.copy()
    a["NS"] = a.NUM.astype(str).str.strip()
    fuera = []
    for r in g.itertuples():
        sub = b[(b.EMP == r.EMP) & (b.NIFK == r.NIFK) & (b.KF == r.KF) &
                (b.TIPO == r.TIPO) & (b.B2 == r.B2)]
        en_a3 = a[(a.EMP == r.EMP) & (a.NIFK == r.NIFK) & (a.TIPO == r.TIPO) &
                  (a.B2 == r.B2) & (a.T2 == r.T2)]
        if en_a3.NS.nunique() < 2:            # en A3 llegan iguales: el criterio ya lo detecta
            continue
        fechas = sorted(set(sub.FECHA.dt.strftime("%d/%m/%Y")))
        fuera.append({"emp": r.EMP, "prov": str(r.prov),
                      "reales": sorted(set(sub.NS)), "en_a3": sorted(set(en_a3.NS)),
                      "tipo": float(r.TIPO), "base": float(r.B2), "total": float(r.T2),
                      "cuota": float(r.cuota), "docs": int(r.docs), "fechas": fechas,
                      "links": [{"id": x.IDDOC, "num": x.NS, "url": str(x.LINK)}
                                for _, x in sub.drop_duplicates("IDDOC").iterrows()
                                if isinstance(x.LINK, str) and x.LINK.startswith("http")][:4]})
    return sorted(fuera, key=lambda f: -abs(f["cuota"]))


# --------------------------------------------------------------------------
# Resumen por sociedad
# --------------------------------------------------------------------------

def por_sociedad(a3, bilky, cot, dup):
    ga = a3.groupby("EMP").agg(lin_a=("BASE", "size"), base_a=("BASE", "sum"),
                               cuota_a=("CUOTA", "sum"), total_a=("TOTAL", "sum"))
    gb = bilky.groupby("EMP").agg(lin_b=("BASE", "size"), base_b=("BASE", "sum"),
                                  cuota_b=("CUOTA", "sum"), total_b=("TOTAL", "sum"))
    e = ga.join(gb, how="outer").fillna(0)
    e["d_base"] = (e.base_a - e.base_b).round(DEC)
    e["d_cuota"] = (e.cuota_a - e.cuota_b).round(DEC)
    e = e.join(cot.solo_a.groupby("EMP").cuota_a.sum().rename("solo_a3"))
    e = e.join(cot.solo_b.groupby("EMP").cuota_b.sum().rename("solo_bilky"))
    e = e.join(cot.dif_comunes.groupby("EMP").d_cuota.sum().rename("importes"))
    rect = a3[a3.TIPOFRA.str.startswith("R", na=False) & (a3.TIPOFRA.str.len() == 2)]
    e = e.join(rect.groupby("EMP").CUOTA.sum().rename("rectificativas"))
    sf = a3[a3.TIPOFRA == "SF"]
    e = e.join(sf.groupby("EMP").size().rename("lineas_vacias"))
    e = e.fillna(0).reset_index()
    return e.sort_values("d_cuota", key=abs, ascending=False)


def por_tipo_iva(a3, bilky):
    ta = a3.groupby("TIPO").agg(base_a=("BASE", "sum"), cuota_a=("CUOTA", "sum"), lin_a=("BASE", "size"))
    tb = bilky.groupby("TIPO").agg(base_b=("BASE", "sum"), cuota_b=("CUOTA", "sum"), lin_b=("BASE", "size"))
    t = ta.join(tb, how="outer").fillna(0).reset_index()
    t["d_cuota"] = (t.cuota_a - t.cuota_b).round(DEC)
    return t
