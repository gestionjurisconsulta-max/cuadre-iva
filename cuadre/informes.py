# -*- coding: utf-8 -*-
"""Generacion del Excel de trabajo y de los dos informes HTML."""
import json
import os
import re

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import analisis as AN

PLANTILLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas")


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------

def eur(v, dec=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    neg = v < 0
    s = ("%%.%df" % dec) % abs(v)
    ent, _, dc = s.partition(".")
    ent = re.sub(r"\B(?=(\d{3})+(?!\d))", ".", ent)
    return ("−" if neg else "") + (ent + "," + dc if dc else ent)


def sgn(v, dec=2):
    return ("+" if v > 0 else "") + eur(v, dec)


def ent(v):
    return re.sub(r"\B(?=(\d{3})+(?!\d))", ".", str(int(v)))


def pct(v, dec=1):
    return ("%%.%df" % dec % (100 * v)).replace(".", ",")


def plural(n, sing, plur=None):
    return sing if n == 1 else (plur if plur is not None else sing + "s")


def entorno():
    e = Environment(loader=FileSystemLoader(PLANTILLAS), undefined=StrictUndefined,
                    autoescape=True, trim_blocks=True, lstrip_blocks=True)
    e.filters.update(eur=eur, sgn=sgn, ent=ent, pct=pct)
    return e


def _json(x):
    """JSON seguro para incrustar en un <script>: nada puede cerrar la etiqueta."""
    return (json.dumps(x, ensure_ascii=False, default=str)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------

def excel(ruta, ctx):
    a3, bk, cot, con = ctx["a3"], ctx["bk"], ctx["cot"], ctx["con"]
    dup, soc, tip = ctx["dup"], ctx["soc"], ctx["tip"]
    nombres = ctx["nombres"]

    resumen = [["Lineas del libro", len(a3), len(bk), len(a3) - len(bk)]]
    vac = int((a3.TIPOFRA == "SF").sum())
    if vac:
        resumen.append(["   de ellas, lineas vacias tipo SF (solo A3)", vac, 0, vac])
    resumen += [
        ["Base imponible", round(a3.BASE.sum(), 2), round(bk.BASE.sum(), 2), round(a3.BASE.sum() - bk.BASE.sum(), 2)],
        ["Cuota IVA soportado", round(a3.CUOTA.sum(), 2), round(bk.CUOTA.sum(), 2), con["total"]],
        ["Total factura", round(a3.TOTAL.sum(), 2), round(bk.TOTAL.sum(), 2), round(a3.TOTAL.sum() - bk.TOTAL.sum(), 2)],
        ["Sociedades", a3.EMP.nunique(), bk.EMP.nunique(), ""],
        ["", "", "", ""],
        ["CONCILIACION DE LA DIFERENCIA DE CUOTA", "", "", ""],
    ]
    for p in con["partidas"]:
        resumen.append([("(+) " if p["valor"] >= 0 else "(-) ") + p["titulo"], "", "", p["valor"]])
    resumen.append(["= DIFERENCIA TOTAL DE CUOTA", "", "", con["suma"]])
    R = pd.DataFrame(resumen, columns=["CONCEPTO", "A3", "BILKY", "DIFERENCIA"])

    S = soc.copy()
    S.insert(1, "SOCIEDAD", [nombres.get(x, "") for x in S.EMP])
    S["CUADRA"] = np.where(S.d_cuota.abs() < 0.01, "SI", "NO")
    S = S.rename(columns={"EMP": "NIF_SOCIEDAD", "lin_a": "LINEAS_A3", "lin_b": "LINEAS_BILKY",
                          "base_a": "BASE_A3", "base_b": "BASE_BILKY", "cuota_a": "CUOTA_A3",
                          "cuota_b": "CUOTA_BILKY", "total_a": "TOTAL_A3", "total_b": "TOTAL_BILKY",
                          "d_base": "DIF_BASE", "d_cuota": "DIF_CUOTA", "solo_a3": "SOLO_A3",
                          "solo_bilky": "SOLO_BILKY", "importes": "DIF_IMPORTES",
                          "rectificativas": "RECTIFICATIVAS", "lineas_vacias": "LINEAS_SF"})

    def _huerf(d, lado):
        c = "a" if lado == "a" else "b"
        x = pd.DataFrame({
            "NIF_SOCIEDAD": d.EMP, "SOCIEDAD": [nombres.get(v, "") for v in d.EMP],
            "NIF_PROVEEDOR": d.NIFK, "PROVEEDOR": d["nom_" + c],
            "N_FACTURA": d["num_" + c], "FECHA": d["fec_" + c],
            "TIPO_IVA": d.TIPO, "BASE": d["base_" + c].round(2), "CUOTA_IVA": d["cuota_" + c].round(2)})
        return x.sort_values("CUOTA_IVA", key=abs, ascending=False)

    D = cot.dif_comunes.copy()
    D = pd.DataFrame({
        "NIF_SOCIEDAD": D.EMP, "SOCIEDAD": [nombres.get(v, "") for v in D.EMP],
        "NIF_PROVEEDOR": D.NIFK, "PROVEEDOR": D.nom_a, "N_A3": D.num_a, "N_BILKY": D.num_b,
        "TIPO_IVA": D.TIPO, "BASE_A3": D.base_a.round(2), "BASE_BILKY": D.base_b.round(2),
        "DIF_BASE": D.d_base, "CUOTA_A3": D.cuota_a.round(2), "CUOTA_BILKY": D.cuota_b.round(2),
        "DIF_CUOTA": D.d_cuota,
        "MOTIVO": D.motivo.map({"dup_a3": "Duplicada en A3", "dup_bilky": "Duplicada en Bilky",
                                "importe": "Importe distinto"})}).sort_values(
        "DIF_CUOTA", key=abs, ascending=False)

    ETI = {"solo_a3": "Corregir en A3", "doc_repetido": "Revisar en Bilky",
           "sincontraste": "Sin contraste en Bilky", "linea_repetida": "Lineas identicas en la factura",
           "falso": "No es duplicado"}
    U = pd.DataFrame([{
        "#": f["i"], "VEREDICTO": ETI[f["v"]], "NIF_SOCIEDAD": f["emp"],
        "SOCIEDAD": nombres.get(f["emp"], f["empresa"]), "NIF_PROVEEDOR": f["nifp"],
        "PROVEEDOR": f["prov"], "N_EN_A3": f["num_a3"],
        "N_REALES_BILKY": " | ".join(f["reales"]), "FECHAS": " | ".join(f["fechas"]),
        "TIPO_IVA": f["tipo"], "BASE": f["base"], "TOTAL": f["total"],
        "VECES_A3": f["rep_a3"], "VECES_BILKY": f["rep_bilky"], "DOCS_BILKY": f["docs_bilky"],
        "IVA_REPETIDO": f["sobrante"],
        "ENLACE": f["links"][0]["url"] if f["links"] else ""} for f in dup["facturas"]])

    T = tip.rename(columns={"TIPO": "TIPO_IVA", "base_a": "BASE_A3", "base_b": "BASE_BILKY",
                            "cuota_a": "CUOTA_A3", "cuota_b": "CUOTA_BILKY",
                            "lin_a": "LINEAS_A3", "lin_b": "LINEAS_BILKY", "d_cuota": "DIF_CUOTA"})

    rect = con["rectificativas"]
    RE = pd.DataFrame({
        "NIF_SOCIEDAD": rect.EMP, "SOCIEDAD": [nombres.get(v, "") for v in rect.EMP],
        "TIPO_FRA": rect.TIPOFRA, "NIF_PROVEEDOR": rect.NIF_PROV, "PROVEEDOR": rect.NOMBRE,
        "N_FACTURA": rect.NUM, "FECHA": rect.FECHA, "TIPO_IVA": rect.TIPO,
        "BASE": rect.B2, "CUOTA_IVA": rect.C2, "TOTAL": rect.T2}).sort_values("CUOTA_IVA")

    TR = pd.DataFrame(ctx["truncados"])
    AV = pd.DataFrame(ctx["avisos_tabla"])

    hojas = [
        ("RESUMEN", R), ("POR SOCIEDAD", S.round(2)),
        ("SOLO EN A3", _huerf(cot.solo_a, "a").round(2)),
        ("SOLO EN BILKY", _huerf(cot.solo_b, "b").round(2)),
        ("DIF IMPORTES", D.round(2)), ("POR TIPO DE IVA", T.round(2)),
        ("DUPLICADAS", U), ("RECTIFICATIVAS", RE.round(2)),
        ("N FACTURA TRUNCADO", TR), ("AVISOS", AV),
    ]
    with pd.ExcelWriter(ruta, engine="openpyxl") as w:
        for nombre, df in hojas:
            if df is None or len(df) == 0:
                df = pd.DataFrame({"(sin registros)": []})
            df.to_excel(w, sheet_name=nombre, index=False)
        for nombre, df in hojas:
            ws = w.sheets[nombre]
            for col in ws.columns:
                ancho = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 46)
            ws.freeze_panes = "A2"
    return ruta


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def html(ruta, plantilla, contexto):
    env = entorno()
    salida = env.get_template(plantilla).render(**contexto)
    if "{%" in salida:
        raise RuntimeError("La plantilla %s ha dejado marcas sin sustituir." % plantilla)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(salida)
    return ruta
