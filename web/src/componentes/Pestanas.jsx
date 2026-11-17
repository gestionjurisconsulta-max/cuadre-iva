import { useRef } from 'react'

// Pestañas con el patrón ARIA de verdad: una tablist de tabs y un solo tabpanel
// cuyo contenido cambia. Roving tabindex y flechas para recorrerlas con el
// teclado, para que el lector de pantalla las anuncie como pestañas y no como
// una fila de botones sueltos.
//
//   opciones: [[clave, etiqueta], ...]   valor/cambia: la pestaña activa
//   etiqueta: nombre de la tablist       base: prefijo de los id (res, hist…)
//
// El tabpanel lo pone la página: un <div role="tabpanel" id={`${base}-panel`}
// aria-labelledby={`${base}-tab-${valor}`}> alrededor del contenido.
export default function Pestanas({ opciones, valor, cambia, etiqueta, base = 'p' }) {
  const refs = useRef({})

  function alTeclado(e, i) {
    const n = opciones.length
    let j = null
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % n
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + n) % n
    else if (e.key === 'Home') j = 0
    else if (e.key === 'End') j = n - 1
    else return
    e.preventDefault()
    const k = opciones[j][0]
    cambia(k)
    refs.current[k]?.focus()
  }

  return (
    <div className="pestanas" role="tablist" aria-label={etiqueta}>
      {opciones.map(([k, t], i) => {
        const activa = valor === k
        return (
          <button key={k} type="button" role="tab" id={`${base}-tab-${k}`}
                  aria-selected={activa} aria-controls={`${base}-panel`}
                  tabIndex={activa ? 0 : -1}
                  ref={(el) => { refs.current[k] = el }}
                  className={activa ? 'activa' : ''}
                  onClick={() => cambia(k)}
                  onKeyDown={(e) => alTeclado(e, i)}>
            {t}
          </button>
        )
      })}
    </div>
  )
}
