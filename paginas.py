# -*- coding: utf-8 -*-
"""Pestana de historico: consulta por rango de fechas y exportacion."""
import io
import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from cuadre import bd
from cuadre.informes import ent, eur

VEREDICTOS = {
    "solo_a3": "Corregir en A3",
    "doc_repetido": "Revisar en Bilky",
    "sincontraste": "Sin contraste",
    "linea_repetida": "Líneas idénticas",
    "falso": "No es duplicado",
}
CLASES = {"solo_a3": "Solo en A3", "solo_bilky": "Solo en Bilky", "importe": "Importe distinto"}


def _excel(hojas):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nombre, df in hojas:
            (df if len(df) else pd.DataFrame({"(sin registros)": []})).to_excel(
                w, sheet_name=nombre[:31], index=False)
        for nombre, df in hojas:
            ws = w.sheets[nombre[:31]]
            for col in ws.columns:
                ancho = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 44)
            ws.freeze_panes = "A2"
    return buf.getvalue()


def _fecha(s, por_defecto):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return por_defecto


def historico(ruta_bd):
    cargas = bd.resumen_por_periodo(ruta_bd)
    if not len(cargas):
        st.info("Todavía no hay nada archivado. Marca **Archivar en el histórico** al generar "
                "un cuadre y aparecerá aquí.")
        return

    st.subheader("Trimestres archivados")
    vista = cargas.copy()
    vista["cuadra"] = vista.cuadra.map({1: "sí", 0: "NO"})
    vista["tasa_regla"] = (100 * vista.tasa_regla).round(1)
    vista = vista.rename(columns={
        "periodo": "Periodo", "ejecutado_en": "Ejecutado", "lineas_a3": "Líneas A3",
        "lineas_bilky": "Líneas Bilky", "sociedades": "Sociedades", "cuota_a3": "Cuota A3",
        "cuota_bilky": "Cuota Bilky", "dif_cuota": "Diferencia", "cuadra": "Cuadra",
        "tasa_regla": "Regla %", "duplicadas": "Duplicadas", "duplicadas_accion": "A revisar"})
    st.dataframe(vista, width="stretch", hide_index=True)

    minf, maxf = bd.rango_fechas(ruta_bd)
    hoy = date.today()
    ini_def, fin_def = _fecha(minf, hoy), _fecha(maxf, hoy)

    st.subheader("Consultar y exportar")
    c1, c2 = st.columns(2)
    desde = c1.date_input("Desde", value=ini_def, format="DD/MM/YYYY")
    hasta = c2.date_input("Hasta", value=fin_def, format="DD/MM/YYYY")
    st.caption("El rango se aplica sobre la **fecha de expedición de la factura**. "
               "No es lo mismo que el trimestre en que se declaró: una factura de marzo "
               "puede estar en el libro del 2T. Con el filtro de trimestres acotas eso.")

    c1, c2, c3 = st.columns([2, 2, 1])
    peri = c1.multiselect("Trimestres", bd.periodos(ruta_bd), default=[])
    socs = bd.sociedades(ruta_bd)
    etiquetas = {"%s · %s" % (r.emp, r.sociedad or "?"): r.emp for r in socs.itertuples()}
    elegidas = c2.multiselect("Sociedades", list(etiquetas), default=[])
    libro = c3.selectbox("Libro", ["Ambos", "A3", "BILKY"])

    emps = [etiquetas[e] for e in elegidas] or None
    filtro = dict(desde=desde, hasta=hasta, emps=emps, periodos_=peri or None)

    lin = bd.lineas(ruta_bd, libro=libro, **filtro)
    dup = bd.duplicadas(ruta_bd, desde=desde, hasta=hasta, periodos_=peri or None, emps=emps)
    des = bd.descuadres(ruta_bd, desde=desde, hasta=hasta, periodos_=peri or None, emps=emps)

    a, b, c, d = st.columns(4)
    a.metric("Líneas", ent(len(lin)))
    a3 = lin[lin.libro == "A3"]
    bk = lin[lin.libro == "BILKY"]
    b.metric("Cuota A3", "%s €" % eur(a3.cuota.sum()))
    c.metric("Cuota Bilky", "%s €" % eur(bk.cuota.sum()))
    d.metric("Diferencia", "%s €" % eur(a3.cuota.sum() - bk.cuota.sum()))

    if not len(lin):
        st.warning("No hay líneas en ese rango con esos filtros.")
        return

    t1, t2, t3, t4 = st.tabs(["Líneas", "Duplicadas (%d)" % len(dup),
                              "Descuadres (%d)" % len(des), "Entre trimestres"])

    with t1:
        porm = (lin.assign(mes=lin.fecha.str[:7])
                   .groupby(["mes", "libro"]).cuota.sum().unstack(fill_value=0))
        if len(porm) > 1:
            st.caption("Cuota por mes de factura")
            st.bar_chart(porm, height=220)
        st.dataframe(lin.drop(columns=["carga_id"]).head(3000), width="stretch",
                     hide_index=True)
        if len(lin) > 3000:
            st.caption("Mostrando 3.000 de %s líneas. La exportación las incluye todas."
                       % ent(len(lin)))

    with t2:
        if len(dup):
            v = dup.copy()
            v["veredicto"] = v.veredicto.map(VEREDICTOS).fillna(v.veredicto)
            st.dataframe(v.drop(columns=["carga_id"]), width="stretch", hide_index=True)
        else:
            st.caption("Sin duplicadas en el rango.")

    with t3:
        if len(des):
            v = des.copy()
            v["clase"] = v.clase.map(CLASES).fillna(v.clase)
            st.dataframe(v.drop(columns=["carga_id"]), width="stretch", hide_index=True)
        else:
            st.caption("Sin descuadres en el rango.")

    with t4:
        st.caption("La misma factura declarada en el libro de A3 de dos trimestres distintos. "
                   "Es lo que ningún informe de un solo trimestre puede ver. Se excluyen los "
                   "números que no identifican la factura.")
        cruz = bd.duplicadas_entre_periodos(ruta_bd, minimo_iva=0.01, limite=500)
        if len(cruz):
            st.error("%d facturas aparecen en más de un trimestre, con %s € de IVA repetido."
                     % (len(cruz), eur(cruz.iva_repetido.sum())))
            st.dataframe(cruz, width="stretch", hide_index=True)
        else:
            st.success("Ninguna factura se repite entre trimestres.")
        evo = bd.evolucion_duplicadas(ruta_bd)
        if len(evo):
            st.caption("Sociedades con duplicadas a revisar, por número de trimestres afectados")
            st.dataframe(evo, width="stretch", hide_index=True)

    st.subheader("Exportar")
    rango = "%s a %s" % (desde.strftime("%d-%m-%Y"), hasta.strftime("%d-%m-%Y"))
    hojas = [("LINEAS", lin.drop(columns=["carga_id"])),
             ("DUPLICADAS", dup.drop(columns=["carga_id"]) if len(dup) else dup),
             ("DESCUADRES", des.drop(columns=["carga_id"]) if len(des) else des),
             ("ENTRE TRIMESTRES", bd.duplicadas_entre_periodos(ruta_bd, minimo_iva=0.01)),
             ("TRIMESTRES", cargas)]
    st.download_button("Descargar Excel del rango seleccionado", _excel(hojas),
                       file_name="Historico IVA %s.xlsx" % rango,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.download_button("Descargar solo las líneas (.csv)",
                       lin.drop(columns=["carga_id"]).to_csv(index=False, sep=";", decimal=","),
                       file_name="Lineas IVA %s.csv" % rango, mime="text/csv",
                       width="stretch")

    with st.expander("Mantenimiento"):
        st.caption("Base de datos: %s (%s)" % (
            ruta_bd or bd.dsn_por_defecto(),
            _tam(ruta_bd)))
        quitar = st.selectbox("Borrar un trimestre del histórico", ["—"] + bd.periodos(ruta_bd))
        if quitar != "—" and st.button("Borrar %s" % quitar, type="secondary"):
            n = bd.borra_periodo(ruta_bd, quitar)
            st.success("Borrado %s (%d carga)." % (quitar, n))
            st.rerun()


def _tam(dsn):
    """Tamano del histórico. Ya no es un fichero: se lo preguntamos al motor."""
    try:
        return bd.tamano(dsn)
    except Exception:
        return "no disponible"
