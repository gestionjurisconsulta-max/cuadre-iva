// Único punto por el que se habla con la API. En desarrollo Vite hace de proxy
// hacia el 8000; en producción el nginx sirve el frontend y pasa /api al backend,
// así que la ruta relativa vale en los dos sitios.
const BASE = '/api'

async function pide(ruta, opciones = {}) {
  const r = await fetch(BASE + ruta, opciones)
  if (!r.ok) {
    // La API devuelve {detalle} en los errores de lectura y {detail} en los de
    // FastAPI. Se prueban los dos antes de rendirse al código de estado.
    let mensaje = `Error ${r.status}`
    try {
      const cuerpo = await r.json()
      mensaje = cuerpo.detalle || cuerpo.detail || mensaje
    } catch { /* respuesta sin JSON */ }
    throw new Error(mensaje)
  }
  return r.status === 204 ? null : r.json()
}

export const salud = () => pide('/salud')

export function creaCuadre({ a3, bilky, periodo, archivar }) {
  const datos = new FormData()
  a3.forEach((f) => datos.append('a3', f))
  bilky.forEach((f) => datos.append('bilky', f))
  const q = new URLSearchParams()
  if (periodo) q.set('periodo', periodo)
  q.set('archivar', archivar ? 'true' : 'false')
  return pide(`/cuadres?${q}`, { method: 'POST', body: datos })
}

export const estadoCuadre = (id) => pide(`/cuadres/${id}`)
export const resultadoCuadre = (id) => pide(`/cuadres/${id}/resultado`)
export const ficherosCuadre = (id) => pide(`/cuadres/${id}/ficheros`)
export const listaCuadres = (limite = 20) => pide(`/cuadres?limite=${limite}`)
export const borraCuadre = (id) => pide(`/cuadres/${id}`, { method: 'DELETE' })

export const urlFichero = (id, clave, incrustado = false) =>
  `${BASE}/cuadres/${id}/ficheros/${clave}${incrustado ? '?incrustado=true' : ''}`

export const historico = {
  periodos: () => pide('/historico/periodos'),
  resumen: () => pide('/historico/resumen'),
  sociedades: () => pide('/historico/sociedades'),
  duplicadas: (p = {}) => pide('/historico/duplicadas?' + new URLSearchParams(p)),
  descuadres: (p = {}) => pide('/historico/descuadres?' + new URLSearchParams(p)),
  entrePeriodos: () => pide('/historico/entre-periodos'),
  evolucion: () => pide('/historico/evolucion'),
  borra: (periodo) => pide(`/historico/${encodeURIComponent(periodo)}`, { method: 'DELETE' }),
}
