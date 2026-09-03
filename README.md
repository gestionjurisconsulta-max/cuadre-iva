# Cuadre de IVA · A3 contra Bilky

Sube los dos libros de IVA soportado de un trimestre y genera el Excel de trabajo
y los dos informes.

## Puesta en marcha

```bash
cp .env.example .env          # y cambia POSTGRES_PASSWORD
docker compose up -d
docker compose exec api python gestion_usuarios.py crear victor "Victor Cisneros"
```

Se entra por `http://localhost:8081`. Ya está.

Son tres contenedores: `db` (PostgreSQL), `api` (FastAPI) y `web` (la interfaz
compilada, servida por nginx).

**Solo `web` publica puerto.** La API y la base hablan por la red interna de
docker y no se alcanzan desde fuera: a la API solo se llega atravesando nginx,
que además sirve la interfaz desde el mismo origen. Por eso la cookie de sesión
es de primera parte y no hace falta CORS.

**El TLS no está incluido.** Lo pone quien administre el VPS, delante de esto —
un nginx o un Caddy con el certificado del dominio—. No viene aquí porque
depende del dominio y del certificado, y equivocarse ahí es peor que no ponerlo.
Cuando esté, hay que poner `CUADRE_COOKIE_SEGURA=1` en el `.env` para que la
cookie deje de viajar por http.

**`web` escucha solo en `127.0.0.1`, y en el 8081.** Va a un VPS donde hay más
proyectos, y publicar en `0.0.0.0` abriría la aplicación a internet por http sin
que nadie lo haya decidido —docker escribe sus reglas antes que las de `ufw`,
así que el cortafuegos no lo tapa—. El 8081 y no el 8080 porque el 8080 lo
declara el dashboard de carpetas; si en el servidor estuviera cogido igualmente,
se cambia `CUADRE_PUERTO` en el `.env` y ya. Para desplegarlo,
**[DESPLIEGUE.md](DESPLIEGUE.md)**: comprobar puertos, proxy con TLS,
cortafuegos y copias.

### Para desarrollar

```bash
docker compose up -d db
uvicorn api.main:app --reload
cd web && npm run dev
```

Entras por `http://localhost:5173` y el servidor de desarrollo hace de proxy
hacia la API.

### Desde línea de comandos

Con carpetas:

```bash
python cuadre_cli.py --a3 "Libros IVA 3T 2026/Recibidas A3" --bilky "Libros IVA 3T 2026/BILKY 3T" --salida "Libros IVA 3T 2026" --bd
```

o con ficheros sueltos:

```bash
python cuadre_cli.py --a3 "REVISION FACTURA A3 3T 2026.xlsx" --bilky "REVISION FACTURA BILKY 3T 2026.xlsx" --salida "LIBROS DE IVA 3T 2026"
```

Devuelve código 0 si la conciliación cuadra y no hay avisos graves.

## Qué ficheros admite

De cada sistema puedes subir **el fichero unificado o los sueltos de cada
sociedad**, y mezclarlos si hace falta. En la interfaz se seleccionan varios a la
vez; en el CLI se pasa una carpeta o una lista.

| Origen | Formatos |
|---|---|
| A3 | el Excel unificado, o los CSV por sociedad tal cual los exporta (`;`, cp1252 y un `;` de más al final de cada fila) |
| Bilky | el export unificado de 46 columnas, o el fichero por sociedad de 14 |

El export por sociedad de Bilky no trae `Identificador Bilky`, así que se saca de
la URL de `invoice_link`. Es el mismo identificador.

### De dónde sale la sociedad

Cuando el fichero no trae columna de origen —el caso de los CSV sueltos— el NIF
se saca del **nombre del fichero**. Se reconocen estos patrones:

    2026B01709237GPAKSPASERVICIOSINTEGRALESSL.csv          A3, sociedad
    202638092900RGCISNEROSMULLERVICTOR.csv                 A3, persona física
    Export-Bilky-Factura-recibida-B01709237-Trimestre-2-2026.xlsx
    B10994051-ALADDIN-786-SL-libro-de-iva-facturas-recibidas-Trimestre-1-2026.xlsx

Si un fichero no encaja en ninguno, sus filas se descartan y el sistema avisa. Y
como el nombre de Bilky lleva la razón social legible, se prefiere ése al de A3,
que viene sin espacios.

## Qué genera

| Fichero | Contenido |
|---|---|
| `COMPARATIVA IVA A3 vs BILKY <periodo>.xlsx` | 14 pestañas con todo el detalle |
| `Comparativa_IVA_A3_vs_BILKY_<periodo>.html` | Cuadre general y conciliación de la diferencia |
| `Facturas_Duplicadas_IVA_<periodo>.html` | Duplicadas con veredicto y enlace al documento en Bilky |

Y archiva la ejecución en el histórico, para poder consultarla luego por rango de
fechas junto con la de los demás trimestres.

## Cómo cuadra

El cotejo se hace a nivel **factura × tipo de IVA**, no línea a línea: Bilky
desglosa rappels y descuentos en líneas aparte que A3 contabiliza netos, y
compararlos uno a uno generaría diferencias que no existen.

La clave de emparejamiento es NIF de sociedad + NIF de proveedor + número de
factura normalizado + tipo de IVA. Lo que no casa por número se intenta rescatar
por proveedor, fecha e importe.

La diferencia de cuota se descompone en cuatro partidas que deben sumar el total
exacto. **Si no suma, el informe lo dice en rojo y el CLI devuelve código 1.**

## La regla de truncado

A3 no guarda el número de factura completo: conserva los **10 últimos caracteres**
del original —espacios y separadores incluidos— y convierte barras, guiones y
puntos en espacios.

    2026FA / 260107604   ->   260107604
    26/000/009950        ->   000 009950
    FNB26/033375         ->   B26 033375

Esa regla está deducida de los datos, no documentada por el fabricante. Por eso
**se vuelve a medir en cada ejecución**: si el acierto baja del 95 % el sistema
avisa de que A3 probablemente ha cambiado el formato de exportación, en lugar de
emparejar mal en silencio.

Su efecto secundario es que dos facturas distintas del mismo proveedor pueden
quedar con el mismo número. Son los *falsos duplicados*, y por eso el informe de
duplicadas contrasta cada caso contra Bilky, que sí conserva el número entero.

## Avisos automáticos

Cada ejecución revisa además:

- **ficheros importados sin coma decimal**, con todo multiplicado por cien. Es lo
  que sale de abrir el CSV de A3 con un locale inglés, y el síntoma es un tipo de
  IVA de 2.100 %. Invalida el cuadre entero, así que además de avisarlo el
  primero, **la ejecución no se archiva en el histórico** aunque esté marcada la
  casilla: unas cifras así se quedarían ahí para siempre ensuciando la
  comparación entre trimestres. Los informes sí se generan, que para eso sirven
  —para ver el desastre—, pero la pantalla los muestra apagados
- **la misma factura cargada en dos sociedades distintas** —mismo proveedor,
  número, fecha e importe—, que es un error de asignación: el gasto se lo queda
  quien no es
- **duplicados que solo se ven en el libro de Bilky.** El criterio de la pestaña
  de duplicadas parte de A3: si A3 tiene la factura una sola vez no la marca, por
  mucho que en Bilky haya dos documentos
- **tipos de IVA que no existen** en el impuesto (un 10,5 % es un error de tecleo)
- **números de factura que no coinciden entre los dos libros** en facturas que sí
  son la misma. En el SII se declara el número, no el importe
- sociedades que están en un libro y no en el otro
- líneas sin NIF de expedidor (no declarables en el SII)
- tipos de IVA que solo existen en uno de los dos libros
- números que no identifican la factura (el mismo «número» en muchos documentos
  y muchos días, normalmente parte de un NIF colado en el campo)
- duplicados reales que el criterio de coincidencia exacta no ve, por diferencias
  de formato en el número
- líneas vacías de tipo SF

Salen en la pantalla de resultados, en la cabecera de los dos informes y en la
pestaña `AVISOS` del Excel. Los cuatro primeros tienen además su propia pestaña
con el detalle: `DUPLICADAS EN BILKY`, `MISMA FRA 2 SOCIEDADES`,
`N FACTURA DISCREPANTE` y `TIPO IVA INVALIDO`.

### El céntimo que escondía duplicados

Dos capturas del mismo documento no salen idénticas: el OCR redondea distinto y
la cuota baila un céntimo. Como el criterio comparaba importes exactos, esas
parejas quedaban en grupos separados y no se marcaban. Ahora se admite un margen
de 0,05 € (`analisis.TOL_DUP`).

No es un detalle menor: el duplicado más caro del 2T 2026 —TUC EXPRESS, 2.719,03 €
de IVA— se escapaba porque una copia decía 2.719,03 y la otra 2.719,02.

## Si cambian los ficheros de origen

Las columnas se localizan por nombre, tolerando acentos y mayúsculas, y cada
destino admite varios nombres de origen. Si falta alguna obligatoria, el sistema
para y dice cuál y en qué fichero, en vez de adivinar. El esquema está en
`cuadre/lectura.py`, en `COLS_A3` y `COLS_BILKY`.

Si aparece un patrón nuevo de nombre de fichero, se añade a `_PATRONES_EMP` en
ese mismo módulo.

## Histórico

Cada ejecución se archiva en **PostgreSQL**. Se guardan las líneas de los dos
libros, las duplicadas con su veredicto, los descuadres y los avisos. Un
trimestre son unas 68.000 líneas.

El motor se levanta con Docker:

```bash
docker compose up -d db
```

La conexión se indica con la variable `CUADRE_BD`, en formato
`postgresql://usuario:clave@host:puerto/base`. Copia `.env.example` a `.env`
para tenerla a mano. El puerto publicado es el **5433** y no el 5432, para no
chocar con un PostgreSQL que ya esté instalado en la máquina.

Si vuelves a cargar un trimestre que ya estaba, **sustituye** al anterior: se
entiende que el export nuevo corrige al viejo. Para quitar uno, en la pestaña
*Histórico* > *Mantenimiento*.

Desde línea de comandos se archiva con `--bd`, y `--ruta-bd` acepta otro DSN.

> Los importes van en `DOUBLE PRECISION`, no en `REAL`. En SQLite `REAL` son 8
> bytes, pero en PostgreSQL son 4 y solo guardan unos 6 dígitos significativos:
> una cuota de 2.216.121,79 € se redondearía sola.

> Y las fechas se guardan como texto en ISO, `aaaa-mm-dd`, en **todas** las
> tablas. Se filtran comparando texto, así que basta con que una las escriba en
> `dd/mm/aaaa` para que su filtro por rango devuelva cero sin decir nada. Le pasó
> a la tabla de duplicadas y hay una comprobación en la regresión para que no
> vuelva a pasar.

### Dos fechas que no son la misma

- **fecha de factura** — la de expedición
- **trimestre** — aquel en cuyo libro se declaró

No coinciden siempre: este trimestre hay 1.912 líneas en el libro del 2T con
fecha de otro periodo, lo normal en facturas recibidas con retraso. El filtro por
rango va por fecha de factura; el filtro de trimestres acota lo otro. Combinados
responden a las dos preguntas.

### Lo que solo se ve con histórico

La pestaña *Entre trimestres* busca la misma factura declarada en el libro de A3
de dos trimestres distintos. Es un riesgo que ningún informe de un solo trimestre
puede detectar. Se excluyen los números que no identifican la factura —el caso
MAKRO—, porque si no darían falsos positivos en cada trimestre.

También hay un resumen de qué sociedades repiten duplicadas trimestre tras
trimestre, que es lo que distingue un despiste puntual de un problema de proceso.

## La API

```bash
docker compose up -d db
uvicorn api.main:app --reload
```

La documentación interactiva queda en `http://localhost:8000/docs`.

Un cuadre tarda unos 30 segundos, así que no cabe en una petición síncrona: se
suben los libros, la API responde **202** con el id del trabajo, y el cliente
pregunta luego por el estado.

```
POST   /api/cuadres                        sube los libros y encola
GET    /api/cuadres/{id}                   estado, paso actual, resumen y avisos
GET    /api/cuadres/{id}/resultado         el análisis completo en JSON
GET    /api/cuadres/{id}/ficheros          los tres generados
GET    /api/cuadres/{id}/ficheros/{clave}  descarga uno: excel|comparativa|duplicadas
GET    /api/historico/…                    periodos, líneas, duplicadas, descuadres
DELETE /api/historico/{periodo}            quita un trimestre
GET    /api/salud                          para el healthcheck
```

El resultado en JSON lleva lo mismo que pintan los dos informes, así que el
frontend puede dibujarlo a su manera o limitarse a ofrecer la descarga. Los tres
ficheros pesan unos 450 KB en total y se guardan en la propia base: así no hace
falta un volumen compartido entre contenedores y borrarlos es un `DELETE`.

Los cuadres corren en un pool de hilos dentro del proceso de la API, con el
estado en PostgreSQL para que sobreviva a un reinicio. Da para varias personas
del despacho a la vez, que es el caso; con varias réplicas de la API haría falta
una cola de verdad.

Los libros de un cliente no se quedan en el servidor para siempre:
`POST /api/mantenimiento/limpieza` tira los cuadres de más de 30 días
(`CUADRE_RETENCION_DIAS`) y marca como fallidos los que se quedaron colgados.

## El frontend

```bash
cd web
npm install
npm run dev
```

Se abre en `http://localhost:5173`. Necesita la API en marcha; el servidor de
desarrollo hace de proxy hacia ella, así que el código usa siempre rutas
relativas y en producción vale igual detrás de nginx.

Si esos puertos están ocupados —pasa— se cambian por entorno:

```bash
CUADRE_WEB_PUERTO=5180 CUADRE_API=http://127.0.0.1:8010 npm run dev
```

Es React sin TypeScript y sin librería de componentes: las únicas dependencias
son `react`, `react-dom` y `react-router-dom`. La gráfica de cuota por mes está
hecha con CSS: una librería de gráficas serían 200 KB más de bundle y otra
dependencia que mantener, por un solo gráfico. El CSS reutiliza los mismos
tokens que `cuadre/plantillas/base.html` —colores, tipografías, tema claro y
oscuro— para que la interfaz y los informes que genera parezcan lo que son: la
misma herramienta.

    web/src/api.js        único punto por el que se habla con la API
    web/src/formato.js    euros y fechas a la española
    web/src/paginas/      Entrar · NuevoCuadre · Resultado · Histórico · Cuenta

En el histórico se consulta por rango de fechas, trimestre, sociedad y libro, y
lo consultado se lleva a un Excel de cinco hojas o a un CSV. Los agregados se
calculan en el servidor: un rango de un trimestre son ~68.000 líneas y mandarlas
enteras para pintar cuatro cifras no tendría sentido.

La pantalla de resultado ofrece las dos cosas a la vez, y ya se decidirá con qué
quedarse: las tablas pintadas desde el JSON, y los informes HTML enteros
incrustados y descargables.

## Entrar

La aplicación pide usuario y contraseña. **No hay permisos: quien entra ve y
hace todo.** La cuenta existe para saber quién hizo cada cosa y para que esto no
quede abierto en internet, no para repartir capacidades.

Las cuentas se crean en el servidor, que es donde está la base:

```bash
python gestion_usuarios.py crear victor "Victor Cisneros"
python gestion_usuarios.py listar
python gestion_usuarios.py clave victor
python gestion_usuarios.py desactivar victor
```

La contraseña se teclea al vuelo y no se pasa como argumento: un argumento queda
en el historial del shell y en la lista de procesos.

Unas cuantas decisiones que conviene conocer antes de tocar nada:

- La sesión viaja en una **cookie httpOnly**, no en un token guardado por el
  navegador. Es la diferencia entre que un fallo de XSS sea una molestia o sea el
  robo de la sesión.
- La contraseña se guarda con **scrypt** (biblioteca estándar, una dependencia
  menos que parchear). Cifrar tarda ~130 ms: imperceptible al entrar, caro de
  repetir millones de veces para quien se lleve la tabla.
- De la sesión se guarda el **sha256 del testigo**, no el testigo. Quien copie la
  base no se lleva con ella las sesiones abiertas.
- Entrar mal da **el mismo mensaje** tanto si el usuario no existe como si la
  contraseña está mal: distinguirlos diría qué nombres son reales.
- Cambiar la contraseña **cierra todas las sesiones**, que es lo que se espera
  cuando se cambia porque se sospecha que alguien la sabe.

En el VPS hay que poner `CUADRE_COOKIE_SEGURA=1` para que la cookie viaje solo
por https.

> Como no hay permisos, **cualquiera con cuenta puede borrar un trimestre del
> histórico**. Queda en el log de quién fue, pero no hay vuelta atrás. Si algún
> día molesta, es el primer sitio donde poner una distinción.

### El orden de las líneas

Las líneas del histórico salen ordenadas por

    fecha, sociedad, NIF del proveedor, número normalizado, libro, tipo de IVA

y cada pieza está ahí por un motivo concreto:

- **Por NIF del proveedor, no por nombre.** Las empresas cambian de nombre y el
  NIF no: la misma `A17371758` es *MIQUEL ALIMENTACIO GRUP SAU* en A3 y
  *TRANSGOURMET IBERICA SA* en Bilky. Ordenando por nombre, las dos caras de
  cada factura acababan en extremos opuestos de la tabla.
- **Por el número normalizado**, que es el que empareja los dos libros. A3
  guarda `2139041133` y Bilky `250212139041133`; al aplicar la regla de truncado
  los dos dan lo mismo. Vale igual para los que llevan `/`, `.` o `,`.
- **A3 antes que Bilky**, que sale solo del alfabeto.
- **Los tipos de menor a mayor**: 4 %, 10 %, 21 %.

La fecha va primero para no perder el recorrido cronológico. Separa las
facturas que tienen fecha distinta en cada libro —32 de 21.411 en el 2T 2026—
y ésas son justo las que conviene mirar.

## Los contenedores

    Dockerfile          la API, sobre python:3.12.10-slim
    web/Dockerfile      compila con Node y sirve con nginx
    web/nginx.conf      el proxy hacia la API y la ruta de la SPA
    docker-compose.yml  los tres servicios

Unas cuantas cosas que conviene saber antes de tocarlos:

- **La versión de Python va clavada**, igual que las librerías, y por el mismo
  motivo: un cambio de versión puede mover un redondeo sin avisar.
- **La imagen del frontend no lleva Node.** Se compila en una etapa y en la
  final solo quedan los estáticos y nginx: unos 50 MB en vez de 400.
- **La API corre con un solo worker**, a propósito. Los cuadres van en un pool
  de hilos dentro del proceso y cada uno atiende solo los trabajos que ha
  aceptado él; con varios workers, un trabajo lanzado en uno sería invisible
  para los demás. Para atender más a la vez se sube `CUADRE_TRABAJADORES`, no
  el número de workers.
- **La API no corre como root**, por si alguien se cuela por la aplicación.
- **Las cabeceras de seguridad van repetidas en cada `location`** del nginx. No
  es descuido: en nginx un `add_header` dentro de un bloque *anula* todos los
  heredados del padre. Ponerlas solo arriba hace que no lleguen donde hay otras,
  y es un fallo que no se ve —la configuración parece correcta y las cabeceras
  simplemente no están—.
- **`client_max_body_size` tiene que coincidir con `CUADRE_MAX_SUBIDA_MB`**, o
  nginx cortaría la subida antes de que la API pueda decir nada.
- El `.dockerignore` deja fuera `problemas/`, `datos/` y cualquier `.xlsx`: los
  libros de clientes no entran en ninguna imagen.

### Mantenimiento

```bash
docker compose logs -f api                  # qué está pasando
docker compose exec api python gestion_usuarios.py listar
docker compose exec db pg_dump -U cuadre cuadre > copia.sql
docker compose pull && docker compose up -d --build   # actualizar
```

La limpieza de cuadres viejos se ejecuta al arrancar la API. Para forzarla,
`POST /api/mantenimiento/limpieza`, que es lo que llamarías desde un cron.

## Tests

Son tres, y hacen cosas distintas. Pásalos los tres después de tocar el código.

```bash
docker compose up -d db
python tests/test_basico.py
```

Los dos tests archivan en el histórico, así que necesitan el motor levantado.
Cada uno crea y tira su propia base desechable (`cuadre_test_basico`,
`cuadre_test_regresion`, `cuadre_test_interfaz`), para no arrastrar datos de una
ejecución a la siguiente.

85 comprobaciones sobre un juego de datos inventado que se genera solo. No
necesita ficheros de ningún cliente, así que corre en cualquier equipo y sirve
para estrenar una máquina o para validar una subida de versión de las librerías.
El juego es pequeño pero pasa por todos los caminos: factura común, número
truncado, solo en A3, solo en Bilky, diferencia de importe, rectificativa
huérfana, duplicada real, falso duplicado por colisión y fichero descartado. Las
cifras esperadas están calculadas a mano en la cabecera del fichero.

Un segundo juego cubre los avisos que no dependen de A3, cada uno reproduciendo
en pequeño un caso real: la duplicada que solo se ve en Bilky y que se partía por
un céntimo, la misma factura en dos sociedades, el tipo de IVA inexistente, el
número que no coincide entre libros y el fichero importado sin coma decimal.

```bash
python tests/test_regresion.py
```

El 2T 2026 está revisado a mano, así que sirve de referencia. Comprueba 61 cifras
conocidas —la diferencia de 74.318,31 €, las 54 duplicadas con su veredicto, los
18 duplicados que solo se ven en Bilky con sus 5.123,81 € de IVA, las 7
colisiones de número, y que el histórico archiva y sustituye bien—. Cubre los dos
caminos de entrada, el del CLI (rutas) y el de la interfaz (ficheros subidos),
porque no son el mismo código. Necesita los ficheros del trimestre: se buscan en
`CUADRE_DATOS` o en la ruta por defecto de OneDrive.

```bash
python tests/test_api.py
```

Recorre la API entera con el juego inventado: subir, esperar, leer el JSON,
descargar los tres ficheros, consultar el histórico y borrar. Comprueba también
lo que tiene que fallar —extensión no admitida, cuadre inexistente, un libro con
las columnas de otro— y que falle con el código correcto y no con un 500.

El primero dice si el motor funciona; el segundo, si las cifras son las buenas;
el tercero, si la capa HTTP no se pierde nada por el camino. Ninguno sustituye a
los otros.

### Versiones de las librerías

Están fijadas exactamente en `requirements.txt`, no con `>=`. Las cifras se
declaran a Hacienda y un cambio de versión de pandas puede mover un redondeo sin
avisar. Para subir alguna: cambia el número, pasa los dos tests, y sube el cambio
solo si los dos siguen en verde.

## Estructura

    cuadre/
      lectura.py     lee los dos Excel y valida las columnas
      normaliza.py   la regla de truncado y su verificación
      analisis.py    cotejo, conciliación, duplicadas y detecciones
      informes.py    Excel y renderizado de plantillas
      bd.py          histórico en SQLite y consultas por rango
      pipeline.py    orquestación y avisos
      exporta.py     el histórico a Excel y CSV
      trabajos.py    cola de cuadres y ficheros generados
      usuarios.py    cuentas y sesiones
      plantillas/    base.html + los dos informes
    api/             la API HTTP (FastAPI)
    Dockerfile       imagen de la API
    web/             el frontend (React + Vite)
    app.py           interfaz web local
    paginas.py       pestaña de histórico
    cuadre_cli.py    línea de comandos
    gestion_usuarios.py  alta y baja de cuentas
    docker-compose.yml  los tres servicios
    DESPLIEGUE.md    cómo subirlo al VPS compartido
    despliegue/      el vhost de nginx para el proxy del VPS
    tests/           test_basico.py (datos inventados) y test_regresion.py (2T 2026)

## Alcance

Solo **IVA soportado** (facturas recibidas). Para el repercutido haría falta ver
un export de cada sistema, porque los campos no son los mismos.
