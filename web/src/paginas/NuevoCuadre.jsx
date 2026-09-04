import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { creaCuadre } from '../api.js'

const EXTENSIONES = ['.xlsx', '.xlsm', '.xls', '.csv']

function admitido(f) {
  if (!f || !f.name) return false
  if (f.name.startsWith('~$') || f.name.startsWith('._')) return false
  return EXTENSIONES.some((e) => f.name.toLowerCase().endsWith(e))
}

// Extrae recursivamente los ficheros desde un FileSystemDirectoryHandle (API nativa moderna)
async function extraeDeDirectoryHandle(dirHandle, rutaActual = '') {
  const ficheros = []
  for await (const entry of dirHandle.values()) {
    const ruta = rutaActual ? `${rutaActual}/${entry.name}` : entry.name
    if (entry.kind === 'file') {
      const file = await entry.getFile()
      try {
        Object.defineProperty(file, 'rutaRelativa', { value: ruta, writable: true, configurable: true })
      } catch {
        file.rutaRelativa = ruta
      }
      ficheros.push(file)
    } else if (entry.kind === 'directory') {
      const sub = await extraeDeDirectoryHandle(entry, ruta)
      ficheros.push(...sub)
    }
  }
  return ficheros
}

// Abre el selector de carpetas nativo del navegador/sistema operativo
async function seleccionarCarpeta() {
  // 1. En Chrome, Edge y navegadores modernos: window.showDirectoryPicker abre el diálogo nativo de carpetas de Windows
  if (typeof window.showDirectoryPicker === 'function') {
    try {
      const dirHandle = await window.showDirectoryPicker()
      return await extraeDeDirectoryHandle(dirHandle, dirHandle.name)
    } catch (e) {
      if (e.name === 'AbortError') return []
      console.warn('showDirectoryPicker falló o fue denegado, intentando fallback:', e)
    }
  }

  // 2. Fallback con input HTML configurado directamente como directorio
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.webkitdirectory = true
    input.setAttribute('webkitdirectory', '')
    input.setAttribute('directory', '')
    input.multiple = true
    input.style.display = 'none'
    document.body.appendChild(input)

    input.onchange = (e) => {
      const files = Array.from(e.target.files || [])
      document.body.removeChild(input)
      resolve(files)
    }
    input.oncancel = () => {
      document.body.removeChild(input)
      resolve([])
    }
    input.click()
  })
}

// Extrae recursivamente todos los ficheros de un FileSystemEntry (cuando se arrastra una carpeta)
async function extraeFicherosDeEntry(entry) {
  if (!entry) return []
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file(
        (file) => {
          try {
            const rel = entry.fullPath ? entry.fullPath.replace(/^\//, '') : file.name
            Object.defineProperty(file, 'rutaRelativa', { value: rel, writable: true, configurable: true })
          } catch {
            file.rutaRelativa = file.name
          }
          resolve([file])
        },
        () => resolve([])
      )
    })
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    const todos = []
    const leeLote = () =>
      new Promise((resolve) => {
        reader.readEntries(
          async (entries) => {
            if (!entries || entries.length === 0) {
              resolve(todos)
            } else {
              for (const e of entries) {
                const sub = await extraeFicherosDeEntry(e)
                todos.push(...sub)
              }
              resolve(await leeLote())
            }
          },
          () => resolve(todos)
        )
      })
    return leeLote()
  }
  return []
}

// Extrae todos los ficheros de un evento drag & drop soportando carpetas anidadas
async function extraeFicherosDeDataTransfer(dataTransfer) {
  const items = dataTransfer.items
  if (items && items.length > 0 && typeof items[0].webkitGetAsEntry === 'function') {
    const promesas = []
    for (let i = 0; i < items.length; i++) {
      const entry = items[i].webkitGetAsEntry()
      if (entry) promesas.push(extraeFicherosDeEntry(entry))
    }
    const resultados = await Promise.all(promesas)
    return resultados.flat()
  }
  return Array.from(dataTransfer.files || [])
}

// Deduce el periodo trimestral inspeccionando rutas o nombres de ficheros
function deducePeriodo(ficheros) {
  for (const f of ficheros) {
    const texto = `${f.webkitRelativePath || f.rutaRelativa || ''} ${f.name}`
    let m = texto.match(/\b([1-4])\s*[Tt]\s*[-_ ]?\s*(20\d{2})\b/)
    if (m) return `${m[1]}T ${m[2]}`
    m = texto.match(/\b(20\d{2})\s*[-_ ]?\s*([1-4])\s*[Tt]\b/)
    if (m) return `${m[2]}T ${m[1]}`
    m = texto.match(/Trimestre\s*[-_ ]?\s*([1-4])\s*[-_ ]?\s*(20\d{2})/i)
    if (m) return `${m[1]}T ${m[2]}`
  }
  return ''
}

// Caja de subida para cada sistema individual (acepta ficheros, carpetas arrastradas y selector)
function Soltar({ lado, clase, ayuda, ficheros, cambia, onPeriodoDetectado }) {
  const [encima, setEncima] = useState(false)
  const [cargandoCarpeta, setCargandoCarpeta] = useState(false)
  const entradaFicheros = useRef(null)

  function anade(nuevos) {
    const validos = [...nuevos].filter(admitido)
    if (validos.length === 0) return
    const nombres = new Set(ficheros.map((f) => f.name))
    const nuevosUnicos = validos.filter((f) => !nombres.has(f.name))
    const actualizados = [...ficheros, ...nuevosUnicos]
    cambia(actualizados)
    if (onPeriodoDetectado) {
      const p = deducePeriodo(actualizados)
      if (p) onPeriodoDetectado(p)
    }
  }

  async function manejaDrop(e) {
    e.preventDefault()
    setEncima(false)
    const extraidos = await extraeFicherosDeDataTransfer(e.dataTransfer)
    anade(extraidos)
  }

  async function elegirCarpeta(e) {
    e.stopPropagation()
    setCargandoCarpeta(true)
    try {
      const extraidos = await seleccionarCarpeta()
      if (extraidos && extraidos.length > 0) {
        anade(extraidos)
      }
    } finally {
      setCargandoCarpeta(false)
    }
  }

  return (
    <div
      className={`soltar ${clase} ${encima ? 'encima' : ''} ${ficheros.length ? 'lleno' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={manejaDrop}
    >
      <div className="cabecera-soltar">
        <div className="etiqueta">
          Libros de {lado} {ficheros.length > 0 && <span className="small faint">({ficheros.length})</span>}
        </div>
        {ficheros.length > 0 && (
          <button
            type="button"
            className="btn-mini"
            title="Vaciar lista"
            onClick={(e) => {
              e.stopPropagation()
              cambia([])
            }}
          >
            Vaciar
          </button>
        )}
      </div>

      <div className="small muted">{ayuda}</div>

      <div className="soltar-botones" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="btn-accion-soltar primario"
          onClick={elegirCarpeta}
          disabled={cargandoCarpeta}
        >
          {cargandoCarpeta ? 'Abriendo carpeta…' : `📁 Subir carpeta de ${lado}`}
        </button>
        <button
          type="button"
          className="btn-accion-soltar"
          onClick={() => entradaFicheros.current?.click()}
        >
          📄 Examinar ficheros
        </button>
      </div>

      <input
        ref={entradaFicheros}
        type="file"
        multiple
        hidden
        accept={EXTENSIONES.join(',')}
        onChange={(e) => { anade(e.target.files); e.target.value = '' }}
      />

      {ficheros.length > 0 && (
        <ul className="lista-fich" onClick={(e) => e.stopPropagation()}>
          {ficheros.map((f) => (
            <li key={f.name}>
              <span title={f.name}>{f.name}</span>
              <span className="faint small">{Math.round(f.size / 1024)} KB</span>
              <button
                type="button"
                className="quitar"
                title="Quitar"
                onClick={() => cambia(ficheros.filter((x) => x.name !== f.name))}
              >
                ×
              </button>
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
  // 'actualiza' de salida: subir el libro corregido de una sociedad no puede
  // borrar las otras setenta. Sustituir el trimestre entero se pide a mano.
  const [modo, setModo] = useState('actualiza')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)

  const navega = useNavigate()
  const listo = a3.length > 0 && bilky.length > 0 && !enviando

  async function envia() {
    setEnviando(true)
    setError(null)
    try {
      const { id } = await creaCuadre({ a3, bilky, periodo: periodo.trim(), archivar, modo })
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
          Puedes subir la carpeta completa del trimestre o los ficheros sueltos de cada
          sociedad en cada sistema. Se admiten Excel y CSV.
        </p>
      </section>

      <section className="rejilla2">
        <Soltar
          lado="A3"
          clase="a3"
          ficheros={a3}
          cambia={setA3}
          ayuda="El Excel unificado o los CSV por sociedad"
          onPeriodoDetectado={(p) => { if (!periodo) setPeriodo(p) }}
        />
        <Soltar
          lado="Bilky"
          clase="bilky"
          ficheros={bilky}
          cambia={setBilky}
          ayuda="El export unificado o el de cada sociedad"
          onPeriodoDetectado={(p) => { if (!periodo) setPeriodo(p) }}
        />
      </section>

      <section className="tarjeta">
        <p className="sec-label">Paso 2</p>
        <h3 style={{ marginBottom: 14 }}>Opciones</h3>
        <div style={{ display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div>
            <label className="small muted" htmlFor="periodo" style={{ display: 'block', marginBottom: 4 }}>
              Periodo
            </label>
            <input
              id="periodo"
              type="text"
              value={periodo}
              placeholder="Se deduce solo"
              onChange={(e) => setPeriodo(e.target.value)}
              style={{ width: 180 }}
            />
            <div className="small faint" style={{ marginTop: 4 }}>P. ej. 3T 2026</div>
          </div>
          <label className="casilla" style={{ maxWidth: 460 }}>
            <input
              type="checkbox"
              checked={archivar}
              onChange={(e) => setArchivar(e.target.checked)}
              style={{ marginTop: 5 }}
            />
            <span>
              <strong>Archivar en el histórico</strong>
              <span className="small muted" style={{ display: 'block' }}>
                Permite consultarlo después y comparar trimestres.
              </span>
            </span>
          </label>
        </div>

        {archivar && (
          <div className="modo-archivo">
            <p className="small muted" style={{ marginBottom: 8 }}>
              Si ya hay algo archivado de ese periodo:
            </p>
            <label className="casilla">
              <input
                type="radio"
                name="modo"
                checked={modo === 'actualiza'}
                onChange={() => setModo('actualiza')}
                style={{ marginTop: 5 }}
              />
              <span>
                <strong>Actualizar solo las sociedades que subo</strong>
                <span className="small muted" style={{ display: 'block' }}>
                  El resto del trimestre se queda como está. Es lo que hace falta para
                  corregir una sociedad sin volver a subir las demás.
                </span>
              </span>
            </label>
            <label className="casilla">
              <input
                type="radio"
                name="modo"
                checked={modo === 'sustituye'}
                onChange={() => setModo('sustituye')}
                style={{ marginTop: 5 }}
              />
              <span>
                <strong>Sustituir el trimestre entero</strong>
                <span className="small muted" style={{ display: 'block' }}>
                  El periodo pasará a ser exactamente esta subida.
                </span>
              </span>
            </label>
            {modo === 'sustituye' && (
              <div className="aviso-sustituye">
                Todo lo que ese periodo tenga archivado y no venga en esta subida
                <strong> se borra del histórico</strong>, sin poder deshacerlo. Súbelo
                completo, con todas las sociedades del trimestre.
              </div>
            )}
          </div>
        )}
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
