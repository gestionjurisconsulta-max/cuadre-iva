# -*- coding: utf-8 -*-
"""Lectura y normalizacion de los dos libros de IVA soportado.

Admite los formatos que salen de cada sistema:

  A3     un unico Excel unificado, o los CSV sueltos de cada sociedad tal cual
         los exporta (separados por ';', en cp1252 y con un ';' de mas al final)
  Bilky  el export unificado de 46 columnas, o el fichero por sociedad de 14

Cuando el fichero no trae columna de origen --el caso de los CSV sueltos-- la
sociedad se saca del nombre del propio fichero.
"""
import io
import os
import re
import unicodedata

import numpy as np
import pandas as pd


class ErrorDeLectura(Exception):
    """El fichero no tiene la forma esperada."""


def _clave(s):
    """Nombre de columna normalizado: sin acentos, sin signos, minusculas."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


# destino -> (fragmentos aceptados, obligatoria)
COLS_A3 = {
    "TIPOFRA":  (("tipodefactura",), True),
    "FECHA":    (("fechaexpedicion",), True),
    "NUM":      (("serienumero",), True),
    "NIF_PROV": (("identificacionnifexpedidor",), True),
    "NOMBRE":   (("nombreexpedidor",), True),
    "TOTAL":    (("totalfactura",), True),
    "BASE":     (("baseimponible",), True),
    "TIPO":     (("tipodeiva",), True),
    "CUOTA":    (("cuotaivasoportado",), True),
    "SOURCE":   (("sourcename",), False),
    "DEDUC":    (("cuotadeducible",), False),
    "RECARGO":  (("cuotarecargoeq",), False),
}

COLS_BILKY = {
    "FECHA":    (("fecha",), True),
    "NIF_PROV": (("nif",), True),
    "NOMBRE":   (("nombrelegal",), True),
    "BASE":     (("baseimponible",), True),
    "CUOTA":    (("iva",), True),
    "TIPO":     (("tipodeiva",), True),
    "TOTAL":    (("total",), True),
    "NUM":      (("numerodefactura",), True),
    "SOURCE":   (("sourcename",), False),
    "IDDOC":    (("identificadorbilky",), False),
    "RECARGO":  (("recargo",), False),
    "LINK":     (("vinculofra", "invoicelink"), False),
}

# NIF, NIE y CIF espanoles: siempre nueve caracteres.
NIF = r"(?:[0-9]{8}[A-Za-z]|[XYZxyz][0-9]{7}[A-Za-z]|[A-Za-z][0-9]{7}[0-9A-Za-z])"
_PATRONES_EMP = (
    re.compile(r"^\d{4}(" + NIF + r")G", re.I),     # A3:    2026B01709237GNOMBRESL
    re.compile(r"^(" + NIF + r")[-_ ]", re.I),      # Bilky: B10994051-ALADDIN-786-SL-...
    re.compile(r"[-_ ](" + NIF + r")[-_ ]", re.I),  # Bilky: Export-Bilky-...-B01709237-...
    re.compile(r"^\d{4}(" + NIF + r")", re.I),      # A3 sin la G
    re.compile(r"(" + NIF + r")", re.I),            # ultimo recurso
)
_RE_NOMBRE_A3 = re.compile(r"^\d{4}" + NIF + r"G(.+)$", re.I)
_RE_NOMBRE_BILKY = re.compile(r"^" + NIF + r"-(.+?)-libro-de-iva", re.I)


def nif_de_nombre(nombre):
    """Extrae el NIF de la sociedad del nombre del fichero."""
    base = os.path.splitext(os.path.basename(str(nombre)))[0]
    for p in _PATRONES_EMP:
        m = p.search(base)
        if m:
            return m.group(1).upper()
    return None


def nombre_de_fichero(nombre):
    """Nombre legible de la sociedad, si el fichero lo lleva."""
    base = os.path.splitext(os.path.basename(str(nombre)))[0]
    m = _RE_NOMBRE_BILKY.search(base)
    if m:
        return m.group(1).replace("-", " ").replace("_", " ").strip().upper()
    m = _RE_NOMBRE_A3.search(base)
    if m:
        return m.group(1).strip().upper()
    return ""


def importe(x):
    """Convierte un importe en formato espanol ('1.234,56') o numerico a float."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip().replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "nan", "None"):
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.replace("€", "").replace("EUR", "")
    if "," in s:                      # coma decimal, punto de millares
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:            # solo puntos y mas de uno: todos millares
        s = s.replace(".", "")
    elif "." in s:
        entero, dec = s.rsplit(".", 1)
        if len(dec) == 3 and entero.lstrip("+-").isdigit():
            s = entero + dec          # 1.234 -> 1234
    try:
        v = float(s)
    except ValueError:
        return np.nan
    return -v if neg else v


def texto_num(x):
    """Numero de factura como texto, sin el '.0' que mete pandas en los enteros."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    if isinstance(x, float) and float(x).is_integer():
        x = int(x)
    return str(x).strip()


def _fechas(serie):
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pd.to_datetime(serie, errors="coerce")
    mejor, mejor_ok = None, -1
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        f = pd.to_datetime(serie, format=formato, errors="coerce")
        ok = f.notna().sum()
        if ok > mejor_ok:
            mejor, mejor_ok = f, ok
    if mejor_ok < 0.5 * len(serie):
        mejor = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    return mejor


# --------------------------------------------------------------------------
# Lectura de un fichero suelto
# --------------------------------------------------------------------------

def _bytes(origen):
    if hasattr(origen, "read"):
        pos = origen.tell()
        origen.seek(0)
        b = origen.read()
        origen.seek(pos)
        return b
    with open(origen, "rb") as f:
        return f.read()


def _lee_csv(crudo, nombre):
    texto = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = crudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ErrorDeLectura("No se ha podido descifrar la codificacion de %s." % nombre)
    cabecera = texto.split("\n", 1)[0]
    sep = max(";,\t|", key=cabecera.count)
    if cabecera.count(sep) == 0:
        raise ErrorDeLectura(
            "%s no parece un CSV: la primera linea no tiene separadores." % nombre)
    # Las exportaciones de A3 llevan un separador de mas al final de cada fila,
    # que sin index_col=False desplazaria todas las columnas.
    return pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, index_col=False,
                       skip_blank_lines=True)


def _lee_tabla(origen, nombre):
    ext = os.path.splitext(str(nombre))[1].lower()
    try:
        crudo = _bytes(origen)
    except PermissionError:
        raise ErrorDeLectura(
            "No se ha podido abrir %s.\nSuele pasar por dos motivos: el fichero esta abierto "
            "en Excel (cierralo), o esta en OneDrive sin descargar (boton derecho > Conservar "
            "siempre en este dispositivo)." % nombre)
    except OSError as e:
        raise ErrorDeLectura("No se ha podido abrir %s: %s" % (nombre, e))
    if not crudo:
        raise ErrorDeLectura("El fichero %s esta vacio." % nombre)
    if ext == ".csv" or (ext not in (".xlsx", ".xlsm", ".xls") and crudo[:2] != b"PK"):
        df = _lee_csv(crudo, nombre)
    else:
        try:
            df = pd.read_excel(io.BytesIO(crudo))
        except Exception as e:
            raise ErrorDeLectura("No se ha podido leer %s como Excel: %s" % (nombre, e))
    if len(df) == 0:
        raise ErrorDeLectura("El fichero %s no tiene filas." % nombre)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def entradas(origenes):
    """Acepta una ruta, un buffer, o una lista de cualquiera de las dos cosas.

    Devuelve [(nombre, origen), ...]. Un directorio se expande a sus ficheros.
    """
    if origenes is None:
        return []
    if isinstance(origenes, (str, os.PathLike)) and os.path.isdir(str(origenes)):
        carpeta = str(origenes)
        origenes = [os.path.join(carpeta, f) for f in sorted(os.listdir(carpeta))
                    if os.path.splitext(f)[1].lower() in (".csv", ".xlsx", ".xlsm", ".xls")
                    and not f.startswith("~$")]
        if not origenes:
            raise ErrorDeLectura("La carpeta %s no tiene ficheros CSV ni Excel." % carpeta)
    if isinstance(origenes, (str, os.PathLike)) or hasattr(origenes, "read"):
        origenes = [origenes]
    salida = []
    for o in origenes:
        if isinstance(o, (tuple, list)) and len(o) == 2:
            salida.append((str(o[0]), o[1]))
        elif hasattr(o, "name"):
            salida.append((os.path.basename(str(o.name)), o))
        else:
            salida.append((os.path.basename(str(o)), o))
    return salida


def _localiza(df, mapa, origen, nombre_fichero):
    disponibles = {_clave(c): c for c in df.columns}
    encontradas, faltan = {}, []
    for destino, (fragmentos, obligatoria) in mapa.items():
        real = None
        for frag in fragmentos:
            real = disponibles.get(frag)
            if real is None:
                candidatas = [v for k, v in disponibles.items() if k.startswith(frag)]
                real = candidatas[0] if candidatas else None
            if real is not None:
                break
        if real is None:
            if obligatoria:
                faltan.append(fragmentos[0])
        else:
            encontradas[destino] = real
    if faltan:
        raise ErrorDeLectura(
            "En el fichero de %s «%s» faltan columnas obligatorias: %s.\n"
            "Columnas encontradas: %s"
            % (origen, nombre_fichero, ", ".join(faltan),
               ", ".join(str(c) for c in df.columns[:40])))
    return encontradas


_RE_ID_ENLACE = re.compile(r"/([A-Za-z0-9]{6,})/?$")


def _id_de_enlace(url):
    if not isinstance(url, str):
        return ""
    m = _RE_ID_ENLACE.search(url.strip())
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# Lectura de un libro completo
# --------------------------------------------------------------------------

def lee_a3(origenes):
    """Libro de IVA soportado de A3: un Excel unificado o varios CSV por sociedad."""
    return _lee_libro(origenes, "A3", COLS_A3, _fila_a3)


def lee_bilky(origenes):
    """Libro de facturas recibidas de Bilky: export unificado o uno por sociedad."""
    return _lee_libro(origenes, "Bilky", COLS_BILKY, _fila_bilky)


def _fila_a3(df, c, nombre_fichero):
    d = pd.DataFrame(index=df.index)
    d["TIPOFRA"] = df[c["TIPOFRA"]].fillna("").astype(str).str.strip().str.upper()
    d["FECHA"] = _fechas(df[c["FECHA"]])
    d["NUM"] = df[c["NUM"]].map(texto_num)
    d["NIF_PROV"] = df[c["NIF_PROV"]].fillna("NAN").astype(str).str.strip().str.upper()
    d["NOMBRE"] = df[c["NOMBRE"]].fillna("").astype(str).str.strip()
    for k in ("BASE", "TIPO", "CUOTA", "TOTAL"):
        d[k] = df[c[k]].map(importe)
    d["RECARGO"] = df[c["RECARGO"]].map(importe) if "RECARGO" in c else 0.0
    d["IDDOC"] = ""
    d["LINK"] = ""
    return d


def _fila_bilky(df, c, nombre_fichero):
    d = pd.DataFrame(index=df.index)
    d["TIPOFRA"] = ""
    d["FECHA"] = _fechas(df[c["FECHA"]])
    d["NUM"] = df[c["NUM"]].map(texto_num)
    d["NIF_PROV"] = df[c["NIF_PROV"]].fillna("NAN").astype(str).str.strip().str.upper()
    d["NOMBRE"] = df[c["NOMBRE"]].fillna("").astype(str).str.strip()
    for k in ("BASE", "TIPO", "CUOTA", "TOTAL"):
        d[k] = df[c[k]].map(importe)
    d["RECARGO"] = df[c["RECARGO"]].map(importe) if "RECARGO" in c else 0.0
    d["LINK"] = df[c["LINK"]].fillna("").astype(str).str.strip() if "LINK" in c else ""
    if "IDDOC" in c:
        d["IDDOC"] = df[c["IDDOC"]].fillna("").astype(str).str.strip()
    else:
        # El export por sociedad no trae el identificador, pero va dentro del enlace.
        d["IDDOC"] = d["LINK"].map(_id_de_enlace)
    return d


def _lee_libro(origenes, origen, mapa, construye):
    lista = entradas(origenes)
    if not lista:
        raise ErrorDeLectura("No se ha indicado ningun fichero de %s." % origen)

    trozos, sin_nif = [], []
    for nombre, dato in lista:
        df = _lee_tabla(dato, nombre)
        c = _localiza(df, mapa, origen, nombre)
        d = construye(df, c, nombre)
        if "SOURCE" in c:
            d["SOURCE"] = df[c["SOURCE"]].astype(str).str.replace(
                r"\.(csv|xlsx|xlsm)$", "", regex=True).str.strip()
        else:
            d["SOURCE"] = os.path.splitext(nombre)[0]
        d["EMP"] = d.SOURCE.map(nif_de_nombre)
        d["EMPRESA"] = d.SOURCE.map(nombre_de_fichero)
        if d.EMP.isna().any():
            sin_nif.append(nombre)
        trozos.append(d)

    d = pd.concat(trozos, ignore_index=True) if len(trozos) > 1 else trozos[0]
    if d.EMP.isna().all():
        raise ErrorDeLectura(
            "No se ha podido identificar la sociedad de ningun registro de %s.\n"
            "El NIF se saca del nombre del fichero o de la columna de origen; se esperaba "
            "algo como '2026B01709237GNOMBRESL.csv' o "
            "'B10994051-NOMBRE-SL-libro-de-iva-...xlsx'.\nPrimer valor leido: %r"
            % (origen, d.SOURCE.iloc[0] if len(d) else None))
    if sin_nif:
        d = d[d.EMP.notna()].reset_index(drop=True)
    d.attrs["ficheros"] = [n for n, _ in lista]
    d.attrs["sin_nif"] = sin_nif
    return _cierra(d, origen)


def _cierra(d, origen):
    for k in ("BASE", "TIPO", "CUOTA", "TOTAL", "RECARGO"):
        d[k] = pd.to_numeric(d[k], errors="coerce").fillna(0.0)
    for k in ("IDDOC", "LINK", "EMPRESA", "TIPOFRA"):
        d[k] = d[k].fillna("").astype(str)
    d["B2"] = d.BASE.round(2)
    d["C2"] = d.CUOTA.round(2)
    d["T2"] = d.TOTAL.round(2)
    d["NIFK"] = d.NIF_PROV.str.replace(r"[^A-Z0-9]", "", regex=True)
    sin_fecha = int(d.FECHA.isna().sum())
    if len(d) and sin_fecha == len(d):
        raise ErrorDeLectura("No se ha podido interpretar ninguna fecha del libro de %s." % origen)
    ficheros = d.attrs.get("ficheros", [])
    sinnif = d.attrs.get("sin_nif", [])
    d = d.reset_index(drop=True)
    d.attrs["origen"] = origen
    d.attrs["sin_fecha"] = sin_fecha
    d.attrs["ficheros"] = ficheros
    d.attrs["sin_nif"] = sinnif
    return d


def nombres_sociedades(*libros):
    """NIF de sociedad -> nombre. Gana el nombre mas legible de los disponibles."""
    nombres = {}
    for libro in libros:
        if libro is None or not len(libro):
            continue
        for emp, nom in libro[libro.EMPRESA != ""].groupby("EMP").EMPRESA.first().items():
            actual = nombres.get(emp, "")
            if not actual or (" " in nom and " " not in actual):
                nombres[emp] = nom
    return nombres
