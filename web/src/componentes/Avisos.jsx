import { useState } from 'react'

// Los graves se ven siempre; el resto se pliega, que en un trimestre normal son
// treinta y tantos y taparían lo importante.
export default function Avisos({ avisos }) {
  const [abierto, setAbierto] = useState(false)
  if (!avisos?.length) return null
  const graves = avisos.filter((a) => a.nivel === 'grave')
  const resto = avisos.filter((a) => a.nivel !== 'grave')

  return (
    <section>
      {graves.map((a, i) => (
        <div key={i} className="aviso grave">
          <span className="et">grave</span>
          <span>{a.texto}</span>
        </div>
      ))}
      {resto.length > 0 && (
        <>
          <button className="secundaria" onClick={() => setAbierto(!abierto)}
                  style={{ marginTop: graves.length ? 10 : 0 }}>
            {abierto ? 'Ocultar' : 'Ver'} los {resto.length} avisos restantes
          </button>
          {abierto && (
            <div style={{ marginTop: 10 }}>
              {resto.map((a, i) => (
                <div key={i} className={`aviso ${a.nivel === 'info' ? 'info' : 'aviso_'}`}>
                  <span className="et">{a.nivel}</span>
                  <span>{a.texto}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
