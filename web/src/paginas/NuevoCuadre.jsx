import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { creaCuadre } from '../api.js'

const EXTENSIONES = ['.xlsx', '.xlsm', '.xls', '.csv']

function admitido(f) {
  return EXTENSIONES.some((e) => f.name.toLowerCase().endsWith(e))
}

// Caja de subida: acepta arrastrar y también el selector de siempre, porque no
// todo el mundo arrastra ficheros.
function Soltar({ lado, clase, ayuda, ficheros, cambia }) {
  const [encima, setEncima] = useState(false)
  const entrada = useRef(null)

  function anade(nuevos) {
    const validos = [...nuevos].filter(admitido)
    const nombres = new Set(ficheros.map((f) => f.name))
    cambia([...ficheros, ...validos.filter((f) => !nombres.has(f.name))])
  }

  return (
    <div
      className={`soltar ${clase} ${encima ? 'encima' : ''} ${ficheros.length ? 'lleno' : ''}`}
      onClick={() => entrada.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={(e) => { e.preventDefault(); setEncima(false); anade(e.dataTransfer.files) }}
    >
      <div className="etiqueta">Libros de {lado}</div>
      <div className="small muted">{ayuda}</div>
      <input
        ref={entrada} type="file" multiple hidden
        accept={EXTENSIONES.join(',')}
        onChange={(e) => { anade(e.target.files); e.target.value = '' }}
      />
      {ficheros.length > 0 && (
        <ul className="lista-fich" onClick={(e) => e.stopPropagation()}>
          {ficheros.map((f) => (
            <li key={f.name}>
              <span>{f.name}</span>
              <span className="faint small">{Math.round(f.size / 1024)} KB</span>
              <button className="quitar" title="Quitar"
                      onClick={() => cambia(ficheros.filter((x) => x.name !== f.name))}>×</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function NuevoCuadre() {
  const [a3, setA3] = useState([])
  const [bilky, setBilky] = useState([])
  const [periodo, setPeriodo] = useState('')
  const [archivar, setArchivar] = useState(true)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)
  const navega = useNavigate()

  const listo = a3.length > 0 && bilky.length > 0 && !enviando

  async function envia() {
    setEnviando(true)
    setError(null)
    try {
      const { id } = await creaCuadre({ a3, bilky, periodo: periodo.trim(), archivar })
      navega(`/cuadres/${id}`)
    } catch (e) {
      setError(e.message)
      setEnviando(false)
    }
  }

  return (
    <>
      <section>
        <p className="sec-label">Paso 1</p>
        <h2>Sube los libros de IVA soportado del trimestre</h2>
        <p className="muted" style={{ marginTop: 6 }}>
          De cada sistema puedes subir el fichero unificado o los sueltos de cada
          sociedad, y mezclarlos si hace falta. Se admiten Excel y CSV.
        </p>
      </section>

      <section className="rejilla2">
        <Soltar lado="A3" clase="a3" ficheros={a3} cambia={setA3}
                ayuda="El Excel unificado o los CSV por sociedad" />
        <Soltar lado="Bilky" clase="bilky" ficheros={bilky} cambia={setBilky}
                ayuda="El export unificado o el de cada sociedad" />
      </section>

      <section className="tarjeta">
        <p className="sec-label">Paso 2</p>
        <h3 style={{ marginBottom: 14 }}>Opciones</h3>
        <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div>
            <label className="small muted" htmlFor="periodo" style={{ display: 'block', marginBottom: 4 }}>
              Periodo
            </label>
            <input id="periodo" type="text" value={periodo} placeholder="Se deduce solo"
                   onChange={(e) => setPeriodo(e.target.value)} style={{ width: 180 }} />
            <div className="small faint" style={{ marginTop: 4 }}>P. ej. 3T 2026</div>
          </div>
          <label className="casilla" style={{ maxWidth: 460 }}>
            <input type="checkbox" checked={archivar} onChange={(e) => setArchivar(e.target.checked)}
                   style={{ marginTop: 5 }} />
            <span>
              <strong>Archivar en el histórico</strong>
              <span className="small muted" style={{ display: 'block' }}>
                Permite consultarlo después y comparar trimestres. Si ya hay una carga
                de ese periodo, la sustituye.
              </span>
            </span>
          </label>
        </div>
      </section>

      {error && (
        <section className="error-caja">
          <strong>No se ha podido lanzar el cuadre.</strong>
          <div className="small" style={{ marginTop: 4 }}>{error}</div>
        </section>
      )}

      <section>
        <button className="principal" disabled={!listo} onClick={envia}>
          {enviando ? 'Enviando…' : 'Generar informes'}
        </button>
        {!listo && !enviando && (
          <span className="small muted" style={{ marginLeft: 14 }}>
            Hacen falta ficheros de los dos sistemas.
          </span>
        )}
        <p className="small faint" style={{ marginTop: 12 }}>
          Un trimestre completo tarda alrededor de un minuto. Puedes seguir el
          avance en la pantalla siguiente.
        </p>
      </section>
    </>
  )
}
