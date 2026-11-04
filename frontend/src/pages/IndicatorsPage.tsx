import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { Card, ErrorNote, Placeholder } from '../components/ui'
import { MarketSearchPanel } from '../components/MarketSearchPanel'
import { WatchlistStar } from '../components/WatchlistButton'
import { useWatchlist } from '../hooks/useWatchlist'

export default function IndicatorsPage() {
  const [filter, setFilter] = useState('')
  const [onlyWatched, setOnlyWatched] = useState(false)
  const { list: watchlist, isWatched } = useWatchlist()
  const { data, error, isLoading } = useQuery({
    queryKey: ['indicators'],
    queryFn: async () => {
      const { data, error } = await api.GET('/indicators')
      if (error) throw error
      return data
    },
  })

  const filtered = useMemo(() => {
    if (!data) return []
    const q = filter.trim().toLowerCase()
    let rows = data
    if (q) rows = rows.filter((row) => row.code.toLowerCase().includes(q) || row.country.toLowerCase().includes(q))
    if (onlyWatched) rows = rows.filter((row) => isWatched(row.code))
    return rows
  }, [data, filter, onlyWatched, isWatched])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-100">Indicateurs collectés</h1>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={onlyWatched} onChange={(e) => setOnlyWatched(e.target.checked)} />
            ★ Ma liste de suivi {watchlist.length > 0 && `(${watchlist.length})`}
          </label>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filtrer par code ou pays…"
            className="w-64 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
          />
        </div>
      </div>

      <MarketSearchPanel />

      <Card>
        {isLoading && <Placeholder>Chargement…</Placeholder>}
        {error && <ErrorNote>Impossible de charger le catalogue d'indicateurs.</ErrorNote>}
        {data && filtered.length === 0 && (
          <Placeholder>
            {onlyWatched
              ? 'Aucune action de ta liste de suivi ne correspond à ce filtre.'
              : `Aucun indicateur ne correspond à « ${filter} ».`}
          </Placeholder>
        )}
        {filtered.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-800">
                  <th className="py-2 pr-2"></th>
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Pays</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Fréq.</th>
                  <th className="py-2 pr-4">Observations</th>
                  <th className="py-2 pr-4">Dernière donnée</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.code} className="border-b border-slate-900 hover:bg-slate-800/40">
                    <td className="py-2 pr-2">{row.connector === 'yfinance' && <WatchlistStar code={row.code} />}</td>
                    <td className="py-2 pr-4 font-mono">
                      {row.connector === 'yfinance' ? (
                        <span className="flex items-center gap-2">
                          <Link to={`/quote?code=${encodeURIComponent(row.code)}`} className="text-sky-400 hover:underline">
                            {row.code}
                          </Link>
                          <Link
                            to={`/forecast?code=${encodeURIComponent(row.code)}`}
                            className="text-xs text-slate-500 hover:text-sky-400 hover:underline"
                          >
                            prévision →
                          </Link>
                        </span>
                      ) : (
                        row.code
                      )}
                    </td>
                    <td className="py-2 pr-4">{row.country}</td>
                    <td className="py-2 pr-4 text-slate-400">{row.connector}</td>
                    <td className="py-2 pr-4 text-slate-400">{row.frequency}</td>
                    <td className="py-2 pr-4 font-mono tabular-nums">{row.n_obs.toLocaleString('fr-FR')}</td>
                    <td className="py-2 pr-4 text-slate-400">{row.last_timestamp ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
