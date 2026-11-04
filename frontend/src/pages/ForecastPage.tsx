import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api, apiErrorMessage } from '../api/client'
import type { components } from '../api/schema'
import { CandlestickChart } from '../components/CandlestickChart'
import { Card, Delta, ErrorNote, Num, Placeholder, Spinner } from '../components/ui'
import { WatchlistButton } from '../components/WatchlistButton'

type Horizon = '1w' | '1m'
type ShortTermModelResult = components['schemas']['ShortTermModelResult']
type EnsembleResponse = components['schemas']['EnsembleResponse']

// Libellés d'affichage des 5 modèles court terme non-IA (voir app/forecast/short_term/) —
// `key` doit correspondre à `HorizonModel.name` côté backend.
const SHORT_TERM_MODEL_LABELS: { key: string; label: string }[] = [
  { key: 'har_rv', label: 'HAR-RV (volatilité)' },
  { key: 'arima', label: 'ARIMA' },
  { key: 'kalman_trend', label: 'Filtre de Kalman' },
  { key: 'ou_meanrevert', label: 'Ornstein-Uhlenbeck' },
  { key: 'reversal', label: 'Retournement' },
]

// Libellés d'affichage des 6 modèles moyen terme non-IA (voir app/forecast/medium_term/) — ne
// tournent qu'à horizon "1m" (dicts vides sinon, voir pipeline.py).
const MEDIUM_TERM_MODEL_LABELS: { key: string; label: string }[] = [
  { key: 'momentum_12_1', label: 'Momentum 12-1' },
  { key: 'ts_momentum', label: 'Momentum temporel (TSMOM)' },
  { key: 'markov_switching', label: 'Markov switching' },
  { key: 'ff5_momentum', label: 'Fama-French 5 + momentum' },
  { key: 'pead', label: 'Post-earnings drift' },
  { key: 'var_market', label: 'VAR titre/marché' },
]

// Libellés d'affichage des 6 modèles long terme non-IA (voir app/forecast/long_term/) — ne
// tournent qu'à horizon "1m" (dicts vides sinon, voir pipeline.py).
const LONG_TERM_MODEL_LABELS: { key: string; label: string }[] = [
  { key: 'cape', label: 'CAPE de Shiller (proxy P/E)' },
  { key: 'dividend_yield', label: 'Rendement du dividende' },
  { key: 'gordon_ddm', label: 'Gordon / DDM' },
  { key: 'implied_erp', label: 'Prime de risque implicite' },
  { key: 'value_profitability', label: 'Facteurs value/profitabilité' },
  { key: 'cointegration_vecm', label: 'Cointégration / VECM' },
]

function ModelResultsTable({
  labels,
  models,
  errors,
}: {
  labels: { key: string; label: string }[]
  models: Record<string, ShortTermModelResult>
  errors: Record<string, string>
}) {
  if (Object.keys(models).length === 0 && Object.keys(errors).length === 0) {
    return <Placeholder>Aucun résultat.</Placeholder>
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-400">
          <th className="pb-1 pr-4 font-normal">Modèle</th>
          <th className="pb-1 pr-4 font-normal">Rendement attendu</th>
          <th className="pb-1 font-normal">Écart-type</th>
        </tr>
      </thead>
      <tbody>
        {labels.map(({ key, label }) => {
          const result = models[key]
          const err = errors[key]
          if (!result && !err) return null
          return (
            <tr key={key} className="border-t border-slate-800">
              <td className="py-1.5 pr-4 text-slate-300">{label}</td>
              {result ? (
                <>
                  <td className="py-1.5 pr-4">
                    <Delta value={result.mu_pct} />
                  </td>
                  <td className="py-1.5 font-mono text-slate-200">{result.sigma_pct.toFixed(2)} %</td>
                </>
              ) : (
                <td className="py-1.5 text-slate-500" colSpan={2}>
                  <ErrorNote>{err}</ErrorNote>
                </td>
              )}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// Carte « ensemble pondéré par backtest » (voir app/forecast/weighting.py). Appel lourd (backtest
// walk-forward complet, de l'ordre de la minute) : déclenché à la demande, jamais automatiquement.
function EnsembleCard({ code, horizon }: { code: string; horizon: Horizon }) {
  const [method, setMethod] = useState<'hedge' | 'naive'>('hedge')
  const [requested, setRequested] = useState<string | null>(null)
  const key = `${code}|${horizon}|${method}`

  const ensemble = useQuery({
    queryKey: ['ensemble', code, horizon, method],
    enabled: requested === key,
    staleTime: Infinity,
    retry: false,
    queryFn: async (): Promise<EnsembleResponse> => {
      const { data, error } = await api.GET('/ensemble/{indicator_code}', {
        params: { path: { indicator_code: code }, query: { horizon, method } },
      })
      if (error) throw error
      return data
    },
  })

  const data = requested === key ? ensemble.data : undefined
  const rows = data
    ? Object.entries(data.backtest_models).sort(([a], [b]) => (data.weights[b] ?? 0) - (data.weights[a] ?? 0))
    : []

  return (
    <Card title="Ensemble pondéré par backtest" className="md:col-span-2">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="flex overflow-hidden rounded-md border border-slate-700">
          {(['hedge', 'naive'] as const).map((m) => (
            <button
              type="button"
              key={m}
              onClick={() => setMethod(m)}
              className={`px-3 py-1 text-sm ${method === m ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'}`}
            >
              {m === 'hedge' ? 'Hedge' : '1/erreur'}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setRequested(key)}
          disabled={requested === key && ensemble.isFetching}
          className="rounded-md bg-sky-500 px-3 py-1 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-50"
        >
          Calculer l'ensemble
        </button>
        <span className="text-xs text-slate-500">Backtest walk-forward complet : peut prendre environ une minute.</span>
      </div>

      {requested === key && ensemble.isFetching && (
        <div className="flex items-center gap-2 text-slate-400">
          <Spinner /> Backtest en cours…
        </div>
      )}
      {requested === key && ensemble.error && <ErrorNote>{apiErrorMessage(ensemble.error)}</ErrorNote>}

      {data && (
        <>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <div>
              <span className="text-slate-400">Rendement attendu </span>
              <Delta value={data.combined.mu_pct} />
            </div>
            <div>
              <span className="text-slate-400">Écart-type </span>
              <span className="font-mono text-slate-200">{data.combined.sigma_pct.toFixed(2)} %</span>
            </div>
            <div className="text-xs text-slate-500">{data.backtest_n_test_points} points de test</div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="pb-1 pr-4 font-normal">Modèle</th>
                <th className="pb-1 pr-4 font-normal">Poids</th>
                <th className="pb-1 pr-4 font-normal">CRPS</th>
                <th className="pb-1 pr-4 font-normal">Hit ratio</th>
                <th className="pb-1 pr-4 font-normal">IC</th>
                <th className="pb-1 font-normal">Sharpe déflaté</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, m]) => (
                <tr key={name} className="border-t border-slate-800">
                  <td className="py-1.5 pr-4 text-slate-300">{name}</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-200">{((data.weights[name] ?? 0) * 100).toFixed(1)} %</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-200">{m.crps_pct.toFixed(3)}</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-200">{m.hit_ratio == null ? '—' : `${(m.hit_ratio * 100).toFixed(0)} %`}</td>
                  <td className="py-1.5 pr-4 font-mono text-slate-200">{m.ic == null ? '—' : m.ic.toFixed(2)}</td>
                  <td className="py-1.5 font-mono text-slate-200">{m.deflated_sharpe == null ? '—' : m.deflated_sharpe.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {Object.keys(data.backtest_errors).length > 0 && (
            <p className="mt-2 text-xs text-slate-500">
              Modèles en échec pendant le backtest : {Object.keys(data.backtest_errors).join(', ')}.
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Poids nul pour tout modèle qui ne bat pas la baseline « rendement nul ». Seuls les 8 modèles à barres OHLCV
            (+ GARCH) sont rejoués dans le passé ; les modèles réseau et long terme n'y participent pas (voir le README).
          </p>
        </>
      )}
    </Card>
  )
}

export default function ForecastPage() {
  const [params, setParams] = useSearchParams()
  const code = params.get('code') ?? ''
  const [horizon, setHorizon] = useState<Horizon>('1w')
  const [useKronos, setUseKronos] = useState(false)
  const [submittedCode, setSubmittedCode] = useState(code || null)

  const kronosEnabled = useQuery({
    queryKey: ['kronos-enabled'],
    queryFn: async () => {
      const { data, error } = await api.GET('/forecast-kronos-enabled')
      if (error) throw error
      return data
    },
  })

  const ohlc = useQuery({
    queryKey: ['ohlc', submittedCode],
    enabled: !!submittedCode,
    queryFn: async () => {
      const { data, error } = await api.GET('/ohlc/{indicator_code}', {
        params: { path: { indicator_code: submittedCode! }, query: { period: '2y' } },
      })
      if (error) throw error
      return data
    },
  })

  const forecast = useQuery({
    queryKey: ['forecast', submittedCode, horizon, useKronos],
    enabled: !!submittedCode,
    queryFn: async () => {
      const { data, error } = await api.GET('/forecast/{indicator_code}', {
        params: { path: { indicator_code: submittedCode! }, query: { period: '5y', horizon, kronos: useKronos } },
      })
      if (error) throw error
      return data
    },
  })

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setParams(code ? { code } : {})
    setSubmittedCode(code || null)
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-semibold text-slate-100">Prévision</h1>

      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-3">
        <input
          value={code}
          onChange={(e) => setParams({ code: e.target.value })}
          placeholder="Code (ex. DE_DAX, USA_APPLE)…"
          className="w-56 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <div className="flex overflow-hidden rounded-md border border-slate-700">
          {(['1w', '1m'] as Horizon[]).map((h) => (
            <button
              type="button"
              key={h}
              onClick={() => setHorizon(h)}
              className={`px-3 py-1.5 text-sm ${horizon === h ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'}`}
            >
              {h === '1w' ? '~1 semaine' : '~1 mois'}
            </button>
          ))}
        </div>
        {kronosEnabled.data?.enabled && (
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={useKronos} onChange={(e) => setUseKronos(e.target.checked)} />
            Prévision Kronos (IA)
          </label>
        )}
        <button type="submit" className="rounded-md bg-sky-500 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400">
          Lancer le calcul
        </button>
        {submittedCode && <WatchlistButton code={submittedCode} />}
      </form>

      {!submittedCode && <Placeholder>Saisis un code d'indicateur de marché pour commencer (voir l'onglet Indicateurs).</Placeholder>}

      {submittedCode && (
        <>
          <Card title={`Historique — ${submittedCode}`}>
            {ohlc.isLoading && <Spinner />}
            {ohlc.error && <ErrorNote>{apiErrorMessage(ohlc.error)}</ErrorNote>}
            {ohlc.data && ohlc.data.length > 0 && <CandlestickChart bars={ohlc.data} />}
          </Card>

          {forecast.isLoading && (
            <Card>
              <div className="flex items-center gap-2 text-slate-400">
                <Spinner /> Calcul en cours{useKronos ? ' (Kronos sur CPU : peut prendre plusieurs minutes)' : ''}…
              </div>
            </Card>
          )}
          {forecast.error && <ErrorNote>{apiErrorMessage(forecast.error)}</ErrorNote>}

          {forecast.data && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Card title="Volatilité GARCH(1,1)">
                {forecast.data.garch ? (
                  <>
                    <div className="text-2xl font-mono">{forecast.data.garch.weekly_vol_forecast_pct.toFixed(2)} %</div>
                    <p className="mt-1 text-sm text-slate-400">volatilité prévue cumulée sur les 5 prochains jours de bourse</p>
                  </>
                ) : (
                  <ErrorNote>{forecast.data.garch_error ?? 'Échec du calcul GARCH.'}</ErrorNote>
                )}
              </Card>

              <Card title={`Rendement prévu (XGBoost, ${forecast.data.ml_forecast?.horizon_days ?? '—'} j)`}>
                {forecast.data.ml_forecast ? (
                  <Delta value={forecast.data.ml_forecast.predicted_return_pct} />
                ) : (
                  <ErrorNote>{forecast.data.ml_error ?? 'Échec du calcul du modèle.'}</ErrorNote>
                )}
              </Card>

              <Card title="Régime de marché (HMM)">
                {forecast.data.regime ? (
                  <>
                    <div className="text-lg">{forecast.data.regime.current_regime}</div>
                    <p className="text-sm text-slate-400">depuis le {forecast.data.regime.current_regime_since}</p>
                  </>
                ) : (
                  <ErrorNote>{forecast.data.regime_error ?? 'Échec de la détection de régime.'}</ErrorNote>
                )}
              </Card>

              <Card title="Modèles court terme (non-IA)" className="md:col-span-2">
                <ModelResultsTable
                  labels={SHORT_TERM_MODEL_LABELS}
                  models={forecast.data.short_term_models}
                  errors={forecast.data.short_term_errors}
                />
                <p className="mt-3 text-xs text-slate-500">
                  HAR-RV n'a pas de vue directionnelle (modèle de volatilité pure). Ornstein-Uhlenbeck et retournement sont des
                  versions simplifiées à un seul actif (voir le README) — pas les versions multi-titres complètes.
                </p>
              </Card>

              {horizon === '1m' && (
                <Card title="Modèles moyen terme (non-IA)" className="md:col-span-2">
                  <ModelResultsTable
                    labels={MEDIUM_TERM_MODEL_LABELS}
                    models={forecast.data.medium_term_models}
                    errors={forecast.data.medium_term_errors}
                  />
                  <p className="mt-3 text-xs text-slate-500">
                    Momentum 12-1, TSMOM et Fama-French 5 + momentum sont des versions simplifiées à un seul actif / par ETF
                    proxys (voir le README). PEAD utilise les dates de résultats yfinance (couverture variable) ; faute
                    d'assez de surprises passées pour ce titre, il se rabat sur une pente calibrée sur la littérature plutôt
                    qu'ajustée sur ce titre précis.
                  </p>
                </Card>
              )}

              {horizon === '1m' && (
                <Card title="Modèles long terme (non-IA)" className="md:col-span-2">
                  <ModelResultsTable
                    labels={LONG_TERM_MODEL_LABELS}
                    models={forecast.data.long_term_models}
                    errors={forecast.data.long_term_errors}
                  />
                  <p className="mt-3 text-xs text-slate-500">
                    Rendement/écart-type ANNUELS mis à l'échelle de l'horizon (voir le README) — ces modèles raisonnent
                    nativement sur 1 à 10 ans, pas sur quelques jours. Dividende/Gordon échouent sans dividende versé ;
                    Cointégration/VECM échoue si le titre n'est pas statistiquement cointégré avec le marché (résultat
                    légitime, pas un bug).
                  </p>
                </Card>
              )}

              <EnsembleCard key={`${submittedCode}|${horizon}`} code={submittedCode} horizon={horizon} />

              {(forecast.data.kronos || forecast.data.kronos_error) && (
                <Card title="Prévision Kronos (IA auto-hébergée)">
                  {forecast.data.kronos ? (
                    <>
                      <div className="text-lg">
                        <Num value={forecast.data.kronos.last_known_close} /> →{' '}
                        <Num value={forecast.data.kronos.predictions.at(-1)?.close} />
                      </div>
                      <p className="text-sm text-slate-400">clôture prévue après {forecast.data.kronos.predictions.length} jours</p>
                    </>
                  ) : (
                    <ErrorNote>{forecast.data.kronos_error}</ErrorNote>
                  )}
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
