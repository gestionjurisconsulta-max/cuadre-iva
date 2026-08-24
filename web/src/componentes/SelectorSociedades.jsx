import { useEffect, useMemo, useRef, useState } from 'react'

// Son 93 sociedades: una nube de fichas no se puede recorrer con la vista. Esto
// es un desplegable con buscador que filtra por nombre y por NIF, porque a veces
// se busca por uno y a veces por el otro.
export default function SelectorSociedades({ sociedades, elegidas, cambia }) {
  const [abierto, setAbierto] = useState(false)
  const [busca, setBusca] = useState('')
  const caja = useRef(null)
  const entrada = useRef(null)

  // Cerrar al pulsar fuera o con Escape: si no, el panel se queda abierto
  // tapando la tabla y hay que volver a buscar el botón para cerrarlo.
  useEffect(() => {
    if (!abierto) return
    const fuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierto(false) }
    const tecla = (e) => { if (e.key === 'Escape') setAbierto(false) }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', tecla)
    entrada.current?.focus()
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('keydown', tecla)
    }
  }, [abierto])

  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase()
    if (!q) return sociedades
    return sociedades.filter(
      (s) => (s.sociedad || '').toLowerCase().includes(q) || s.emp.toLowerCase().includes(q))
  }, [sociedades, busca])

  function alterna(emp) {
    cambia(elegidas.includes(emp) ? elegidas.filter((x) => x !== emp) : [...elegidas, emp])
  }

  const rotulo = elegidas.length === 0
    ? 'Todas las sociedades'
    : elegidas.length === 1
      ? (sociedades.find((s) => s.emp === elegidas[0])?.sociedad || elegidas[0])
      : `${elegidas.length} sociedades`

  return (
    <div className="selector" ref={caja}>
      <label className="small muted" htmlFor="soc-boton">Sociedades</label>
      <button id="soc-boton" type="button" className="selector-boton"
              aria-expanded={abierto} onClick={() => setAbierto(!abierto)}>
        <span className={elegidas.length ? '' : 'muted'}>{rotulo}</span>
        <span className="flecha">▾</span>
      </button>

      {abierto && (
        <div className="selector-panel">
          <input
            ref={entrada} type="text" value={busca} placeholder="Buscar por nombre o NIF…"
            onChange={(e) => setBusca(e.target.value)} />
          <div className="selector-lista">
            {filtradas.length === 0 && (
              <p className="small muted" style={{ padding: '10px 12px', margin: 0 }}>
                Ninguna sociedad coincide con «{busca}».
              </p>
            )}
            {filtradas.map((s) => (
              <label key={s.emp} className="selector-fila">
                <input type="checkbox" checked={elegidas.includes(s.emp)}
                       onChange={() => alterna(s.emp)} />
                <span className="nom">{s.sociedad || s.emp}</span>
                <span className="mono faint">{s.emp}</span>
              </label>
            ))}
          </div>
          <div className="selector-pie">
            <span className="small muted">
              {elegidas.length
                ? `${elegidas.length} de ${sociedades.length}`
                : `${filtradas.length} de ${sociedades.length}`}
            </span>
            {busca && filtradas.length > 0 && (
              <button type="button" className="enlace"
                      onClick={() => cambia([...new Set([...elegidas,
                                                         ...filtradas.map((s) => s.emp)])])}>
                Marcar las {filtradas.length} filtradas
              </button>
            )}
            {elegidas.length > 0 && (
              <button type="button" className="enlace" onClick={() => cambia([])}>
                Quitar selección
              </button>
            )}
          </div>
        </div>
      )}

      {/* Las elegidas se ven fuera del panel: si no, al cerrarlo no se sabe qué
          filtro está puesto sin volver a abrirlo. */}
      {elegidas.length > 0 && (
        <div className="etiquetas" style={{ marginTop: 8 }}>
          {elegidas.map((emp) => {
            const s = sociedades.find((x) => x.emp === emp)
            return (
              <button key={emp} className="ficha activa" onClick={() => alterna(emp)}
                      title={`${s?.sociedad || ''} · ${emp} — quitar`}>
                {s?.sociedad || emp} ×
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
