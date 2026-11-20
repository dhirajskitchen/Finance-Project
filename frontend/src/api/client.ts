const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface Ticker {
  symbol: string
  name: string
  sector: string
}

export interface PriceBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export interface PriceSeries {
  ticker: string
  prices: PriceBar[]
  last_updated: string | null
}

export type PriceRange = '1m' | '3m' | '6m' | '1y' | '5y' | 'max'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  tickers: () => get<Ticker[]>('/stocks'),
  prices: (ticker: string, range: PriceRange) =>
    get<PriceSeries>(`/stocks/${encodeURIComponent(ticker)}/prices?range=${range}`),
}
