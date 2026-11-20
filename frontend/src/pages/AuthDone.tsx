import { useEffect } from 'react'

// The API redirects here after setting the refresh cookie. A full reload lets AuthProvider
// pick the session up from the cookie, which is simpler than threading state through the router.
export default function AuthDone() {
  useEffect(() => {
    window.location.replace('/')
  }, [])
  return <main><p className="muted">Signing you in…</p></main>
}
