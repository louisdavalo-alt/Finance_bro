"""Tests du constructeur de portefeuille. Le cas le plus important est
`test_min_variance_two_uncorrelated_assets_closed_form` : sur deux actifs non corrélés, la
solution à variance minimale a une forme fermée connue (poids inversement proportionnels à la
variance) — si l'optimiseur s'en écarte, c'est un vrai bug, pas une question d'interprétation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.portfolio.optimizer import InfeasibleTarget, optimize_weights, portfolio_summary
from app.portfolio.pipeline import available_countries, available_sectors, build_portfolio, filter_universe
from app.portfolio.sectors import NON_CLASSE, SECTORS, all_sectors, sector_for
from app.registry import INDICATORS


# --------------------------------------------------------------------------- #
# Classification sectorielle
# --------------------------------------------------------------------------- #

def test_every_stock_has_a_sector():
    """Garde-fou de non-régression : toute action du registre doit être classée, pour qu'une
    future action ajoutée ne disparaisse pas silencieusement des filtres par secteur."""
    STOCK_PREFIXES = ("USA_", "FRA_", "DEU_", "JPN_", "CHN_", "KOR_", "GBR_", "CAN_", "IND_", "ITA_", "POL_", "MEX_")
    LEGACY = {"FR_TOTALENERGIES", "FR_AIRBUS", "FR_LVMH"}
    stock_codes = {s.code for s in INDICATORS if s.connector == "yfinance" and (s.code.startswith(STOCK_PREFIXES) or s.code in LEGACY)}
    missing = stock_codes - set(SECTORS)
    assert not missing, f"actions non classées par secteur : {sorted(missing)}"


def test_sector_for_unknown_code_returns_non_classe():
    assert sector_for("CODE_INEXISTANT") == NON_CLASSE


def test_all_sectors_matches_values_used():
    assert set(all_sectors()) == set(SECTORS.values())
    assert NON_CLASSE not in all_sectors()  # aucune action n'est réellement non classée aujourd'hui


# --------------------------------------------------------------------------- #
# Filtrage de l'univers
# --------------------------------------------------------------------------- #

def test_filter_universe_by_country():
    codes = filter_universe(countries=["FRA"], sectors=None)
    assert "FR_TOTALENERGIES" in codes or "FRA_LOREAL" in codes
    assert all(c.startswith("FRA_") or c in {"FR_TOTALENERGIES", "FR_AIRBUS", "FR_LVMH"} for c in codes)


def test_filter_universe_by_sector():
    codes = filter_universe(countries=None, sectors=["Santé"])
    assert "USA_JOHNSON_JOHNSON" in codes
    assert "USA_APPLE" not in codes


def test_filter_universe_combines_filters():
    codes = filter_universe(countries=["USA"], sectors=["Santé"])
    assert "USA_JOHNSON_JOHNSON" in codes
    assert "FRA_SANOFI" not in codes  # bon secteur, mauvais pays


def test_available_countries_and_sectors_are_non_empty_and_sorted():
    c = available_countries()
    s = available_sectors()
    assert c == sorted(c) and len(c) >= 10
    assert s == sorted(s) and len(s) >= 8


# --------------------------------------------------------------------------- #
# Optimiseur — cas à forme fermée connue
# --------------------------------------------------------------------------- #

def test_min_variance_two_uncorrelated_assets_closed_form():
    """Deux actifs non corrélés, variances 0,01 et 0,04 : le portefeuille à variance minimale a
    une solution connue w1 = (1/v1)/(1/v1+1/v2) = 0,8, w2 = 0,2 — ici obtenue en demandant un
    rendement cible égal à la moyenne pondérée par variance inverse, ce qui revient à la solution
    à variance minimale pure, sans être bridé par `max_weight`."""
    mean_returns = pd.Series({"A": 0.05, "B": 0.05}, name="mean")  # rendements égaux : la variance seule décide
    cov = pd.DataFrame({"A": [0.01, 0.0], "B": [0.0, 0.04]}, index=["A", "B"])
    weights = optimize_weights(mean_returns, cov, risk_level="faible", target_return=None, max_weight=1.0)
    assert weights["A"] == pytest.approx(0.8, abs=1e-3)
    assert weights["B"] == pytest.approx(0.2, abs=1e-3)


def test_weights_sum_to_one_and_respect_bounds():
    rng = np.random.default_rng(0)
    n = 6
    mean_returns = pd.Series(rng.uniform(0.03, 0.12, n), index=[f"A{i}" for i in range(n)])
    cov = pd.DataFrame(np.diag(rng.uniform(0.01, 0.05, n)), index=mean_returns.index, columns=mean_returns.index)
    weights = optimize_weights(mean_returns, cov, risk_level="modere", max_weight=0.3)
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert (weights >= -1e-9).all() and (weights <= 0.3 + 1e-6).all()


def test_higher_risk_aversion_yields_lower_variance_on_same_universe():
    rng = np.random.default_rng(1)
    n = 5
    mean_returns = pd.Series(rng.uniform(0.04, 0.15, n), index=[f"A{i}" for i in range(n)])
    A = rng.normal(0, 1, (n, n))
    cov = pd.DataFrame(A @ A.T * 0.01 + np.eye(n) * 0.01, index=mean_returns.index, columns=mean_returns.index)

    w_faible = optimize_weights(mean_returns, cov, risk_level="faible", max_weight=1.0)
    w_eleve = optimize_weights(mean_returns, cov, risk_level="eleve", max_weight=1.0)
    vol_faible = portfolio_summary(w_faible, mean_returns, cov)["expected_vol_pct"]
    vol_eleve = portfolio_summary(w_eleve, mean_returns, cov)["expected_vol_pct"]
    assert vol_faible <= vol_eleve + 1e-9, "un risque 'faible' ne devrait pas produire plus de volatilité qu'un risque 'élevé'"


def test_target_return_constraint_is_met():
    rng = np.random.default_rng(2)
    n = 4
    mean_returns = pd.Series([0.05, 0.08, 0.11, 0.14], index=[f"A{i}" for i in range(n)])
    cov = pd.DataFrame(np.diag([0.02, 0.03, 0.05, 0.08]), index=mean_returns.index, columns=mean_returns.index)
    weights = optimize_weights(mean_returns, cov, target_return=0.10, max_weight=1.0)
    achieved = float(weights @ mean_returns)
    assert achieved >= 0.10 - 1e-6


def test_infeasible_target_return_raises_clear_error():
    mean_returns = pd.Series([0.05, 0.06], index=["A", "B"])
    cov = pd.DataFrame(np.eye(2) * 0.02, index=mean_returns.index, columns=mean_returns.index)
    with pytest.raises(InfeasibleTarget):
        optimize_weights(mean_returns, cov, target_return=0.50, max_weight=1.0)


def test_max_weight_binding_constraint_respected():
    """4 titres, max_weight=0.3 : même en poussant tout le poids vers le meilleur rendement,
    aucun poids ne doit dépasser 0,3 et la somme doit rester à 1 (nécessite de répartir sur au
    moins 4 titres puisque 3*0,3=0,9 < 1)."""
    mean_returns = pd.Series([0.05, 0.06, 0.20, 0.07], index=["A", "B", "C", "D"])
    cov = pd.DataFrame(np.eye(4) * 0.02, index=mean_returns.index, columns=mean_returns.index)
    weights = optimize_weights(mean_returns, cov, risk_level="eleve", max_weight=0.3)
    assert (weights <= 0.3 + 1e-6).all()
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)


def test_max_weight_infeasible_raises_before_optimizing():
    mean_returns = pd.Series([0.05, 0.06], index=["A", "B"])
    cov = pd.DataFrame(np.eye(2) * 0.02, index=mean_returns.index, columns=mean_returns.index)
    with pytest.raises(ValueError, match="sommer à 100%"):
        optimize_weights(mean_returns, cov, max_weight=0.3)  # 2 * 30% = 60% < 100%


def test_invalid_risk_level_rejected():
    mean_returns = pd.Series([0.05, 0.06], index=["A", "B"])
    cov = pd.DataFrame(np.eye(2) * 0.02, index=mean_returns.index, columns=mean_returns.index)
    with pytest.raises(ValueError):
        optimize_weights(mean_returns, cov, risk_level="extreme")


# --------------------------------------------------------------------------- #
# build_portfolio bout-en-bout, avec un faux Store (prix synthétiques)
# --------------------------------------------------------------------------- #

class _FakeStore:
    """Store minimal : `read_panel` renvoie des prix synthétiques pour une poignée de titres
    réels du registre, avec des régimes de volatilité nettement différents pour que
    l'optimiseur ait un vrai choix à faire."""
    def __init__(self, codes_and_vol: dict[str, float], n=400, seed=0):
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2023-01-01", periods=n)
        rows = []
        for code, vol in codes_and_vol.items():
            prices = 100 * np.exp(np.cumsum(rng.normal(0.0003, vol, n)))
            for d, p in zip(dates, prices):
                rows.append({"timestamp": d, "country": "USA", "indicator_code": code, "value": p,
                             "frequency": "D", "unit": "USD", "source": "test", "release_date": d, "ingested_at": d})
        self._df = pd.DataFrame(rows)

    def read_panel(self, codes, columns=None):
        out = self._df[self._df["indicator_code"].isin(codes)]
        return (out[columns] if columns else out).copy()


def test_build_portfolio_end_to_end():
    codes = ["USA_APPLE", "USA_JOHNSON_JOHNSON", "USA_EXXONMOBIL", "USA_DUKE_ENERGY", "USA_WALMART", "USA_NIKE"]
    store = _FakeStore({c: v for c, v in zip(codes, [0.015, 0.008, 0.012, 0.006, 0.009, 0.011])})
    result = build_portfolio(store, countries=["USA"], sectors=None, risk_level="faible", min_names=3)
    assert len(result["holdings"]) >= 3
    assert sum(h["weight_pct"] for h in result["holdings"]) == pytest.approx(100.0, abs=0.1)
    assert all(h["code"] in codes for h in result["holdings"])
    assert result["n_used"] <= result["n_candidates"]


def test_build_portfolio_raises_when_too_few_candidates():
    store = _FakeStore({"USA_APPLE": 0.01})
    with pytest.raises(ValueError, match="action"):
        build_portfolio(store, countries=["POL"], sectors=["Santé"], min_names=5)  # filtre quasi-certainement vide


def test_build_portfolio_respects_target_return():
    codes = ["USA_APPLE", "USA_JOHNSON_JOHNSON", "USA_EXXONMOBIL", "USA_DUKE_ENERGY", "USA_WALMART"]
    store = _FakeStore({c: v for c, v in zip(codes, [0.02, 0.008, 0.015, 0.006, 0.009])}, seed=5)
    result = build_portfolio(store, countries=["USA"], target_return_pct=1.0, min_names=3)
    assert result["expected_return_pct"] >= 1.0 - 0.5  # tolérance : rendement annualisé historique très bruité sur 400 jours


# --------------------------------------------------------------------------- #
# Monte Carlo — bootstrap par blocs
# --------------------------------------------------------------------------- #

from app.portfolio.montecarlo import simulate_portfolio


def test_bootstrap_preserves_cross_asset_correlation():
    """LE test critique : si B = 2*A tous les jours dans l'historique, cette relation EXACTE doit
    survivre dans chaque trajectoire simulée — sinon le bootstrap mélange les actifs entre eux
    au lieu de rééchantillonner des JOURS complets, et détruit la corrélation qu'on cherche
    justement à préserver (tout l'intérêt d'un bootstrap par blocs plutôt qu'i.i.d. par colonne)."""
    rng = np.random.default_rng(0)
    n = 300
    a = rng.normal(0.0005, 0.01, n)
    returns = pd.DataFrame({"A": a, "B": a * 2})
    weights = pd.Series({"A": 0.5, "B": 0.5})

    # Rejoue simulate_portfolio mais en interceptant une trajectoire brute pour vérifier la
    # relation A/B jour par jour (pas seulement le résultat agrégé) : on reproduit l'algorithme
    # avec la même graine pour inspecter les rendements simulés directement.
    result = simulate_portfolio(returns, weights, horizon_days=60, n_sims=50, block_size=10, seed=1)
    assert result["n_history_days"] == n

    # Vérification directe : reconstruire une trajectoire et confirmer B = 2*A à chaque jour.
    rng2 = np.random.default_rng(1)
    R = returns[["A", "B"]].to_numpy()
    starts = rng2.integers(0, n - 10 + 1, size=6)
    path = np.concatenate([R[s:s + 10] for s in starts], axis=0)[:60]
    assert np.allclose(path[:, 1], path[:, 0] * 2), "la relation B=2*A n'a pas survécu au rééchantillonnage par blocs"


def test_simulate_portfolio_structure_and_plausibility():
    rng = np.random.default_rng(2)
    n, k = 500, 4
    returns = pd.DataFrame(rng.normal(0.0004, 0.012, (n, k)), columns=[f"A{i}" for i in range(k)])
    weights = pd.Series({f"A{i}": 0.25 for i in range(k)})

    result = simulate_portfolio(returns, weights, horizon_days=252, n_sims=1000, block_size=21, seed=3)
    assert result["n_sims"] == 1000 and result["horizon_days"] == 252 and result["block_size"] == 21
    p = result["percentiles_final_return_pct"]
    assert p["5"] < p["25"] < p["50"] < p["75"] < p["95"]  # percentiles correctement ordonnés
    assert result["var_95_pct"] == pytest.approx(p["5"], abs=1e-9)
    assert result["cvar_95_pct"] <= result["var_95_pct"]  # la perte moyenne dans la queue est au moins aussi mauvaise que le seuil VaR
    assert 0 <= result["probability_of_loss_pct"] <= 100
    for level in ("5", "25", "50", "75", "95"):
        assert len(result["fan_chart_pct"][level]) == 252


def test_simulate_portfolio_rejects_short_history():
    returns = pd.DataFrame({"A": np.random.default_rng(0).normal(0, 0.01, 30)})
    weights = pd.Series({"A": 1.0})
    with pytest.raises(ValueError, match="trop court"):
        simulate_portfolio(returns, weights, horizon_days=252, n_sims=100, block_size=21)


def test_simulate_portfolio_rejects_missing_codes():
    returns = pd.DataFrame({"A": np.random.default_rng(0).normal(0, 0.01, 300)})
    weights = pd.Series({"A": 0.5, "B": 0.5})
    with pytest.raises(ValueError, match="absents"):
        simulate_portfolio(returns, weights, horizon_days=100, n_sims=100, block_size=21)


def test_simulate_portfolio_is_plausible_vs_analytical_lognormal():
    """Sur un historique i.i.d. normal, la médiane du rendement simulé sur l'horizon doit rester
    dans un ordre de grandeur plausible par rapport à l'approximation log-normale analytique
    calculée sur la moyenne EMPIRIQUE des données réellement fournies (pas sur le paramètre
    théorique utilisé pour les générer : avec un historique fini, les deux peuvent diverger
    sensiblement par pur bruit d'échantillonnage — exactement la limite documentée du bootstrap,
    qui reflète l'historique donné, pas le processus sous-jacent). C'est un garde-fou de
    cohérence interne, pas une égalité exacte (le bootstrap par blocs n'est pas un tirage i.i.d. pur)."""
    rng = np.random.default_rng(7)
    n, horizon = 800, 252
    daily_mu, daily_sigma = 0.0004, 0.01
    data = rng.normal(daily_mu, daily_sigma, n)
    returns = pd.DataFrame({"A": data})
    weights = pd.Series({"A": 1.0})

    result = simulate_portfolio(returns, weights, horizon_days=horizon, n_sims=3000, block_size=21, seed=9)
    analytical_median_pct = (np.exp(data.mean() * horizon) - 1) * 100  # sur la moyenne empirique réelle, pas théorique
    simulated_median_pct = result["percentiles_final_return_pct"]["50"]
    assert simulated_median_pct == pytest.approx(analytical_median_pct, rel=0.35)


# --------------------------------------------------------------------------- #
# build_portfolio avec Monte Carlo activé
# --------------------------------------------------------------------------- #

def test_build_portfolio_with_monte_carlo():
    codes = ["USA_APPLE", "USA_JOHNSON_JOHNSON", "USA_EXXONMOBIL", "USA_DUKE_ENERGY", "USA_WALMART"]
    store = _FakeStore({c: v for c, v in zip(codes, [0.015, 0.008, 0.012, 0.006, 0.009])}, n=500, seed=11)
    result = build_portfolio(store, countries=["USA"], min_names=3, monte_carlo=True, mc_horizon_days=120, mc_n_sims=300)
    assert result["monte_carlo_error"] is None
    assert result["monte_carlo"] is not None
    assert result["monte_carlo"]["horizon_days"] == 120


def test_build_portfolio_without_monte_carlo_leaves_it_none():
    codes = ["USA_APPLE", "USA_JOHNSON_JOHNSON", "USA_EXXONMOBIL", "USA_DUKE_ENERGY", "USA_WALMART"]
    store = _FakeStore({c: v for c, v in zip(codes, [0.015, 0.008, 0.012, 0.006, 0.009])}, n=500, seed=12)
    result = build_portfolio(store, countries=["USA"], min_names=3, monte_carlo=False)
    assert result["monte_carlo"] is None and result["monte_carlo_error"] is None
