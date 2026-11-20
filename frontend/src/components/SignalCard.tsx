import type { Signal } from '../api/client'

const ORDER = ['down', 'flat', 'up'] as const
const LABEL = { down: 'Down', flat: 'Flat', up: 'Up' } as const

// A top class under ~45% means the model has no strong view; say so instead of showing a confident "buy".
const LOW_CONVICTION = 0.45

export default function SignalCard({ signal }: { signal: Signal }) {
  const low = signal.probability < LOW_CONVICTION
  return (
    <section className="card" aria-label="Trading signal">
      <h2>
        Signal: <span className={`pill ${signal.action}`}>{signal.action.toUpperCase()}</span>
      </h2>
      <p className="muted">
        Next {signal.horizon_days} trading days, as of {signal.date}.{' '}
        {low && <strong>Low conviction: the model has no strong view.</strong>}
      </p>
      <div className="bars">
        {ORDER.map((c) => (
          <div key={c} className="bar-row">
            <span>{LABEL[c]}</span>
            <div className="bar-track">
              <div className={`bar-fill ${c}`} style={{ width: `${signal.probabilities[c] * 100}%` }} />
            </div>
            <span>{(signal.probabilities[c] * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
      <p className="muted">
        {signal.disclaimer} Model {signal.model_version}.
      </p>
    </section>
  )
}
