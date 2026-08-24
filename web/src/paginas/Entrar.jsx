import { useEffect, useState } from 'react'
import { entrar, salud } from '../api.js'

export default function Entrar({ alEntrar }) {
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
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

  return (
    <div className="caja-entrar">
      <h1>Cuadre de IVA</h1>
      <p className="muted small">A3 contra Bilky</p>

      {sinUsuarios ? (
        <div className="error-caja" style={{ marginTop: 22, textAlign: 'left' }}>
          <strong>Todavía no hay ninguna cuenta.</strong>
          <p className="small" style={{ margin: '6px 0 0' }}>
            Se crean desde el servidor, con:
          </p>
          <code className="mono small">python gestion_usuarios.py crear usuario "Nombre"</code>
        </div>
      ) : (
        <form onSubmit={envia} style={{ marginTop: 24 }}>
          <label className="small muted" htmlFor="usuario">Usuario</label>
          <input id="usuario" type="text" value={usuario} autoFocus autoComplete="username"
                 onChange={(e) => setUsuario(e.target.value)} />
          <label className="small muted" htmlFor="clave" style={{ marginTop: 14 }}>Contraseña</label>
          <input id="clave" type="password" value={clave} autoComplete="current-password"
                 onChange={(e) => setClave(e.target.value)} />
          {error && <p className="small" style={{ color: 'var(--crit)', marginBottom: 0 }}>{error}</p>}
          <button className="principal" type="submit" style={{ width: '100%', marginTop: 20 }}
                  disabled={enviando || !usuario || !clave}>
            {enviando ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      )}
    </div>
  )
}
