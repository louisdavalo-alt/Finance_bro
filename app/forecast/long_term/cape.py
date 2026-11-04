"""CAPE de Shiller (Cyclically Adjusted P/E ; Shiller, 1988/2000).

⚠️ Simplification majeure : le vrai CAPE lisse les bénéfices sur 10 ans ajustés à l'inflation et
s'appuie sur une régression empirique établie sur des décennies de données du S&P 500 (le jeu de
données Case-Shiller, disponible ni via `yfinance` ni ailleurs dans ce projet). Ce module utilise
le P/E TRAILING courant (non lissé, non ajusté à l'inflation, `Ticker.get_info()["trailingPE"]`)
comme proxy, combiné à l'heuristique simplifiée souvent citée en vulgarisation du CAPE : le
rendement réel attendu à long terme est de l'ordre du earnings yield (1/P/E) — PAS une régression
historique propre à ce titre ni au marché."""
from __future__ import annotations

import asyncio

from ..model_base import PredictionResult
from ._common import scale_to_horizon

# Volatilité annuelle actions typique (ordre de grandeur courant de la littérature, PAS estimée
# sur ce titre) : ce module n'a pas de série de rendements à régresser, à la différence des
# autres modèles de ce projet qui estiment leur propre écart-type empiriquement.
LITERATURE_ANNUAL_SIGMA_PCT = 16.0


def fit_cape_forecast(trailing_pe: float | None, horizon_days: int = 21) -> dict:
    if trailing_pe is None or trailing_pe <= 0:
        raise ValueError("P/E trailing indisponible ou non positif pour ce titre (yfinance)")

    earnings_yield_pct = 100.0 / trailing_pe
    mu_pct, sigma_pct = scale_to_horizon(earnings_yield_pct, LITERATURE_ANNUAL_SIGMA_PCT, horizon_days)
    return {
        "expected_return_pct": mu_pct,
        "sigma_pct": sigma_pct,
        "trailing_pe": trailing_pe,
        "earnings_yield_pct": earnings_yield_pct,
    }


async def fetch_cape_forecast(symbol: str, horizon_days: int) -> PredictionResult:
    """Fonction async car appel réseau (`get_info()`) — appelée comme une tâche parallèle dans
    `pipeline.run_forecast`."""

    def _sync() -> dict:
        import yfinance as yf

        return yf.Ticker(symbol).get_info()

    info = await asyncio.to_thread(_sync)
    trailing_pe = (info or {}).get("trailingPE")
    result = fit_cape_forecast(trailing_pe, horizon_days=horizon_days)
    return PredictionResult(mu_pct=result["expected_return_pct"], sigma_pct=result["sigma_pct"], diagnostics=result)
