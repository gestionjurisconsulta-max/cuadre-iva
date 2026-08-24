# API del cuadre de IVA.
#
# La version de Python va clavada igual que las librerias: esta herramienta
# produce cifras que se declaran a Hacienda, y un cambio de version puede mover
# un redondeo sin avisar. Es la misma con la que pasan los tres tests.
FROM python:3.12.10-slim

# PYTHONUNBUFFERED para que los logs salgan al momento y no por bloques, que en
# un contenedor es la diferencia entre ver lo que pasa y no verlo.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias en una capa aparte: cambian mucho menos que el codigo, asi
# que se reaprovechan en cada reconstruccion.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cuadre/ ./cuadre/
COPY api/ ./api/
COPY cuadre_cli.py gestion_usuarios.py ./

# Sin privilegios: si alguien se cuela por la aplicacion, que no sea como root.
RUN useradd --create-home --uid 10001 cuadre && chown -R cuadre:cuadre /app
USER cuadre

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/salud', timeout=4).status == 200 else 1)"

# Un solo proceso a proposito. Los cuadres corren en un pool de hilos dentro de
# este proceso y cada uno atiende solo los trabajos que ha aceptado el; con
# varios workers, un trabajo lanzado en uno seria invisible para los demas.
# Para atender mas a la vez se sube CUADRE_TRABAJADORES, no el numero de workers.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
