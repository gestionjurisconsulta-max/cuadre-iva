# -*- coding: utf-8 -*-
"""Interfaz local del cuadre de IVA A3 · Bilky.

Arrancar con cuadre-iva.bat, o con:  streamlit run app.py
"""
import io
import os
import sys
import traceback
import zipfile
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paginas
from cuadre import bd, pipeline
from cuadre.informes import ent as _ent, eur as _eur
from cuadre.lectura import ErrorDeLectura

st.set_page_config(page_title="Cuadre de IVA A3 · Bilky", page_icon="🧾", layout="centered")

st.markdown("""
<style>
  .block-container{max-width:960px; padding-top:2.4rem}
  h1{font-size:1.9rem !important; letter-spacing:-.01em}
  .cap{color:#6b7280; font-size:.9rem; margin-top:-.6rem}
  div[data-testid="stMetricValue"]{font-size:1.4rem}
</style>
""", unsafe_allow_html=True)

st.title("Cuadre de IVA · A3 contra Bilky")
st.markdown('<p class="cap">Todo se ejecuta en este equipo: los ficheros no salen de aquí.</p>',
            unsafe_allow_html=True)

RUTA_BD = bd.dsn_por_defecto()
tab_nuevo, tab_hist = st.tabs(["Nuevo cuadre", "Histórico"])


with tab_nuevo:
    st.caption("Sube los libros de IVA soportado del trimestre y se generan el Excel "
               "de trabajo y los dos informes. Puedes subir el fichero unificado de cada "
               "sistema o los ficheros sueltos de cada sociedad, en Excel o en CSV.")
    col1, col2 = st.columns(2)
    with col1:
        f_a3 = st.file_uploader("Libros de **A3**", type=["xlsx", "xlsm", "csv"], key="a3",
                                accept_multiple_files=True)
        if f_a3:
            st.caption("%d %s" % (len(f_a3), "fichero" if len(f_a3) == 1 else "ficheros"))
    with col2:
        f_bk = st.file_uploader("Libros de **Bilky**", type=["xlsx", "xlsm", "csv"], key="bk",
                                accept_multiple_files=True)
        if f_bk:
            st.caption("%d %s" % (len(f_bk), "fichero" if len(f_bk) == 1 else "ficheros"))

    archivar = st.checkbox(
        "Archivar en el histórico", value=True,
        help="Guarda las líneas de los dos libros, las duplicadas y los descuadres para "
             "poder consultarlos después por rango de fechas. Si ya hay una carga de ese "
             "trimestre, se sustituye por ésta.")

    with st.expander("Opciones"):
        periodo = st.text_input(
            "Periodo", value="",
            placeholder="Se deduce del nombre de los ficheros, p. ej. 2T 2026",
            help="Nombra los ficheros de salida, identifica la carga en el histórico y "
                 "sirve para contar las facturas de fuera del trimestre.")
        destino = st.text_input(
            "Carpeta de salida", value="",
            placeholder="Vacío = se descargan desde aquí sin escribir en disco",
            help="Si indicas una carpeta, los tres ficheros se guardan también ahí.")

    lanzar = st.button("Generar informes", type="primary",
                       disabled=not (f_a3 and f_bk), width="stretch")

    if lanzar:
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_salida",
                           datetime.now().strftime("%Y%m%d-%H%M%S"))
        barra = st.progress(0.0, text="Preparando…")
        pasos = {"n": 0}

        def progreso(txt):
            pasos["n"] += 1
            barra.progress(min(pasos["n"] / 7.0, 0.95), text=txt)

        fallo = None
        res = None
        try:
            res = pipeline.ejecuta(
                [(f.name, io.BytesIO(f.getvalue())) for f in f_a3],
                [(f.name, io.BytesIO(f.getvalue())) for f in f_bk],
                destino.strip() or tmp, periodo=periodo.strip() or None,
                progreso=progreso, guardar_en_bd=archivar, ruta_bd=RUTA_BD)
        except ErrorDeLectura as e:
            fallo = ("No se ha podido leer alguno de los ficheros.", str(e))
        except Exception:
            fallo = ("El cuadre ha fallado. Detalle técnico:", traceback.format_exc())

        barra.empty()

        if fallo:
            st.error(fallo[0])
            st.code(fallo[1])
        else:
            r = res["resumen"]
            if res["cuadra"]:
                st.success("La conciliación cuadra: la diferencia de cuota queda explicada "
                           "al céntimo.")
            else:
                st.error("La conciliación NO cuadra. Revisa los avisos antes de usar "
                         "estos informes.")

            a, b, c = st.columns(3)
            a.metric("Diferencia de cuota", "%s €" % _eur(res["dif_cuota"]))
            b.metric("Facturas que cuadran", "%s de %s"
                     % (_ent(r["cuadran"]), _ent(r["facturas_comunes"])))
            c.metric("Duplicadas a revisar", _ent(r["duplicadas_accion"]),
                     help="De %s detectadas en total" % _ent(r["duplicadas"]))

            st.caption(
                "A3: %s líneas · %s € de cuota  |  Bilky: %s líneas · %s € de cuota  |  "
                "%d sociedades  |  regla de truncado: %.1f %% de acierto"
                % (_ent(r["lineas_a3"]), _eur(r["cuota_a3"]), _ent(r["lineas_bilky"]),
                   _eur(r["cuota_bilky"]), r["sociedades"], 100 * res["regla"]["tasa"]))

            graves = [x for x in res["avisos"] if x["nivel"] == "grave"]
            otros = [x for x in res["avisos"] if x["nivel"] != "grave"]
            for av in graves:
                st.error(av["texto"])
            if otros:
                with st.expander("%d avisos" % len(otros)):
                    for av in otros:
                        (st.warning if av["nivel"] == "aviso" else st.info)(av["texto"])

            st.subheader("Ficheros")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in res["ficheros"]:
                    z.write(f, os.path.basename(f))
            st.download_button(
                "Descargar los tres ficheros (.zip)", buf.getvalue(),
                file_name="Cuadre IVA%s.zip" % ((" " + res["periodo"]) if res["periodo"] else ""),
                mime="application/zip", width="stretch")
            for f in res["ficheros"]:
                with open(f, "rb") as fh:
                    st.download_button(os.path.basename(f), fh.read(),
                                       file_name=os.path.basename(f), width="stretch")

            if destino.strip():
                st.caption("Guardados también en %s" % destino.strip())
            else:
                st.caption("Copia temporal en %s" % tmp)
            if res.get("bd"):
                st.caption("Archivado en el histórico como carga %d%s. Consúltalo en la "
                           "pestaña **Histórico**."
                           % (res["bd"]["carga_id"],
                              " (sustituye una carga anterior del mismo trimestre)"
                              if res["bd"]["sustituidas"] else ""))


with tab_hist:
    paginas.historico(RUTA_BD)
