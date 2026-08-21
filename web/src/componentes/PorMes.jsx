import { eur } from '../formato.js'

// Barras de cuota por mes, en CSS. Una librería de gráficas por un solo gráfico
// serían 200 KB más de bundle y otra dependencia que mantener.
export default function PorMes({ datos }) {
  if (!datos?.length || datos.length < 2) return null
  const tope = Math.max(...datos.flatMap((d) => [Math.abs(d.a3), Math.abs(d.bilky)])) || 1

  return (
    <figure className="por-mes">
      <figcaption className="small muted">
        Cuota por mes de factura
        <span className="leyenda"><i className="c-a3" /> A3</span>
        <span className="leyenda"><i className="c-bk" /> Bilky</span>
      </figcaption>
      <div className="barras">
        {datos.map((d) => (
          <div key={d.mes} className="mes" title={`${d.mes}\nA3: ${eur(d.a3)} €\nBilky: ${eur(d.bilky)} €`}>
            <div className="par">
              <span className="b c-a3" style={{ height: `${(100 * Math.abs(d.a3)) / tope}%` }} />
              <span className="b c-bk" style={{ height: `${(100 * Math.abs(d.bilky)) / tope}%` }} />
            </div>
            <span className="etiq">{d.mes.slice(5)}/{d.mes.slice(2, 4)}</span>
          </div>
        ))}
      </div>
    </figure>
  )
}
