import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type PriceRange } from '../api/client'
import ForecastPanel from '../components/ForecastPanel'
import PriceChart from '../components/PriceChart'
import SignalCard from '../components/SignalCard'

const RANGES: PriceRange[] = ['1m', '3m', '6m', '1y', '5y', 'max']

export default function StockDetail() {
  const { ticker = 'AAPL' } = useParams()
  const navigate = useNavigate()
  const [range, setRange] = useState<PriceRange>('1y')

  const tickers = useQuery({ queryKey: ['tickers'], queryFn: api.tickers })
  const prices = useQuery({
    queryKey: ['prices', ticker, range],
    queryFn: () => api.prices(ticker, range),
  })

  const signal = useQuery({ queryKey: ['signal', ticker], queryFn: () => api.signal(ticker), retry: false })
  const forecast = useQuery({ queryKey: ['forecast', ticker], queryFn: () => api.forecast(ticker), retry: false })

  return (
    <main>
      <header className="row">
        <h1>Stock Detail</h1>
        <select value={ticker} onChange={(e) => navigate(`/stocks/${e.target.value}`)}>
          {(tickers.data ?? [{ symbol: ticker, name: ticker, sector: '' }]).map((t) => (
            <option key={t.symbol} value={t.symbol}>
              {t.symbol} — {t.name}
            </option>
          ))}
        </select>
      </header>

      <div className="row">
        {RANGES.map((r) => (
          <button key={r} className={r === range ? 'active' : ''} onClick={() => setRange(r)}>
            {r.toUpperCase()}
          </button>
        ))}
      </div>

      {prices.isPending && <p className="muted">Loading… (the API may take a moment to wake up)</p>}
      {prices.isError && <p className="error">Could not load prices: {prices.error.message}</p>}
      {prices.data && (
        <>
          <PriceChart prices={prices.data.prices} />
          <p className="muted">
            Last updated: {prices.data.last_updated ?? 'never'} · Educational tool, not financial advice.
          </p>
        </>
      )}

      {signal.data && <SignalCard signal={signal.data} />}
      {signal.isError && <p className="muted">No signal available for this ticker yet.</p>}
      {forecast.data && <ForecastPanel data={forecast.data} />}
    </main>
  )
}
