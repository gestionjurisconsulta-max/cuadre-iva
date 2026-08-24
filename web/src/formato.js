// Las cifras se declaran a Hacienda: se escriben como en España, con la coma
// decimal y el punto de millares, y siempre con dos decimales.
// useGrouping:'always' a propósito: en español Intl no separa los millares de
// los números de cuatro dígitos, y escribiría 4879,20 donde el informe pone
// 4.879,20. Las dos cifras salen de la misma herramienta y tienen que leerse igual.
const EUR = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: 'always',
})
const ENT = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0, useGrouping: 'always' })

export const eur = (v) => (v === null || v === undefined || Number.isNaN(v) ? '—' : EUR.format(v))
export const ent = (v) => (v === null || v === undefined ? '—' : ENT.format(v))
export const pct = (v) => `${(100 * v).toFixed(1).replace('.', ',')} %`

// El tipo de IVA se escribe sin decimales cuando es entero: 21 %, no 21,0 %.
export const tipo = (v) =>
  `${Number.isInteger(v) ? v : String(v).replace('.', ',')} %`

export const fecha = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export const kb = (bytes) => `${Math.round(bytes / 1024)} KB`
