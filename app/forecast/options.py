"""Analyse du positionnement via les options — Put/Call Ratio, Max Pain, skew de volatilité
implicite. Appel direct à `yfinance` (`Ticker.options` + `Ticker.option_chain(date)`), comme
`ohlc.py`/`quote.py` : rien n'est stocké ni mis en cache.

⚠️ Pas de Gamma Exposure (GEX) ici : `yfinance` ne fournit pas les Grecques par contrat (pas de
colonne gamma dans `option_chain`), seulement la volatilité implicite. Un GEX exact nécessiterait
soit une source avec les Grecques, soit un recalcul par Black-Scholes à partir de l'IV — une
approximation supplémentaire sur une donnée déjà approximative (l'IV de `yfinance` elle-même
vient de son propre calcul, pas du carnet d'ordres du marché d'options). Volontairement pas
implémenté pour l'instant plutôt que d'empiler les approximations sans les signaler clairement.

⚠️ Non testé en conditions réelles (Yahoo Finance bloqué par le pare-feu du bac à sable, comme
pour le reste du connecteur `yfinance`) : les tests portent sur un carnet d'options synthétique
avec des valeurs calculées à la main (`tests/test_forecast.py`).
"""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from ..connectors.yfin import YFinanceNotInstalled


class OptionChainUnavailable(Exception):
    """Levée quand `yfinance` ne renvoie aucune échéance ou aucun contrat exploitable."""


def _fetch_option_chain_sync(symbol: str, expiration: str | None):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise YFinanceNotInstalled("le paquet 'yfinance' n'est pas installé : `pip install yfinance`") from exc

    ticker = yf.Ticker(symbol)
    expirations = list(ticker.options)
    if not expirations:
        raise OptionChainUnavailable(f"aucune échéance d'options disponible pour {symbol!r} (pas d'options cotées ?)")
    exp = expiration if expiration else expirations[0]
    if exp not in expirations:
        raise OptionChainUnavailable(f"échéance {exp!r} introuvable pour {symbol!r} — disponibles : {expirations}")

    chain = ticker.option_chain(exp)
    try:
        spot = float(ticker.fast_info.last_price)
    except Exception:
        spot = None
    return chain.calls, chain.puts, exp, expirations, spot


def put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> dict:
    """PCR en volume et en open interest. `None` quand le dénominateur est nul (pas de calls
    échangés) plutôt qu'une division par zéro silencieuse."""
    call_vol, put_vol = calls["volume"].fillna(0).sum(), puts["volume"].fillna(0).sum()
    call_oi, put_oi = calls["openInterest"].fillna(0).sum(), puts["openInterest"].fillna(0).sum()
    return {
        "pcr_volume": float(put_vol / call_vol) if call_vol else None,
        "pcr_open_interest": float(put_oi / call_oi) if call_oi else None,
        "call_volume": float(call_vol), "put_volume": float(put_vol),
        "call_open_interest": float(call_oi), "put_open_interest": float(put_oi),
    }


def max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> dict:
    """Strike qui minimise la valeur totale que les VENDEURS d'options (marché/market makers)
    devraient payer aux DÉTENTEURS si le sous-jacent se réglait exactement à ce prix à
    l'échéance — la théorie du « Max Pain » veut que le prix ait tendance à graviter vers ce
    niveau à l'approche de l'expiration (contesté empiriquement, à prendre comme un indicateur
    parmi d'autres, pas une certitude)."""
    strikes = sorted(set(calls["strike"]).union(puts["strike"]))
    if not strikes:
        raise OptionChainUnavailable("aucun strike exploitable dans ce carnet d'options")

    call_oi = calls.set_index("strike")["openInterest"].fillna(0)
    put_oi = puts.set_index("strike")["openInterest"].fillna(0)
    call_strikes, call_vals = call_oi.index.to_numpy(dtype=float), call_oi.to_numpy(dtype=float)
    put_strikes, put_vals = put_oi.index.to_numpy(dtype=float), put_oi.to_numpy(dtype=float)

    # Matrice (règlement × strike) en une passe NumPy, au lieu d'une boucle Python par strike.
    settles = np.asarray(strikes, dtype=float)[:, None]
    call_payout = (np.clip(settles - call_strikes[None, :], 0, None) * call_vals).sum(axis=1)
    put_payout = (np.clip(put_strikes[None, :] - settles, 0, None) * put_vals).sum(axis=1)
    payouts = [float(v) for v in call_payout + put_payout]

    best_idx = int(np.argmin(payouts))
    return {
        "max_pain_strike": float(strikes[best_idx]),
        "strikes": [float(s) for s in strikes],
        "total_payout_by_strike": payouts,
    }


def iv_skew(calls: pd.DataFrame, puts: pd.DataFrame, spot: float | None) -> dict | None:
    """Compare la volatilité implicite d'un put hors-la-monnaie (~10% sous le spot) à celle d'un
    call hors-la-monnaie symétrique (~10% au-dessus) : un skew positif (put > call) signale que
    le marché paie plus cher pour se couvrir contre une baisse que pour profiter d'une hausse —
    la configuration la plus fréquente sur actions. `None` si le spot est inconnu ou si aucun
    contrat n'est assez proche des cibles à ±10%."""
    if spot is None or spot <= 0:
        return None

    def _closest_iv(df: pd.DataFrame, target_strike: float) -> float | None:
        d = df.dropna(subset=["impliedVolatility", "strike"])
        if d.empty:
            return None
        idx = (d["strike"] - target_strike).abs().idxmin()
        return float(d.loc[idx, "impliedVolatility"]) * 100

    put_iv = _closest_iv(puts, spot * 0.90)
    call_iv = _closest_iv(calls, spot * 1.10)
    atm_call_iv = _closest_iv(calls, spot)
    atm_put_iv = _closest_iv(puts, spot)
    if put_iv is None or call_iv is None:
        return None

    return {
        "otm_put_iv_pct": put_iv, "otm_call_iv_pct": call_iv,
        "skew_pct_points": put_iv - call_iv,
        "atm_call_iv_pct": atm_call_iv, "atm_put_iv_pct": atm_put_iv,
    }


async def analyze_options(symbol: str, expiration: str | None = None) -> dict:
    calls, puts, exp, expirations, spot = await asyncio.to_thread(_fetch_option_chain_sync, symbol, expiration)
    return {
        "expiration_used": exp,
        "available_expirations": expirations[:12],  # les 12 prochaines, pas la totalité si la liste est très longue
        "spot_price": spot,
        "pcr": put_call_ratio(calls, puts),
        "max_pain": max_pain(calls, puts),
        "iv_skew": iv_skew(calls, puts, spot),
    }
