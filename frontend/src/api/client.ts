export const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

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

export interface Signal {
  ticker: string
  date: string
  horizon_days: number
  prediction: 'down' | 'flat' | 'up'
  action: 'sell' | 'hold' | 'buy'
  probability: number
  probabilities: Record<'down' | 'flat' | 'up', number>
  model_version: string
  disclaimer: string
}

export interface ModelError {
  mae: number
  mape: number
  direction_accuracy: number | null
}

export interface Forecast {
  ticker: string
  last_close: number
  last_date: string
  forecast: { date: string; ets: number; naive: number }[]
  evaluation: {
    window_days: number
    naive: ModelError
    ets: ModelError
    ets_beats_naive: boolean
    mae_improvement_pct: number
  }
  note: string
}

export type PriceRange = '1m' | '3m' | '6m' | '1y' | '5y' | 'max'

export interface User {
  id: number
  email: string
}

export interface Holding {
  id: number
  ticker: string
  quantity: number
  avg_price: number
}

export interface Portfolio {
  id: number
  name: string
  holdings: Holding[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// The access token lives only in memory; the refresh token is an httpOnly cookie the page can't read.
let accessToken: string | null = null

// Refresh tokens rotate on every use, so concurrent refreshes must share one request
// (a second use of the same token would look like theft and end the session).
let inflightRefresh: Promise<string | null> | null = null

export function refreshSession(): Promise<string | null> {
  inflightRefresh ??= (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
      if (!res.ok) {
        accessToken = null
        return null
      }
      accessToken = ((await res.json()) as { access_token: string }).access_token
      return accessToken
    } catch {
      return null
    } finally {
      inflightRefresh = null
    }
  })()
  return inflightRefresh
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {})
  accessToken = null
}

async function errorFrom(res: Response): Promise<ApiError> {
  let detail = res.statusText
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') detail = body.detail
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, detail)
}

async function request<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  const send = () =>
    fetch(`${BASE}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(auth && accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
    })
  let res = await send()
  if (auth && res.status === 401 && (await refreshSession())) res = await send()
  if (!res.ok) throw await errorFrom(res)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) })

export const api = {
  tickers: () => request<Ticker[]>('/stocks'),
  prices: (ticker: string, range: PriceRange) =>
    request<PriceSeries>(`/stocks/${encodeURIComponent(ticker)}/prices?range=${range}`),

  signal: (ticker: string) => request<Signal>(`/stocks/${encodeURIComponent(ticker)}/signal`),
  forecast: (ticker: string) => request<Forecast>(`/stocks/${encodeURIComponent(ticker)}/forecast`),

  me: () => request<User>('/auth/me', {}, true),
  portfolios: () => request<Portfolio[]>('/portfolios', {}, true),
  portfolio: (id: number) => request<Portfolio>(`/portfolios/${id}`, {}, true),
  createPortfolio: (name: string) => request<Portfolio>('/portfolios', json('POST', { name }), true),
  renamePortfolio: (id: number, name: string) =>
    request<Portfolio>(`/portfolios/${id}`, json('PUT', { name }), true),
  deletePortfolio: (id: number) => request<void>(`/portfolios/${id}`, { method: 'DELETE' }, true),
  addHolding: (id: number, h: { ticker: string; quantity: number; avg_price: number }) =>
    request<Holding>(`/portfolios/${id}/holdings`, json('POST', h), true),
  updateHolding: (id: number, hid: number, h: { quantity: number; avg_price: number }) =>
    request<Holding>(`/portfolios/${id}/holdings/${hid}`, json('PUT', h), true),
  deleteHolding: (id: number, hid: number) =>
    request<void>(`/portfolios/${id}/holdings/${hid}`, { method: 'DELETE' }, true),
}
