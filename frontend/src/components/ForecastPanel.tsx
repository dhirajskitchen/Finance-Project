import type { Forecast } from '../api/client'

const pct = (v: number) => `${(v * 100).toFixed(2)}%`

export default function ForecastPanel({ data }: { data: Forecast }) {
  const ev = data.evaluation
  return (
    <section className="card" aria-label="Price forecast">
      <h2>Forecast vs. naive baseline</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Smoothing model</th>
            <th>Naive (= last close)</th>
          </tr>
        </thead>
        <tbody>
          {data.forecast.map((p) => (
            <tr key={p.date}>
              <td>{p.date}</td>
              <td>{p.ets.toFixed(2)}</td>
              <td>{p.naive.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Over the last {ev.window_days} days, one-step-ahead error was{' '}
        <strong>{pct(ev.ets.mape)}</strong> for the smoothing model vs <strong>{pct(ev.naive.mape)}</strong> for
        naive.{' '}
        {ev.ets_beats_naive
          ? `The smoothing model was ${ev.mae_improvement_pct.toFixed(1)}% better.`
          : 'The smoothing model did not beat naive.'}
      </p>
      <p className="muted">{data.note}</p>
    </section>
  )
}
