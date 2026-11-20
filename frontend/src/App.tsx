import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, RequireAuth } from './auth'
import Layout from './components/Layout'
import AuthDone from './pages/AuthDone'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import PortfolioPage from './pages/PortfolioPage'
import StockDetail from './pages/StockDetail'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/auth/done" element={<AuthDone />} />
            <Route
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/portfolios/:id" element={<PortfolioPage />} />
              <Route path="/stocks/:ticker" element={<StockDetail />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
