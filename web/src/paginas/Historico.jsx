import { useEffect, useState } from 'react'
import { historico, listaCuadres } from '../api.js'
import { ent, eur, fecha, pct, tipo } from '../formato.js'
import Tabla from '../componentes/Tabla.jsx'

export default function Historico() {
  const [pestana, setPestana] = useState('trimestres')
  const [resumen, setResumen] = useState(null)
  const [entre, setEntre] = useState(null)
  const [evolucion, setEvolucion] = useState(null)
  const [cuadres, setCuadres] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([historico.resumen(), listaCuadres(20)])
      .then(([r, c]) => { setResumen(r); setCuadres(c) })
      .catch((e) => setError(e.message))
  }, [])

  // Lo de entre trimestres es una consulta cara: solo se pide si se mira.
  useEffect(() => {
    if (pestana === 'entre' && entre === null) {
      historico.entrePeriodos().then(setEntre).catch((e) => setError(e.message))
    }
    if (pestana === 'evolucion' && evolucion === null) {
      historico.evolucion().then(setEvolucion).catch((e) => setError(e.message))
    }
  }, [pestana, entre, evolucion])

  if (error) {
    return <section className="error-caja"><strong>No se ha podido leer el histórico.</strong>
      <div className="small" style={{ marginTop: 4 }}>{error}</div></section>
  }
  if (!resumen) return <p className="cargando">Cargando…</p>

  return (
    <>
      <section>
        <p className="sec-label">Histórico</p>
        <h2>Lo que se ha ido archivando</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          Cada cuadre archivado guarda las líneas de los dos libros, las duplicadas
          con su veredicto y los descuadres. Eso permite mirar cosas que ningún
          trimestre suelto puede ver.
        </p>
      </section>

      <div className="pestanas">
        {[['trimestres', 'Trimestres'], ['entre', 'Entre trimestres'],
          ['evolucion', 'Sociedades que repiten'], ['cuadres', 'Últimos cuadres']].map(([k, t]) => (
          <button key={k} className={pestana === k ? 'activa' : ''} onClick={() => setPestana(k)}>{t}</button>
        ))}
      </div>

      {pestana === 'trimestres' && (
        <Tabla
          columnas={[
            { clave: 'periodo', titulo: 'Periodo' },
            { clave: 'ejecutado_en', titulo: 'Cargado', pinta: (f) => fecha(f.ejecutado_en) },
            { clave: 'sociedades', titulo: 'Sociedades', n: true },
            { clave: 'lineas_a3', titulo: 'Líneas A3', n: true, pinta: (f) => ent(f.lineas_a3) },
            { clave: 'lineas_bilky', titulo: 'Líneas Bilky', n: true, pinta: (f) => ent(f.lineas_bilky) },
            { clave: 'dif_cuota', titulo: 'Diferencia', n: true, pinta: (f) => eur(f.dif_cuota) },
            { clave: 'cuadra', titulo: '', pinta: (f) => (
              <span className={`pastilla ${f.cuadra ? 'no' : 'corregir'}`}>
                {f.cuadra ? 'cuadra' : 'no cuadra'}
              </span>) },
            { clave: 'duplicadas_accion', titulo: 'Duplicadas', n: true },
            { clave: 'tasa_regla', titulo: 'Truncado', n: true, pinta: (f) => pct(f.tasa_regla) },
          ]}
          filas={resumen}
          vacio="Todavía no se ha archivado ningún trimestre." />
      )}

      {pestana === 'entre' && (
        <>
          <h3>La misma factura declarada en dos trimestres</h3>
          <p className="muted small">
            Es el riesgo que ningún informe de un trimestre suelto puede detectar. Se
            excluyen los números que no identifican la factura, que si no darían falsos
            positivos en cada trimestre.
          </p>
          {entre === null ? <p className="cargando">Buscando…</p> : (
            <Tabla
              columnas={[
                { clave: 'emp', titulo: 'Sociedad', mono: true },
                { clave: 'sociedad', titulo: '' },
                { clave: 'proveedor', titulo: 'Proveedor' },
                { clave: 'num_clave', titulo: 'Nº factura', mono: true },
                { clave: 'periodos', titulo: 'Trimestres' },
                { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
                { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
                { clave: 'iva_repetido', titulo: 'IVA repetido', n: true, pinta: (f) => eur(f.iva_repetido) },
              ]}
              filas={entre} limite={60}
              vacio="Ninguna factura aparece en dos trimestres. Hace falta más de un trimestre archivado para que esto diga algo." />
          )}
        </>
      )}

      {pestana === 'evolucion' && (
        <>
          <h3>Sociedades que repiten duplicadas trimestre tras trimestre</h3>
          <p className="muted small">
            Es lo que distingue un despiste puntual de un problema de proceso.
          </p>
          {evolucion === null ? <p className="cargando">Cargando…</p> : (
            <Tabla
              columnas={[
                { clave: 'emp', titulo: 'NIF', mono: true },
                { clave: 'sociedad', titulo: 'Sociedad' },
                { clave: 'trimestres', titulo: 'Trimestres', n: true },
                { clave: 'periodos', titulo: 'Cuáles' },
                { clave: 'facturas', titulo: 'Facturas', n: true },
                { clave: 'iva', titulo: 'IVA', n: true, pinta: (f) => eur(f.iva) },
              ]}
              filas={evolucion}
              vacio="Nada archivado todavía." />
          )}
        </>
      )}

      {pestana === 'cuadres' && (
        <Tabla
          columnas={[
            { clave: 'creado_en', titulo: 'Lanzado', pinta: (f) => fecha(f.creado_en) },
            { clave: 'periodo', titulo: 'Periodo', pinta: (f) => f.periodo || '—' },
            { clave: 'estado', titulo: 'Estado', pinta: (f) => (
              <span className={`pastilla ${f.estado === 'hecho' ? 'no' : f.estado === 'fallido' ? 'corregir' : 'revisar'}`}>
                {f.estado}
              </span>) },
            { clave: 'paso', titulo: 'Detalle', pinta: (f) => f.error || f.paso },
            { clave: 'id', titulo: '', pinta: (f) => f.estado === 'hecho'
                ? <a href={`/cuadres/${f.id}`}>Ver</a> : null },
          ]}
          filas={cuadres || []}
          vacio="Todavía no se ha lanzado ningún cuadre." />
      )}
    </>
  )
}
