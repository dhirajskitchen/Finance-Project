import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type Holding } from '../api/client'

function HoldingRow({ portfolioId, h, onChanged }: { portfolioId: number; h: Holding; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [qty, setQty] = useState(String(h.quantity))
  const [price, setPrice] = useState(String(h.avg_price))

  const save = useMutation({
    mutationFn: () => api.updateHolding(portfolioId, h.id, { quantity: Number(qty), avg_price: Number(price) }),
    onSuccess: () => {
      setEditing(false)
      onChanged()
    },
  })
  const remove = useMutation({ mutationFn: () => api.deleteHolding(portfolioId, h.id), onSuccess: onChanged })
  const error = save.error ?? remove.error

  return (
    <>
      <tr>
        <td>
          <Link to={`/stocks/${h.ticker}`}>{h.ticker}</Link>
        </td>
        <td>
          {editing ? (
            <input type="number" min="0" step="any" value={qty} onChange={(e) => setQty(e.target.value)} aria-label="Quantity" />
          ) : (
            h.quantity
          )}
        </td>
        <td>
          {editing ? (
            <input type="number" min="0" step="any" value={price} onChange={(e) => setPrice(e.target.value)} aria-label="Average price" />
          ) : (
            h.avg_price.toFixed(2)
          )}
        </td>
        <td className="actions">
          {editing ? (
            <>
              <button className="primary" onClick={() => save.mutate()} disabled={save.isPending}>Save</button>
              <button onClick={() => setEditing(false)}>Cancel</button>
            </>
          ) : (
            <>
              <button onClick={() => setEditing(true)}>Edit</button>
              <button onClick={() => remove.mutate()} disabled={remove.isPending}>Delete</button>
            </>
          )}
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={4} className="error">{error.message}</td>
        </tr>
      )}
    </>
  )
}

export default function PortfolioPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [qty, setQty] = useState('')
  const [price, setPrice] = useState('')

  const portfolio = useQuery({ queryKey: ['portfolio', id], queryFn: () => api.portfolio(id), enabled: Number.isFinite(id) })
  const tickers = useQuery({ queryKey: ['tickers'], queryFn: api.tickers })

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['portfolio', id] })
    void qc.invalidateQueries({ queryKey: ['portfolios'] })
  }

  const add = useMutation({
    mutationFn: () => api.addHolding(id, { ticker, quantity: Number(qty), avg_price: Number(price) }),
    onSuccess: () => {
      setTicker('')
      setQty('')
      setPrice('')
      refresh()
    },
  })
  const del = useMutation({
    mutationFn: () => api.deletePortfolio(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['portfolios'] })
      navigate('/')
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate()
  }

  if (portfolio.isPending) return <main><p className="muted">Loading…</p></main>
  if (portfolio.isError)
    return (
      <main>
        <p className="error">{portfolio.error.message}</p>
        <Link to="/">Back to portfolios</Link>
      </main>
    )

  const held = new Set(portfolio.data.holdings.map((h) => h.ticker))

  return (
    <main>
      <div className="row">
        <Link to="/">← Portfolios</Link>
      </div>
      <header className="row">
        <h1>{portfolio.data.name}</h1>
        <span className="spacer" />
        <button
          onClick={() => {
            if (window.confirm(`Delete "${portfolio.data.name}" and all its holdings?`)) del.mutate()
          }}
        >
          Delete portfolio
        </button>
      </header>

      <table>
        <thead>
          <tr><th>Ticker</th><th>Quantity</th><th>Avg price</th><th /></tr>
        </thead>
        <tbody>
          {portfolio.data.holdings.map((h) => (
            <HoldingRow key={h.id} portfolioId={id} h={h} onChanged={refresh} />
          ))}
          {portfolio.data.holdings.length === 0 && (
            <tr><td colSpan={4} className="muted">No holdings yet.</td></tr>
          )}
        </tbody>
      </table>

      <h2>Add holding</h2>
      <form className="row" onSubmit={submit}>
        <select value={ticker} onChange={(e) => setTicker(e.target.value)} required aria-label="Ticker">
          <option value="">Ticker…</option>
          {tickers.data?.filter((t) => !held.has(t.symbol)).map((t) => (
            <option key={t.symbol} value={t.symbol}>{t.symbol} — {t.name}</option>
          ))}
        </select>
        <input type="number" min="0" step="any" placeholder="Quantity" value={qty} onChange={(e) => setQty(e.target.value)} required aria-label="Quantity" />
        <input type="number" min="0" step="any" placeholder="Avg price" value={price} onChange={(e) => setPrice(e.target.value)} required aria-label="Average price" />
        <button className="primary" disabled={add.isPending}>Add</button>
      </form>
      {add.isError && <p className="error">{add.error.message}</p>}
    </main>
  )
}
