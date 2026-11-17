import { useEffect, useState } from 'react'

// El CSS ya sabe de tres temas: el del sistema (prefers-color-scheme) y las dos
// anulaciones por data-theme. Faltaba el mando. Esto lo pone en la cabecera y
// recuerda la elección; mientras no se toca nada, se sigue al sistema.

function IconoSol() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

function IconoLuna() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  )
}

function guardado() {
  try {
    const g = localStorage.getItem('tema')
    if (g === 'light' || g === 'dark') return g
  } catch { /* sin localStorage (modo privado, etc.) */ }
  return null
}

// null = automático: se sigue al sistema hasta que el usuario elige una vez.
export default function Tema() {
  const [tema, setTema] = useState(guardado)

  useEffect(() => {
    const raiz = document.documentElement
    if (tema) {
      raiz.dataset.theme = tema
      try { localStorage.setItem('tema', tema) } catch { /* sin localStorage */ }
    } else {
      delete raiz.dataset.theme
      try { localStorage.removeItem('tema') } catch { /* sin localStorage */ }
    }
  }, [tema])

  const oscuro = tema
    ? tema === 'dark'
    : !!window.matchMedia?.('(prefers-color-scheme: dark)').matches

  return (
    <button type="button" className="tema"
            aria-label={oscuro ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
            title={oscuro ? 'Tema claro' : 'Tema oscuro'}
            onClick={() => setTema(oscuro ? 'light' : 'dark')}>
      {oscuro ? <IconoSol /> : <IconoLuna />}
    </button>
  )
}
