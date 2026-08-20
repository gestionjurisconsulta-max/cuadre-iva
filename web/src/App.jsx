import { useCallback, useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { SESION_CAIDA, salir, yo } from './api.js'
import NuevoCuadre from './paginas/NuevoCuadre.jsx'
import Resultado from './paginas/Resultado.jsx'
import Historico from './paginas/Historico.jsx'
import Entrar from './paginas/Entrar.jsx'
import Cuenta from './paginas/Cuenta.jsx'

export default function App() {
  // null = todavía no sabemos si hay sesión; false = no hay; objeto = sí.
  const [quien, setQuien] = useState(null)
  const navega = useNavigate()

  useEffect(() => {
    yo().then(setQuien).catch(() => setQuien(false))
  }, [])

  // Si la sesión caduca a media faena, se vuelve al login en vez de dejar la
  // pantalla en blanco con un error que nadie entiende.
  useEffect(() => {
    const alCaer = () => setQuien(false)
    window.addEventListener(SESION_CAIDA, alCaer)
    return () => window.removeEventListener(SESION_CAIDA, alCaer)
  }, [])

  const sal = useCallback(async () => {
    try { await salir() } catch { /* la cookie se va igual */ }
    setQuien(false)
    navega('/')
  }, [navega])

  if (quien === null) return <p className="cargando" style={{ textAlign: 'center' }}>Cargando…</p>
  if (quien === false) return <Entrar alEntrar={setQuien} />

  return (
    <>
      <header className="band">
        <div className="wrap">
          <h1>Cuadre de IVA · A3 contra Bilky</h1>
          <nav>
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'activo' : '')}>
              Nuevo cuadre
            </NavLink>
            <NavLink to="/historico" className={({ isActive }) => (isActive ? 'activo' : '')}>
              Histórico
            </NavLink>
            <NavLink to="/cuenta" className={({ isActive }) => (isActive ? 'activo' : '')}>
              {quien.nombre}
            </NavLink>
            <button className="salir" onClick={sal}>Salir</button>
          </nav>
        </div>
      </header>
      <main>
        <div className="wrap">
          <Routes>
            <Route path="/" element={<NuevoCuadre />} />
            <Route path="/cuadres/:id" element={<Resultado />} />
            <Route path="/historico" element={<Historico />} />
            <Route path="/cuenta" element={<Cuenta quien={quien} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </>
  )
}
