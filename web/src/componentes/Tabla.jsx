import { useMemo, useState } from 'react'

// Tabla mínima: columnas declaradas como {clave, titulo, n?, mono?, pinta?}.
// Se ordena pinchando en la cabecera: una vez ascendente, otra descendente, y
// a la tercera vuelve al orden con el que vino del servidor. Con
// `ordena: false` una columna deja de responder al clic.

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

  if (!filas?.length) return <p className="muted small">{sinNada}</p>

  // Recortar DESPUÉS de ordenar: al revés se ordenarían solo las primeras y
  // parecería que el listado está ordenado cuando no lo está.
  const vistas = limite ? ordenadas.slice(0, limite) : ordenadas

  function pincha(c) {
    if (c.ordena === false) return
    setOrden((o) => {
      if (!o || o.clave !== c.clave) return { clave: c.clave, desc: false }
      return o.desc ? null : { clave: c.clave, desc: true }
    })
  }

  return (
    <>
      <div className="tw">
        <table>
          <thead>
            <tr>
              {columnas.map((c) => {
                const activa = orden && orden.clave === c.clave
                const puede = c.ordena !== false
                return (
                  <th key={c.clave}
                      className={[c.n ? 'n' : '', puede ? 'ord' : '', activa ? 'activa' : ''].join(' ').trim()}
                      onClick={() => pincha(c)}
                      title={puede ? 'Ordenar por esta columna' : undefined}>
                    {c.titulo}
                    {activa && <span className="flecha">{orden.desc ? '▼' : '▲'}</span>}
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
      {limite && filas.length > limite && (
        <p className="small muted" style={{ marginTop: 8 }}>
          Se muestran {limite} de {filas.length}
          {orden ? ', ordenadas por esta pantalla' : ''}. El listado completo está en el Excel.
        </p>
      )}
    </>
  )
}
