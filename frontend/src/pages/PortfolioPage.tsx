import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, apiErrorMessage } from '../api/client'
import { Card, Delta, ErrorNote, Num, Placeholder, Spinner } from '../components/ui'
import { FanChart } from '../components/FanChart'

type Risk = 'faible' | 'modere' | 'eleve'

export default function PortfolioPage() {
  const [countries, setCountries] = useState<string[]>([])
  const [sectors, setSectors] = useState<string[]>([])
  const [risk, setRisk] = useState<Risk>('modere')
  const [monteCarlo, setMonteCarlo] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const universe = useQuery({
    queryKey: ['portfolio-universe'],
    queryFn: async () => {
      const { data, error } = await api.GET('/portfolio/universe')
      if (error) throw error
      return data
    },
  })

  const portfolio = useQuery({
    queryKey: ['portfolio', countries, sectors, risk, monteCarlo],
    enabled: submitted,
    queryFn: async () => {
      const { data, error } = await api.GET('/portfolio', {
        params: { query: { country: countries, sector: sectors, risk, monte_carlo: monteCarlo } },
      })
      if (error) throw error
      return data
    },
  })

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Constructeur de portefeuille</h1>
      <p className="max-w-3xl text-sm text-slate-400">
        ⚠️ Outil d'aide à la réflexion sur des compromis rendement/risque, pas un conseil en investissement — optimisation
        moyenne-variance sur l'historique déjà collecté par le pipeline.
      </p>

      <Card title="Filtres">
        {universe.isLoading && <Spinner />}
        {universe.data && (
          <div className="flex flex-col gap-4">
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Pays (vide = tous)</div>
              <div className="flex flex-wrap gap-2">
                {universe.data.countries.map((c) => (
                  <button
                    key={c}
                    onClick={() => toggle(countries, setCountries, c)}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      countries.includes(c) ? 'border-sky-500 bg-sky-500/15 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Secteurs (vide = tous)</div>
              <div className="flex flex-wrap gap-2">
                {universe.data.sectors.map((s) => (
                  <button
                    key={s}
                    onClick={() => toggle(sectors, setSectors, s)}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      sectors.includes(s) ? 'border-sky-500 bg-sky-500/15 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex overflow-hidden rounded-md border border-slate-700">
                {(['faible', 'modere', 'eleve'] as Risk[]).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRisk(r)}
                    className={`px-3 py-1.5 text-sm capitalize ${risk === r ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'}`}
                  >
                    {r}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={monteCarlo} onChange={(e) => setMonteCarlo(e.target.checked)} />
                Évaluer par Monte Carlo
              </label>
              <button
                onClick={() => setSubmitted(true)}
                className="rounded-md bg-sky-500 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400"
              >
                Construire
              </button>
            </div>
          </div>
        )}
      </Card>

      {!submitted && <Placeholder>Choisis des filtres (ou laisse-les vides) puis lance la construction.</Placeholder>}
      {portfolio.isLoading && (
        <Card>
          <div className="flex items-center gap-2 text-slate-400">
            <Spinner /> Optimisation en cours…
          </div>
        </Card>
      )}
      {portfolio.error && <ErrorNote>{apiErrorMessage(portfolio.error)}</ErrorNote>}

      {portfolio.data && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Card title="Rendement annualisé attendu">
              <Delta value={portfolio.data.expected_return_pct} />
            </Card>
            <Card title="Volatilité annualisée">
              <Num value={portfolio.data.expected_vol_pct} />
              <span className="ml-1 text-slate-400">%</span>
            </Card>
            <Card title="Titres retenus">
              <span className="font-mono">
                {portfolio.data.n_used} / {portfolio.data.n_candidates}
              </span>
            </Card>
          </div>

          <Card title="Composition">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-800">
                  <th className="py-2 pr-4">Titre</th>
                  <th className="py-2 pr-4">Pays</th>
                  <th className="py-2 pr-4">Secteur</th>
                  <th className="py-2 pr-4">Poids</th>
                  <th className="py-2 pr-4">Rendement attendu</th>
                  <th className="py-2 pr-4">Volatilité</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.data.holdings.map((h) => (
                  <tr key={h.code} className="border-b border-slate-900">
                    <td className="py-2 pr-4 font-mono">{h.code}</td>
                    <td className="py-2 pr-4">{h.country}</td>
                    <td className="py-2 pr-4 text-slate-400">{h.sector}</td>
                    <td className="py-2 pr-4 font-mono tabular-nums">{h.weight_pct.toFixed(1)} %</td>
                    <td className="py-2 pr-4">
                      <Delta value={h.expected_return_pct} />
                    </td>
                    <td className="py-2 pr-4 font-mono tabular-nums">{h.volatility_pct.toFixed(1)} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {(portfolio.data.monte_carlo || portfolio.data.monte_carlo_error) && (
            <Card title="Évaluation par Monte Carlo (bootstrap par blocs)">
              {portfolio.data.monte_carlo ? (
                <>
                  <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
                    <div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">Médiane</div>
                      <Delta value={portfolio.data.monte_carlo.percentiles_final_return_pct['50']} />
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">Probabilité de perte</div>
                      <Num value={portfolio.data.monte_carlo.probability_of_loss_pct} />
                      <span className="ml-1 text-slate-400">%</span>
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">VaR 95 %</div>
                      <Delta value={portfolio.data.monte_carlo.var_95_pct} />
                    </div>
                    <div>
                      <div className="text-xs uppercase tracking-wide text-slate-500">CVaR 95 %</div>
                      <Delta value={portfolio.data.monte_carlo.cvar_95_pct} />
                    </div>
                  </div>
                  <FanChart
                    fan={portfolio.data.monte_carlo.fan_chart_pct}
                    horizonDays={portfolio.data.monte_carlo.horizon_days}
                  />
                  <p className="mt-2 text-xs text-slate-500">
                    Rendement cumulé jour par jour sur {portfolio.data.monte_carlo.horizon_days} jours de bourse —
                    bande claire : 5ᵉ à 95ᵉ percentile, bande foncée : 25ᵉ à 75ᵉ, ligne : médiane. Basé sur{' '}
                    {portfolio.data.monte_carlo.n_sims.toLocaleString('fr-FR')} trajectoires rééchantillonnées par
                    blocs à partir de {portfolio.data.monte_carlo.n_history_days} jours d'historique réel — reflète ce
                    qui s'est passé sur cette période, pas une prévision garantie.
                  </p>
                </>
              ) : (
                <ErrorNote>{portfolio.data.monte_carlo_error}</ErrorNote>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
