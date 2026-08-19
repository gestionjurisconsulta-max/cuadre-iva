# -*- coding: utf-8 -*-
"""Orquestacion: de los dos Excel a los tres ficheros de salida."""
import os
import re
from collections import Counter

import numpy as np
import pandas as pd

from . import analisis as AN
from . import informes as IN
from . import lectura, normaliza as N


TOPE_AVISOS = 8


def _int(x, defecto=0):
    """int() tolerante: un maximo sobre una tabla vacia es NaN, y NaN es 'truthy'."""
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return defecto
        return int(x)
    except (TypeError, ValueError):
        return defecto


def _resume_ficheros(a3, bk):
    """Etiqueta corta de los ficheros de entrada para la cabecera de los informes."""
    salida = []
    for libro, lado in ((a3, "A3"), (bk, "Bilky")):
        fs = libro.attrs.get("ficheros", [])
        if len(fs) == 1:
            salida.append(fs[0])
        elif fs:
            salida.append("%s: %d ficheros" % (lado, len(fs)))
    return salida


def _periodo(nombres):
    """Deduce '2T 2026' del nombre de los ficheros; si no, cadena vacia."""
    for n in nombres:
        m = re.search(r"([1-4])\s*T\s*(20\d\d)", str(n), re.I)
        if m:
            return "%sT %s" % (m.group(1), m.group(2))
        m = re.search(r"Trimestre-([1-4])-(20\d\d)", str(n), re.I)
        if m:
            return "%sT %s" % (m.group(1), m.group(2))
    return ""


def _limites(periodo):
    m = re.match(r"([1-4])T (\d{4})", periodo or "")
    if not m:
        return None, None
    t, y = int(m.group(1)), int(m.group(2))
    ini = pd.Timestamp(year=y, month=3 * (t - 1) + 1, day=1)
    fin = (ini + pd.offsets.QuarterEnd(0)).normalize()
    return ini, fin


def _top_proveedores(d, lado, n=14):
    c = "a" if lado == "a" else "b"
    x = d[d["cuota_" + c] > 0] if lado == "a" else d
    g = x.groupby(["NIFK", "nom_" + c]).agg(
        fac=("cuota_" + c, "size"), cuota=("cuota_" + c, "sum"), soc=("EMP", "nunique"))
    g = g.sort_values("cuota", ascending=False).reset_index().head(n)
    # Por nombre, no por posicion: en el itertuple la posicion 1 es NIFK, no el nombre.
    return [{"nif": r.NIFK, "nom": str(getattr(r, "nom_" + c))[:40], "fac": int(r.fac),
             "soc": int(r.soc), "cuota": float(r.cuota)} for r in g.itertuples()]


def _ejemplos_truncado(cot, n=6):
    """Un ejemplo por proveedor, priorizando los que mas caracteres pierden."""
    c = cot.comunes.copy()
    c["L"] = c.num_b.astype(str).str.strip().str.len()
    c = c[c.L > N.LONGITUD].sort_values("L", ascending=False).drop_duplicates("nom_b")
    out = []
    for r in c.head(n).itertuples():
        real = str(r.num_b).strip()
        out.append({"real": real, "a3": str(r.num_a).strip(), "prov": str(r.nom_b)[:34],
                    "perdido": real[:-N.LONGITUD], "conservado": real[-N.LONGITUD:]})
    return out


def ejecuta(ruta_a3, ruta_bilky, carpeta_salida, periodo=None, nombres_ficheros=None,
            progreso=None, guardar_en_bd=False, ruta_bd=None):
    """Lee, cuadra y escribe los tres informes. Devuelve un dict con el resumen.

    Con guardar_en_bd=True la ejecucion se archiva ademas en el historico, y una
    carga anterior del mismo periodo se sustituye por esta.
    """
    def paso(txt):
        if progreso:
            progreso(txt)

    paso("Leyendo el libro de A3…")
    a3 = lectura.lee_a3(ruta_a3)
    paso("Leyendo el libro de Bilky…")
    bk = lectura.lee_bilky(ruta_bilky)
    nf = nombres_ficheros or _resume_ficheros(a3, bk)
    periodo = periodo or _periodo(list(nf) + a3.attrs.get("ficheros", [])
                                 + bk.attrs.get("ficheros", [])) or ""

    paso("Cotejando factura a factura…")
    cot = AN.coteja(a3, bk)
    con = AN.concilia(a3, bk, cot)
    paso("Buscando facturas duplicadas…")
    dup = AN.duplicadas(a3, bk)
    soc = AN.por_sociedad(a3, bk, cot, dup)
    tip = AN.por_tipo_iva(a3, bk)
    sospechosos = AN.numeros_sospechosos(bk)
    no_detectadas = AN.duplicadas_no_detectadas(a3, bk)
    dup_bilky = AN.duplicadas_en_bilky(bk, sospechosos)
    cruzadas = AN.misma_factura_dos_sociedades(a3, bk, sospechosos)
    discrepantes = AN.numeros_discrepantes(cot)
    nombres = lectura.nombres_sociedades(bk, a3)

    # ---------------- avisos ----------------
    avisos = []
    # Antes que nada, si un libro viene con los importes x100 no hay nada que
    # mirar: todas las cifras de abajo estarian mal y el cotejo no casaria nada.
    escalas = {}
    tipos_malos = []
    for libro, lado in ((a3, "A3"), (bk, "Bilky")):
        esc = AN.escala(libro)
        escalas[lado] = esc
        if esc is None:
            tipos_malos += [dict(t, libro=lado) for t in AN.tipos_invalidos(libro)]
        else:
            # Con el libro x100 todos los tipos son invalidos: enumerarlos solo
            # repetiria el aviso de arriba una vez por cada tipo.
            avisos.append({"nivel": "grave", "texto":
                "El fichero de %s viene sin coma decimal: los importes estan multiplicados por "
                "%d y el tipo de IVA sale como %s en vez de %s. Es una importacion hecha con el "
                "separador decimal equivocado. NO uses ninguna cifra de este informe: vuelve a "
                "exportar el fichero, o divide entre %d todas las columnas de importe."
                % (lado, esc["factor"],
                   " / ".join(IN.eur(t, 0) for t in esc["tipos"][:3]),
                   " / ".join(IN.eur(t / 100, 0) for t in esc["tipos"][:3]),
                   esc["factor"])})
    # Lo primero, lo que no se ve: las lineas que ni siquiera han llegado al cuadre.
    # El resto de cifras se calculan sobre lo que queda, asi que todo cuadraria igual.
    for libro, lado in ((a3, "A3"), (bk, "Bilky")):
        for x in libro.attrs.get("descartadas", []):
            muestra = ", ".join("«%s»" % o for o in x["origenes"][:3])
            avisos.append({"nivel": "grave" if abs(x["cuota"]) > 0.01 else "aviso", "texto":
                "En el fichero de %s «%s» se han descartado %s de %s lineas, con %s € de cuota: "
                "no se ha podido deducir el NIF de la sociedad de %s. Esas lineas no entran en "
                "el cuadre y no las recoge ninguna cifra de este informe. Renombra el fichero "
                "con el NIF de la sociedad, o anade el patron en cuadre/lectura.py."
                % (lado, x["fichero"], IN.ent(x["lineas"]), IN.ent(x["total"]),
                   IN.eur(x["cuota"]), muestra)})
        sf_ = libro.attrs.get("sin_fecha", 0)
        if sf_:
            avisos.append({"nivel": "aviso", "texto":
                "%s lineas de %s no tienen una fecha interpretable. Se cuadran igual, pero no "
                "cuentan como facturas de fuera del trimestre ni se pueden filtrar por fecha "
                "en el historico." % (IN.ent(sf_), lado)})
    if not con["cuadra"]:
        avisos.append({"nivel": "grave", "texto":
            "La conciliacion no cuadra: las partidas suman %s € y la diferencia real es %s €. "
            "No des el cuadre por bueno." % (IN.eur(con["suma"]), IN.eur(con["total"]))})
    if cot.regla["aviso"]:
        avisos.append({"nivel": "grave", "texto": cot.regla["aviso"]})
    if not len(cot.comunes):
        avisos.append({"nivel": "grave", "texto":
            "No hay ni una sola factura presente en los dos libros. Lo normal es que los "
            "ficheros subidos no sean del mismo trimestre o no correspondan a las mismas "
            "sociedades: revisa la seleccion antes de mirar ningun importe."})
    solo_en_a3 = sorted(set(a3.EMP) - set(bk.EMP))
    solo_en_bk = sorted(set(bk.EMP) - set(a3.EMP))
    for lado, faltantes, libro, otro in (("A3", solo_en_a3, a3, "Bilky"),
                                         ("Bilky", solo_en_bk, bk, "A3")):
        if not faltantes:
            continue
        cuota = float(libro[libro.EMP.isin(faltantes)].CUOTA.sum())
        lineas_ = int(libro.EMP.isin(faltantes).sum())
        if len(faltantes) > TOPE_AVISOS:
            avisos.append({"nivel": "grave" if len(faltantes) > 20 else "aviso", "texto":
                "%s sociedades tienen libro en %s y no aparecen en %s: %s lineas y %s € de cuota "
                "que no se pueden contrastar. Comprueba que has subido todos los ficheros de %s."
                % (IN.ent(len(faltantes)), lado, otro, IN.ent(lineas_), IN.eur(cuota), otro)})
        else:
            for e in faltantes:
                avisos.append({"nivel": "aviso", "texto":
                    "La sociedad %s (%s) tiene libro en %s y no aparece en %s: %s lineas, %s € de cuota."
                    % (e, nombres.get(e, "?"), lado, otro,
                       IN.ent((libro.EMP == e).sum()), IN.eur(libro[libro.EMP == e].CUOTA.sum()))})
    sf = int((a3.TIPOFRA == "SF").sum())
    if sf:
        avisos.append({"nivel": "info", "texto":
            "A3 trae %s lineas de tipo SF con importes a cero. No afectan al IVA pero "
            "descuadran cualquier recuento de lineas." % IN.ent(sf)})
    sin_nif = a3[(a3.NIFK == "") | (a3.NIFK.isin(["NAN", "NONE"]))]
    if len(sin_nif) and abs(sin_nif.CUOTA.sum()) > 0.01:
        avisos.append({"nivel": "aviso", "texto":
            "%s lineas de A3 no llevan NIF de expedidor y mueven %s € de cuota. "
            "Sin NIF no son declarables en el SII."
            % (IN.ent(len(sin_nif)), IN.eur(sin_nif.CUOTA.sum()))})
    tipos_a = set(tip[tip.lin_a > 0].TIPO)
    tipos_b = set(tip[tip.lin_b > 0].TIPO)
    for t in sorted(tipos_a - tipos_b):
        n = int(tip[tip.TIPO == t].lin_a.iloc[0])
        avisos.append({"nivel": "aviso", "texto":
            "El tipo %s %% solo existe en A3 (%s %s). Revisa si es correcto."
            % (IN.eur(t, 0 if float(t).is_integer() else 1), IN.ent(n), IN.plural(n, "linea"))})
    for s in sospechosos:
        avisos.append({"nivel": "aviso", "texto":
            "En %s, %s facturas de %s comparten el numero «%s» en %s documentos y %s dias distintos%s. "
            "Ese campo no identifica la factura." % (
                s["emp"], IN.ent(s["lineas"]), s["prov"], s["num"], IN.ent(s["docs"]),
                IN.ent(s["dias"]),
                "; coincide con parte del NIF" if s["en_nif"] else "")})
    for f in no_detectadas:
        avisos.append({"nivel": "aviso", "texto":
            "Duplicado que el criterio no marca: %s en %s, capturado dos veces en Bilky como %s "
            "(en A3: %s). %s € de IVA." % (
                f["prov"], f["emp"], " y ".join(f["reales"]), " y ".join(f["en_a3"]),
                IN.eur(f["cuota"]))})
    # El mismo tipo malo suele estar en los dos libros: se nombra una vez.
    vistos_tipo = set()
    for t in tipos_malos:
        if t["tipo"] in vistos_tipo:
            continue
        vistos_tipo.add(t["tipo"])
        libros = sorted(set(x["libro"] for x in tipos_malos if x["tipo"] == t["tipo"]))
        avisos.append({"nivel": "aviso", "texto":
            "El tipo %s %% no existe en el IVA espanol y aparece en %s %s de %s (%s € de cuota). "
            "Ejemplo: %s, factura %s de %s del %s. Suele ser un error de tecleo."
            % (IN.eur(t["tipo"], 2).rstrip("0").rstrip(","), IN.ent(t["lineas"]),
               IN.plural(t["lineas"], "linea"), " y ".join(libros), IN.eur(t["cuota"]),
               t["emp"], t["num"], t["prov"], t["fecha"])})
    iguales = [x for x in dup_bilky if x["clase"] == "igual"]
    distintos = [x for x in dup_bilky if x["clase"] == "distinto"]
    for f in iguales[:TOPE_AVISOS]:
        avisos.append({"nivel": "aviso", "texto":
            "Duplicado en Bilky que A3 no delata: %s en %s, factura %s del %s, capturada en %s "
            "documentos por el mismo importe (%s €). Sobran %s € de IVA."
            % (f["prov"], f["emp"], f["num"], " y ".join(f["fechas"]), IN.ent(f["docs"]),
               IN.eur(f["totales"][0]), IN.eur(f["sobrante"]))})
    if len(iguales) > TOPE_AVISOS:
        resto = iguales[TOPE_AVISOS:]
        avisos.append({"nivel": "aviso", "texto":
            "Y %s duplicados mas en Bilky por %s € de IVA. Estan todos en la hoja "
            "DUPLICADAS EN BILKY del Excel." % (
                IN.ent(len(resto)), IN.eur(sum(f["sobrante"] for f in resto)))})
    # Los de importes distintos no son un veredicto, son una lista de revision:
    # se nombran los mayores y el resto se cuenta, para no ahogar el informe.
    for f in distintos[:4]:
        avisos.append({"nivel": "aviso", "texto":
            "Revisar en Bilky: %s en %s tiene la factura %s del %s en %s documentos con importes "
            "distintos (%s €). O una captura esta incompleta, o son facturas distintas con el "
            "mismo numero." % (
                f["prov"], f["emp"], f["num"], " y ".join(f["fechas"]), IN.ent(f["docs"]),
                " vs ".join(IN.eur(t) for t in f["totales"][:3]))})
    if len(distintos) > 4:
        avisos.append({"nivel": "aviso", "texto":
            "Y %s facturas mas repetidas en Bilky con importes que no cuadran. Hay que mirarlas "
            "una a una: hoja DUPLICADAS EN BILKY del Excel." % IN.ent(len(distintos) - 4)})
    for f in cruzadas:
        avisos.append({"nivel": "grave", "texto":
            "La misma factura esta en dos sociedades: %s, numero %s del %s por %s €, aparece en "
            "%s. Mismo proveedor, numero, fecha e importe: una de las dos la tiene mal asignada."
            % (f["prov"], f["num"], f["fecha"], IN.eur(f["total"]), " y ".join(f["emps"]))})
    for f in discrepantes[:4]:
        avisos.append({"nivel": "aviso", "texto":
            "Numero distinto en los dos libros para la misma factura: %s en %s, %s € del %s, "
            "figura como «%s» en A3 y como «%s» en Bilky (truncado seria «%s»). Uno de los dos "
            "esta mal, y en el SII se declara el numero." % (
                f["prov"], f["emp"], IN.eur(f["base"]),
                pd.Timestamp(f["fecha"]).strftime("%d/%m/%Y"),
                f["num_a3"], f["num_bilky"], f["esperado"])})
    if len(discrepantes) > 4:
        avisos.append({"nivel": "aviso", "texto":
            "Y %s facturas mas con el numero distinto en cada libro: hoja N FACTURA DISCREPANTE "
            "del Excel." % IN.ent(len(discrepantes) - 4)})

    ini, fin = _limites(periodo)
    fuera_a = fuera_b = 0
    if ini is not None:
        fuera_a = int(((a3.FECHA < ini) | (a3.FECHA > fin)).sum())
        fuera_b = int(((bk.FECHA < ini) | (bk.FECHA > fin)).sum())

    # ---------------- fechas ----------------
    c = cot.comunes.copy()
    c["dd"] = (c.fec_a - c.fec_b).dt.days
    fdif = c[c.dd.fillna(0) != 0]
    fechas_det = [{"emp": r.EMP, "prov": str(r.nom_a)[:34], "num": str(r.num_a),
                   "fa": r.fec_a.strftime("%d/%m/%Y"), "fb": r.fec_b.strftime("%d/%m/%Y"),
                   "dd": int(r.dd), "cuota": float(r.cuota_a)}
                  for r in fdif.sort_values("dd", key=abs, ascending=False).head(40).itertuples()]
    cruzan = 0
    if ini is not None and len(fdif):
        da = (fdif.fec_a < ini) | (fdif.fec_a > fin)
        db = (fdif.fec_b < ini) | (fdif.fec_b > fin)
        cruzan = int((da != db).sum())

    # ---------------- tabla de truncados para el Excel ----------------
    ct = cot.comunes.copy()
    ct["L"] = ct.num_b.astype(str).str.strip().str.len()
    ct = ct[ct.L > N.LONGITUD].drop_duplicates(["EMP", "NIFK", "num_b"])
    truncados = [{"NIF_SOCIEDAD": r.EMP, "SOCIEDAD": nombres.get(r.EMP, ""),
                  "NIF_PROVEEDOR": r.NIFK, "PROVEEDOR": str(r.nom_b),
                  "N_REAL_BILKY": str(r.num_b).strip(), "N_MOSTRADO_A3": str(r.num_a).strip(),
                  "CARACTERES_PERDIDOS": int(r.L - N.LONGITUD)}
                 for r in ct.sort_values("L", ascending=False).itertuples()]

    comunes_n = len(cot.comunes)
    cuadran = int((cot.comunes.d_cuota.abs() < 0.01).sum())
    lineas_trunc = _int((cot.comunes.num_b.astype(str).str.strip().str.len() > N.LONGITUD).sum())
    max_len = _int(cot.comunes.num_b.astype(str).str.strip().str.len().max())

    ctx_comun = {
        "periodo": periodo, "ficheros": nf,
        "a3": a3, "bk": bk, "cot": cot, "con": con, "dup": dup, "soc": soc, "tip": tip,
        "nombres": nombres, "truncados": truncados,
        "dup_bilky": dup_bilky, "cruzadas": cruzadas, "discrepantes": discrepantes,
        "tipos_malos": tipos_malos,
        "avisos_tabla": [{"NIVEL": a["nivel"].upper(), "AVISO": a["texto"]} for a in avisos] or
                        [{"NIVEL": "OK", "AVISO": "Sin incidencias detectadas."}],
    }

    # ---------------- contexto de la comparativa ----------------
    tipo_top = tip.reindex(tip.d_cuota.abs().sort_values(ascending=False).index).iloc[0] \
        if len(tip) else None
    dif_imp = cot.dif_comunes[cot.dif_comunes.motivo == "importe"]
    comp = {
        "periodo": periodo, "ficheros": nf, "avisos": avisos,
        "tot": {"lin_a": len(a3), "lin_b": len(bk), "sf": sf,
                "base_a": float(a3.BASE.sum()), "base_b": float(bk.BASE.sum()),
                "cuota_a": float(a3.CUOTA.sum()), "cuota_b": float(bk.CUOTA.sum()),
                "total_a": float(a3.TOTAL.sum()), "total_b": float(bk.TOTAL.sum()),
                "emp_a": int(a3.EMP.nunique()), "emp_b": int(bk.EMP.nunique()),
                "emp_total": len(set(a3.EMP) | set(bk.EMP)),
                "apuntes": len(a3) + len(bk)},
        "dif": {"base": float(a3.BASE.sum() - bk.BASE.sum()), "cuota": con["total"],
                "total": float(a3.TOTAL.sum() - bk.TOTAL.sum()), "lineas": len(a3) - len(bk)},
        "fac": {"comunes": comunes_n, "cuadran": cuadran,
                "pct": (cuadran / comunes_n) if comunes_n else 0,
                "solo_a": len(cot.solo_a), "solo_b": len(cot.solo_b),
                "dif_n": len(cot.dif_comunes), "rescatadas": len(cot.rescatadas)},
        "con": con["partidas"], "cuadra": con["cuadra"], "suma": con["suma"],
        "tipos": [{"tipo": float(r.TIPO), "base_a": float(r.base_a), "base_b": float(r.base_b),
                   "cuota_a": float(r.cuota_a), "cuota_b": float(r.cuota_b),
                   "d": float(r.d_cuota)} for r in tip.itertuples()],
        "tipo_top": ({"tipo": float(tipo_top.TIPO), "d": float(tipo_top.d_cuota)}
                     if tipo_top is not None else None),
        "regla": {"tasa": cot.regla["tasa"], "tasa_trunc": cot.regla["tasa_truncados"],
                  "lineas": lineas_trunc, "lineas_tot": comunes_n,
                  "pct_lineas": (lineas_trunc / comunes_n) if comunes_n else 0,
                  "facturas": len(ct), "max_len": max_len, "longitud": N.LONGITUD,
                  "fiable": cot.regla["fiable"]},
        "trunc_ej": _ejemplos_truncado(cot),
        "colisiones": cot.colisiones,
        "dup": {"meta": dup["meta"], "res": dup["resumen"]},
        "no_detectadas": no_detectadas,
        "dif_importe": [{"emp": r.EMP, "prov": str(r.nom_a)[:32], "na": str(r.num_a),
                         "nb": str(r.num_b), "tipo": float(r.TIPO),
                         "ba": float(r.base_a), "bb": float(r.base_b),
                         "ca": float(r.cuota_a), "cb": float(r.cuota_b), "d": float(r.d_cuota)}
                        for r in dif_imp.sort_values("d_cuota", key=abs, ascending=False).itertuples()],
        "solo_a_prov": _top_proveedores(cot.solo_a, "a"),
        "solo_b_prov": _top_proveedores(cot.solo_b, "b", 10),
        "rect": [{"emp": r.EMP, "tf": r.TIPOFRA, "prov": str(r.NOMBRE)[:32], "num": str(r.NUM),
                  "fecha": r.FECHA.strftime("%d/%m/%Y"), "tipo": float(r.TIPO),
                  "base": float(r.B2), "cuota": float(r.C2)}
                 for r in con["rectificativas"].sort_values("C2").itertuples()],
        "rect_total": float(con["rectificativas"].CUOTA.sum()) if len(con["rectificativas"]) else 0.0,
        "fechas": {"difs": len(fdif), "det": fechas_det, "cruzan": cruzan,
                   "fuera_a": fuera_a, "fuera_b": fuera_b},
        "soc": [{"nif": r.EMP, "nom": nombres.get(r.EMP, ""), "la": int(r.lin_a), "lb": int(r.lin_b),
                 "ca": float(r.cuota_a), "cb": float(r.cuota_b), "dc": float(r.d_cuota),
                 "sa": float(r.solo_a3), "sb": float(r.solo_bilky), "di": float(r.importes),
                 "re": float(r.rectificativas), "sf": int(r.lineas_vacias)}
                for r in soc.itertuples()],
        "soc_cuadran": int((soc.d_cuota.abs() < 0.01).sum()),
        "soc_total": len(soc),
        "soc_solo_a3": [{"nif": e, "nom": nombres.get(e, ""), "lin": int((a3.EMP == e).sum()),
                         "cuota": float(a3[a3.EMP == e].CUOTA.sum())} for e in solo_en_a3],
        "soc_solo_bk": [{"nif": e, "lin": int((bk.EMP == e).sum()),
                         "prov": str(bk[bk.EMP == e].NOMBRE.mode().iloc[0])
                                 if (bk.EMP == e).any() else "",
                         "cuota": float(bk[bk.EMP == e].CUOTA.sum())} for e in solo_en_bk],
    }
    comp["payload"] = IN._json({"tipos": comp["tipos"], "trunc_ej": comp["trunc_ej"],
                                "colisiones": comp["colisiones"], "dif_importe": comp["dif_importe"],
                                "solo_a_prov": comp["solo_a_prov"], "solo_b_prov": comp["solo_b_prov"],
                                "rect": comp["rect"], "fechas": comp["fechas"]["det"],
                                "soc": comp["soc"], "con": comp["con"],
                                "cuota_a": comp["tot"]["cuota_a"], "cuota_b": comp["tot"]["cuota_b"]})

    # ---------------- contexto de duplicadas ----------------
    facturas = dup["facturas"]
    mayor = max(facturas, key=lambda f: abs(f["sobrante"])) if facturas else None
    sa = [f for f in facturas if f["v"] == "solo_a3"]
    fal = [f for f in facturas if f["v"] == "falso"]
    emp_sa = sorted(set(f["emp"] for f in sa))
    prov_fal = Counter(f["prov"] for f in fal).most_common(1)
    dups = {
        "periodo": periodo, "ficheros": nf, "avisos": avisos,
        "regla_longitud": N.LONGITUD, "tol_dup": AN.TOL_DUP,
        "meta": dup["meta"], "res": dup["resumen"],
        "empresas": [dict(e, nom=nombres.get(e["emp"], e["empresa"])) for e in dup["empresas"]],
        "mayor": mayor,
        "solo_a3": {"n": len(sa), "emp": emp_sa,
                    "emp_nom": nombres.get(emp_sa[0], "") if len(emp_sa) == 1 else "",
                    "pos": round(sum(f["sobrante"] for f in sa if f["sobrante"] > 0), 2),
                    "neg": round(sum(f["sobrante"] for f in sa if f["sobrante"] < 0), 2),
                    "neto": round(sum(f["sobrante"] for f in sa), 2)},
        "falsos": {"n": len(fal), "iva": round(sum(f["sobrante"] for f in fal), 2),
                   "prov": prov_fal[0][0] if prov_fal else "",
                   "prov_n": prov_fal[0][1] if prov_fal else 0,
                   "ej": fal[0] if fal else None},
        "multifecha": sum(1 for f in facturas if f["v"] == "doc_repetido" and f["multifecha"]),
        "sospechosos": sospechosos, "no_detectadas": no_detectadas,
        "tot": {"lin_a": len(a3), "lin_b": len(bk), "emp": int(a3.EMP.nunique())},
        "solo_bilky_dup": {
            "igual": [f for f in dup_bilky if f["clase"] == "igual"],
            "distinto": [f for f in dup_bilky if f["clase"] == "distinto"],
            "iva": round(sum(f["sobrante"] for f in dup_bilky if f["clase"] == "igual"), 2)},
        "cruzadas": cruzadas,
    }
    dups["payload"] = IN._json({"facturas": [dict(f, nom=nombres.get(f["emp"], f["empresa"]))
                                             for f in facturas],
                                "res": dup["resumen"], "empresas": dups["empresas"],
                                "meta": dup["meta"]})

    # ---------------- salida ----------------
    os.makedirs(carpeta_salida, exist_ok=True)
    suf = (" " + periodo) if periodo else ""
    suf_f = suf.replace(" ", "_")
    paso("Generando el Excel de trabajo…")
    f_xlsx = IN.excel(os.path.join(carpeta_salida, "COMPARATIVA IVA A3 vs BILKY%s.xlsx" % suf), ctx_comun)
    paso("Generando los informes…")
    f_comp = IN.html(os.path.join(carpeta_salida, "Comparativa_IVA_A3_vs_BILKY%s.html" % suf_f),
                     "comparativa.html", comp)
    f_dup = IN.html(os.path.join(carpeta_salida, "Facturas_Duplicadas_IVA%s.html" % suf_f),
                    "duplicadas.html", dups)

    salida = {"periodo": periodo, "ficheros": [f_xlsx, f_comp, f_dup],
            "avisos": avisos, "cuadra": con["cuadra"],
            "dif_cuota": con["total"], "regla": cot.regla,
            "resumen": {"lineas_a3": len(a3), "lineas_bilky": len(bk),
                        "ficheros_a3": len(a3.attrs.get("ficheros", [])) or 1,
                        "ficheros_bilky": len(bk.attrs.get("ficheros", [])) or 1,
                        "sociedades": comp["tot"]["emp_total"],
                        "cuota_a3": comp["tot"]["cuota_a"], "cuota_bilky": comp["tot"]["cuota_b"],
                        "facturas_comunes": comunes_n, "cuadran": cuadran,
                        "solo_a3": len(cot.solo_a), "solo_bilky": len(cot.solo_b),
                        "duplicadas": dup["meta"]["fras"],
                        "duplicadas_accion": dup["meta"]["accion_fras"],
                        "duplicadas_iva": dup["meta"]["accion_iva"],
                        "dup_bilky": len([f for f in dup_bilky if f["clase"] == "igual"]),
                        "dup_bilky_iva": round(sum(f["sobrante"] for f in dup_bilky
                                                   if f["clase"] == "igual"), 2),
                        "dup_bilky_revisar": len([f for f in dup_bilky
                                                  if f["clase"] == "distinto"]),
                        "cruzadas": len(cruzadas),
                        "numeros_discrepantes": len(discrepantes),
                        "tipos_invalidos": len(tipos_malos)}}

    if guardar_en_bd:
        from . import bd
        paso("Archivando en el histórico…")
        cid, sustituidas = bd.guarda(
            ruta_bd, periodo, a3, bk, cot, con, dup, avisos, nombres, salida["resumen"],
            ficheros=(nf[0], nf[1]),
            huellas=(bd.huella(ruta_a3), bd.huella(ruta_bilky)))
        salida["bd"] = {"carga_id": cid, "sustituidas": len(sustituidas),
                        "ruta": ruta_bd or bd.ruta_por_defecto()}
        if sustituidas:
            avisos.append({"nivel": "info", "texto":
                "Se ha sustituido en el histórico una carga anterior del periodo %s." % periodo})

    return salida
