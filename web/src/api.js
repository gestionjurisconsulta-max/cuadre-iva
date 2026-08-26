// Único punto por el que se habla con la API. En desarrollo Vite hace de proxy
// hacia el 8000; en producción el nginx sirve el frontend y pasa /api al backend,
// así que la ruta relativa vale en los dos sitios.
const BASE = '/api'

// Se dispara cuando la sesión caduca a media faena: App lo escucha y vuelve al
// login sin que nadie se quede mirando una pantalla que no carga.
export const SESION_CAIDA = 'cuadre:sesion-caida'

async function pide(ruta, opciones = {}) {
  // credentials:'include' para que viaje la cookie de sesión.
  const r = await fetch(BASE + ruta, { credentials: 'include', ...opciones })
  if (r.status === 401 && !ruta.startsWith('/auth/')) {
    window.dispatchEvent(new Event(SESION_CAIDA))
    throw new Error('Se ha cerrado la sesión.')
  }
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

export const entrar = (usuario, clave) =>
  pide('/auth/entrar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ usuario, clave }),
  })
export const salir = () => pide('/auth/salir', { method: 'POST' })
export const yo = () => pide('/auth/yo')
export const cambiaClave = (actual, nueva) =>
  pide('/auth/clave', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actual, nueva }),
  })

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
export const urlZip = (id) => `${BASE}/cuadres/${id}/ficheros.zip`

// Los filtros del histórico viajan igual en todas las consultas. Las listas
// --trimestres y sociedades-- van repitiendo el parámetro, que es como las
// espera FastAPI.
function consulta({ desde, hasta, libro, periodos, emps } = {}) {
  const q = new URLSearchParams()
  if (desde) q.set('desde', desde)
  if (hasta) q.set('hasta', hasta)
  if (libro && libro !== 'Ambos') q.set('libro', libro)
  ;(periodos || []).forEach((p) => q.append('periodos', p))
  ;(emps || []).forEach((e) => q.append('emps', e))
  return q
}

export const urlExportar = (formato, filtros) =>
  `${BASE}/historico/exportar.${formato}?${consulta(filtros)}`

export const historico = {
  periodos: () => pide('/historico/periodos'),
  rango: () => pide('/historico/rango'),
  resumenFiltrado: (f) => pide('/historico/resumen-filtrado?' + consulta(f)),
  lineas: (f, limite = 3000) => pide(`/historico/lineas?${consulta(f)}&limite=${limite}`),
  resumen: () => pide('/historico/resumen'),
  sociedades: () => pide('/historico/sociedades'),
  duplicadas: (f = {}) => pide('/historico/duplicadas?' + consulta(f)),
  descuadres: (f = {}) => pide('/historico/descuadres?' + consulta(f)),
  entrePeriodos: (f = {}) => pide('/historico/entre-periodos?' + consulta(f)),
  sospechosos: () => pide('/historico/sospechosos'),
  evolucion: () => pide('/historico/evolucion'),
  borra: (periodo) => pide(`/historico/${encodeURIComponent(periodo)}`, { method: 'DELETE' }),
}
