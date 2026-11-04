"""Orchestration du constructeur de portefeuille : filtre l'univers d'actions par pays et
secteur, calcule rendement/covariance à partir de l'historique déjà collecté (`stats.py`), puis
optimise les poids (`optimizer.py`) selon le niveau de risque et, si demandé, un rendement cible.

⚠️ Outil d'aide à la réflexion sur des compromis rendement/risque, PAS un conseil en
investissement : les rendements attendus sont des moyennes historiques (voir `optimizer.py`), le
nombre de titres disponibles dépend de ce que ton pipeline a réellement collecté, et rien ici ne
tient compte de frais, fiscalité, devise de référence ou liquidité.
"""
from __future__ import annotations

from ..registry import INDICATORS, by_code
from .optimizer import optimize_weights, portfolio_summary
from .sectors import NON_CLASSE, sector_for

STOCK_PREFIXES = ("USA_", "FRA_", "DEU_", "JPN_", "CHN_", "KOR_", "GBR_", "CAN_", "IND_", "ITA_", "POL_", "MEX_")
LEGACY_FRA = {"FR_TOTALENERGIES", "FR_AIRBUS", "FR_LVMH"}  # déjà country="FRA" dans le registre


def _stock_specs():
    for spec in INDICATORS:
        if spec.connector == "yfinance" and (spec.code.startswith(STOCK_PREFIXES) or spec.code in LEGACY_FRA):
            yield spec


def available_countries() -> list[str]:
    return sorted({s.country for s in _stock_specs()})


def available_sectors() -> list[str]:
    from .sectors import all_sectors
    return all_sectors()


def filter_universe(countries: list[str] | None, sectors: list[str] | None) -> list[str]:
    """Codes d'actions du registre correspondant aux filtres (listes vides = pas de filtre sur
    cette dimension). Ne garantit PAS que ces codes ont des données en base : `stats.py` filtre
    ensuite sur l'historique réellement disponible."""
    out = []
    for spec in _stock_specs():
        if countries and spec.country not in countries:
            continue
        if sectors and sector_for(spec.code) not in sectors:
            continue
        out.append(spec.code)
    return out


def build_portfolio(
    store, countries: list[str] | None = None, sectors: list[str] | None = None,
    risk_level: str = "modere", target_return_pct: float | None = None,
    max_weight: float = 0.25, min_names: int = 5,
    monte_carlo: bool = False, mc_horizon_days: int = 252, mc_n_sims: int = 2000,
) -> dict:
    from .stats import compute_return_stats

    candidates = filter_universe(countries, sectors)
    if len(candidates) < min_names:
        raise ValueError(
            f"seulement {len(candidates)} action(s) correspondent à ces filtres dans le registre "
            f"({min_names} minimum) — élargis les pays ou secteurs sélectionnés."
        )

    mean_returns, cov_matrix, codes_used, aligned_returns = compute_return_stats(store, candidates)
    if len(codes_used) < min_names:
        raise ValueError(
            f"seulement {len(codes_used)} action(s) parmi les {len(candidates)} correspondant aux filtres "
            f"ont assez d'historique en base ({min_names} minimum) — as-tu lancé `run_pipeline.sh` récemment ?"
        )

    target = (target_return_pct / 100) if target_return_pct is not None else None
    weights = optimize_weights(mean_returns, cov_matrix, risk_level=risk_level, target_return=target, max_weight=max_weight)
    summary = portfolio_summary(weights, mean_returns, cov_matrix)

    monte_carlo_result, monte_carlo_error = None, None
    if monte_carlo:
        from .montecarlo import simulate_portfolio
        try:
            monte_carlo_result = simulate_portfolio(aligned_returns, weights, horizon_days=mc_horizon_days, n_sims=mc_n_sims)
        except Exception as exc:
            monte_carlo_error = str(exc)

    holdings = []
    for code in weights.index:
        w = float(weights[code])
        if w < 1e-4:  # ne pas lister des poids résiduels non significatifs (bruit numérique)
            continue
        spec = by_code(code)
        holdings.append({
            "code": code, "country": spec.country, "sector": sector_for(code),
            "weight_pct": w * 100,
            "expected_return_pct": float(mean_returns[code]) * 100,
            "volatility_pct": float(cov_matrix.loc[code, code] ** 0.5) * 100,
        })
    holdings.sort(key=lambda h: -h["weight_pct"])

    return {
        "holdings": holdings,
        "n_candidates": len(candidates),
        "n_used": len(codes_used),
        "excluded_for_insufficient_history": sorted(set(candidates) - set(codes_used)),
        "risk_level": risk_level,
        "target_return_pct": target_return_pct,
        "max_weight_pct": max_weight * 100,
        "monte_carlo": monte_carlo_result,
        "monte_carlo_error": monte_carlo_error,
        **summary,
    }
