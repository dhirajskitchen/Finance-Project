import { Navigate, useSearchParams } from 'react-router-dom'
import { BASE } from '../api/client'
import { useAuth } from '../auth'

const ERRORS: Record<string, string> = {
  oauth: 'Google sign-in was cancelled or failed. Please try again.',
  email: 'Your Google account needs a verified email address.',
}

export default function Login() {
  const { user, loading } = useAuth()
  const [params] = useSearchParams()
  const error = params.get('error')

  if (!loading && user) return <Navigate to="/" replace />

  return (
    <main className="narrow">
      <h1>Portfolio Risk &amp; Signal Dashboard</h1>
      <p className="muted">Sign in to build portfolios and see risk analytics and explainable signals.</p>
      {error && <p className="error">{ERRORS[error] ?? 'Sign-in failed.'}</p>}
      <a className="button primary" href={`${BASE}/auth/login`}>
        Sign in with Google
      </a>
      <p className="muted">Educational tool, not financial advice.</p>
    </main>
  )
}
