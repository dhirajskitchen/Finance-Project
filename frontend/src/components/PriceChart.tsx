import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PriceBar } from '../api/client'

export default function PriceChart({ prices }: { prices: PriceBar[] }) {
  if (prices.length === 0) {
    return <p className="muted">No cached prices for this ticker yet.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={360}>
      <LineChart data={prices} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
        <XAxis dataKey="date" minTickGap={48} tick={{ fill: 'var(--muted)', fontSize: 12 }} />
        <YAxis
          domain={['auto', 'auto']}
          width={56}
          tick={{ fill: 'var(--muted)', fontSize: 12 }}
          tickFormatter={(v: number) => v.toFixed(0)}
        />
        <Tooltip formatter={(v) => [Number(v).toFixed(2), 'Close']} />
        <Line type="monotone" dataKey="close" stroke="var(--accent)" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  )
}
