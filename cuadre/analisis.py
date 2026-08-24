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

# Un centimo de diferencia entre dos capturas del mismo documento es ruido de
# OCR, no dos facturas distintas. Sin este margen los duplicados mas caros del
# 2T 2026 --TUC EXPRESS, 2.719,03 €-- se escapaban por 0,01 €.
TOL_DUP = 0.05

# Tipos de IVA que existen en el impuesto espanol. El 5 % es el transitorio de
# la energia y los alimentos; se deja porque aun aparece en facturas antiguas.
TIPOS_LEGALES = (0.0, 4.0, 5.0, 10.0, 21.0)


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
    # Se renombran antes de unir: solo_a ya trae columnas K y num_b (vacias, por
    # venir del outer join), y con suffixes el numero real de Bilky acababa en
    # num_b_b mientras num_b seguia siendo NaN.
    der = solo_b[llaves + ["K", "num_b"]].rename(columns={"K": "K_bk", "num_b": "num_bk"})
    resc = solo_a.merge(der, on=llaves)
    ka = set(zip(resc.EMP, resc.NIFK, resc.K, resc.TIPO))
    kb = set(zip(resc.EMP, resc.NIFK, resc.K_bk, resc.TIPO))
    rescatadas = [{"emp": r.EMP, "prov": str(r.nom_a), "num_a3": str(r.num_a),
                   "num_bilky": str(r.num_bk), "fecha": r.F, "tipo": float(r.TIPO),
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

    # El total no entra en la clave: se comprueba luego con TOL_DUP, para que un
    # centimo de diferencia entre dos capturas no parta el grupo en dos.
    clave = ["EMP", "EMPRESA", "NIFK", "NUM_A3", "TIPO", "B2"]
    viva = a[(a.B2 != 0) | (a.T2 != 0)]          # descarta lineas a cero
    cuenta = viva.groupby(clave).size()
    repetidas = cuenta[cuenta > 1]

    filas = []
    for llave, n in repetidas.items():
        emp, empresa, nifk, num, tipo, b2 = llave
        L = viva[(viva.EMP == emp) & (viva.NIFK == nifk) & (viva.NUM_A3 == num) &
                 (viva.TIPO == tipo) & (viva.B2 == b2)]
        if float(L.T2.max() - L.T2.min()) > TOL_DUP:
            continue                             # mismo tipo y base, totales distintos
        t2 = float(L.T2.iloc[0])
        cand = b[(b.EMP == emp) & (b.NIFK == nifk) & (b.K == N.clave(num))]
        reales = sorted(set(cand.NS))
        misma = cand[(cand.TIPO == tipo) & ((cand.B2 - b2).abs() <= TOL_DUP)]
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


# Un trozo de NIF mas corto que esto no basta para acusar a nadie: «451» cabe
# dentro de demasiados numeros de factura legitimos. Con seis caracteres la
# coincidencia por azar sale a una de cada millon.
MIN_TROZO_NIF = 6


def _docid(libro):
    """Identificador de documento, valga el libro que valga.

    Bilky trae el suyo. A3 no trae ninguno, y ahi estaba el agujero: contar
    documentos por el identificador de Bilky daba siempre 1 en A3, asi que el
    umbral de «cinco documentos» no se cumplia nunca y el libro de A3 era
    invisible para esta comprobacion. Cuando no hay identificador se usa la
    pareja fecha + total, que separa los documentos igual de bien para esto.
    """
    d = libro.IDDOC.astype(str).str.strip() if "IDDOC" in libro.columns else ""
    if isinstance(d, str) or not d.any():
        d = pd.Series([""] * len(libro), index=libro.index)
    falta = d == ""
    if falta.any():
        fecha = libro.FECHA.dt.strftime("%Y%m%d").fillna("")
        d = d.mask(falta, fecha + "|" + libro.T2.round(2).astype(str))
    return d


def numeros_sospechosos(libro, min_docs=5, min_dias=5, nifs_propios=(), lado=None):
    """Numeros que no pueden ser numeros de factura.

    Saltan por dos motivos distintos:

    - Por repetirse: si el mismo «numero» respalda muchos documentos en muchos
      dias, no identifica nada. Es un campo mal capturado.
    - Por ser un NIF: un NIF nunca es un numero de factura, aunque aparezca una
      sola vez. Vale el del proveedor, el de la sociedad, o el de cualquiera de
      las sociedades del despacho --de ahi `nifs_propios`--.

    El segundo criterio hace falta porque el primero pide repeticion, y una
    factura suelta con el NIF en el campo del numero se colaba entera.
    """
    b = libro.copy()
    b["NS"] = b.NUM.astype(str).str.strip()
    b = b[b.NS != ""]
    if not len(b):
        return []
    b["DOCID"] = _docid(b)
    g = b.groupby(["EMP", "NIFK", "NS"]).agg(
        docs=("DOCID", "nunique"), dias=("FECHA", "nunique"),
        lineas=("NS", "size"), prov=("NOMBRE", "first"), cuota=("C2", "sum")).reset_index()

    propios = {str(n).upper() for n in nifs_propios}
    claves = {N.clave(n) for n in propios if N.clave(n)}
    ns = g.NS.map(N.clave)
    # El numero ES un NIF: el del proveedor, el de la sociedad, o el de otra
    # sociedad del despacho. Nunca es un numero de factura valido.
    es_nif_prov = ns == g.NIFK.map(N.clave)
    es_nif_emp = ns == g.EMP.map(N.clave)
    es_nif_propio = ns.isin(claves) if claves else pd.Series(False, index=g.index)
    # O es un trozo largo del NIF del proveedor, que es como se cuela de verdad:
    # «647451» son los seis ultimos de A28647451.
    trozo = pd.Series([len(k) >= MIN_TROZO_NIF and k in N.clave(nifk)
                       for k, nifk in zip(ns, g.NIFK)], index=g.index)

    g["en_nif_prov"] = es_nif_prov | trozo
    g["en_nif_emp"] = es_nif_emp
    g["en_nif_propio"] = es_nif_propio & ~es_nif_emp
    g["en_nif"] = g.en_nif_prov | g.en_nif_emp | g.en_nif_propio
    frecuente = (g.docs >= min_docs) & (g.dias >= min_dias)
    g["motivo"] = ["nif" if n else "repetido" for n in g.en_nif]
    g = g[frecuente | g.en_nif]
    if not len(g):
        return []
    return [{"emp": r.EMP, "nifk": r.NIFK, "prov": str(r.prov), "num": r.NS,
             "libro": lado or str(libro.attrs.get("origen", "")),
             "docs": int(r.docs), "dias": int(r.dias), "lineas": int(r.lineas),
             "cuota": round(float(r.cuota), DEC), "motivo": r.motivo,
             "en_nif_prov": bool(r.en_nif_prov), "en_nif_emp": bool(r.en_nif_emp),
             "en_nif_propio": bool(r.en_nif_propio), "en_nif": bool(r.en_nif)}
            for r in g.sort_values(["docs", "lineas"], ascending=False).itertuples()]


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


def _clave_ignorar(sospechosos):
    """(sociedad, NIF proveedor, numero) de los numeros que no identifican nada."""
    return set((s["emp"], s["nifk"], s["num"]) for s in sospechosos or ())


def _docs_bilky(bilky, ignorar):
    """Un registro por documento de Bilky, con su numero completo normalizado."""
    b = bilky.copy()
    b["NS"] = b.NUM.astype(str).str.strip()
    b = b[(b.NS != "") & (b.IDDOC.astype(str) != "")]
    if ignorar:
        fuera = pd.Series([(e, n, s) in ignorar for e, n, s in zip(b.EMP, b.NIFK, b.NS)],
                          index=b.index, dtype=bool)
        b = b[~fuera]
    b["KF"] = b.NS.map(N.clave)                   # numero COMPLETO, sin truncar
    b = b[b.KF != ""]
    d = b.groupby(["EMP", "NIFK", "KF", "IDDOC"]).agg(
        total=("T2", "sum"), cuota=("C2", "sum"), base=("B2", "sum"),
        num=("NS", "first"), prov=("NOMBRE", "first"),
        fecha=("FECHA", "min"), link=("LINK", "first"), lineas=("T2", "size"))
    return d.reset_index()


def duplicadas_en_bilky(bilky, sospechosos=(), tol=TOL_DUP):
    """Facturas capturadas mas de una vez en Bilky, mirando solo el libro de Bilky.

    `duplicadas` parte de A3: si A3 tiene la factura una sola vez no la ve, por
    mucho que en Bilky haya dos documentos. Y compara importes exactos, asi que
    un centimo entre las dos capturas la esconde. Esta funcion no depende de A3.

    Devuelve tres clases:
      igual     los documentos suman lo mismo -> duplicado real
      distinto  mismo numero y fecha con importes que no cuadran -> hay que mirarlo
      abono     factura y su rectificativa, que se anulan -> no es un duplicado
    """
    d = _docs_bilky(bilky, _clave_ignorar(sospechosos))
    if not len(d):
        return []
    g = d.groupby(["EMP", "NIFK", "KF"])
    salida = []
    for (emp, nifk, _kf), sub in g:
        if sub.IDDOC.nunique() < 2:
            continue
        # Mismo numero en fechas muy separadas: son facturas distintas del mismo
        # proveedor, no dos capturas de una. Solo se agrupa lo que cae junto.
        for _, grupo in _agrupa_por_fecha_o_importe(sub, tol):
            if grupo.IDDOC.nunique() < 2:
                continue
            totales = grupo.total.tolist()
            spread = float(max(totales) - min(totales))
            if min(totales) < -tol < tol < max(totales):
                # Uno en positivo y otro en negativo: es la factura y su abono,
                # que comparten numero por definicion. No es un duplicado.
                clase = "abono"
            elif spread <= tol:
                clase = "igual"
            else:
                clase = "distinto"
            n = int(grupo.IDDOC.nunique())
            cuota = float(grupo.cuota.abs().max())
            salida.append({
                "clase": clase, "emp": emp, "nifk": nifk,
                "prov": str(grupo.prov.iloc[0]), "num": str(grupo.num.iloc[0]),
                "nums": sorted(set(grupo.num.astype(str))),
                "docs": n,
                "fechas": sorted(set(grupo.fecha.dt.strftime("%d/%m/%Y"))),
                "totales": [round(float(t), DEC) for t in totales],
                "cuota": round(cuota, DEC),
                "sobrante": round(cuota * (n - 1), DEC) if clase == "igual" else 0.0,
                "links": [{"id": r.IDDOC, "num": str(r.num), "url": str(r.link)}
                          for r in grupo.itertuples()
                          if isinstance(r.link, str) and r.link.startswith("http")][:4],
            })
    orden = {"igual": 0, "distinto": 1, "abono": 2}
    return sorted(salida, key=lambda f: (orden[f["clase"]],
                                         -max(f["sobrante"], f["cuota"])))


def _agrupa_por_fecha_o_importe(sub, tol):
    """Parte los documentos del mismo numero en grupos que puedan ser el mismo.

    Dos capturas de una factura o comparten fecha, o comparten importe. Si no
    comparten ninguna de las dos cosas son facturas distintas que reutilizan el
    numero, y agruparlas daria un falso positivo.
    """
    pendientes = list(sub.itertuples())
    while pendientes:
        cabeza = pendientes.pop(0)
        juntos = [cabeza]
        resto = []
        for r in pendientes:
            if r.fecha == cabeza.fecha or abs(r.total - cabeza.total) <= tol:
                juntos.append(r)
            else:
                resto.append(r)
        pendientes = resto
        yield cabeza.KF, pd.DataFrame(juntos)


def misma_factura_dos_sociedades(a3, bilky, sospechosos=(), tol=TOL_DUP):
    """La misma factura del mismo proveedor cargada en dos sociedades distintas.

    Es un error de asignacion: el gasto se lo queda quien no es. Se exige que
    coincidan proveedor, numero completo, fecha e importe, porque con menos
    salen los numeros correlativos bajos de dos proveedores cualesquiera.
    """
    ignorar = _clave_ignorar(sospechosos)
    encontrado = {}
    # La clave es la truncada en los dos libros: A3 ya guarda el numero cortado,
    # asi que si Bilky usara el entero los dos lados nunca coincidirian y el
    # mismo caso se contaria dos veces.
    for libro, lado, clave in ((bilky, "Bilky", N.clave_bilky), (a3, "A3", N.clave)):
        if libro is None or not len(libro):
            continue
        d = libro.copy()
        d["NS"] = d.NUM.astype(str).str.strip()
        d = d[(d.NS != "") & (d.NIFK != "") & ~d.NIFK.isin(["NAN", "NONE"])]
        if ignorar:
            fuera = pd.Series([(e, n, s) in ignorar for e, n, s in zip(d.EMP, d.NIFK, d.NS)],
                              index=d.index, dtype=bool)
            d = d[~fuera]
        d["KF"] = d.NS.map(clave)
        d = d[(d.KF != "") & d.FECHA.notna()]
        g = d.groupby(["NIFK", "KF", "FECHA", "EMP"]).agg(
            total=("T2", "sum"), cuota=("C2", "sum"),
            prov=("NOMBRE", "first"), num=("NS", "first"))
        g = g.reset_index()
        for (nifk, kf, fecha), sub in g.groupby(["NIFK", "KF", "FECHA"]):
            if sub.EMP.nunique() < 2:
                continue
            if float(sub.total.max() - sub.total.min()) > tol:
                continue                          # mismo numero, importes distintos
            llave = (nifk, kf, fecha.strftime("%Y-%m-%d"))
            ficha = encontrado.setdefault(llave, {
                "nifk": nifk, "prov": str(sub.prov.iloc[0]), "num": str(sub.num.iloc[0]),
                "fecha": fecha.strftime("%d/%m/%Y"), "total": round(float(sub.total.iloc[0]), DEC),
                "cuota": round(float(sub.cuota.iloc[0]), DEC),
                "emps": sorted(set(sub.EMP)), "libros": []})
            if lado not in ficha["libros"]:
                ficha["libros"].append(lado)
            ficha["emps"] = sorted(set(ficha["emps"]) | set(sub.EMP))
    return sorted(encontrado.values(), key=lambda f: -abs(f["cuota"]))


def numeros_confundibles(a3, bilky):
    """Numeros de factura con letras que parecen latinas y no lo son.

    La «К» de «К178134705» de BIMBO era la cirilica (U+041A), no la K del
    teclado. En pantalla son el mismo caracter, asi que nadie lo ve, pero es
    otro numero: no casa con el otro libro, no aparece al buscarlo, y en el SII
    no cruza con lo que declara el proveedor.

    `clave` ya las traduce para poder cuadrar, pero eso solo tapa el sintoma.
    Hay que enumerarlas para poder corregirlas en el libro de origen.
    """
    salida = []
    for libro, lado in ((a3, "A3"), (bilky, "Bilky")):
        if libro is None or not len(libro):
            continue
        nums = libro.NUM.astype(str)
        # Filtro barato primero: el 99,99 % de los numeros son ASCII puros y no
        # hace falta mirarlos caracter a caracter.
        raros = libro[~nums.map(str.isascii)]
        for r in raros.itertuples():
            hg = N.homoglifos(r.NUM)
            if not hg:
                continue
            salida.append({
                "libro": lado, "emp": r.EMP, "prov": str(r.NOMBRE),
                "num": str(r.NUM).strip(), "limpio": N.sin_homoglifos(str(r.NUM)).strip(),
                "caracteres": [{"car": c, "codigo": cod, "latina": lat} for c, cod, lat in hg],
                "fecha": r.FECHA.strftime("%d/%m/%Y") if pd.notna(r.FECHA) else "",
                "base": float(r.B2), "cuota": round(float(r.C2), DEC),
            })
    return sorted(salida, key=lambda f: (-abs(f["cuota"]), f["num"]))


def numeros_discrepantes(cot):
    """Facturas casadas por importe cuyo numero no coincide entre los dos libros.

    Si la factura es la misma pero el numero de A3 no es el truncado del de
    Bilky, uno de los dos esta mal tecleado. En el SII se declara el numero.
    """
    vacios = ("", "NAN", "NONE", "NAT")
    fuera = []
    for r in cot.rescatadas:
        a3 = str(r["num_a3"]).strip()
        bilky = str(r["num_bilky"]).strip()
        # Sin numero en uno de los dos lados no hay discrepancia que contar: eso
        # es una factura sin numerar, que ya se ve en otro sitio.
        if a3.upper() in vacios or bilky.upper() in vacios:
            continue
        if N.como_a3(bilky).upper() == a3.upper():
            continue                              # el truncado explica la diferencia
        if not N.clave(a3) or not N.clave(bilky):
            continue
        fuera.append(dict(r, esperado=N.como_a3(bilky)))
    return sorted(fuera, key=lambda f: -abs(f["cuota"]))


# --------------------------------------------------------------------------
# Salud de los ficheros de entrada
# --------------------------------------------------------------------------

def escala(libro):
    """Libro leido con los importes sin coma decimal, o sea multiplicados por cien.

    Es lo que pasa cuando el CSV de A3 (coma decimal) se importa con un locale
    ingles: se pierde el separador y todo queda x100. Se ve en el tipo de IVA,
    que pasa a valer 2.100 en vez de 21. Invalida cualquier cifra del cuadre,
    asi que hay que decirlo antes que nada.
    """
    t = libro.TIPO[libro.TIPO.notna() & (libro.TIPO != 0)]
    if len(t) < 20:
        return None
    legales = float(t.round(2).isin(TIPOS_LEGALES).mean())
    cien = float((t / 100).round(2).isin(TIPOS_LEGALES).mean())
    if cien >= 0.95 and legales <= 0.05:
        return {"factor": 100, "lineas": int(len(t)),
                "tipos": [float(x) for x in sorted(set(t.unique()))[:6]]}
    return None


def tipos_invalidos(libro):
    """Tipos de IVA que no existen en el impuesto. Un 10,5 % es un error de tecleo."""
    d = libro[libro.TIPO.notna()]
    g = d.groupby("TIPO").agg(lineas=("BASE", "size"), cuota=("CUOTA", "sum"))
    g = g[~g.index.to_series().round(2).isin(TIPOS_LEGALES)]
    salida = []
    for tipo, r in g.iterrows():
        ej = d[d.TIPO == tipo].sort_values("C2", key=abs, ascending=False).iloc[0]
        salida.append({
            "tipo": float(tipo), "lineas": int(r.lineas), "cuota": round(float(r.cuota), DEC),
            "emp": ej.EMP, "prov": str(ej.NOMBRE), "num": str(ej.NUM).strip(),
            "fecha": ej.FECHA.strftime("%d/%m/%Y") if pd.notna(ej.FECHA) else "",
            "base": float(ej.B2)})
    return sorted(salida, key=lambda f: -f["lineas"])


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
