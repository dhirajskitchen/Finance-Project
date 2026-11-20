import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, logout as apiLogout, refreshSession, type User } from './api/client'

interface AuthState {
  user: User | null
  loading: boolean
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const queryClient = useQueryClient()

  // Restore the session on page load: the refresh cookie yields a fresh in-memory access token.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const token = await refreshSession()
      const me = token ? await api.me().catch(() => null) : null
      if (!cancelled) {
        setUser(me)
        setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const signOut = useCallback(async () => {
    await apiLogout()
    queryClient.clear() // drop cached portfolio data so the next user never sees it
    setUser(null)
  }, [queryClient])

  const value = useMemo(() => ({ user, loading, signOut }), [user, loading, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <main><p className="muted">Loading…</p></main>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}
