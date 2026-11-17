import { useEffect, useMemo, useRef, useState } from 'react'

// Tabla mínima: columnas declaradas como {clave, titulo, n?, mono?, pinta?}.
// Se ordena pinchando --o tabulando hasta la cabecera y pulsando Enter-- en el
// título: una vez ascendente, otra descendente, y a la tercera vuelve al orden
// con el que vino del servidor. Con `ordena: false` una columna deja de
// responder al clic.

function vacio(v) {
  return v === null || v === undefined || v === ''
}

function compara(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' || typeof b === 'boolean') return (a ? 1 : 0) - (b ? 1 : 0)
  // `numeric` para que «10» vaya después de «9» y no antes, que es lo que pasa
  // comparando como texto y desordena cualquier columna de números de factura.
  return String(a).localeCompare(String(b), 'es', { numeric: true, sensitivity: 'base' })
}

export default function Tabla({ columnas, filas, vacio: sinNada = 'Nada que mostrar.', limite }) {
  const [orden, setOrden] = useState(null)      // {clave, desc}
  const tw = useRef(null)
  // Aviso de que la tabla sigue a la derecha: en doce columnas, el scroll
  // horizontal no se ve venir si nada lo anuncia.
  const [masDerecha, setMasDerecha] = useState(false)

  const ordenadas = useMemo(() => {
    if (!orden || !filas?.length) return filas
    const k = orden.clave
    const signo = orden.desc ? -1 : 1
    // sort() es estable, así que al ordenar por sociedad cada una conserva
    // dentro el orden que traía del servidor --por importe--. Eso es lo que
    // hace útil ordenar por sociedad: salen agrupadas y ya priorizadas.
    return [...filas].sort((x, y) => {
      const a = x[k], b = y[k]
      const ea = vacio(a), eb = vacio(b)
      if (ea && eb) return 0
      if (ea) return 1                          // los huecos, siempre al final
      if (eb) return -1
      return signo * compara(a, b)
    })
  }, [filas, orden])

  // Recortar DESPUÉS de ordenar: al revés se ordenarían solo las primeras y
  // parecería que el listado está ordenado cuando no lo está.
  const vistas = limite ? (ordenadas || []).slice(0, limite) : ordenadas

  // Mira si el contenido se sale por la derecha para encender (o apagar) la
  // sombra del borde. Se recalcula al desplazar, al cambiar de tamaño la
  // ventana y cuando cambian las filas o las columnas.
  useEffect(() => {
    const el = tw.current
    if (!el) return
    const revisa = () => setMasDerecha(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
    revisa()
    el.addEventListener('scroll', revisa, { passive: true })
    window.addEventListener('resize', revisa)
    return () => {
      el.removeEventListener('scroll', revisa)
      window.removeEventListener('resize', revisa)
    }
  }, [vistas?.length, columnas.length])

  if (!filas?.length) return <p className="muted small">{sinNada}</p>

  function pincha(c) {
    if (c.ordena === false) return
    setOrden((o) => {
      if (!o || o.clave !== c.clave) return { clave: c.clave, desc: false }
      return o.desc ? null : { clave: c.clave, desc: true }
    })
  }

  return (
    <>
      <div className={`tabla-marco ${masDerecha ? 'masder' : ''}`}>
        <div className="tw" ref={tw}>
          <table>
            <thead>
              <tr>
                {columnas.map((c) => {
                  const activa = orden && orden.clave === c.clave
                  const puede = c.ordena !== false
                  // aria-sort anuncia al lector de pantalla por qué columna y en
                  // qué sentido está ordenado; en las no ordenables no se pone.
                  const aria = !puede ? undefined
                    : activa ? (orden.desc ? 'descending' : 'ascending') : 'none'
                  return (
                    <th key={c.clave} scope="col" aria-sort={aria}
                        className={[c.n ? 'n' : '', puede ? 'ord' : '', activa ? 'activa' : ''].join(' ').trim()}>
                      {puede ? (
                        <button type="button" className="orden" onClick={() => pincha(c)}
                                title="Ordenar por esta columna"
                                aria-label={c.titulo ? undefined : 'Ordenar por esta columna'}>
                          <span>{c.titulo}</span>
                          {activa && <span className="flecha" aria-hidden="true">{orden.desc ? '▼' : '▲'}</span>}
                        </button>
                      ) : c.titulo}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {vistas.map((f, i) => (
                <tr key={i}>
                  {columnas.map((c) => (
                    <td key={c.clave} className={[c.n ? 'n' : '', c.mono ? 'mono' : ''].join(' ').trim()}>
                      {c.pinta ? c.pinta(f) : f[c.clave]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {limite && filas.length > limite && (
        <p className="small muted" style={{ marginTop: 8 }}>
          Se muestran {limite} de {filas.length}
          {orden ? ', ordenadas por esta pantalla' : ''}. El listado completo está en el Excel.
        </p>
      )}
    </>
  )
}
