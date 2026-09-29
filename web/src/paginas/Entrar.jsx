import { useEffect, useState } from 'react'
import { entrar, salud } from '../api.js'

function Ojo({ tachado }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1.8 12S5.5 5.5 12 5.5 22.2 12 22.2 12 18.5 18.5 12 18.5 1.8 12 1.8 12Z" />
      <circle cx="12" cy="12" r="3.2" />
      {tachado && <path d="M4.5 19.5 19.5 4.5" />}
    </svg>
  )
}

export default function Entrar({ alEntrar }) {
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [mayus, setMayus] = useState(false)
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [sinUsuarios, setSinUsuarios] = useState(false)

  // Si la base está recién creada no hay ninguna cuenta, y quien mire la
  // pantalla no tiene por qué adivinar que se crean desde el servidor.
  useEffect(() => {
    salud().then((s) => setSinUsuarios(s.hay_usuarios === false)).catch(() => {})
  }, [])

  async function envia(e) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      alEntrar(await entrar(usuario, clave))
    } catch (err) {
      setError(err.message)
      setEnviando(false)
    }
  }

  // Bloq Mayús con la contraseña tapada es la razón tonta por la que no se
  // entra sin que se vea por qué.
  function vigilaMayus(e) {
    setMayus(!!e.getModifierState && e.getModifierState('CapsLock'))
  }

  return (
    <div className="pantalla-entrar">
      <div className="caja-entrar">
        <h1>Cuadre de IVA</h1>
        <p className="entrar-marca">
          <span className="a3">A3</span> contra <span className="bilky">Bilky</span>
        </p>

        {sinUsuarios ? (
          <div className="error-caja">
            <strong>Todavía no hay ninguna cuenta.</strong>
            <p className="small" style={{ margin: '6px 0 0' }}>Se crean desde el servidor, con:</p>
            <code className="mono small">python gestion_usuarios.py crear usuario "Nombre"</code>
          </div>
        ) : (
          <>
            <form onSubmit={envia}>
              <div className="campo">
                <label className="small muted" htmlFor="usuario">Usuario</label>
                <input id="usuario" name="usuario" type="text" value={usuario} autoFocus
                       autoComplete="username" autoCapitalize="none" spellCheck="false"
                       onChange={(e) => setUsuario(e.target.value)} />
              </div>

              <div className="campo campo-clave">
                <label className="small muted" htmlFor="clave">Contraseña</label>
                <input id="clave" name="clave" type={verClave ? 'text' : 'password'} value={clave}
                       autoComplete="current-password" onKeyUp={vigilaMayus} onKeyDown={vigilaMayus}
                       onChange={(e) => setClave(e.target.value)} />
                <button type="button" className="ver-clave" tabIndex={-1}
                        aria-label={verClave ? 'Ocultar la contraseña' : 'Ver la contraseña'}
                        aria-pressed={verClave}
                        onClick={() => setVerClave((v) => !v)}>
                  <Ojo tachado={verClave} />
                </button>
              </div>

              {mayus && <p className="small aviso-mayus">Bloq Mayús está activado.</p>}
              {error && <p className="error-caja small" role="alert">{error}</p>}

              <button className="principal" type="submit" aria-busy={enviando}
                      disabled={enviando || !usuario || !clave}>
                {enviando ? 'Entrando…' : 'Entrar'}
              </button>
            </form>

            <p className="entrar-pie small faint">
              Las cuentas y las contraseñas las lleva el administrador desde el servidor.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
