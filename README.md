# Cuadre de IVA · A3 contra Bilky

Sube los dos libros de IVA soportado de un trimestre y genera el Excel de trabajo
y los dos informes. Todo se ejecuta en este equipo: los ficheros no salen de aquí.

## Uso

Doble clic en **`cuadre-iva.bat`**. Se abre en el navegador, arrastras los
ficheros de cada sistema y pulsas *Generar informes*.

Desde línea de comandos, con carpetas:

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
  IVA de 2.100 %. Invalida el cuadre entero, así que se avisa como grave y lo
  primero de todo
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

Cada ejecución se archiva en `datos/cuadre.db` (SQLite, sin servidor). Se guardan
las líneas de los dos libros, las duplicadas con su veredicto, los descuadres y
los avisos. Un trimestre ocupa unos 23 MB, así que son ~90 MB al año.

Si vuelves a cargar un trimestre que ya estaba, **sustituye** al anterior: se
entiende que el export nuevo corrige al viejo. Para quitar uno, en la pestaña
*Histórico* > *Mantenimiento*.

Desde línea de comandos se archiva con `--bd`, y `--ruta-bd` cambia el fichero.
También lo cambia la variable de entorno `CUADRE_BD`.

> Ponlo en disco local, no en una carpeta sincronizada de OneDrive. SQLite y la
> sincronización en la nube se llevan mal: si dos equipos escriben a la vez, el
> fichero se corrompe.

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

## Tests

Son dos, y hacen cosas distintas. Pásalos los dos después de tocar el código.

```bash
python tests/test_basico.py
```

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

El primero dice si el motor funciona; el segundo, si las cifras son las buenas.
Ninguno sustituye al otro.

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
      plantillas/    base.html + los dos informes
    app.py           interfaz web local
    paginas.py       pestaña de histórico
    cuadre_cli.py    línea de comandos
    datos/cuadre.db  el histórico (se crea solo)
    tests/           test_basico.py (datos inventados) y test_regresion.py (2T 2026)

## Alcance

Solo **IVA soportado** (facturas recibidas). Para el repercutido haría falta ver
un export de cada sistema, porque los campos no son los mismos.
