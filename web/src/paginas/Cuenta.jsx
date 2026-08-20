import { useState } from 'react'
import { cambiaClave } from '../api.js'

export default function Cuenta({ quien }) {
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repite, setRepite] = useState('')
  const [error, setError] = useState(null)
  const [hecho, setHecho] = useState(false)

  async function envia(e) {
    e.preventDefault()
    setError(null)
    if (nueva !== repite) return setError('La nueva contraseña y su repetición no coinciden.')
    try {
      await cambiaClave(actual, nueva)
      setHecho(true)
    } catch (err) {
      setError(err.message)
    }
  }

  if (hecho) {
    return (
      <section className="tarjeta">
        <h2>Contraseña cambiada</h2>
        <p className="muted">
          Se han cerrado todas las sesiones, también ésta. Vuelve a entrar con la nueva.
        </p>
        <button className="principal" onClick={() => window.location.reload()}>Entrar de nuevo</button>
      </section>
    )
  }

  return (
    <>
      <section>
        <p className="sec-label">Tu cuenta</p>
        <h2>{quien.nombre}</h2>
        <p className="muted small">Usuario <span className="mono">{quien.usuario}</span></p>
      </section>

      <section className="tarjeta" style={{ maxWidth: 460 }}>
        <h3>Cambiar la contraseña</h3>
        <p className="small muted">
          Al cambiarla se cierran todas las sesiones abiertas, incluida ésta.
        </p>
        <form onSubmit={envia} style={{ marginTop: 14 }}>
          <label className="small muted" htmlFor="actual">Contraseña actual</label>
          <input id="actual" type="password" value={actual} autoComplete="current-password"
                 onChange={(e) => setActual(e.target.value)} />
          <label className="small muted" htmlFor="nueva" style={{ marginTop: 12 }}>Nueva</label>
          <input id="nueva" type="password" value={nueva} autoComplete="new-password"
                 onChange={(e) => setNueva(e.target.value)} />
          <label className="small muted" htmlFor="repite" style={{ marginTop: 12 }}>Repítela</label>
          <input id="repite" type="password" value={repite} autoComplete="new-password"
                 onChange={(e) => setRepite(e.target.value)} />
          <p className="small faint" style={{ margin: '8px 0 0' }}>Al menos 10 caracteres.</p>
          {error && <p className="small" style={{ color: 'var(--crit)' }}>{error}</p>}
          <button className="principal" type="submit" style={{ marginTop: 16 }}
                  disabled={!actual || nueva.length < 10}>
            Cambiar
          </button>
        </form>
      </section>
    </>
  )
}
