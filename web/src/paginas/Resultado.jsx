import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { estadoCuadre, ficherosCuadre, resultadoCuadre, urlFichero, urlZip } from '../api.js'
import { ent, eur, kb, pct, tipo } from '../formato.js'
import Avisos from '../componentes/Avisos.jsx'
import Tabla from '../componentes/Tabla.jsx'

// Los pasos que va anunciando el backend, para mover la barra. No es un
// porcentaje real --no se sabe cuánto queda-- pero sí dice por dónde va.
const PASOS = ['Leyendo', 'Cotejando', 'Buscando', 'Generando el Excel', 'Generando los informes', 'Archivando']

function progreso(paso = '') {
  const i = PASOS.findIndex((p) => paso.startsWith(p))
  return i < 0 ? 0.06 : (i + 1) / (PASOS.length + 1)
}

function Metrica({ rotulo, cifra, pie, critico }) {
  return (
    <div className={`metrica ${critico ? 'critico' : ''}`}>
      <div className="rotulo">{rotulo}</div>
      <div className="cifra">{cifra}</div>
      {pie && <div className="small muted">{pie}</div>}
    </div>
  )
}

const ETIQUETAS = {
  solo_a3: ['Corregir en A3', 'corregir'],
  doc_repetido: ['Revisar en Bilky', 'revisar'],
  sincontraste: ['Sin contraste', 'revisar'],
  linea_repetida: ['Líneas idénticas', 'revisar'],
  falso: ['No es duplicado', 'no'],
}

export default function Resultado() {
  const { id } = useParams()
  const [trabajo, setTrabajo] = useState(null)
  const [datos, setDatos] = useState(null)
  const [ficheros, setFicheros] = useState([])
  const [error, setError] = useState(null)
  const [pestana, setPestana] = useState('resumen')
  const temporizador = useRef(null)

  useEffect(() => {
    let vivo = true
    async function mira() {
      try {
        const t = await estadoCuadre(id)
        if (!vivo) return
        setTrabajo(t)
        if (t.estado === 'hecho') {
          const [r, f] = await Promise.all([resultadoCuadre(id), ficherosCuadre(id)])
          if (!vivo) return
          setDatos(r)
          setFicheros(f)
        } else if (t.estado !== 'fallido') {
          temporizador.current = setTimeout(mira, 1500)
        }
      } catch (e) {
        if (vivo) setError(e.message)
      }
    }
    mira()
    return () => { vivo = false; clearTimeout(temporizador.current) }
  }, [id])

  if (error) {
    return (
      <section className="error-caja">
        <strong>No se ha podido consultar el cuadre.</strong>
        <div className="small" style={{ marginTop: 4 }}>{error}</div>
        <p style={{ marginBottom: 0 }}><Link to="/">Volver</Link></p>
      </section>
    )
  }
  if (!trabajo) return <p className="cargando">Cargando…</p>

  if (trabajo.estado === 'fallido') {
    return (
      <>
        <section className="error-caja">
          <strong>El cuadre ha fallado.</strong>
          <div className="small" style={{ marginTop: 6 }}>{trabajo.error}</div>
        </section>
        <p><Link to="/">Empezar otro</Link></p>
      </>
    )
  }

  if (trabajo.estado !== 'hecho' || !datos) {
    return (
      <section className="tarjeta">
        <p className="sec-label">En marcha</p>
        <h2>{trabajo.paso}</h2>
        <p className="muted small">
          Un trimestre completo tarda alrededor de un minuto. Puedes dejar esta
          pestaña abierta; se actualiza sola.
        </p>
        <div className="barra" style={{ marginTop: 16 }}>
          <div style={{ width: `${100 * progreso(trabajo.paso)}%` }} />
        </div>
      </section>
    )
  }

  const r = trabajo.resumen
  const c = datos.comparativa
  const cuadra = c.cuadra
  const dup = datos.duplicadas
  const det = datos.detecciones

  // Si un libro viene x100, ninguna cifra de esta pantalla significa nada. Se
  // dice antes que el veredicto y se apagan las métricas: dejarlas con su
  // aspecto normal las haría parecer buenas.
  const escalas = Object.keys(det.escalas || {})

  return (
    <>
      {escalas.length > 0 && (
        <section className="veredicto mal">
          <h2>Estas cifras no sirven</h2>
          <p style={{ margin: '4px 0 0' }}>
            El fichero de <strong>{escalas.join(' y ')}</strong> viene sin coma decimal: los
            importes están multiplicados por cien y el tipo de IVA sale como 2.100 % en vez de
            21 %. Es una importación hecha con el separador decimal equivocado.
          </p>
          <p style={{ margin: '8px 0 0' }}>
            Vuelve a exportar el fichero desde A3, o divide entre cien todas las columnas de
            importe, y lánzalo otra vez. <strong>No se ha archivado en el histórico.</strong>
          </p>
        </section>
      )}

      <section className={`veredicto ${escalas.length ? 'apagado' : cuadra ? 'ok' : 'mal'}`}>
        <h2>
          {cuadra ? 'La conciliación cuadra' : 'La conciliación NO cuadra'}
          {datos.periodo && <span className="muted"> · {datos.periodo}</span>}
        </h2>
        <p style={{ margin: '4px 0 0' }}>
          {cuadra
            ? <>La diferencia de <strong>{eur(c.dif.cuota)} €</strong> queda explicada al céntimo.</>
            : <>Las partidas suman {eur(c.suma)} € y la diferencia real es {eur(c.dif.cuota)} €. Revisa los avisos antes de usar estos informes.</>}
        </p>
      </section>

      <section className={`metricas ${escalas.length ? "apagado" : ""}`}>
        <Metrica rotulo="Diferencia de cuota" cifra={`${eur(c.dif.cuota)} €`} />
        <Metrica rotulo="Facturas que cuadran" cifra={`${ent(c.fac.cuadran)}`}
                 pie={`de ${ent(c.fac.comunes)} · ${pct(c.fac.pct)}`} />
        <Metrica rotulo="Duplicadas a revisar" cifra={ent(r.duplicadas_accion)}
                 pie={`${eur(r.duplicadas_iva)} € · ${ent(r.duplicadas)} detectadas`}
                 critico={r.duplicadas_accion > 0} />
        <Metrica rotulo="Solo visibles en Bilky" cifra={ent(r.dup_bilky)}
                 pie={`${eur(r.dup_bilky_iva)} € · ${ent(r.dup_bilky_revisar)} a revisar`}
                 critico={r.dup_bilky > 0} />
        <Metrica rotulo="Sociedades" cifra={ent(r.sociedades)}
                 pie={`${ent(c.soc_cuadran)} cuadran exactas`} />
        <Metrica rotulo="Regla de truncado" cifra={pct(c.regla.tasa)}
                 pie={c.regla.fiable ? 'dentro de lo normal' : 'por debajo del umbral'}
                 critico={!c.regla.fiable} />
      </section>

      <Avisos avisos={trabajo.avisos} />

      <section>
        <div className="pestanas">
          {[['resumen', 'Resumen'], ['duplicadas', `Duplicadas (${dup.facturas.length})`],
            ['detecciones', 'Otras detecciones'], ['sociedades', 'Por sociedad'],
            ['informes', 'Informes']].map(([k, t]) => (
            <button key={k} className={pestana === k ? 'activa' : ''} onClick={() => setPestana(k)}>{t}</button>
          ))}
        </div>

        {pestana === 'resumen' && (
          <>
            <h3>Cómo se explica la diferencia</h3>
            <p className="muted small">
              Las partidas tienen que sumar exactamente la diferencia de cuota. Si no suma, algo se ha perdido por el camino.
            </p>
            <Tabla
              columnas={[
                { clave: 'titulo', titulo: 'Partida' },
                { clave: 'detalle', titulo: 'Detalle' },
                { clave: 'valor', titulo: 'Importe', n: true, pinta: (f) => `${eur(f.valor)} €` },
              ]}
              filas={c.con} />
            <h3 style={{ marginTop: 24 }}>Por tipo de IVA</h3>
            <Tabla
              columnas={[
                { clave: 'tipo', titulo: 'Tipo', pinta: (f) => tipo(f.tipo) },
                { clave: 'base_a', titulo: 'Base A3', n: true, pinta: (f) => eur(f.base_a) },
                { clave: 'base_b', titulo: 'Base Bilky', n: true, pinta: (f) => eur(f.base_b) },
                { clave: 'cuota_a', titulo: 'Cuota A3', n: true, pinta: (f) => eur(f.cuota_a) },
                { clave: 'cuota_b', titulo: 'Cuota Bilky', n: true, pinta: (f) => eur(f.cuota_b) },
                { clave: 'd', titulo: 'Diferencia', n: true, pinta: (f) => eur(f.d) },
              ]}
              filas={c.tipos} />
          </>
        )}

        {pestana === 'duplicadas' && (
          <Tabla
            columnas={[
              { clave: 'v', titulo: 'Veredicto', pinta: (f) => {
                const [t, cl] = ETIQUETAS[f.v] || [f.v, 'no']
                return <span className={`pastilla ${cl}`}>{t}</span>
              } },
              { clave: 'emp', titulo: 'Sociedad', mono: true, pinta: (f) => f.nom || f.emp },
              { clave: 'prov', titulo: 'Proveedor' },
              { clave: 'num_a3', titulo: 'Nº en A3', mono: true },
              { clave: 'fechas', titulo: 'Fechas', pinta: (f) => f.fechas.join(' · ') },
              { clave: 'tipo', titulo: 'Tipo', n: true, pinta: (f) => tipo(f.tipo) },
              { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
              { clave: 'sobrante', titulo: 'IVA repetido', n: true, pinta: (f) => eur(f.sobrante) },
              { clave: 'enlace', titulo: '', pinta: (f) => f.links?.[0]
                  ? <a href={f.links[0].url} target="_blank" rel="noreferrer">Ver en Bilky</a> : null },
            ]}
            filas={dup.facturas} limite={60}
            vacio="No se ha detectado ninguna factura duplicada." />
        )}

        {pestana === 'detecciones' && (
          <>
            <h3>Duplicados que solo se ven en el libro de Bilky</h3>
            <p className="muted small">
              A3 tiene la factura una sola vez, así que el criterio que parte de A3 no los marca.
            </p>
            <Tabla
              columnas={[
                { clave: 'clase', titulo: 'Clase', pinta: (f) => (
                  <span className={`pastilla ${f.clase === 'igual' ? 'corregir' : f.clase === 'distinto' ? 'revisar' : 'no'}`}>
                    {f.clase === 'igual' ? 'Duplicado real' : f.clase === 'distinto' ? 'Importes distintos' : 'Factura y abono'}
                  </span>) },
                { clave: 'emp', titulo: 'Sociedad', mono: true },
                { clave: 'prov', titulo: 'Proveedor' },
                { clave: 'num', titulo: 'Nº factura', mono: true },
                { clave: 'fechas', titulo: 'Fechas', pinta: (f) => f.fechas.join(' · ') },
                { clave: 'docs', titulo: 'Docs', n: true },
                { clave: 'totales', titulo: 'Totales', n: true, pinta: (f) => f.totales.map((t) => eur(t)).join(' · ') },
                { clave: 'sobrante', titulo: 'IVA que sobra', n: true, pinta: (f) => eur(f.sobrante) },
              ]}
              filas={det.dup_bilky} limite={40}
              vacio="Ninguno." />

            {det.cruzadas.length > 0 && (
              <>
                <h3 style={{ marginTop: 24 }}>La misma factura en dos sociedades</h3>
                <Tabla
                  columnas={[
                    { clave: 'prov', titulo: 'Proveedor' },
                    { clave: 'num', titulo: 'Nº factura', mono: true },
                    { clave: 'fecha', titulo: 'Fecha' },
                    { clave: 'total', titulo: 'Total', n: true, pinta: (f) => eur(f.total) },
                    { clave: 'emps', titulo: 'Sociedades', mono: true, pinta: (f) => f.emps.join(' · ') },
                  ]}
                  filas={det.cruzadas} />
              </>
            )}

            {det.tipos_invalidos.length > 0 && (
              <>
                <h3 style={{ marginTop: 24 }}>Tipos de IVA que no existen</h3>
                <Tabla
                  columnas={[
                    { clave: 'tipo', titulo: 'Tipo', pinta: (f) => tipo(f.tipo) },
                    { clave: 'libro', titulo: 'Libro' },
                    { clave: 'lineas', titulo: 'Líneas', n: true },
                    { clave: 'cuota', titulo: 'Cuota', n: true, pinta: (f) => eur(f.cuota) },
                    { clave: 'emp', titulo: 'Ejemplo', mono: true },
                    { clave: 'num', titulo: 'Factura', mono: true },
                    { clave: 'prov', titulo: 'Proveedor' },
                  ]}
                  filas={det.tipos_invalidos} />
              </>
            )}

            {det.discrepantes.length > 0 && (
              <>
                <h3 style={{ marginTop: 24 }}>Números que no coinciden entre los dos libros</h3>
                <p className="muted small">En el SII se declara el número, así que uno de los dos está mal.</p>
                <Tabla
                  columnas={[
                    { clave: 'emp', titulo: 'Sociedad', mono: true },
                    { clave: 'prov', titulo: 'Proveedor' },
                    { clave: 'num_a3', titulo: 'En A3', mono: true },
                    { clave: 'num_bilky', titulo: 'En Bilky', mono: true },
                    { clave: 'fecha', titulo: 'Fecha' },
                    { clave: 'base', titulo: 'Base', n: true, pinta: (f) => eur(f.base) },
                  ]}
                  filas={det.discrepantes} limite={30} />
              </>
            )}
          </>
        )}

        {pestana === 'sociedades' && (
          <Tabla
            columnas={[
              { clave: 'nif', titulo: 'NIF', mono: true },
              { clave: 'nom', titulo: 'Sociedad' },
              { clave: 'la', titulo: 'Líneas A3', n: true, pinta: (f) => ent(f.la) },
              { clave: 'lb', titulo: 'Líneas Bilky', n: true, pinta: (f) => ent(f.lb) },
              { clave: 'ca', titulo: 'Cuota A3', n: true, pinta: (f) => eur(f.ca) },
              { clave: 'cb', titulo: 'Cuota Bilky', n: true, pinta: (f) => eur(f.cb) },
              { clave: 'dc', titulo: 'Diferencia', n: true, pinta: (f) => eur(f.dc) },
              { clave: 'cuadra', titulo: '', pinta: (f) => Math.abs(f.dc) < 0.01
                  ? <span className="pastilla no">cuadra</span> : null },
            ]}
            filas={c.soc} limite={100} />
        )}

        {pestana === 'informes' && (
          <>
            <div className="descargas">
              <a className="descarga" href={urlZip(id)}>
                <span className="nom">Los tres, en un ZIP</span>
                <span className="small muted">Excel y los dos informes</span>
                <span className="small faint">
                  {kb(ficheros.reduce((s, f) => s + f.bytes, 0))}
                </span>
              </a>
              {ficheros.map((f) => (
                <a key={f.clave} className="descarga" href={urlFichero(id, f.clave)}>
                  <span className="nom">
                    {{ excel: 'Excel de trabajo', comparativa: 'Informe de cuadre',
                       duplicadas: 'Informe de duplicadas' }[f.clave] || f.clave}
                  </span>
                  <span className="small muted">{f.nombre}</span>
                  <span className="small faint">{kb(f.bytes)}</span>
                </a>
              ))}
            </div>
            <h3 style={{ margin: '26px 0 10px' }}>Informe de duplicadas</h3>
            <iframe className="informe" title="Informe de duplicadas"
                    src={urlFichero(id, 'duplicadas', true)} />
            <h3 style={{ margin: '26px 0 10px' }}>Informe de cuadre</h3>
            <iframe className="informe" title="Informe de cuadre"
                    src={urlFichero(id, 'comparativa', true)} />
          </>
        )}
      </section>

      <section>
        <Link to="/">← Hacer otro cuadre</Link>
        {trabajo.carga_id && (
          <span className="small muted" style={{ marginLeft: 16 }}>
            Archivado en el histórico como carga {trabajo.carga_id}.
          </span>
        )}
      </section>
    </>
  )
}
