import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import NuevoCuadre from './paginas/NuevoCuadre.jsx'
import Resultado from './paginas/Resultado.jsx'
import Historico from './paginas/Historico.jsx'

export default function App() {
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
          </nav>
        </div>
      </header>
      <main>
        <div className="wrap">
          <Routes>
            <Route path="/" element={<NuevoCuadre />} />
            <Route path="/cuadres/:id" element={<Resultado />} />
            <Route path="/historico" element={<Historico />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </>
  )
}
