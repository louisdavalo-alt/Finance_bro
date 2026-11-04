import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, apiErrorMessage } from '../api/client'
import { CandlestickChart } from './CandlestickChart'
import { Card, ErrorNote, Placeholder, Spinner } from './ui'

/** Recherche libre d'actions absentes du catalogue (`/indicators`) auprès de Yahoo Finance, pour
 * l'onglet « Indicateurs » (voir `IndicatorsPage.tsx`). Une fois un symbole chargé (aperçu en
 * direct, rien stocké), deux choix : l'ajouter à la bibliothèque active — ce qui rapatrie aussi
 * tout son historique dans le cache local — ou juste l'observer, sans rien persister. */
export function MarketSearchPanel() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  // Nom déjà connu via /market-search, conservé pour l'aperçu : /market-lookup ne le redemande
  // pas (voir sa docstring côté API) pour rester un appel aussi léger que /quote.
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(null)
  const [activatedCode, setActivatedCode] = useState<string | null>(null)
  const symbol = selected?.symbol ?? null

  const search = useQuery({
    queryKey: ['market-search', submittedQuery],
    enabled: submittedQuery.length > 0,
    queryFn: async () => {
      const { data, error } = await api.GET('/market-search', { params: { query: { q: submittedQuery, limit: 10 } } })
      if (error) throw error
      return data
    },
  })

  const lookup = useQuery({
    queryKey: ['market-lookup', symbol],
    enabled: !!symbol,
    queryFn: async () => {
      const { data, error } = await api.GET('/market-lookup/{symbol}', { params: { path: { symbol: symbol! } } })
      if (error) throw error
      return data
    },
  })

  const lookupOhlc = useQuery({
    queryKey: ['market-lookup-ohlc', symbol],
    enabled: !!symbol,
    queryFn: async () => {
      const { data, error } = await api.GET('/market-lookup/{symbol}/ohlc', {
        params: { path: { symbol: symbol! }, query: { period: '1y' } },
      })
      if (error) throw error
      return data
    },
  })

  const activate = useMutation({
    mutationFn: async (s: { symbol: string; name: string }) => {
      const { data, error } = await api.POST('/market-activate', {
        body: { symbol: s.symbol, name: s.name || undefined },
      })
      if (error) throw error
      return data
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['indicators'] })
      setActivatedCode(created.code)
    },
  })

  function onSearchSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSelected(null)
    setActivatedCode(null)
    setSubmittedQuery(query.trim())
  }

  function closePreview() {
    setSelected(null)
    setActivatedCode(null)
  }

  return (
    <Card title="Rechercher une action absente du catalogue">
      <p className="mb-3 text-sm text-slate-400">
        Recherche libre auprès de Yahoo Finance — pour une action qui n'apparaît pas dans le tableau ci-dessous.
      </p>
      <form onSubmit={onSearchSubmit} className="flex flex-wrap items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Nom ou symbole (ex. Rivian, RIVN)…"
          className="w-64 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <button type="submit" className="rounded-md bg-sky-500 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400">
          Rechercher
        </button>
      </form>

      {search.isLoading && (
        <div className="mt-3 flex items-center gap-2 text-slate-400">
          <Spinner /> Recherche…
        </div>
      )}
      {search.error && (
        <div className="mt-3">
          <ErrorNote>{apiErrorMessage(search.error)}</ErrorNote>
        </div>
      )}
      {search.data && search.data.length === 0 && (
        <div className="mt-3">
          <Placeholder>Aucun résultat pour « {submittedQuery} ».</Placeholder>
        </div>
      )}

      {search.data && search.data.length > 0 && !symbol && (
        <ul className="mt-3 flex flex-col divide-y divide-slate-800">
          {search.data.map((r) => (
            <li key={r.symbol} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div>
                <span className="font-mono text-slate-100">{r.symbol}</span>
                <span className="ml-2 text-slate-400">{r.name}</span>
                {r.exchange && <span className="ml-2 text-xs text-slate-500">{r.exchange}</span>}
              </div>
              {r.already_tracked ? (
                <span className="text-xs text-slate-500">déjà suivi — {r.code}</span>
              ) : (
                <button
                  onClick={() => {
                    setActivatedCode(null)
                    setSelected({ symbol: r.symbol, name: r.name })
                  }}
                  className="rounded-md border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800"
                >
                  Charger →
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {symbol && (
        <div className="mt-4 border-t border-slate-800 pt-4">
          {(lookup.isLoading || lookupOhlc.isLoading) && (
            <div className="flex items-center gap-2 text-slate-400">
              <Spinner /> Chargement de {symbol}…
            </div>
          )}
          {lookup.error && <ErrorNote>{apiErrorMessage(lookup.error)}</ErrorNote>}

          {lookup.data && (
            <>
              <div className="mb-3 flex items-baseline justify-between">
                <div>
                  <span className="font-mono text-lg text-slate-100">{symbol}</span>
                  {(lookup.data.name || selected?.name) && (
                    <span className="ml-2 text-slate-400">{lookup.data.name ?? selected?.name}</span>
                  )}
                </div>
                {lookup.data.last != null && (
                  <span className="font-mono text-lg tabular-nums text-slate-100">
                    {lookup.data.last.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{' '}
                    <span className="text-sm text-slate-400">{lookup.data.currency}</span>
                  </span>
                )}
              </div>

              {lookupOhlc.data && lookupOhlc.data.length > 0 && <CandlestickChart bars={lookupOhlc.data} height={260} />}

              {activatedCode ? (
                <div className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
                  Ajouté à la bibliothèque active sous le code <span className="font-mono">{activatedCode}</span> — historique
                  rapatrié dans le cache, visible dans le tableau ci-dessous.
                </div>
              ) : (
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <p className="text-xs text-slate-500">
                    « Ajouter » rapatrie tout l'historique dans le cache local et fait apparaître {symbol} dans le tableau,
                    comme n'importe quel autre indicateur. « Juste observer » referme cet aperçu sans rien enregistrer.
                  </p>
                </div>
              )}

              {!activatedCode && (
                <div className="mt-3 flex items-center gap-3">
                  <button
                    onClick={() => selected && activate.mutate(selected)}
                    disabled={activate.isPending}
                    className="rounded-md bg-sky-500 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-60"
                  >
                    {activate.isPending ? 'Ajout en cours…' : 'Ajouter à la bibliothèque active'}
                  </button>
                  <button
                    onClick={closePreview}
                    className="rounded-md border border-slate-700 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
                  >
                    Juste observer (fermer)
                  </button>
                </div>
              )}
              {activate.error && (
                <div className="mt-3">
                  <ErrorNote>{apiErrorMessage(activate.error)}</ErrorNote>
                </div>
              )}
              {activatedCode && (
                <button onClick={closePreview} className="mt-3 text-sm text-slate-400 hover:text-slate-200 hover:underline">
                  Fermer
                </button>
              )}
            </>
          )}
        </div>
      )}
    </Card>
  )
}
