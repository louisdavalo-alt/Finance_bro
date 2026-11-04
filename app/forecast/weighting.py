"""Méta-pondération — étape 3 de l'architecture (« Pondération simple, puis Hedge ») — à partir
des résultats du backtest walk-forward (`backtest.py`) : combine les 9 modèles d'un ticker en UNE
prévision unique, pondérée par leur performance passée sur CE ticker. S'arrête aux deux premières
briques listées par l'architecture (1/erreur récente, puis Hedge) ; le stacking (régression sur
les prévisions des modèles, mentionné dans la même phrase pour la méta-pondération) n'est pas
construit ici — pas encore demandé.

Garde-fou explicite de l'architecture, appliqué dans LES DEUX schémas : « poids nul si la
baseline n'est pas battue » — un modèle dont l'erreur moyenne (CRPS) est au moins aussi mauvaise
que celle de la baseline naïve reçoit un poids nul, jamais seulement réduit.

La métrique de perte, pour les deux schémas, est le **CRPS** (`backtest._crps_normal`) : note la
prévision ENTIÈRE (position ET dispersion), donc reste pertinente même pour un modèle non
directionnel comme GARCH (qui ne serait jamais choisi par une métrique purement directionnelle
comme le hit ratio, alors qu'une bonne lecture du risque a sa valeur dans un ensemble).

Pour Hedge (poids exponentiels — Freund & Schapire, 1997 ; voir aussi Cesa-Bianchi & Lugosi,
*Prediction, Learning, and Games*) : la perte d'un modèle ABSENT à un point de test donné
(historique encore trop court, erreur numérique...) est remplacée par la PIRE perte observée ce
jour-là parmi tous les modèles — un modèle indisponible n'est pas traité comme s'il avait fait
aussi bien que la référence, il est pénalisé comme le pire cas constaté.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import numpy as np

from ..ohlcv_cache import OhlcvCache
from .backtest import BASELINE_NAME, GARCH_NAME, HORIZON_DAYS_BY_KEY, _realized_vol_pct, run_walk_forward_backtest
from .feature_store import read_point_in_time_bars
from .garch import fit_garch_forecast
from .predict import predict_all


def naive_weights(models: dict[str, dict], baseline_name: str = BASELINE_NAME) -> dict[str, float]:
    """Pondération « 1/erreur récente » : `models` est le dict `result["models"]` renvoyé par
    `backtest.run_walk_forward_backtest` (une entrée par modèle, avec `crps_pct` moyen). Poids
    nul pour tout modèle dont le CRPS moyen est >= celui de la baseline, sinon proportionnel à
    `1/crps_pct`, normalisé à somme 1 sur les modèles retenus. Si aucun modèle ne bat la
    baseline, tout le poids retombe sur elle (c'est alors, par construction, la meilleure prévision
    disponible)."""
    if baseline_name not in models:
        raise ValueError(f"{baseline_name!r} absent de `models` — requis comme référence")
    baseline_crps = models[baseline_name].get("crps_pct")

    raw: dict[str, float] = {}
    for name, m in models.items():
        if name == baseline_name:
            continue
        crps = m.get("crps_pct")
        if crps is None or baseline_crps is None or crps >= baseline_crps:
            raw[name] = 0.0
        else:
            raw[name] = 1.0 / crps

    total = sum(raw.values())
    weights = {name: 0.0 for name in raw}
    weights[baseline_name] = 1.0
    if total > 0:
        weights = {name: w / total for name, w in raw.items()}
        weights[baseline_name] = 0.0
    return weights


def hedge_weights(
    crps_series: dict[str, list[float | None]], eta: float = 0.5, baseline_name: str = BASELINE_NAME,
) -> dict[str, float]:
    """Hedge / poids exponentiels, point de test par point de test : `crps_series` est le dict
    `result["crps_series"]` renvoyé par `backtest.run_walk_forward_backtest` (une liste par
    modèle, alignée par position, `None` aux points manqués). Poids initiaux uniformes, mise à
    jour multiplicative `w_i *= exp(-eta * perte_i,t)` puis renormalisation à chaque point —
    `eta` contrôle la vitesse d'adaptation (plus haut = réagit plus vite aux modèles récemment
    performants, au prix de plus de variance point à point).

    Le garde-fou « poids nul si la baseline n'est pas battue » est appliqué À LA FIN, sur la perte
    CUMULÉE sur toute la période (pas point par point, ce qui annulerait l'intérêt de Hedge
    d'apprendre progressivement plutôt que de juger sur un seul instantané) : un modèle dont la
    perte cumulée est pire que celle de la baseline reçoit un poids final nul, puis les poids
    restants sont renormalisés sur les seuls modèles retenus."""
    if baseline_name not in crps_series:
        raise ValueError(f"{baseline_name!r} absent de `crps_series` — requis comme référence")
    names = list(crps_series.keys())
    n_points = len(crps_series[baseline_name])
    if n_points == 0:
        raise ValueError("crps_series vide : aucun point de test à apprendre")

    weights = {name: 1.0 / len(names) for name in names}
    cumulative_loss = {name: 0.0 for name in names}

    for t in range(n_points):
        day_losses = [crps_series[name][t] for name in names if crps_series[name][t] is not None]
        worst = max(day_losses) if day_losses else 0.0
        for name in names:
            loss = crps_series[name][t]
            if loss is None:
                loss = worst
            cumulative_loss[name] += loss
            weights[name] *= np.exp(-eta * loss)
        total = sum(weights.values())
        if total > 0:
            weights = {name: w / total for name, w in weights.items()}

    baseline_cum = cumulative_loss[baseline_name]
    survivors = {
        name: weights[name]
        for name in names
        if name != baseline_name and cumulative_loss[name] < baseline_cum
    }
    total = sum(survivors.values())
    if total <= 0:
        return {name: (1.0 if name == baseline_name else 0.0) for name in names}
    final = {name: 0.0 for name in names}
    for name, w in survivors.items():
        final[name] = w / total
    return final


def combine_predictions(weights: dict[str, float], predictions: dict[str, dict]) -> dict:
    """Combine les prévisions COURANTES (pas historiques — ex. `predict.predict_all` + GARCH en
    direct, chacun au format `{"mu_pct":..., "sigma_pct":...}`) des modèles pondérés en UNE
    prévision d'ensemble.

    `sigma_pct` combine deux sources d'incertitude (loi des variances totales) : la dispersion
    *intra*-modèle (moyenne pondérée des variances individuelles) ET la dispersion *inter*-modèle
    (variance pondérée des `mu_pct` autour de la moyenne d'ensemble) — un ensemble dont les
    membres sont en désaccord est intrinsèquement plus incertain qu'un seul d'entre eux pris
    isolément, même si chacun affiche une faible variance à titre individuel."""
    names = [n for n in weights if weights[n] > 0 and n in predictions]
    if not names:
        raise ValueError("aucun modèle pondéré n'a de prévision courante disponible pour être combiné")

    w = np.array([weights[n] for n in names], dtype=float)
    w = w / w.sum()
    mu = np.array([predictions[n]["mu_pct"] for n in names], dtype=float)
    sigma = np.array([predictions[n]["sigma_pct"] for n in names], dtype=float)

    mu_combined = float(np.sum(w * mu))
    within_model_var = float(np.sum(w * sigma**2))
    between_model_var = float(np.sum(w * (mu - mu_combined) ** 2))
    sigma_combined = float(np.sqrt(within_model_var + between_model_var))

    return {
        "mu_pct": mu_combined,
        "sigma_pct": sigma_combined,
        "weights_used": {n: float(weights[n]) for n in names},
    }


async def _current_predictions(ticker: str, horizon: str, cache: OhlcvCache) -> dict[str, dict]:
    """Prévisions COURANTES (as_of = aujourd'hui) des 9 modèles du backtest, dans le même format
    que `predict.predict_all` — GARCH et la baseline naïve n'en font pas partie (signature
    différente), ajoutés ici à la main pour que `combine_predictions` puisse les recevoir
    exactement comme `backtest.py` les traite."""
    horizon_days = HORIZON_DAYS_BY_KEY[horizon]
    bars = await read_point_in_time_bars(ticker, dt.date.today(), cache)
    if bars.empty:
        raise ValueError(f"aucune barre disponible pour {ticker}")

    results, _errors = await predict_all(ticker, dt.date.today(), horizon, cache)

    log_returns = np.log(bars["Close"]).diff().dropna()
    try:
        garch_res = await asyncio.to_thread(fit_garch_forecast, log_returns, horizon_days)
        results[GARCH_NAME] = {"mu_pct": 0.0, "sigma_pct": garch_res["weekly_vol_forecast_pct"]}
    except Exception:  # noqa: BLE001 - GARCH indisponible : simplement absent du dict, comme un échec de predict_all
        pass

    results[BASELINE_NAME] = {"mu_pct": 0.0, "sigma_pct": _realized_vol_pct(log_returns, horizon_days)}
    return results


async def run_weighted_ensemble_forecast(
    ticker: str, horizon: str, cache: OhlcvCache, method: str = "hedge", eta: float = 0.5,
) -> dict:
    """Bout en bout : backtest walk-forward (`backtest.run_walk_forward_backtest`) → poids
    (`naive_weights` ou `hedge_weights` selon `method`) → prévisions courantes des mêmes 9
    modèles → prévision d'ensemble (`combine_predictions`). Renvoie `{"combined", "weights",
    "method", "backtest_n_test_points", "backtest_models", "backtest_errors"}` — les séries brutes
    du backtest (`crps_series`, dates) ne sont PAS renvoyées (disponibles via
    `run_walk_forward_backtest` pour qui veut les inspecter)."""
    if method not in ("naive", "hedge"):
        raise ValueError(f"méthode de pondération invalide : {method!r} (attendu : 'naive' ou 'hedge')")

    backtest_result = await run_walk_forward_backtest(ticker, horizon, cache)
    if method == "naive":
        weights = naive_weights(backtest_result["models"])
    else:
        weights = hedge_weights(backtest_result["crps_series"], eta=eta)

    predictions = await _current_predictions(ticker, horizon, cache)
    combined = combine_predictions(weights, predictions)

    return {
        "combined": combined,
        "weights": weights,
        "method": method,
        "backtest_n_test_points": backtest_result["n_test_points"],
        # Métriques agrégées par modèle (IC, hit ratio, CRPS, Sharpe...) : ce qui justifie les
        # poids, affiché tel quel par l'API. Les séries brutes (`crps_series`) restent internes.
        "backtest_models": backtest_result["models"],
        "backtest_errors": backtest_result["errors"],
    }
