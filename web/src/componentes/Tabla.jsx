// Tabla mínima: columnas declaradas como {clave, titulo, n?, pinta?}.
export default function Tabla({ columnas, filas, vacio = 'Nada que mostrar.', limite }) {
  if (!filas?.length) return <p className="muted small">{vacio}</p>
  const vistas = limite ? filas.slice(0, limite) : filas
  return (
    <>
      <div className="tw">
        <table>
          <thead>
            <tr>{columnas.map((c) => <th key={c.clave} className={c.n ? 'n' : ''}>{c.titulo}</th>)}</tr>
          </thead>
          <tbody>
            {vistas.map((f, i) => (
              <tr key={i}>
                {columnas.map((c) => (
                  <td key={c.clave} className={[c.n ? 'n' : '', c.mono ? 'mono' : ''].join(' ').trim()}>
                    {c.pinta ? c.pinta(f) : f[c.clave]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {limite && filas.length > limite && (
        <p className="small muted" style={{ marginTop: 8 }}>
          Se muestran {limite} de {filas.length}. El listado completo está en el Excel.
        </p>
      )}
    </>
  )
}
