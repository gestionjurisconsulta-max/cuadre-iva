import { useCallback, useEffect, useState } from 'react'
import { historico, listaCuadres, urlExportar } from '../api.js'
import { ent, eur, fecha, pct, tipo } from '../formato.js'
import Tabla from '../componentes/Tabla.jsx'
import PorMes from '../componentes/PorMes.jsx'
import SelectorSociedades from '../componentes/SelectorSociedades.jsx'

const VEREDICTOS = {
  solo_a3: 'Corregir en A3', doc_repetido: 'Revisar en Bilky',
  sincontraste: 'Sin contraste', linea_repetida: 'Líneas idénticas', falso: 'No es duplicado',
}
const CLASES = { solo_a3: 'Solo en A3', solo_bilky: 'Solo en Bilky', importe: 'Importe distinto' }
const TOPE_TABLA = 3000

export default function Historico() {
  const [cargas, setCargas] = useState(null)
  const [periodos, setPeriodos] = useState([])
  const [sociedades, setSociedades] = useState([])
  const [error, setError] = useState(null)

  // Filtros
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [libro, setLibro] = useState('Ambos')
  const [trimestres, setTrimestres] = useState([])
  const [emps, setEmps] = useState([])

  const [resumen, setResumen] = useState(null)
  const [pestana, setPestana] = useState('lineas')
  const [datos, setDatos] = useState({})
  const [cargando, setCargando] = useState(false)

  const filtros = { desde, hasta, libro, periodos: trimestres, emps }

  useEffect(() => {
    Promise.all([historico.resumen(), historico.periodos(), historico.sociedades(), historico.rango()])
      .then(([c, p, s, r]) => {
        setCargas(c); setPeriodos(p); setSociedades(s)
        // Por defecto, todo lo que hay archivado.
        if (r.desde) setDesde(String(r.desde).slice(0, 10))
        if (r.hasta) setHasta(String(r.hasta).slice(0, 10))
      })
      .catch((e) => setError(e.message))
  }, [])

  const consulta = useCallback(async () => {
    setCargando(true)
    setError(null)
    try {
      setResumen(await historico.resumenFiltrado(filtros))
      setDatos({})            // lo de cada pestaña se pide al abrirla
    } catch (e) {
      setError(e.message)
    }
    setCargando(false)
  }, [desde, hasta, libro, trimestres.join(), emps.join()])

  // Primera consulta en cuanto se sabe el rango disponible.
  useEffect(() => { if (desde || hasta) consulta() }, [desde, hasta])

  // Cada pestaña pide lo suyo la primera vez que se abre.
  useEffect(() => {
    if (!resumen || datos[pestana] !== undefined) return
    const trae = {
      lineas: () => historico.lineas(filtros, TOPE_TABLA),
      duplicadas: () => historico.duplicadas(filtros),
      descuadres: () => historico.descuadres(filtros),
      entre: () => historico.entrePeriodos(filtros),
      sospechosos: () => historico.sospechosos(),
      evolucion: () => historico.evolucion(),
    }[pestana]
    trae?.().then((d) => setDatos((x) => ({ ...x, [pestana]: d }))).catch((e) => setError(e.message))
  }, [pestana, resumen, datos])

  function alterna(lista, pon, valor) {
    pon(lista.includes(valor) ? lista.filter((x) => x !== valor) : [...lista, valor])
  }

  if (error && !cargas) {
    return <section className="error-caja"><strong>No se ha podido leer el histórico.</strong>
      <div className="small" style={{ marginTop: 4 }}>{error}</div></section>
  }
  if (!cargas) return <p className="cargando">Cargando…</p>
  if (!cargas.length) {
    return (
      <section className="tarjeta">
        <h2>Todavía no hay nada archivado</h2>
        <p className="muted">
          Marca <strong>Archivar en el histórico</strong> al generar un cuadre y aparecerá aquí.
        </p>
      </section>
    )
  }

  const pestanas = [
    ['lineas', 'Líneas'],
    ['duplicadas', `Duplicadas${resumen ? ` (${resumen.duplicadas})` : ''}`],
    ['descuadres', `Descuadres${resumen ? ` (${resumen.descuadres})` : ''}`],
    ['entre', 'Entre trimestres'],
    ['sospechosos', 'Números sospechosos'],
    ['evolucion', 'Sociedades que repiten'],
    ['cuadres', 'Últimos cuadres'],
  ]

  return (
    <>
      <section>
        <p className="sec-label">Histórico</p>
        <h2>Trimestres archivados</h2>
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
            { clave: 'duplicadas_accion', titulo: 'A revisar', n: true },
            { clave: 'tasa_regla', titulo: 'Truncado', n: true, pinta: (f) => pct(f.tasa_regla) },
          ]}
          filas={cargas} />
      </section>

      <section className="tarjeta">
        <h3>Consultar y exportar</h3>
        <p className="small muted">
          El rango se aplica sobre la <strong>fecha de expedición de la factura</strong>. No es lo
          mismo que el trimestre en que se declaró: una factura de marzo puede estar en el libro
          del 2T. Con el filtro de trimestres acotas eso.
        </p>

        <div className="filtros">
          <div>
            <label className="small muted" htmlFor="desde">Desde</label>
            <input id="desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
          </div>
          <div>
            <label className="small muted" htmlFor="hasta">Hasta</label>
            <input id="hasta" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
          </div>
          <div>
            <label className="small muted" htmlFor="libro">Libro</label>
            <select id="libro" value={libro} onChange={(e) => setLibro(e.target.value)}>
              <option>Ambos</option><option>A3</option><option>BILKY</option>
            </select>
          </div>

          <SelectorSociedades sociedades={sociedades} elegidas={emps} cambia={setEmps} />
        </div>

        <div style={{ marginTop: 14 }}>
          <span className="small muted">Trimestres</span>
          <div className="etiquetas">
            {periodos.map((p) => (
              <button key={p} className={trimestres.includes(p) ? 'ficha activa' : 'ficha'}
                      onClick={() => alterna(trimestres, setTrimestres, p)}>{p}</button>
            ))}
          </div>
        </div>

        <button className="principal" onClick={consulta} disabled={cargando}
                style={{ marginTop: 16 }}>
          {cargando ? 'Consultando…' : 'Consultar'}
        </button>
        {(trimestres.length > 0 || emps.length > 0 || libro !== 'Ambos') && (
          <button className="secundaria" style={{ marginLeft: 10 }}
                  onClick={() => { setTrimestres([]); setEmps([]); setLibro('Ambos') }}>
            Quitar filtros
          </button>
        )}
      </section>

      {error && <section className="error-caja small">{error}</section>}

      {resumen && (
        <>
          <section className="metricas">
            <div className="metrica"><div className="rotulo">Líneas</div>
              <div className="cifra">{ent(resumen.lineas)}</div></div>
            <div className="metrica"><div className="rotulo">Cuota A3</div>
              <div className="cifra">{eur(resumen.cuota_a3)} €</div></div>
            <div className="metrica"><div className="rotulo">Cuota Bilky</div>
              <div className="cifra">{eur(resumen.cuota_bilky)} €</div></div>
            <div className="metrica"><div className="rotulo">Diferencia</div>
              <div className="cifra">{eur(resumen.diferencia)} €</div></div>
          </section>

          {resumen.lineas === 0 ? (
            <section className="tarjeta">
              <p className="muted" style={{ margin: 0 }}>No hay líneas en ese rango con esos filtros.</p>
            </section>
          ) : (
            <>
              <section>
                <div className="pestanas">
                  {pestanas.map(([k, t]) => (
                    <button key={k} className={pestana === k ? 'activa' : ''}
                            onClick={() => setPestana(k)}>{t}</button>
                  ))}
                </div>

                {pestana === 'lineas' && (
                  <>
                    <PorMes datos={resumen.por_mes} />
                    {datos.lineas === undefined ? <p className="cargando">Cargando líneas…</p> : (
                      <>
                        <Tabla
                          columnas={[
                            { clave: 'libro', titulo: 'Libro' },
                            { clave: 'periodo', titulo: 'Periodo' },
                            { clave: 'emp', titulo: 'Sociedad', mono: true },
                            { clave: 'proveedor', titulo: 'Proveedor' },
                            { clave: 'num', titulo: 'Nº factura', mono: true },
                            { clave: 'fecha', titulo: 'Fecha' },
                            { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
                            { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
                            { clave: 'cuota', titulo: 'Cuota', n: true, pinta: (f) => eur(f.cuota) },
                            { clave: 'total', titulo: 'Total', n: true, pinta: (f) => eur(f.total) },
                          ]}
                          filas={datos.lineas} />
                        {resumen.lineas > TOPE_TABLA && (
                          <p className="small muted" style={{ marginTop: 8 }}>
                            Mostrando {ent(TOPE_TABLA)} de {ent(resumen.lineas)} líneas.
                            La exportación las incluye todas.
                          </p>
                        )}
                      </>
                    )}
                  </>
                )}

                {pestana === 'duplicadas' && (
                  datos.duplicadas === undefined ? <p className="cargando">Cargando…</p> : (
                    <Tabla
                      columnas={[
                        { clave: 'veredicto', titulo: 'Veredicto', pinta: (f) => (
                          <span className={`pastilla ${f.veredicto === 'falso' ? 'no' : 'corregir'}`}>
                            {VEREDICTOS[f.veredicto] || f.veredicto}
                          </span>) },
                        { clave: 'periodo', titulo: 'Periodo' },
                        { clave: 'emp', titulo: 'Sociedad', mono: true },
                        { clave: 'proveedor', titulo: 'Proveedor' },
                        { clave: 'num_a3', titulo: 'Nº en A3', mono: true },
                        { clave: 'fechas', titulo: 'Fechas' },
                        { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
                        { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
                        { clave: 'sobrante', titulo: 'IVA repetido', n: true, pinta: (f) => eur(f.sobrante) },
                        { clave: 'enlace', titulo: '', ordena: false, pinta: (f) => f.enlace
                            ? <a href={f.enlace} target="_blank" rel="noreferrer">Bilky</a> : null },
                      ]}
                      filas={datos.duplicadas} limite={500}
                      vacio="Sin duplicadas en el rango." />
                  )
                )}

                {pestana === 'descuadres' && (
                  datos.descuadres === undefined ? <p className="cargando">Cargando…</p> : (
                    <Tabla
                      columnas={[
                        { clave: 'clase', titulo: 'Clase', pinta: (f) => (
                          <span className="pastilla revisar">{CLASES[f.clase] || f.clase}</span>) },
                        { clave: 'periodo', titulo: 'Periodo' },
                        { clave: 'emp', titulo: 'Sociedad', mono: true },
                        { clave: 'proveedor', titulo: 'Proveedor' },
                        { clave: 'num', titulo: 'Nº factura', mono: true },
                        { clave: 'fecha', titulo: 'Fecha' },
                        { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
                        { clave: 'cuota_a', titulo: 'Cuota A3', n: true, pinta: (f) => eur(f.cuota_a) },
                        { clave: 'cuota_b', titulo: 'Cuota Bilky', n: true, pinta: (f) => eur(f.cuota_b) },
                        { clave: 'dif_cuota', titulo: 'Diferencia', n: true, pinta: (f) => eur(f.dif_cuota) },
                      ]}
                      filas={datos.descuadres} limite={500}
                      vacio="Sin descuadres en el rango." />
                  )
                )}

                {pestana === 'entre' && (
                  <>
                    <h3>La misma factura declarada en dos trimestres</h3>
                    <p className="muted small">
                      Es el riesgo que ningún informe de un trimestre suelto puede detectar. Se
                      excluyen los números que no identifican la factura, que si no darían falsos
                      positivos en cada trimestre.
                    </p>
                    <p className="muted small">
                      Los filtros acotan <strong>antes</strong> de buscar las repeticiones, y con
                      los trimestres eso cambia lo que ves: marcar 1T y 3T no es «las repetidas
                      que además estén ahí», es «mirando solo el 1T y el 3T, cuáles se repiten».
                      Una factura que esté en el 1T y en el 2T no saldrá, porque dentro de lo
                      elegido solo aparece una vez.
                    </p>
                    {trimestres.length === 1 && (
                      <div className="aviso aviso_" style={{ marginBottom: 12 }}>
                        <span className="et">ojo</span>
                        <span>
                          Con un solo trimestre marcado esto siempre sale vacío: hacen falta
                          dos para que algo pueda repetirse entre ellos. Marca otro, o quita
                          el filtro de trimestres.
                        </span>
                      </div>
                    )}
                    <p className="muted small">
                      La columna <strong>libro</strong> dice dónde está la repetición, y no
                      significan lo mismo: en <strong>A3</strong> es una deducción declarada dos
                      veces; en <strong>Bilky</strong>, una captura repetida que todavía no ha
                      llegado a A3; y en <strong>los dos</strong> es lo peor, porque entonces el
                      cuadre entre libros no la delata.
                    </p>
                    {datos.entre === undefined ? <p className="cargando">Buscando…</p> : (
                      <>
                        {datos.entre.length > 0 && (() => {
                          const reales = datos.entre.filter((f) => !f.colision)
                          const choques = datos.entre.length - reales.length
                          return (
                          <div className={`aviso ${reales.length ? 'grave' : 'aviso_'}`}
                               style={{ marginBottom: 12 }}>
                            <span className="et">{reales.length ? 'ojo' : 'nada'}</span>
                            <span>
                              {reales.length
                                ? <>{ent(reales.length)} facturas aparecen en más de un trimestre, con{' '}
                                    <strong>{eur(reales.reduce((s, f) => s + f.iva_repetido, 0))} €</strong>{' '}
                                    de IVA repetido.</>
                                : <>Ninguna factura se repite entre trimestres.</>}
                              {choques > 0 && (
                                <span style={{ display: 'block' }}>
                                  Otras {ent(choques)} lo parecen pero no lo son: la regla de
                                  truncado de A3 las deja con el mismo número. Van marcadas abajo.
                                </span>
                              )}
                              {/* Sobre `reales`, no sobre el total: si el titular
                                  deja fuera las colisiones, el desglose por libro
                                  tampoco puede contarlas o no sumarian igual. */}
                              {['A3', 'BILKY'].map((lib) => {
                                const d = reales.filter((f) => f.libro === lib)
                                if (!d.length) return null
                                return (
                                  <span key={lib} style={{ display: 'block' }}>
                                    En {lib}: {ent(d.length)} por{' '}
                                    {eur(d.reduce((s, f) => s + f.iva_repetido, 0))} €.
                                  </span>
                                )
                              })}
                            </span>
                          </div>
                          )
                        })()}
                        <Tabla
                          columnas={[
                            { clave: 'colision', titulo: '', pinta: (f) => f.colision
                                ? <span className="pastilla no" title="La regla de truncado de A3 deja dos facturas distintas con el mismo número">colisión</span>
                                : <span className="pastilla corregir">repetida</span> },
                            { clave: 'libro', titulo: 'Libro', pinta: (f) => (
                              <span className={`pastilla ${f.libro === 'A3' ? 'a3' : 'bilky'}`}>
                                {f.libro}
                              </span>) },
                            { clave: 'emp', titulo: 'Sociedad', mono: true },
                            { clave: 'sociedad', titulo: '' },
                            { clave: 'proveedor', titulo: 'Proveedor' },
                            { clave: 'numeros', titulo: 'Nº factura', mono: true },
                            { clave: 'fechas', titulo: 'Fecha', mono: true },
                            { clave: 'periodos', titulo: 'Trimestres' },
                            { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
                            { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
                            { clave: 'iva_repetido', titulo: 'IVA repetido', n: true, pinta: (f) => eur(f.iva_repetido) },
                          ]}
                          filas={datos.entre} limite={200}
                          vacio="Ninguna factura se repite entre trimestres. Hace falta más de un trimestre archivado para que esto diga algo." />
                      </>
                    )}
                  </>
                )}

                {pestana === 'sospechosos' && (
                  <>
                    <h3>Números que no identifican ninguna factura</h3>
                    <p className="muted small">
                      En el informe de cada cuadre esto sale del trimestre suelto. Aquí se ve lo
                      que solo se nota cruzando lo archivado: el mismo «número» del mismo
                      proveedor repartido por varias sociedades y varios trimestres. Estas
                      facturas no se pueden cotejar entre libros, no se encuentran buscándolas, y
                      en el SII no cruzan con lo que declara el proveedor.
                    </p>
                    {datos.sospechosos === undefined ? <p className="cargando">Buscando…</p> : (
                      <>
                        {datos.sospechosos.length > 0 && (
                          <div className="etiquetas" style={{ marginBottom: 12 }}>
                            {Object.entries(datos.sospechosos.reduce((a, f) => {
                              a[f.motivo] = (a[f.motivo] || 0) + 1
                              return a
                            }, {})).sort((a, b) => b[1] - a[1]).map(([m, n]) => (
                              <span key={m} className="ficha">{m} · {ent(n)}</span>
                            ))}
                          </div>
                        )}
                        <Tabla
                          columnas={[
                            { clave: 'motivo', titulo: 'Por qué', pinta: (f) => (
                              <span className={`pastilla ${f.es_nif ? 'corregir' : 'revisar'}`}>
                                {f.motivo}
                              </span>) },
                            { clave: 'sociedades', titulo: 'Socs.', n: true, pinta: (f) => (
                              f.sociedades > 1
                                ? <strong>{ent(f.sociedades)}</strong>
                                : <span className="faint">{ent(f.sociedades)}</span>) },
                            { clave: 'libro', titulo: 'Libro', pinta: (f) => (
                              <span className={`pastilla ${f.libro === 'A3' ? 'a3' : 'bilky'}`}>
                                {f.libro}
                              </span>) },
                            { clave: 'emp', titulo: 'Sociedad', mono: true },
                            { clave: 'sociedad', titulo: '' },
                            { clave: 'nif_prov', titulo: 'NIF prov.', mono: true },
                            { clave: 'proveedor', titulo: 'Proveedor' },
                            { clave: 'num', titulo: 'Nº factura', mono: true },
                            { clave: 'periodos', titulo: 'Trimestres' },
                            { clave: 'lineas', titulo: 'Líneas', n: true, pinta: (f) => ent(f.lineas) },
                            { clave: 'dias', titulo: 'Días', n: true, pinta: (f) => ent(f.dias) },
                            { clave: 'cuota', titulo: 'Cuota', n: true, pinta: (f) => eur(f.cuota) },
                          ]}
                          filas={datos.sospechosos} limite={300}
                          vacio="Ningún número sospechoso. Todos identifican una factura." />
                      </>
                    )}
                  </>
                )}

                {pestana === 'evolucion' && (
                  <>
                    <h3>Sociedades que repiten duplicadas trimestre tras trimestre</h3>
                    <p className="muted small">
                      Es lo que distingue un despiste puntual de un problema de proceso.
                    </p>
                    {datos.evolucion === undefined ? <p className="cargando">Cargando…</p> : (
                      <Tabla
                        columnas={[
                          { clave: 'emp', titulo: 'NIF', mono: true },
                          { clave: 'sociedad', titulo: 'Sociedad' },
                          { clave: 'trimestres', titulo: 'Trimestres', n: true },
                          { clave: 'periodos', titulo: 'Cuáles' },
                          { clave: 'facturas', titulo: 'Facturas', n: true },
                          { clave: 'iva', titulo: 'IVA', n: true, pinta: (f) => eur(f.iva) },
                        ]}
                        filas={datos.evolucion} vacio="Nada archivado todavía." />
                    )}
                  </>
                )}

                {pestana === 'cuadres' && <UltimosCuadres />}
              </section>

              <section>
                <p className="sec-label">Exportar</p>
                <h3 style={{ marginBottom: 12 }}>Llevarse lo consultado</h3>
                <div className="descargas">
                  <a className="descarga" href={urlExportar('xlsx', filtros)}>
                    <span className="nom">Excel del rango</span>
                    <span className="small muted">Líneas, duplicadas, descuadres y contexto</span>
                    <span className="small faint">5 hojas · todas las líneas</span>
                  </a>
                  <a className="descarga" href={urlExportar('csv', filtros)}>
                    <span className="nom">Solo las líneas (.csv)</span>
                    <span className="small muted">Separado por punto y coma, coma decimal</span>
                    <span className="small faint">{ent(resumen.lineas)} líneas</span>
                  </a>
                </div>
              </section>
            </>
          )}
        </>
      )}

      <Mantenimiento periodos={periodos} alBorrar={() => window.location.reload()} />
    </>
  )
}

function UltimosCuadres() {
  const [filas, setFilas] = useState(null)
  useEffect(() => { listaCuadres(20).then(setFilas).catch(() => setFilas([])) }, [])
  if (!filas) return <p className="cargando">Cargando…</p>
  return (
    <Tabla
      columnas={[
        { clave: 'creado_en', titulo: 'Lanzado', pinta: (f) => fecha(f.creado_en) },
        { clave: 'usuario', titulo: 'Quién', pinta: (f) => f.usuario || '—' },
        { clave: 'periodo', titulo: 'Periodo', pinta: (f) => f.periodo || '—' },
        { clave: 'estado', titulo: 'Estado', pinta: (f) => (
          <span className={`pastilla ${f.estado === 'hecho' ? 'no' : f.estado === 'fallido' ? 'corregir' : 'revisar'}`}>
            {f.estado}
          </span>) },
        { clave: 'paso', titulo: 'Detalle', pinta: (f) => f.error || f.paso },
        { clave: 'id', titulo: '', pinta: (f) => f.estado === 'hecho'
            ? <a href={`/cuadres/${f.id}`}>Ver</a> : null },
      ]}
      filas={filas} vacio="Todavía no se ha lanzado ningún cuadre." />
  )
}

function Mantenimiento({ periodos, alBorrar }) {
  const [abierto, setAbierto] = useState(false)
  const [elegido, setElegido] = useState('')
  const [confirmando, setConfirmando] = useState(false)
  const [mensaje, setMensaje] = useState(null)

  async function borra() {
    try {
      const r = await historico.borra(elegido)
      setMensaje(`Borrado ${r.periodo} (${r.cargas} carga).`)
      setConfirmando(false)
      setTimeout(alBorrar, 900)
    } catch (e) {
      setMensaje(e.message)
    }
  }

  return (
    <section>
      <button className="secundaria" onClick={() => setAbierto(!abierto)}>
        {abierto ? 'Ocultar' : 'Mantenimiento'}
      </button>
      {abierto && (
        <div className="tarjeta" style={{ marginTop: 12, maxWidth: 560 }}>
          <h3>Borrar un trimestre del histórico</h3>
          <p className="small muted">
            Se lleva por delante sus líneas, duplicadas, descuadres y avisos.
            No hay vuelta atrás: para recuperarlo habría que volver a cargar los libros.
          </p>
          <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
            <select value={elegido} onChange={(e) => { setElegido(e.target.value); setConfirmando(false) }}>
              <option value="">Elige un trimestre…</option>
              {periodos.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            {elegido && !confirmando && (
              <button className="secundaria" onClick={() => setConfirmando(true)}>
                Borrar {elegido}
              </button>
            )}
            {confirmando && (
              <>
                <button className="peligro" onClick={borra}>Sí, borrar {elegido}</button>
                <button className="secundaria" onClick={() => setConfirmando(false)}>Cancelar</button>
              </>
            )}
          </div>
          {mensaje && <p className="small" style={{ marginBottom: 0 }}>{mensaje}</p>}
        </div>
      )}
    </section>
  )
}
