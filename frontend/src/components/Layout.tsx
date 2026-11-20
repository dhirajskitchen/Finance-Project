import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Layout() {
  const { user, signOut } = useAuth()
  return (
    <>
      <nav className="nav">
        <Link to="/">Portfolios</Link>
        <Link to="/stocks/AAPL">Stocks</Link>
        <span className="spacer" />
        {user && <span className="muted">{user.email}</span>}
        <button onClick={() => void signOut()}>Sign out</button>
      </nav>
      <Outlet />
    </>
  )
}
