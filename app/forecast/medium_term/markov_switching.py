"""Markov switching (Hamilton, 1989) — modèle à changement de régime où la moyenne ET la variance
du rendement quotidien basculent entre `k_regimes` états selon une chaîne de Markov cachée, ajusté
par maximum de vraisemblance via `statsmodels.tsa.regime_switching.markov_regression.
MarkovRegression`.

Distinct du HMM déjà utilisé pour l'affichage du régime courant (`app/forecast/regime.py`,
`hmmlearn`) : même famille de modèles, mais utilisé ICI pour PRÉVOIR un rendement (en projetant
la distribution de probabilité des régimes `horizon_days` jours en avant via la matrice de
transition, puis en pondérant les moyennes de régime par cette distribution), pas seulement pour
étiqueter la période actuelle. Les deux coexistent sans redondance fonctionnelle.

⚠️ Les régimes ne sont pas triés/étiquetés par rendement moyen (contrairement à `regime.py`) :
`current_regime` est un simple index (0, 1, ...), à lire avec `regime_means_daily_pct` pour savoir
lequel est haussier/baissier sur CET ajustement précis (l'ordre peut changer d'un ajustement à
l'autre)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model_base import PredictionResult

MIN_OBS = 300


def fit_markov_switching_forecast(log_returns: pd.Series, horizon_days: int = 21, k_regimes: int = 2) -> dict:
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

    r = log_returns.dropna()
    if len(r) < MIN_OBS:
        raise ValueError(
            f"historique trop court pour un Markov switching fiable ({len(r)} points, {MIN_OBS} recommandés)"
        )

    mod = MarkovRegression(r.values, k_regimes=k_regimes, switching_variance=True)
    res = mod.fit()

    params = dict(zip(mod.param_names, res.params))
    means = np.array([params[f"const[{i}]"] for i in range(k_regimes)])
    variances = np.array([params[f"sigma2[{i}]"] for i in range(k_regimes)])

    # res.regime_transition[i, j, 0] = P(régime i à t | régime j à t-1) — colonnes de somme 1 ;
    # on projette la distribution de probabilité des régimes jour après jour sur l'horizon, et on
    # pondère les moyennes/variances de régime par cette distribution à chaque pas (plutôt que de
    # supposer le régime courant figé sur tout l'horizon).
    transition = res.regime_transition[:, :, 0]
    probs = np.asarray(res.filtered_marginal_probabilities[-1])

    cum_log_return = 0.0
    cum_var = 0.0
    for _ in range(horizon_days):
        probs = transition @ probs
        cum_log_return += float(probs @ means)
        cum_var += float(probs @ variances)

    current_probs = np.asarray(res.filtered_marginal_probabilities[-1])
    return {
        "expected_return_pct": (np.exp(cum_log_return) - 1) * 100,
        "sigma_pct": float(np.sqrt(max(cum_var, 0.0))) * 100,
        "current_regime": int(np.argmax(current_probs)),
        "current_regime_probabilities": [float(x) for x in current_probs],
        "regime_means_daily_pct": [float(m) * 100 for m in means],
        "regime_vols_daily_pct": [float(np.sqrt(v)) * 100 for v in variances],
        "n_obs": int(len(r)),
    }


class MarkovSwitchingModel:
    name = "markov_switching"

    def predict(self, bars: pd.DataFrame, horizon_days: int) -> PredictionResult:
        log_ret = np.log(bars["Close"]).diff()
        result = fit_markov_switching_forecast(log_ret, horizon_days=horizon_days)
        return PredictionResult(
            mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result
        )
