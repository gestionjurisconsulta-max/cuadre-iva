# -*- coding: utf-8 -*-
"""Exportacion del historico a Excel y CSV.

Consultar el historico por rango sirve de poco si luego no te lo puedes llevar a
una hoja: esto es lo que convierte la consulta en una herramienta de trabajo.

Los agregados se calculan aqui, en el servidor, y no en el navegador. Un rango
de un trimestre son ~68.000 lineas, y mandarlas enteras para pintar cuatro
cifras seria absurdo.
"""
import io

import pandas as pd

from . import bd

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _filtros(desde=None, hasta=None, periodos=None, emps=None):
    return dict(desde=desde or None, hasta=hasta or None,
                periodos_=periodos or None, emps=emps or None)


def resumen(dsn=None, desde=None, hasta=None, libro=None, periodos=None, emps=None):
    """Las cifras del rango y la cuota por mes, sin traerse las lineas."""
    f = _filtros(desde, hasta, periodos, emps)
    lin = bd.lineas(dsn, libro=libro, limite=None, **f)
    if not len(lin):
        return {"lineas": 0, "cuota_a3": 0.0, "cuota_bilky": 0.0, "diferencia": 0.0,
                "por_mes": [], "duplicadas": 0, "descuadres": 0}
    a3 = lin[lin.libro == "A3"]
    bk = lin[lin.libro == "BILKY"]
    mes = (lin.assign(mes=lin.fecha.str[:7])
              .groupby(["mes", "libro"]).cuota.sum().unstack(fill_value=0).round(2))
    return {
        "lineas": int(len(lin)),
        "cuota_a3": round(float(a3.cuota.sum()), 2),
        "cuota_bilky": round(float(bk.cuota.sum()), 2),
        "diferencia": round(float(a3.cuota.sum() - bk.cuota.sum()), 2),
        "por_mes": [{"mes": m, "a3": float(r.get("A3", 0)), "bilky": float(r.get("BILKY", 0))}
                    for m, r in mes.to_dict(orient="index").items()],
        "duplicadas": int(len(bd.duplicadas(dsn, **f))),
        "descuadres": int(len(bd.descuadres(dsn, **f))),
    }


def _sin_carga(df):
    return df.drop(columns=["carga_id"]) if "carga_id" in df.columns else df


def excel(dsn=None, desde=None, hasta=None, libro=None, periodos=None, emps=None):
    """Un libro con todo lo del rango: lineas, duplicadas, descuadres y contexto."""
    f = _filtros(desde, hasta, periodos, emps)
    hojas = [
        ("LINEAS", _sin_carga(bd.lineas(dsn, libro=libro, limite=None, **f))),
        ("DUPLICADAS", _sin_carga(bd.duplicadas(dsn, **f))),
        ("DESCUADRES", _sin_carga(bd.descuadres(dsn, **f))),
        ("ENTRE TRIMESTRES", bd.duplicadas_entre_periodos(dsn, minimo_iva=0.01)),
        ("NUMEROS SOSPECHOSOS", bd.numeros_sospechosos(dsn)),
        ("TRIMESTRES", bd.resumen_por_periodo(dsn)),
    ]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nombre, df in hojas:
            (df if len(df) else pd.DataFrame({"(sin registros)": []})).to_excel(
                w, sheet_name=nombre[:31], index=False)
        for nombre, df in hojas:
            ws = w.sheets[nombre[:31]]
            for col in ws.columns:
                ancho = max((len(str(c.value)) for c in col[:200] if c.value is not None),
                            default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 44)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def csv_lineas(dsn=None, desde=None, hasta=None, libro=None, periodos=None, emps=None):
    """Las lineas en CSV, con el formato que espera Excel en español."""
    lin = _sin_carga(bd.lineas(dsn, libro=libro, limite=None,
                               **_filtros(desde, hasta, periodos, emps)))
    return lin.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def nombre(prefijo, desde=None, hasta=None, extension="xlsx"):
    if desde and hasta:
        rango = " %s a %s" % (str(desde)[:10], str(hasta)[:10])
    else:
        rango = ""
    return "%s%s.%s" % (prefijo, rango, extension)
