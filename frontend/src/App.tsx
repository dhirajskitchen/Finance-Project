import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import StockDetail from './pages/StockDetail'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60_000, retry: 1 } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/stocks/:ticker" element={<StockDetail />} />
          <Route path="*" element={<Navigate to="/stocks/AAPL" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
