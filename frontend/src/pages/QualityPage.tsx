import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { api, apiErrorMessage } from '../api/client'
import { Card, ErrorNote, Placeholder, Spinner } from '../components/ui'

type SortKey = 'indicator_code' | 'median_lag_days' | 'n_obs'

export default function QualityPage() {
  const [sortKey, setSortKey] = useState<SortKey>('median_lag_days')
  const [sortDir, setSortDir] = useState<1 | -1>(-1)

  const { data, error, isLoading } = useQuery({
    queryKey: ['lag-report'],
    queryFn: async () => {
      const { data, error } = await api.GET('/lag-report')
      if (error) throw error
      return data
    },
  })

  const rows = useMemo(() => {
    if (!data) return []
    return [...data].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av === bv) return 0
      if (av === null || av === undefined) return 1
      if (bv === null || bv === undefined) return -1
      return sortDir * (av > bv ? 1 : -1)
    })
  }, [data, sortKey, sortDir])

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortDir(sortDir === 1 ? -1 : 1)
    else {
      setSortKey(key)
      setSortDir(-1)
    }
  }

  function arrow(key: SortKey) {
    return key === sortKey ? (sortDir === 1 ? ' ▲' : ' ▼') : ''
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Qualité des données</h1>
      <p className="max-w-3xl text-sm text-slate-400">
        Écart réel observé entre la période décrite par une observation et sa date de publication estimée, par
        indicateur — permet de repérer les sources particulièrement en retard, à prendre en compte pour tout calcul
        « au jour le jour » (voir le traitement du biais de look-ahead dans <code>resample.py</code>).
      </p>

      <Card>
        {isLoading && (
          <div className="flex items-center gap-2 text-slate-400">
            <Spinner /> Chargement…
          </div>
        )}
        {error && <ErrorNote>{apiErrorMessage(error)}</ErrorNote>}
        {data && data.length === 0 && <Placeholder>Aucune donnée de décalage disponible.</Placeholder>}
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-800">
                  <th className="cursor-pointer py-2 pr-4 hover:text-slate-300" onClick={() => sortBy('indicator_code')}>
                    Indicateur{arrow('indicator_code')}
                  </th>
                  <th className="cursor-pointer py-2 pr-4 hover:text-slate-300" onClick={() => sortBy('median_lag_days')}>
                    Décalage médian (j){arrow('median_lag_days')}
                  </th>
                  <th className="cursor-pointer py-2 pr-4 hover:text-slate-300" onClick={() => sortBy('n_obs')}>
                    Observations{arrow('n_obs')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.indicator_code} className="border-b border-slate-900 hover:bg-slate-800/40">
                    <td className="py-2 pr-4 font-mono">{r.indicator_code}</td>
                    <td className="py-2 pr-4 font-mono tabular-nums">
                      {r.median_lag_days === null || r.median_lag_days === undefined ? '—' : Math.round(r.median_lag_days)}
                    </td>
                    <td className="py-2 pr-4 font-mono tabular-nums">{r.n_obs.toLocaleString('fr-FR')}</td>
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
