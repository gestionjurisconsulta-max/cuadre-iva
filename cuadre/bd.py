# -*- coding: utf-8 -*-
"""Historico de cuadres en SQLite.

Guarda cada ejecucion completa --las lineas de los dos libros, las duplicadas con
su veredicto, los descuadres y los avisos-- para poder consultarlas despues por
rango de fechas y comparar trimestres entre si.

Dos fechas conviven y no significan lo mismo:

  fecha         la de expedicion de la factura
  periodo       el trimestre en cuyo libro se declaro

No coinciden siempre: una factura de marzo puede declararse en el libro del 2T.
Las consultas dejan elegir por cual filtrar.
"""
import hashlib
import os
import sqlite3
from datetime import datetime

import pandas as pd

VERSION_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
  clave TEXT PRIMARY KEY,
  valor TEXT
);

CREATE TABLE IF NOT EXISTS cargas (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  periodo       TEXT NOT NULL,
  ejecutado_en  TEXT NOT NULL,
  fichero_a3    TEXT,
  fichero_bilky TEXT,
  huella_a3     TEXT,
  huella_bilky  TEXT,
  lineas_a3     INTEGER,
  lineas_bilky  INTEGER,
  sociedades    INTEGER,
  cuota_a3      REAL,
  cuota_bilky   REAL,
  dif_cuota     REAL,
  cuadra        INTEGER,
  tasa_regla    REAL,
  duplicadas    INTEGER,
  duplicadas_accion INTEGER
);

CREATE TABLE IF NOT EXISTS lineas (
  carga_id   INTEGER NOT NULL REFERENCES cargas(id) ON DELETE CASCADE,
  periodo    TEXT NOT NULL,
  libro      TEXT NOT NULL,
  emp        TEXT,
  sociedad   TEXT,
  fecha      TEXT,
  nif_prov   TEXT,
  proveedor  TEXT,
  num        TEXT,
  num_clave  TEXT,
  tipofra    TEXT,
  tipo       REAL,
  base       REAL,
  cuota      REAL,
  total      REAL,
  iddoc      TEXT,
  enlace     TEXT
);

CREATE TABLE IF NOT EXISTS duplicadas (
  carga_id   INTEGER NOT NULL REFERENCES cargas(id) ON DELETE CASCADE,
  periodo    TEXT NOT NULL,
  emp        TEXT, sociedad TEXT,
  nif_prov   TEXT, proveedor TEXT,
  num_a3     TEXT, num_clave TEXT,
  fecha      TEXT, fechas TEXT,
  tipo REAL, base REAL, total REAL, cuota REAL,
  rep_a3 INTEGER, rep_bilky INTEGER, docs_bilky INTEGER,
  veredicto TEXT, sobrante REAL, enlace TEXT
);

CREATE TABLE IF NOT EXISTS descuadres (
  carga_id INTEGER NOT NULL REFERENCES cargas(id) ON DELETE CASCADE,
  periodo  TEXT NOT NULL,
  clase    TEXT NOT NULL,          -- solo_a3 | solo_bilky | importe
  emp TEXT, sociedad TEXT,
  nif_prov TEXT, proveedor TEXT,
  num TEXT, fecha TEXT, tipo REAL,
  base_a REAL, cuota_a REAL, base_b REAL, cuota_b REAL, dif_cuota REAL
);

CREATE TABLE IF NOT EXISTS avisos (
  carga_id INTEGER NOT NULL REFERENCES cargas(id) ON DELETE CASCADE,
  periodo TEXT NOT NULL, nivel TEXT, texto TEXT
);

CREATE INDEX IF NOT EXISTS ix_lin_fecha    ON lineas(fecha);
CREATE INDEX IF NOT EXISTS ix_lin_periodo  ON lineas(periodo, libro);
CREATE INDEX IF NOT EXISTS ix_lin_emp      ON lineas(emp);
CREATE INDEX IF NOT EXISTS ix_lin_prov     ON lineas(nif_prov);
CREATE INDEX IF NOT EXISTS ix_lin_carga    ON lineas(carga_id);
CREATE INDEX IF NOT EXISTS ix_lin_dup      ON lineas(libro, emp, nif_prov, num_clave, tipo, base);
CREATE INDEX IF NOT EXISTS ix_dup_periodo  ON duplicadas(periodo);
CREATE INDEX IF NOT EXISTS ix_dup_emp      ON duplicadas(emp, veredicto);
CREATE INDEX IF NOT EXISTS ix_des_periodo  ON descuadres(periodo, clase);
CREATE INDEX IF NOT EXISTS ix_des_fecha    ON descuadres(fecha);
"""


def ruta_por_defecto():
    return os.environ.get("CUADRE_BD", os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "cuadre.db"))


def conecta(ruta=None):
    ruta = ruta or ruta_por_defecto()
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    cx = sqlite3.connect(ruta)
    cx.execute("PRAGMA foreign_keys = ON")
    cx.execute("PRAGMA journal_mode = WAL")
    cx.executescript(ESQUEMA)
    cx.execute("INSERT OR IGNORE INTO meta(clave, valor) VALUES ('version', ?)",
               (str(VERSION_ESQUEMA),))
    cx.commit()
    return cx


def huella(origen):
    """sha256 de la entrada de un libro, sea una ruta, un buffer, una carpeta o
    una lista de cualquiera de ellos. Sirve para saber si un export ya se cargo.

    Usa la misma normalizacion que el lector, para no interpretar la entrada de
    dos formas distintas en dos sitios distintos.
    """
    from .lectura import entradas

    h = hashlib.sha256()
    for nombre, dato in entradas(origen):
        h.update(str(nombre).encode("utf-8"))
        if hasattr(dato, "read"):
            pos = dato.tell()
            dato.seek(0)
            for trozo in iter(lambda: dato.read(1 << 20), b""):
                h.update(trozo)
            dato.seek(pos)
        else:
            with open(dato, "rb") as f:
                for trozo in iter(lambda: f.read(1 << 20), b""):
                    h.update(trozo)
    return h.hexdigest()


def carga_previa(cx, periodo):
    r = cx.execute("SELECT id, ejecutado_en FROM cargas WHERE periodo = ? ORDER BY id",
                   (periodo,)).fetchall()
    return r


# --------------------------------------------------------------------------
# Guardado
# --------------------------------------------------------------------------

def _lineas(df, libro, nombres):
    return pd.DataFrame({
        "libro": libro,
        "emp": df.EMP,
        "sociedad": [nombres.get(e, "") for e in df.EMP],
        "fecha": df.FECHA.dt.strftime("%Y-%m-%d"),
        "nif_prov": df.NIFK,
        "proveedor": df.NOMBRE,
        "num": df.NUM.astype(str),
        "num_clave": df.NUM_CLAVE if "NUM_CLAVE" in df.columns else "",
        "tipofra": df.TIPOFRA,
        "tipo": df.TIPO, "base": df.B2, "cuota": df.C2, "total": df.T2,
        "iddoc": df.IDDOC if "IDDOC" in df.columns else "",
        "enlace": df.LINK if "LINK" in df.columns else "",
    })


def guarda(ruta_bd, periodo, a3, bk, cot, con, dup, avisos, nombres, resumen,
           ficheros=("", ""), huellas=("", ""), reemplaza=True):
    """Escribe una ejecucion completa. Devuelve (carga_id, cargas_reemplazadas)."""
    from . import normaliza as N

    cx = conecta(ruta_bd)
    periodo = periodo or "sin periodo"
    previas = [r[0] for r in carga_previa(cx, periodo)]
    if previas and reemplaza:
        cx.executemany("DELETE FROM cargas WHERE id = ?", [(i,) for i in previas])
        for tabla in ("lineas", "duplicadas", "descuadres", "avisos"):
            cx.executemany("DELETE FROM %s WHERE carga_id = ?" % tabla, [(i,) for i in previas])
    elif previas:
        cx.close()
        raise ValueError("Ya hay una carga del periodo %s. Usa reemplaza=True." % periodo)

    cur = cx.execute(
        "INSERT INTO cargas (periodo, ejecutado_en, fichero_a3, fichero_bilky, huella_a3,"
        " huella_bilky, lineas_a3, lineas_bilky, sociedades, cuota_a3, cuota_bilky, dif_cuota,"
        " cuadra, tasa_regla, duplicadas, duplicadas_accion)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (periodo, datetime.now().isoformat(timespec="seconds"), ficheros[0], ficheros[1],
         huellas[0], huellas[1], len(a3), len(bk), resumen["sociedades"],
         resumen["cuota_a3"], resumen["cuota_bilky"], con["total"], int(con["cuadra"]),
         cot.regla["tasa"], dup["meta"]["fras"], dup["meta"]["accion_fras"]))
    cid = cur.lastrowid

    a = a3.copy(); a["NUM_CLAVE"] = a.NUM.map(N.clave)
    b = bk.copy(); b["NUM_CLAVE"] = b.NUM.map(N.clave_bilky)
    L = pd.concat([_lineas(a, "A3", nombres), _lineas(b, "BILKY", nombres)], ignore_index=True)
    L.insert(0, "periodo", periodo)
    L.insert(0, "carga_id", cid)
    L.to_sql("lineas", cx, if_exists="append", index=False)

    if dup["facturas"]:
        D = pd.DataFrame([{
            "carga_id": cid, "periodo": periodo, "emp": f["emp"],
            "sociedad": nombres.get(f["emp"], f["empresa"]), "nif_prov": f["nifp"],
            "proveedor": f["prov"], "num_a3": f["num_a3"], "num_clave": N.clave(f["num_a3"]),
            "fecha": f["lineas"][0]["fecha"], "fechas": " | ".join(f["fechas"]),
            "tipo": f["tipo"], "base": f["base"], "total": f["total"], "cuota": f["cuota"],
            "rep_a3": f["rep_a3"], "rep_bilky": f["rep_bilky"], "docs_bilky": f["docs_bilky"],
            "veredicto": f["v"], "sobrante": f["sobrante"],
            "enlace": f["links"][0]["url"] if f["links"] else ""} for f in dup["facturas"]])
        D.to_sql("duplicadas", cx, if_exists="append", index=False)

    trozos = []
    for clase, d, lado in (("solo_a3", cot.solo_a, "a"), ("solo_bilky", cot.solo_b, "b"),
                           ("importe", cot.dif_comunes, None)):
        if not len(d):
            continue
        c = lado or "a"
        trozos.append(pd.DataFrame({
            "carga_id": cid, "periodo": periodo, "clase": clase, "emp": d.EMP,
            "sociedad": [nombres.get(e, "") for e in d.EMP],
            "nif_prov": d.NIFK, "proveedor": d["nom_" + c], "num": d["num_" + c].astype(str),
            "fecha": d["fec_" + c].dt.strftime("%Y-%m-%d"), "tipo": d.TIPO,
            "base_a": d.base_a.round(2), "cuota_a": d.cuota_a.round(2),
            "base_b": d.base_b.round(2), "cuota_b": d.cuota_b.round(2),
            "dif_cuota": d.d_cuota}))
    if trozos:
        pd.concat(trozos, ignore_index=True).to_sql("descuadres", cx, if_exists="append", index=False)

    if avisos:
        pd.DataFrame([{"carga_id": cid, "periodo": periodo, "nivel": a["nivel"],
                       "texto": a["texto"]} for a in avisos]).to_sql(
            "avisos", cx, if_exists="append", index=False)

    cx.commit()
    cx.close()
    return cid, previas


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------

def cargas(ruta_bd=None):
    cx = conecta(ruta_bd)
    df = pd.read_sql_query("SELECT * FROM cargas ORDER BY periodo", cx)
    cx.close()
    return df


def periodos(ruta_bd=None):
    cx = conecta(ruta_bd)
    r = [x[0] for x in cx.execute("SELECT periodo FROM cargas ORDER BY periodo").fetchall()]
    cx.close()
    return r


def rango_fechas(ruta_bd=None):
    cx = conecta(ruta_bd)
    r = cx.execute("SELECT MIN(fecha), MAX(fecha) FROM lineas").fetchone()
    cx.close()
    return r


def _filtra(sql, params, desde, hasta, campo_fecha, libro, emps, provs, periodos_):
    if desde:
        sql += " AND %s >= ?" % campo_fecha
        params.append(str(desde))
    if hasta:
        sql += " AND %s <= ?" % campo_fecha
        params.append(str(hasta))
    if libro and libro != "Ambos":
        sql += " AND libro = ?"
        params.append(libro)
    if emps:
        sql += " AND emp IN (%s)" % ",".join("?" * len(emps))
        params += list(emps)
    if provs:
        sql += " AND nif_prov IN (%s)" % ",".join("?" * len(provs))
        params += list(provs)
    if periodos_:
        sql += " AND periodo IN (%s)" % ",".join("?" * len(periodos_))
        params += list(periodos_)
    return sql, params


def lineas(ruta_bd=None, desde=None, hasta=None, por="fecha", libro=None,
           emps=None, provs=None, periodos_=None, limite=None):
    """Lineas de los dos libros filtradas por rango.

    por='fecha'   filtra por fecha de expedicion de la factura
    por='periodo' filtra por el trimestre en cuyo libro se declaro
    """
    cx = conecta(ruta_bd)
    if por == "periodo":
        sql = "SELECT * FROM lineas WHERE 1=1"
        params = []
        sql, params = _filtra(sql, params, None, None, "fecha", libro, emps, provs, periodos_)
    else:
        sql = "SELECT * FROM lineas WHERE 1=1"
        params = []
        sql, params = _filtra(sql, params, desde, hasta, "fecha", libro, emps, provs, periodos_)
    sql += " ORDER BY fecha, emp, proveedor"
    if limite:
        sql += " LIMIT %d" % int(limite)
    df = pd.read_sql_query(sql, cx, params=params)
    cx.close()
    return df


def duplicadas(ruta_bd=None, desde=None, hasta=None, veredictos=None, periodos_=None, emps=None):
    cx = conecta(ruta_bd)
    sql = "SELECT * FROM duplicadas WHERE 1=1"
    params = []
    if desde:
        sql += " AND fecha >= ?"; params.append(str(desde))
    if hasta:
        sql += " AND fecha <= ?"; params.append(str(hasta))
    if veredictos:
        sql += " AND veredicto IN (%s)" % ",".join("?" * len(veredictos)); params += list(veredictos)
    if periodos_:
        sql += " AND periodo IN (%s)" % ",".join("?" * len(periodos_)); params += list(periodos_)
    if emps:
        sql += " AND emp IN (%s)" % ",".join("?" * len(emps)); params += list(emps)
    sql += " ORDER BY ABS(sobrante) DESC"
    df = pd.read_sql_query(sql, cx, params=params)
    cx.close()
    return df


def descuadres(ruta_bd=None, desde=None, hasta=None, clases=None, periodos_=None, emps=None):
    cx = conecta(ruta_bd)
    sql = "SELECT * FROM descuadres WHERE 1=1"
    params = []
    if desde:
        sql += " AND fecha >= ?"; params.append(str(desde))
    if hasta:
        sql += " AND fecha <= ?"; params.append(str(hasta))
    if clases:
        sql += " AND clase IN (%s)" % ",".join("?" * len(clases)); params += list(clases)
    if periodos_:
        sql += " AND periodo IN (%s)" % ",".join("?" * len(periodos_)); params += list(periodos_)
    if emps:
        sql += " AND emp IN (%s)" % ",".join("?" * len(emps)); params += list(emps)
    sql += " ORDER BY ABS(dif_cuota) DESC"
    df = pd.read_sql_query(sql, cx, params=params)
    cx.close()
    return df


def resumen_por_periodo(ruta_bd=None):
    cx = conecta(ruta_bd)
    df = pd.read_sql_query(
        "SELECT periodo, ejecutado_en, lineas_a3, lineas_bilky, sociedades,"
        " cuota_a3, cuota_bilky, dif_cuota, cuadra, tasa_regla, duplicadas,"
        " duplicadas_accion FROM cargas ORDER BY periodo", cx)
    cx.close()
    return df


def sociedades(ruta_bd=None):
    cx = conecta(ruta_bd)
    df = pd.read_sql_query(
        "SELECT emp, MAX(sociedad) AS sociedad, COUNT(*) AS lineas"
        " FROM lineas GROUP BY emp ORDER BY emp", cx)
    cx.close()
    return df


def duplicadas_entre_periodos(ruta_bd=None, minimo_iva=0.0, limite=None, dias_basura=3):
    """La misma factura declarada en el libro de A3 de dos trimestres distintos.

    Es el riesgo que solo aparece cuando hay historico: dentro de un trimestre el
    informe ya lo detecta, pero una factura repetida en 1T y en 2T no la ve nadie.

    Se excluyen los numeros que no identifican nada --el mismo «numero» en mas de
    `dias_basura` fechas distintas dentro de un mismo trimestre, como cuando se
    cuela parte de un NIF en el campo--, porque generarian falsos positivos.
    """
    cx = conecta(ruta_bd)
    df = pd.read_sql_query("""
        WITH basura AS (
            SELECT emp, nif_prov, num_clave
              FROM lineas
             WHERE libro = 'A3' AND num_clave <> ''
             GROUP BY emp, nif_prov, num_clave, periodo
            HAVING COUNT(DISTINCT fecha) > ?
        )
        SELECT l.emp, MAX(l.sociedad) AS sociedad, l.nif_prov,
               MAX(l.proveedor) AS proveedor, l.num_clave, l.tipo, l.base,
               COUNT(DISTINCT l.periodo) AS trimestres,
               GROUP_CONCAT(DISTINCT l.periodo) AS periodos,
               GROUP_CONCAT(l.fecha) AS fechas,
               SUM(l.cuota) AS cuota_total, MAX(l.cuota) AS cuota_una,
               COUNT(*) AS lineas
          FROM lineas l
         WHERE l.libro = 'A3' AND l.num_clave <> '' AND (l.base <> 0 OR l.total <> 0)
           AND NOT EXISTS (SELECT 1 FROM basura b
                            WHERE b.emp = l.emp AND b.nif_prov = l.nif_prov
                              AND b.num_clave = l.num_clave)
         GROUP BY l.emp, l.nif_prov, l.num_clave, l.tipo, l.base
        HAVING COUNT(DISTINCT l.periodo) > 1
         ORDER BY ABS(SUM(l.cuota) - MAX(l.cuota)) DESC
    """, cx, params=[dias_basura])
    cx.close()
    if not len(df):
        return df
    # El campo del numero a veces trae el NIF del proveedor o el de la propia
    # sociedad. Entonces dos facturas distintas del mismo importe --un alquiler
    # mensual, por ejemplo-- pareceria la misma repetida.
    from . import normaliza as N
    es_nif = [nc == N.clave(np_) or nc == N.clave(e)
              for nc, np_, e in zip(df.num_clave, df.nif_prov, df.emp)]
    df = df[~pd.Series(es_nif, index=df.index)]
    df["iva_repetido"] = (df.cuota_total - df.cuota_una).round(2)
    if minimo_iva:
        df = df[df.iva_repetido.abs() >= minimo_iva]
    if limite:
        df = df.head(int(limite))
    return df.reset_index(drop=True)


def evolucion_duplicadas(ruta_bd=None):
    """Sociedades que repiten duplicadas trimestre tras trimestre."""
    cx = conecta(ruta_bd)
    df = pd.read_sql_query("""
        SELECT emp, MAX(sociedad) AS sociedad,
               COUNT(DISTINCT periodo) AS trimestres,
               GROUP_CONCAT(DISTINCT periodo) AS periodos,
               COUNT(*) AS facturas,
               ROUND(SUM(sobrante), 2) AS iva
          FROM duplicadas
         WHERE veredicto IN ('solo_a3','doc_repetido','sincontraste')
         GROUP BY emp
         ORDER BY trimestres DESC, iva DESC
    """, cx)
    cx.close()
    return df


def borra_periodo(ruta_bd, periodo):
    cx = conecta(ruta_bd)
    ids = [r[0] for r in cx.execute("SELECT id FROM cargas WHERE periodo = ?", (periodo,))]
    for tabla in ("lineas", "duplicadas", "descuadres", "avisos"):
        cx.executemany("DELETE FROM %s WHERE carga_id = ?" % tabla, [(i,) for i in ids])
    cx.executemany("DELETE FROM cargas WHERE id = ?", [(i,) for i in ids])
    cx.commit()
    cx.execute("VACUUM")
    cx.close()
    return len(ids)
