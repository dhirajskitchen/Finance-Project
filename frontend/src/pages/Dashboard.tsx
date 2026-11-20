import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

export default function Dashboard() {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const portfolios = useQuery({ queryKey: ['portfolios'], queryFn: api.portfolios })

  const create = useMutation({
    mutationFn: (n: string) => api.createPortfolio(n),
    onSuccess: () => {
      setName('')
      return qc.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (name.trim()) create.mutate(name.trim())
  }

  return (
    <main>
      <h1>Your portfolios</h1>
      <form className="row" onSubmit={submit}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New portfolio name"
          maxLength={100}
          aria-label="New portfolio name"
        />
        <button className="primary" disabled={create.isPending || !name.trim()}>
          Create
        </button>
      </form>
      {create.isError && <p className="error">{create.error.message}</p>}

      {portfolios.isPending && <p className="muted">Loading…</p>}
      {portfolios.isError && <p className="error">{portfolios.error.message}</p>}
      {portfolios.data?.length === 0 && <p className="muted">No portfolios yet. Create one above.</p>}
      <ul className="cards">
        {portfolios.data?.map((p) => (
          <li key={p.id}>
            <Link to={`/portfolios/${p.id}`}>
              <strong>{p.name}</strong>
              <span className="muted">{p.holdings.length} holdings</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  )
}
